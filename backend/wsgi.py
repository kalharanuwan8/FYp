"""
Entry point. In development: `python wsgi.py`
In production: use eventlet/gunicorn directly against `app` -
  e.g. `gunicorn --worker-class eventlet -w 1 wsgi:app`
(SocketIO requires a single worker with eventlet/gevent, not multiple
sync workers, since it needs to hold long-lived WebSocket connections.)
"""

import os

from app import create_app
from app.extensions import socketio

app = create_app()

if __name__ == "__main__":
    # socketio.run (not app.run) so WebSocket upgrade requests are handled
    # Debug mode and LAN exposure are opt-in (the Werkzeug debugger allows code execution).
    socketio.run(
        app,
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", 5000)),
        debug=os.environ.get("FLASK_DEBUG") == "1",
    )