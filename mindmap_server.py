"""An optional server for the Mind Map Editor on your local network.

It serves mindmap-editor.html and keeps maps as .zip files in one folder, so every device on the
network opens and saves the same maps. Standard library only; paste it into a Jupyter notebook and run:

    srv = start_mind_map_server('~/mindmaps')     # then browse to http://<this computer>:8765/
    srv.shutdown()                                # to stop it

There is no password: anyone who can reach the port can read and change the maps.

The API, which the editor uses:
    GET /api/maps              -> [{"name", "modified", "size", "etag"}], newest first
    GET /api/maps/<name>.zip   -> the zip, with an ETag header
    PUT /api/maps/<name>.zip   -> stores the zip. With If-Match: <etag>, refuses (409) if the map has
                                  changed since; with If-None-Match: *, refuses (409) if it already exists
<name> is an editor key: lower-case letters, digits and underscores.
"""
import hashlib
import http.server
import json
import os
import re
import threading
import zipfile
from io import BytesIO
from pathlib import Path

EDITOR = Path(__file__).resolve().parent / 'mindmap-editor.html' if '__file__' in globals() else None
MAX_BYTES = 200 * 1024 * 1024
_NAME = re.compile(r'^/api/maps/([a-z0-9_]+)\.zip$')


def _etag(data):
    return '"' + hashlib.sha256(data).hexdigest()[:16] + '"'


class _Handler(http.server.BaseHTTPRequestHandler):
    folder = None    # set by start_mind_map_server
    editor = None

    def log_message(self, *args):
        pass

    def _send(self, status, body=b'', ctype='application/json', headers=()):
        self.send_response(status)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status, text):
        self._send(status, json.dumps({'error': text}).encode())

    def do_GET(self):
        path = self.path.split('?')[0]
        if path in ('/', '/mindmap-editor.html'):
            return self._send(200, self.editor.read_bytes(), 'text/html; charset=utf-8')
        if path == '/api/maps':
            maps = []
            for f in self.folder.glob('*.zip'):
                if re.fullmatch(r'[a-z0-9_]+', f.stem):
                    data = f.read_bytes()
                    maps.append({'name': f.stem, 'modified': f.stat().st_mtime, 'size': len(data), 'etag': _etag(data)})
            maps.sort(key=lambda m: -m['modified'])
            return self._send(200, json.dumps(maps).encode())
        m = _NAME.match(path)
        if m and (self.folder / (m[1] + '.zip')).is_file():
            data = (self.folder / (m[1] + '.zip')).read_bytes()
            return self._send(200, data, 'application/zip', [('ETag', _etag(data))])
        self._error(404, 'not found')

    def do_PUT(self):
        m = _NAME.match(self.path.split('?')[0])
        if not m:
            return self._error(404, 'maps are saved as /api/maps/<key>.zip')
        size = int(self.headers.get('Content-Length') or 0)
        if size > MAX_BYTES:
            return self._error(413, 'too large')
        data = self.rfile.read(size)
        if not zipfile.is_zipfile(BytesIO(data)):
            return self._error(400, 'not a zip file')
        target = self.folder / (m[1] + '.zip')
        with _lock:
            wanted = self.headers.get('If-Match')
            if wanted and target.is_file() and _etag(target.read_bytes()) != wanted:
                return self._error(409, 'the map has changed since it was opened')
            if self.headers.get('If-None-Match') == '*' and target.is_file():
                return self._error(409, 'a map with that name is already here')
            tmp = target.with_suffix('.zip.tmp')
            tmp.write_bytes(data)
            os.replace(tmp, target)
        self._send(200, b'{}', headers=[('ETag', _etag(data))])


_lock = threading.Lock()


def start_mind_map_server(folder, port=8765, host='0.0.0.0', editor=None):
    """Start the server in a background thread and return it (call .shutdown() to stop).

    folder: where the maps are kept (created if missing). port=0 picks a free port (see .server_port).
    host='0.0.0.0' accepts connections from the whole network; use '127.0.0.1' for this computer only.
    editor: path of mindmap-editor.html; by default the copy beside this file.
    """
    folder = Path(folder).expanduser()
    folder.mkdir(parents=True, exist_ok=True)
    editor = Path(editor or EDITOR or 'mindmap-editor.html').expanduser()
    if not editor.is_file():
        raise FileNotFoundError(f'{editor} not found; pass editor= the path of mindmap-editor.html')
    handler = type('Handler', (_Handler,), {'folder': folder, 'editor': editor})
    srv = http.server.ThreadingHTTPServer((host, port), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
