import json
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'projects/week-2-task-5'))
import main
import web


class Provider(BaseHTTPRequestHandler):
    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if payload.get('response_format'):
            data = json.loads(payload['messages'][-1]['content'])
            facts = data['old_facts']
            user = data['current_user']
            for trigger, key, value in [('Меня зовут Анна', 'name', 'Анна'), ('Город: Минск', 'city', 'Минск'), ('Язык проекта: Python', 'language', 'Python'), ('Бюджет: 1000', 'budget', '1000'), ('город теперь Брест', 'city', 'Брест'), ('Метка:', 'label', '<img src=x onerror=alert(1)>')]:
                if trigger in user:
                    facts[key] = value
            content = json.dumps(facts, ensure_ascii=False)
        else:
            content = 'Ответ mock: ' + payload['messages'][-1]['content']
        response = json.dumps({'choices': [{'message': {'content': content}, 'finish_reason': 'stop'}], 'usage': {'prompt_tokens': 100, 'completion_tokens': 20, 'total_tokens': 120}}, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, *args):
        pass


provider = ThreadingHTTPServer(('127.0.0.1', 0), Provider)
threading.Thread(target=provider.serve_forever, daemon=True).start()
main.load_api_key = lambda: 'local-validation-placeholder'
main.ChatAgent.api_url = f'http://127.0.0.1:{provider.server_port}/chat/completions'
with tempfile.TemporaryDirectory(prefix='day10-validation-') as directory:
    server = web.ChatServer(0, database_path=Path(directory) / 'context.sqlite3')
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(json.dumps({'port': server.server_port}), flush=True)
    for line in sys.stdin:
        if line.strip() == 'stop':
            break
    server.shutdown()
    server.server_close()
provider.shutdown()
provider.server_close()
