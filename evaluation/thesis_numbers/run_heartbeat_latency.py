"""
Full-path heartbeat latency with real face frames.

Posts JPEG frames (224x224, OpenCV JPEG quality 50, matching the frontend
canvas size and toDataURL quality 0.5) to POST /api/session/<id>/heartbeat.

One warm-up heartbeat, then 50 timed heartbeats. Repeated with CUDA disabled
in a second process.

Does not modify checkpoints. Uses a throwaway sqlite database under raw/.
"""
from __future__ import annotations

import base64
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

import urllib.error
import urllib.request

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
OUT = Path(__file__).resolve().parent
RAW = OUT / "raw"
RAW.mkdir(parents=True, exist_ok=True)

VIDEOS = [
    Path(r"D:\uni\6th sem\IRP\Data collection\raw data\participant 1\natural.mp4"),
    Path(r"D:\uni\6th sem\IRP\Data collection\raw data\participant 1\focused.mp4"),
    Path(r"D:\uni\6th sem\IRP\Data collection\raw data\participant 1\distracted.mp4"),
]
N_TIMED = 50
EMAIL = "thesis.heartbeat@luma.demo"
PASSWORD = "ThesisHeartbeat123!"


def collect_face_jpegs(n_needed: int) -> list[dict]:
    cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    kept = []
    for video in VIDEOS:
        if len(kept) >= n_needed:
            break
        cap = cv2.VideoCapture(str(video))
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open {video}")
        idx = 0
        while len(kept) < n_needed:
            ok, frame = cap.read()
            if not ok:
                break
            if idx % 5 != 0:
                idx += 1
                continue
            resized = cv2.resize(frame, (224, 224), interpolation=cv2.INTER_LINEAR)
            ok_j, buf = cv2.imencode(
                ".jpg", resized, [int(cv2.IMWRITE_JPEG_QUALITY), 50]
            )
            if not ok_j:
                idx += 1
                continue
            raw = buf.tobytes()
            decoded = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
            gray = cv2.cvtColor(decoded, cv2.COLOR_BGR2GRAY)
            faces = cascade.detectMultiScale(gray, 1.1, 5, minSize=(50, 50))
            if len(faces) > 0:
                kept.append(
                    {
                        "video": video.name,
                        "frame_index": idx,
                        "jpeg_bytes": len(raw),
                        "data_url": "data:image/jpeg;base64,"
                        + base64.b64encode(raw).decode("ascii"),
                    }
                )
            idx += 1
        cap.release()
    if len(kept) < n_needed:
        raise RuntimeError(f"Only collected {len(kept)} face frames, need {n_needed}")
    return kept


def prepare_db(db_path: Path) -> int:
    if db_path.exists():
        db_path.unlink()
    env = os.environ.copy()
    env["DATABASE_URL"] = "sqlite:///" + db_path.resolve().as_posix()
    env["FLASK_ENV"] = "development"
    env["SEED_DEFAULT_ACCOUNTS"] = "false"
    env.pop("CUDA_VISIBLE_DEVICES", None)
    proc = subprocess.run(
        [sys.executable, str(OUT / "prepare_heartbeat_db.py")],
        cwd=str(BACKEND),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    (RAW / "prepare_heartbeat_db_last.txt").write_text(
        proc.stdout + "\n--- stderr ---\n" + proc.stderr, encoding="utf-8"
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"prepare_heartbeat_db failed ({proc.returncode}): {proc.stderr[-2000:]}"
        )
    module_id = None
    for line in proc.stdout.splitlines():
        if line.startswith("MODULE_ID "):
            module_id = int(line.split()[1])
    if module_id is None:
        raise RuntimeError(f"no MODULE_ID in prepare output: {proc.stdout[-500:]}")
    return module_id


def percentile_linear(values: list[float], q: float) -> float:
    """NumPy linear percentile (Hyndman-Fan type 7), also computed explicitly."""
    arr = np.asarray(values, dtype=np.float64)
    np_val = float(np.percentile(arr, q, method="linear"))
    n = arr.shape[0]
    if n == 1:
        manual = float(arr[0])
    else:
        xs = np.sort(arr)
        pos = (n - 1) * (q / 100.0)
        lo = int(np.floor(pos))
        hi = int(np.ceil(pos))
        w = pos - lo
        manual = float(xs[lo] * (1.0 - w) + xs[hi] * w)
    if manual != np_val and abs(manual - np_val) > 1e-9:
        raise RuntimeError(f"percentile mismatch manual={manual} numpy={np_val}")
    return np_val


def http_json(method: str, url: str, payload=None, headers=None, timeout=30):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    if payload is not None:
        req.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {"raw": raw[:500]}
        return exc.code, parsed


def wait_until(url: str, proc: subprocess.Popen, timeout_s: float = 180.0) -> None:
    deadline = time.perf_counter() + timeout_s
    last = None
    while time.perf_counter() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"server exited {proc.returncode} before ready; last={last}")
        try:
            http_json("GET", url, timeout=2)
            return
        except urllib.error.HTTPError:
            return
        except Exception as exc:
            last = str(exc)
            time.sleep(0.5)
    raise RuntimeError(f"server did not listen: {last}")


def run_condition(tag: str, frames: list[dict], disable_cuda: bool) -> dict:
    db_path = RAW / f"heartbeat_{tag}.db"
    # prepare_db imports the app into THIS process. Do it before the server,
    # and do not call MLService here.
    module_id = prepare_db(db_path)
    port = 8765 if tag == "cuda" else 8766
    env = os.environ.copy()
    env["DATABASE_URL"] = "sqlite:///" + db_path.resolve().as_posix()
    env["FLASK_ENV"] = "development"
    env["SEED_DEFAULT_ACCOUNTS"] = "false"
    env["THESIS_PORT"] = str(port)
    env["PYTHONUNBUFFERED"] = "1"
    if disable_cuda:
        env["CUDA_VISIBLE_DEVICES"] = "-1"
    else:
        env.pop("CUDA_VISIBLE_DEVICES", None)
    log_path = RAW / f"heartbeat_server_{tag}.log"
    log_f = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, str(OUT / "heartbeat_server.py")],
        cwd=str(BACKEND),
        env=env,
        stdout=log_f,
        stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        wait_until(base + "/api/auth/login", proc)
        login_status, login_body = http_json(
            "POST",
            base + "/api/auth/login",
            {"email": EMAIL, "password": PASSWORD},
            timeout=30,
        )
        if login_status != 200:
            raise RuntimeError(f"login failed {login_status} {login_body}")
        token = login_body["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        t0 = time.perf_counter()
        start_status, start_body = http_json(
            "POST",
            base + "/api/session/start",
            {"module_id": module_id, "is_monitored": True},
            headers=headers,
            timeout=300,
        )
        start_ms = (time.perf_counter() - t0) * 1000.0
        if start_status != 201:
            raise RuntimeError(f"start failed {start_status} {start_body}")
        sid = start_body["session_id"]

        def post_frame(frame):
            t0 = time.perf_counter()
            status, body = http_json(
                "POST",
                f"{base}/api/session/{sid}/heartbeat",
                {"image": frame["data_url"], "is_quiz_context": False},
                headers=headers,
                timeout=300,
            )
            dt = (time.perf_counter() - t0) * 1000.0
            return dt, status, body

        warm_dt, warm_status, warm_body = post_frame(frames[0])
        timed = []
        for frame in frames[1 : 1 + N_TIMED]:
            dt, status, body = post_frame(frame)
            timed.append(
                {
                    "ms": dt,
                    "status": status,
                    "verdict": body.get("verdict"),
                    "reason": body.get("reason"),
                    "ml_mode": body.get("ml_mode"),
                    "face_detected": body.get("face_detected"),
                    "video": frame["video"],
                    "frame_index": frame["frame_index"],
                }
            )
        http_json("POST", f"{base}/api/session/{sid}/stop", {}, headers=headers, timeout=60)
        times = [row["ms"] for row in timed]
        log_f.flush()
        server_log = log_path.read_text(encoding="utf-8", errors="replace")
        cuda_line = next(
            (ln for ln in server_log.splitlines() if ln.startswith("THESIS_SERVER_CUDA")),
            None,
        )
        return {
            "tag": tag,
            "disable_cuda_env": disable_cuda,
            "cuda_line": cuda_line,
            "port": port,
            "session_start_ms": start_ms,
            "warmup_heartbeat_ms": warm_dt,
            "warmup_status": warm_status,
            "warmup_verdict": warm_body.get("verdict"),
            "warmup_reason": warm_body.get("reason"),
            "warmup_ml_mode": warm_body.get("ml_mode"),
            "warmup_face_detected": warm_body.get("face_detected"),
            "n": len(times),
            "min_ms": float(min(times)),
            "median_ms": float(statistics.median(times)),
            "p95_linear_ms": percentile_linear(times, 95),
            "max_ms": float(max(times)),
            "n_status_200": sum(1 for row in timed if row["status"] == 200),
            "n_face_detected_true": sum(1 for row in timed if row["face_detected"] is True),
            "n_reason_no_face": sum(1 for row in timed if row["reason"] == "no_face"),
            "ml_modes": sorted({str(row["ml_mode"]) for row in timed}),
            "verdicts": {
                str(k): int(sum(1 for row in timed if row["verdict"] == k))
                for k in sorted({row["verdict"] for row in timed}, key=lambda x: str(x))
            },
            "timed_rows": timed,
        }
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
        log_f.close()


def main() -> None:
    print("collecting face frames", flush=True)
    frames = collect_face_jpegs(1 + N_TIMED)
    manifest = [
        {"video": f["video"], "frame_index": f["frame_index"], "jpeg_bytes": f["jpeg_bytes"]}
        for f in frames
    ]
    (RAW / "heartbeat_frames_manifest.json").write_text(
        json.dumps(
            {
                "resize": "cv2.resize to 224x224 INTER_LINEAR",
                "jpeg_quality": 50,
                "jpeg_quality_note": "OpenCV IMWRITE_JPEG_QUALITY 50 matches the frontend canvas.toDataURL('image/jpeg', 0.5) quality argument. The encoder is OpenCV, not the browser encoder.",
                "face_prefilter": "After 224x224 resize and JPEG quality 50 decode, Haar detectMultiScale(gray, 1.1, 5, minSize=(50,50)), the same call ml_service uses. Frames that fail this are not posted.",
                "n_frames": len(frames),
                "frames": manifest,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"collected {len(frames)}", flush=True)
    results = {}
    for tag, disable in (("cuda", False), ("cpu", True)):
        print(f"RUN {tag}", flush=True)
        results[tag] = run_condition(tag, frames, disable_cuda=disable)
        slim = {k: v for k, v in results[tag].items() if k != "timed_rows"}
        print(json.dumps(slim, indent=2), flush=True)
    (RAW / "heartbeat_latency.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )
    print("WROTE heartbeat_latency.json", flush=True)


if __name__ == "__main__":
    main()
