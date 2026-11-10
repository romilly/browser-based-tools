import threading
from mindmap_server import start_mind_map_server

srv = start_mind_map_server('~/mindmaps')
print(f'Serving on port {srv.server_port}; Ctrl+C to stop')
threading.Event().wait()     # block forever, so the server keeps running
