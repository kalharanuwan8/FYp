"""
Entry point. In development: `python wsgi.py`
In production: use eventlet/gunicorn directly against `app` -
  e.g. `gunicorn --worker-class eventlet -w 1 wsgi:app`
(SocketIO requires a single worker with eventlet/gevent, not multiple
sync workers, since it needs to hold long-lived WebSocket connections.)
"""

from app import create_app
from app.extensions import socketio

app = create_app()

if __name__ == "__main__":
    # socketio.run (not app.run) so WebSocket upgrade requests are handled
    socketio.run(app, host="0.0.0.0", port=int(__import__("os").environ.get("PORT", 5000)), debug=True)