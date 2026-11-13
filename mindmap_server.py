"""An optional server for the Mind Map Editor and the Diagram Editor on your local network.

It serves mindmap-editor.html and diagram-editor.html, and keeps maps as .zip files in one folder and diagrams
as .yaml files in another, so every device on the network opens and saves the same ones. Standard library only;
paste it into a Jupyter notebook and run:

    srv = start_mind_map_server('~/mindmaps')     # then browse to http://<this computer>:8765/
    srv.shutdown()                                # to stop it

The Mind Map Editor is at the top, http://<this computer>:8765/, and the Diagram Editor at
http://<this computer>:8765/diagram-editor.html; http://<this computer>:8765/home links to both and to their
documentation (each editor's logo goes there). Diagrams are kept in a 'diagrams' folder inside the maps folder,
unless you choose another with diagrams=.

There is no password: anyone who can reach the port can read and change the maps and diagrams.

The API, which the editors use (the same for diagrams, with /api/diagrams and <name>.yaml):
    GET /api/maps              -> [{"name", "modified", "size", "etag"}], newest first
    GET /api/maps/<name>.zip   -> the zip, with an ETag header
    PUT /api/maps/<name>.zip   -> stores the zip. With If-Match: <etag>, refuses (409) if the map has
                                  changed since; with If-None-Match: *, refuses (409) if it already exists
<name> is an editor key: lower-case letters, digits and underscores.

Maps can be kept in folders: <name> may be a path of keys such as projects/toolbox/plan. A folder is there
while it holds a map; saving or moving a map into a new folder makes it, and an emptied folder goes.
    GET /api/maps/             -> {"folder", "folders": [names], "files": [as above, newest first]} at the top
    GET /api/maps/<folder>/    -> the same for one folder ("name" is the whole path)
    DELETE /api/maps/<name>.zip  -> moves the map into .trash inside the maps folder, with the time in its
                                    name. With If-Match: <etag>, refuses (409) if the map has changed since
    POST /api/maps/<name>.zip  with {"to": "<new name>"} -> moves or renames the map; 409 if one is there
    POST /api/maps/<folder>/   with {"to": "<new folder>"} -> moves or renames the folder and all in it
Nothing empties .trash; delete what you no longer want from it yourself.
"""
import hashlib
import http.server
import json
import os
import re
import threading
import time
import zipfile
from io import BytesIO
from pathlib import Path

HERE = Path(__file__).resolve().parent if '__file__' in globals() else None
EDITOR = HERE / 'mindmap-editor.html' if HERE else None
DIAGRAM_EDITOR = HERE / 'diagram-editor.html' if HERE else None
HOME = HERE / 'home.html' if HERE else None
MAX_BYTES = 200 * 1024 * 1024
_KEY = r'[a-z0-9_]+'
_PATH = rf'{_KEY}(?:/{_KEY})*'
_FILE = re.compile(rf'^/api/(maps|diagrams)/({_PATH})\.(zip|yaml)$')
_FOLDER = re.compile(rf'^/api/(maps|diagrams)/(?:({_PATH})/)?$')


def _is_zip(data):
    return zipfile.is_zipfile(BytesIO(data))


def _is_text(data):
    try:
        return bool(data.decode('utf-8').strip())
    except UnicodeDecodeError:
        return False


# What each kind of file is called, its extension, its media type, and how a stored one is checked.
_KINDS = {
    'maps': {'noun': 'map', 'ext': 'zip', 'ctype': 'application/zip', 'ok': _is_zip, 'not_ok': 'not a zip file'},
    'diagrams': {'noun': 'diagram', 'ext': 'yaml', 'ctype': 'application/yaml; charset=utf-8', 'ok': _is_text,
                 'not_ok': 'not a YAML text file'},
}


def _etag(data):
    return '"' + hashlib.sha256(data).hexdigest()[:16] + '"'


class _Handler(http.server.BaseHTTPRequestHandler):
    folders = None   # {'maps': folder, 'diagrams': folder}, set by start_mind_map_server
    pages = None     # {path: file of the page served there}

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

    def _taken(self, kind, target):
        """True if target is in a folder kept for another kind (by default diagrams are in a folder inside the maps)."""
        mine = self.folders[kind]
        return any(k != kind and mine in f.parents and (target == f or f in target.parents)
                   for k, f in self.folders.items())

    def _file(self, path):
        """(kind, file path) for /api/<kind>/<name>.<ext> with the right extension for its kind, else None."""
        m = _FILE.match(path)
        if m and _KINDS[m[1]]['ext'] == m[3]:
            target = self.folders[m[1]] / f'{m[2]}.{m[3]}'
            if not self._taken(m[1], target):
                return m[1], target
        return None

    def _folder(self, path):
        """(kind, folder path) for /api/<kind>/ or /api/<kind>/<folder>/, else None."""
        m = _FOLDER.match(path)
        if m:
            target = self.folders[m[1]] / (m[2] or '')
            if not self._taken(m[1], target):
                return m[1], target
        return None

    def _files(self, kind, folder, deep=False):
        """The files of this kind in a folder (and, if deep, in the folders inside it) whose names are editor keys."""
        root, ext = self.folders[kind], _KINDS[kind]['ext']
        for f in (folder.rglob if deep else folder.glob)('*.' + ext) if folder.is_dir() else []:
            keys = f.relative_to(root).with_suffix('').parts
            if f.is_file() and all(re.fullmatch(_KEY, k) for k in keys) and not self._taken(kind, f):
                yield f

    def _listing(self, kind, folder):
        root, found = self.folders[kind], []
        for f in self._files(kind, folder):
            data = f.read_bytes()
            found.append({'name': f.relative_to(root).with_suffix('').as_posix(), 'modified': f.stat().st_mtime,
                          'size': len(data), 'etag': _etag(data)})
        found.sort(key=lambda m: -m['modified'])
        inside = sorted(d.name for d in (folder.iterdir() if folder.is_dir() else [])
                        if d.is_dir() and re.fullmatch(_KEY, d.name) and any(self._files(kind, d, deep=True)))
        return {'folder': folder.relative_to(root).as_posix() if folder != root else '', 'folders': inside,
                'files': found}

    def _prune(self, kind, folder):
        """Remove a folder left empty, and those above it that it leaves empty."""
        root = self.folders[kind]
        while root in folder.parents:
            try:
                folder.rmdir()
            except OSError:
                break
            folder = folder.parent

    def do_GET(self):
        path = self.path.split('?')[0]
        page = self.pages.get(path)
        if page and page.is_file():
            return self._send(200, page.read_bytes(), 'text/html; charset=utf-8')
        kind = path[len('/api/'):] if path.startswith('/api/') else None
        if kind in _KINDS:
            return self._send(200, json.dumps(self._listing(kind, self.folders[kind])['files']).encode())
        hit = self._folder(path)
        if hit:
            return self._send(200, json.dumps(self._listing(*hit)).encode())
        hit = self._file(path)
        if hit and hit[1].is_file():
            data = hit[1].read_bytes()
            return self._send(200, data, _KINDS[hit[0]]['ctype'], [('ETag', _etag(data))])
        self._error(404, 'not found')

    def do_DELETE(self):
        hit = self._file(self.path.split('?')[0])
        if not hit:
            return self._error(404, 'not found')
        kind, target = hit
        k, root = _KINDS[kind], self.folders[kind]
        with _lock:
            if not target.is_file():
                return self._error(404, 'not found')
            wanted = self.headers.get('If-Match')
            if wanted and _etag(target.read_bytes()) != wanted:
                return self._error(409, f"the {k['noun']} has changed since it was opened")
            stamp, n = time.strftime('%Y%m%d-%H%M%S'), 0
            while True:
                name = f"{target.stem}.{stamp}{'-' + str(n) if n else ''}{target.suffix}"
                bin_ = root / '.trash' / target.relative_to(root).with_name(name)
                if not bin_.exists():
                    break
                n += 1
            bin_.parent.mkdir(parents=True, exist_ok=True)
            os.replace(target, bin_)
            self._prune(kind, target.parent)
        self._send(200, b'{}')

    def do_POST(self):
        path = self.path.split('?')[0]
        file, folder = self._file(path), self._folder(path)
        if not file and not (folder and folder[1] != self.folders[folder[0]]):
            return self._error(404, 'not found')
        kind, source = file or folder
        k, root = _KINDS[kind], self.folders[kind]
        try:
            to = json.loads(self.rfile.read(min(int(self.headers.get('Content-Length') or 0), 10000)))['to']
        except (ValueError, KeyError, TypeError):
            to = None
        if not isinstance(to, str) or not re.fullmatch(_PATH, to):
            return self._error(400, 'send {"to": "<name>"}, a path of lower-case letters, digits and underscores')
        target = root / (f"{to}.{k['ext']}" if file else to)
        if self._taken(kind, target):
            return self._error(400, 'that folder is kept for something else')
        if folder and (target == source or source in target.parents):
            return self._error(400, "a folder can't be moved into itself")
        with _lock:
            if not (source.is_file() if file else any(self._files(kind, source, deep=True))):
                return self._error(404, 'not found')
            if target.exists():
                what = f"a {k['noun']}" if file else 'a folder'
                return self._error(409, f'{what} with that name is already here')
            target.parent.mkdir(parents=True, exist_ok=True)
            os.rename(source, target)
            self._prune(kind, source.parent)
            tag = [('ETag', _etag(target.read_bytes()))] if file else []
        self._send(200, b'{}', headers=tag)

    def do_PUT(self):
        path = self.path.split('?')[0]
        hit = self._file(path)
        if not hit:
            if path.startswith('/api/diagrams'):
                return self._error(404, 'diagrams are saved as /api/diagrams/<key>.yaml')
            return self._error(404, 'maps are saved as /api/maps/<key>.zip')
        kind, target = hit
        k = _KINDS[kind]
        size = int(self.headers.get('Content-Length') or 0)
        if size > MAX_BYTES:
            return self._error(413, 'too large')
        data = self.rfile.read(size)
        if not k['ok'](data):
            return self._error(400, k['not_ok'])
        with _lock:
            wanted = self.headers.get('If-Match')
            if wanted and target.is_file() and _etag(target.read_bytes()) != wanted:
                return self._error(409, f"the {k['noun']} has changed since it was opened")
            if self.headers.get('If-None-Match') == '*' and target.is_file():
                return self._error(409, f"a {k['noun']} with that name is already here")
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_suffix(target.suffix + '.tmp')
            tmp.write_bytes(data)
            os.replace(tmp, target)
        self._send(200, b'{}', headers=[('ETag', _etag(data))])


_lock = threading.Lock()


def start_mind_map_server(folder, port=8765, host='0.0.0.0', editor=None, diagrams=None, diagram_editor=None):
    """Start the server in a background thread and return it (call .shutdown() to stop).

    folder: where the maps are kept (created if missing). port=0 picks a free port (see .server_port).
    host='0.0.0.0' accepts connections from the whole network; use '127.0.0.1' for this computer only.
    editor: path of mindmap-editor.html; by default the copy beside this file.
    diagrams: where the diagrams are kept; by default a 'diagrams' folder inside folder, made when the first is saved.
    diagram_editor: path of diagram-editor.html; by default the copy beside this file. If there is none, the server
        still keeps diagrams but doesn't serve the editor.
    """
    folder = Path(folder).expanduser()
    folder.mkdir(parents=True, exist_ok=True)
    editor = Path(editor or EDITOR or 'mindmap-editor.html').expanduser()
    if not editor.is_file():
        raise FileNotFoundError(f'{editor} not found; pass editor= the path of mindmap-editor.html')
    diagram_editor = Path(diagram_editor or DIAGRAM_EDITOR or 'diagram-editor.html').expanduser()
    diagrams = Path(diagrams).expanduser() if diagrams else folder / 'diagrams'
    home = Path(HOME or 'home.html')
    handler = type('Handler', (_Handler,), {
        'folders': {'maps': folder, 'diagrams': diagrams},
        'pages': {'/': editor, '/mindmap-editor.html': editor, '/diagram-editor.html': diagram_editor,
                  '/home': home, '/home.html': home},
    })
    srv = http.server.ThreadingHTTPServer((host, port), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
