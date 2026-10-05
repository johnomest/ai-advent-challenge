import json
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'projects/week-2-task-2'))
import main
import web

class Provider(BaseHTTPRequestHandler):
    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        message = payload['messages'][-1]['content']
        if message.startswith('DELAY'):
            time.sleep(12)
        data = json.dumps({'choices': [{'message': {'content': 'Локальный ответ: ' + message}}], 'usage': {'total_tokens': 12}}, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def log_message(self, *args):
        pass

provider = ThreadingHTTPServer(('127.0.0.1', 0), Provider)
threading.Thread(target=provider.serve_forever, daemon=True).start()
main.load_api_key = lambda: 'local-validation-placeholder'
main.ChatAgent.api_url = f'http://127.0.0.1:{provider.server_port}/chat/completions'
validation_dir = Path(tempfile.mkdtemp(prefix='goost-validation-'))
database = validation_dir / 'context.sqlite3'
server = web.ChatServer(0, database_path=database)
port = server.server_port
threading.Thread(target=server.serve_forever, daemon=True).start()
print(json.dumps({'port': port, 'provider_port': provider.server_port, 'database': str(database)}), flush=True)
for line in sys.stdin:
    if line.strip() == 'restart':
        server.shutdown()
        server.server_close()
        server = web.ChatServer(port, database_path=database)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        print('RESTARTED', flush=True)
    elif line.strip() == 'stop':
        break
server.shutdown()
server.server_close()
provider.shutdown()
provider.server_close()
