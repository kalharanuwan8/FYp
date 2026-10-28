"""
Disposable Flask server for the heartbeat latency run.

Environment (set by the caller before launch):
  DATABASE_URL   sqlite file that already contains the fixture user/module
  THESIS_PORT    port to bind
  CUDA_VISIBLE_DEVICES  optional, "-1" disables CUDA
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
os.chdir(BACKEND)
sys.path.insert(0, str(BACKEND))

import torch

print(
    f"THESIS_SERVER_CUDA available={torch.cuda.is_available()} "
    f"device_count={torch.cuda.device_count()} "
    f"name={torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none'}",
    flush=True,
)

from app import create_app
from app.extensions import socketio

app = create_app()
port = int(os.environ["THESIS_PORT"])
print(f"THESIS_SERVER_LISTEN 127.0.0.1:{port}", flush=True)
socketio.run(
    app,
    host="127.0.0.1",
    port=port,
    debug=False,
    use_reloader=False,
    allow_unsafe_werkzeug=True,
)
