import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

spec = importlib.util.spec_from_file_location('service30_tests', Path(__file__).with_name('main.py'))
service = importlib.util.module_from_spec(spec)
spec.loader.exec_module(service)
bot = service.opt.rag.load('telegram30_tests', Path(__file__).with_name('telegram_bot.py'))


def reply(question, history):
    history.extend([{'role': 'user', 'content': question}, {'role': 'assistant', 'content': 'OK'}])
    return {'answer': 'OK', 'seconds': 0, 'tokens': 1, 'sources': []}


class EngineTests(unittest.TestCase):
    def make_engine(self, backend=reply, capacity=8):
        engine = service.Engine(backend, capacity)
        self.addCleanup(engine.close)
        return engine

    def test_gpu_calls_serial_and_histories_separate(self):
        started, release = threading.Event(), threading.Event()
        calls = []
        def backend(question, history):
            calls.append((question, list(history), threading.get_ident()))
            if question == 'first':
                started.set()
                self.assertTrue(release.wait(2))
            return reply(question, history)
        engine = self.make_engine(backend)
        first = engine.submit('api:a', 'first')
        self.assertTrue(started.wait(1))
        second = engine.submit('api:b', 'second')
        third = engine.submit('api:c', 'third')
        self.assertFalse(second.done())
        release.set()
        for future in (first, second, third):
            self.assertEqual(future.result(2)['answer'], 'OK')
        engine.jobs.join()
        engine.submit('api:a', 'followup').result(2)
        self.assertEqual([item[0] for item in calls], ['first', 'second', 'third', 'followup'])
        self.assertEqual(len({item[2] for item in calls}), 1)
        self.assertEqual(calls[1][1], [])
        self.assertEqual(calls[-1][1][0]['content'], 'first')

    def test_busy_session_and_bounded_queue(self):
        started, release = threading.Event(), threading.Event()
        def backend(question, history):
            started.set()
            release.wait(2)
            return reply(question, history)
        engine = self.make_engine(backend, capacity=1)
        try:
            first = engine.submit('api:a', 'first')
            self.assertTrue(started.wait(1))
            with self.assertRaises(service.ServiceError) as error:
                engine.submit('api:a', 'other')
            self.assertEqual(error.exception.status, 409)
            with self.assertRaises(service.ServiceError):
                engine.reset('api:a')
            second = engine.submit('api:b', 'second')
            with self.assertRaises(service.ServiceError) as error:
                engine.submit('api:c', 'full')
            self.assertEqual(error.exception.status, 503)
        finally:
            release.set()
        first.result(2)
        second.result(2)

    def test_failed_and_cancelled_requests_do_not_change_history(self):
        started, release = threading.Event(), threading.Event()
        def backend(question, history):
            reply(question, history)
            if question == 'fail':
                raise RuntimeError('offline')
            if question == 'cancel':
                started.set()
                release.wait(2)
            return reply('result', history)
        engine = self.make_engine(backend)
        engine.submit('api:a', 'first').result(2)
        engine.jobs.join()
        before = list(engine.sessions['api:a']['history'])
        failed = engine.submit('api:a', 'fail')
        with self.assertRaises(service.ServiceError):
            failed.result(2)
        engine.jobs.join()
        self.assertEqual(engine.sessions['api:a']['history'], before)
        cancelled = engine.submit('api:a', 'cancel')
        self.assertTrue(started.wait(1))
        with engine.lock:
            cancelled.cancel()
        release.set()
        engine.jobs.join()
        self.assertEqual(engine.sessions['api:a']['history'], before)

    def test_rate_limit_survives_reset(self):
        engine = self.make_engine()
        for _ in range(service.RATE):
            engine.submit('api:a', 'question').result(2)
            engine.jobs.join()
            engine.reset('api:a')
        with self.assertRaises(service.ServiceError) as error:
            engine.submit('api:a', 'seventh')
        self.assertEqual(error.exception.status, 429)
        self.assertEqual(engine.sessions['api:a']['history'], [])

    def test_input_limits_and_expired_queue(self):
        engine = self.make_engine()
        for question in ('', ' ' * 3, 'x' * (service.MAX_QUESTION + 1), '\ud800', 42):
            with self.assertRaises(service.ServiceError):
                engine.submit('api:a', question)
        with self.assertRaises(service.ServiceError):
            engine.submit('../a', 'valid question')
        with patch.object(service, 'DEADLINE', -1):
            future = engine.submit('api:a', 'expired')
            with self.assertRaises(service.ServiceError) as error:
                future.result(2)
            self.assertEqual(error.exception.status, 504)
        self.assertEqual(engine.sessions['api:a']['history'], [])

    def test_shutdown_cancels_active_and_queued_requests(self):
        started, release = threading.Event(), threading.Event()
        def backend(question, history):
            started.set()
            release.wait(2)
            return reply(question, history)
        engine = self.make_engine(backend)
        first = engine.submit('api:a', 'first')
        self.assertTrue(started.wait(1))
        second = engine.submit('api:b', 'second')
        engine.close()
        release.set()
        engine.worker.join(2)
        self.assertTrue(first.cancelled())
        self.assertTrue(second.cancelled())
        self.assertEqual(engine.sessions['api:a']['history'], [])


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.engine = service.Engine(reply)
        self.key = 'k' * 32
        self.server = service.Server(('127.0.0.1', 0), service.handler(self.engine, self.key))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        self.opener = build_opener(ProxyHandler({}))

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        self.engine.close()

    def request(self, path, payload=None, auth=True, raw=None):
        headers = {'Authorization': 'Bearer ' + self.key} if auth else {}
        headers['Content-Type'] = 'application/json'
        data = raw if raw is not None else json.dumps(payload).encode() if payload is not None else None
        try:
            with self.opener.open(Request(self.base + path, data=data, headers=headers), timeout=3) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.load(error)

    def test_auth_and_actual_http_chat_reset(self):
        self.assertEqual(self.request('/health', auth=False)[0], 401)
        self.assertEqual(self.request('/chat', {'question': 'Q'}, auth=False)[0], 401)
        status, result = self.request('/chat', {'question': 'Q'})
        self.assertEqual(status, 200)
        self.assertTrue(result['session'].startswith('api:'))
        self.engine.jobs.join()
        self.assertEqual(self.request('/reset', {'session': result['session']})[0], 200)
        self.assertEqual(self.request('/health')[1]['completed'], 1)

    def test_malformed_body_and_untrusted_parameters_rejected(self):
        self.assertEqual(self.request('/chat', raw=b'{')[0], 400)
        self.assertEqual(self.request('/chat', raw=b'x' * (service.MAX_BODY + 1))[0], 413)
        for payload in ([], {'question': 'Q', 'max_tokens': 99999}, {'question': 'Q', 'session': 'bad'},
                        {'question': 'x' * (service.MAX_QUESTION + 1)}):
            self.assertEqual(self.request('/chat', payload)[0], 400)
        self.assertEqual(self.request('/reset', {})[0], 400)


class AccessTests(unittest.TestCase):
    def test_pairing_is_one_time_expiring_and_persistent(self):
        with tempfile.TemporaryDirectory() as folder:
            access = bot.Access(123, '789', Path(folder))
            self.assertFalse(access.permits(456))
            self.assertFalse(access.pair(456, 'wrong-code'))
            code = access.code
            self.assertTrue(access.pair(456, code))
            self.assertTrue(access.permits(456))
            self.assertTrue(access.permits(789))
            self.assertFalse(access.pair(999, code))
            self.assertFalse(access.permits(999))
            reopened = bot.Access(123, '', Path(folder))
            self.assertTrue(reopened.permits(456))
            self.assertFalse(reopened.permits(789))
            with self.assertRaises(ValueError):
                bot.Access(321, '', Path(folder))
        with tempfile.TemporaryDirectory() as folder:
            access = bot.Access(123, '', Path(folder))
            access.expires = -1
            self.assertFalse(access.pair(456, access.code))

    def test_invalid_allowlist_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            for allowed in ('everyone', '-1', '0', '1;2'):
                with self.assertRaises(ValueError):
                    bot.Access(123, allowed, Path(folder))

    def test_group_and_unauthorized_question_never_reach_model(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(bot, 'call', side_effect=[{'ok': True, 'result': {'id': 123, 'username': 'test_bot'}},
                                                       {'ok': True, 'result': {'url': ''}}]):
                instance = bot.Bot('123:' + 'a' * 30, 'http://127.0.0.1:1', 'k' * 32, '', Path(folder))
            with patch.object(instance, 'local') as local, patch.object(instance, 'send') as send:
                instance.dispatch({'message': {'from': {'id': 456}, 'chat': {'id': 456, 'type': 'group'}, 'text': 'Q'}})
                send.assert_not_called()
                instance.dispatch({'message': {'from': {'id': 456}, 'chat': {'id': 456, 'type': 'private'}, 'text': 'Q'}})
                local.assert_not_called()
                self.assertIn('Доступ закрыт', send.call_args.args[1])
            instance.stop()

    def test_telegram_split_preserves_unicode_and_content(self):
        text = '🙂' * 4000 + 'текст'
        chunks = list(bot.split_text(text))
        self.assertEqual(''.join(chunks), text)
        self.assertTrue(all(len(part.encode('utf-16-le')) // 2 <= 3500 for part in chunks))

    def test_paired_user_calls_http_api_in_own_session(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(bot, 'call', side_effect=[{'ok': True, 'result': {'id': 123, 'username': 'test_bot'}},
                                                       {'ok': True, 'result': {'url': ''}}]):
                instance = bot.Bot('123:' + 'a' * 30, 'http://127.0.0.1:1', 'k' * 32, '', Path(folder))
            self.assertTrue(instance.access.pair(456, instance.access.code))
            with patch.object(instance, 'local', return_value={'answer': 'Ответ', 'sources': [], 'seconds': 1}) as local, \
                    patch.object(instance, 'send') as send:
                instance.dispatch({'message': {'from': {'id': 456}, 'chat': {'id': 456, 'type': 'private'}, 'text': 'Вопрос'}})
                instance.executor.shutdown(wait=True)
                local.assert_called_once_with('/chat', {'session': 'telegram:456', 'question': 'Вопрос'})
                self.assertIn('Ответ', send.call_args.args[1])
                self.assertEqual(instance.pending, set())
            instance.stop()

    def test_network_errors_do_not_expose_token_url(self):
        secret_url = 'https://api.telegram.org/bot123:secret/getMe'
        with patch.object(bot, 'build_opener') as opener:
            opener.return_value.open.side_effect = OSError(secret_url)
            with self.assertRaises(RuntimeError) as error:
                bot.call(secret_url, {})
        self.assertNotIn('secret', str(error.exception))

    def test_generated_api_key_preserves_existing_env(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            env = root / '.env'
            env.write_bytes(b'OTHER_KEY=sentinel\r\nLOCAL_AI_API_TOKEN=\r\n')
            with patch.object(service, 'ROOT', root), patch.object(service, 'DATA', root / 'data'):
                key = service.api_key({})
            self.assertGreaterEqual(len(key), 32)
            self.assertTrue(env.read_bytes().startswith(b'OTHER_KEY=sentinel\r\n'))
            self.assertEqual(env.read_text().count('LOCAL_AI_API_TOKEN='), 1)


if __name__ == '__main__':
    unittest.main()
