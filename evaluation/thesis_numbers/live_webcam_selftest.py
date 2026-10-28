"""
Developer self-test, single adult participant.

Run this yourself on the laptop that has the webcam and the real backend:

  venvpy312\\Scripts\\python.exe evaluation\\thesis_numbers\\live_webcam_selftest.py

Requires the backend already running (default http://127.0.0.1:5000) and a
student login that is enrolled in a course with at least one module and has
guardian consent. Defaults match backend/app/services/default_accounts.py.
Override with THESIS_API, THESIS_EMAIL, THESIS_PASSWORD, THESIS_MODULE_ID.

The window prompts each phase. Heartbeats are POST /api/session/<id>/heartbeat
every 2 s with a 224x224 JPEG at quality 0.5, same parameters as
frontend/src/hooks/useMonitoringSession.js captureFrame.

This script does not clear the server-side rolling buffer between phases.
A 5 s on-screen transition is not part of any phase and no heartbeat is sent
during it, so you can change position. The buffer can still contain the last
frames of the previous phase (maxlen 32, fusion uses the last ML_WINDOW_FRAMES).

Label: developer self-test, single adult participant.
"""
from __future__ import annotations

import csv
import os
import sys
import time
import tkinter as tk
from datetime import datetime, timezone
from pathlib import Path

import json as _json
import urllib.error
import urllib.request

import cv2

API = os.environ.get("THESIS_API", "http://127.0.0.1:5000").rstrip("/")
EMAIL = os.environ.get("THESIS_EMAIL", "student@luma.com")
PASSWORD = os.environ.get("THESIS_PASSWORD", "Student123!")
MODULE_ID = os.environ.get("THESIS_MODULE_ID", "").strip()
INTERVAL_S = 2.0
OUT = Path(__file__).resolve().parent / "raw"
OUT.mkdir(parents=True, exist_ok=True)

PHASES = [
    (
        "read_1",
        60,
        "READ NORMALLY — 60 s",
        "Read the text below, including the words at the edges of the screen.\n"
        "Stay seated, face the screen, as you would when studying.",
    ),
    (
        "phone",
        30,
        "PHONE — 30 s",
        "Look down at a phone on the desk. Do not face the screen.",
    ),
    (
        "away",
        30,
        "HEAD AWAY — 30 s",
        "Turn your head fully away from the screen.",
    ),
    (
        "out_of_chair",
        30,
        "OUT OF THE CHAIR — 30 s",
        "Leave the chair so your face is not in front of the camera.",
    ),
    (
        "read_2",
        60,
        "READ NORMALLY AGAIN — 60 s",
        "Sit back down and read the text, including the edges, as in the first phase.",
    ),
]

READING = (
    "TOP EDGE — keep reading this line at the top of the screen.\n\n"
    "Photosynthesis is the process plants use to turn light, water and carbon dioxide "
    "into sugar and oxygen. The light reactions sit in the thylakoid membrane. "
    "The Calvin cycle uses ATP and NADPH to fix carbon. A short glance at a heading "
    "is still part of reading. Stay with the paragraph until the timer ends.\n\n"
    "LEFT EDGE                                                                    RIGHT EDGE\n\n"
    "BOTTOM EDGE — keep reading this line at the bottom of the screen."
)


def http_json(method: str, url: str, payload=None, headers=None, timeout=30):
    data = None if payload is None else _json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    if payload is not None:
        req.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (_json.loads(raw) if raw else {})
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = _json.loads(raw)
        except _json.JSONDecodeError:
            parsed = {"raw": raw[:500]}
        return exc.code, parsed


def login_and_module() -> tuple[dict, int]:
    status, body = http_json(
        "POST",
        f"{API}/api/auth/login",
        {"email": EMAIL, "password": PASSWORD},
        timeout=30,
    )
    if status != 200:
        raise SystemExit(f"login failed {status} {body}")
    token = body["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    if MODULE_ID:
        return headers, int(MODULE_ID)
    enr_status, enr_body = http_json(
        "GET", f"{API}/api/courses/my-enrollments", headers=headers, timeout=30
    )
    if enr_status != 200:
        raise SystemExit(f"enrollments failed {enr_status} {enr_body}")
    subjects = enr_body.get("enrollments") or []
    if not subjects:
        raise SystemExit(
            "No enrollments for this student. Set THESIS_MODULE_ID or enroll the account."
        )
    detail_status, detail_body = http_json(
        "GET",
        f"{API}/api/courses/subjects/{subjects[0]['id']}",
        headers=headers,
        timeout=30,
    )
    if detail_status != 200:
        raise SystemExit(f"subject detail failed {detail_status} {detail_body}")
    modules = [m for m in detail_body.get("modules") or [] if not m.get("is_archived")]
    if not modules:
        raise SystemExit("Enrolled course has no module.")
    return headers, int(modules[0]["id"])


def jpeg_data_url(frame) -> str:
    import base64

    resized = cv2.resize(frame, (224, 224), interpolation=cv2.INTER_LINEAR)
    ok, buf = cv2.imencode(".jpg", resized, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
    if not ok:
        raise RuntimeError("jpeg encode failed")
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode("ascii")


def summarise(rows: list[dict]) -> list[dict]:
    tables = []
    for key, _dur, title, _body in PHASES:
        phase_rows = [r for r in rows if r["phase"] == key]
        n = len(phase_rows)
        def pct(label: str) -> str:
            if n == 0:
                return "n=0"
            c = sum(1 for r in phase_rows if r["verdict"] == label)
            return f"{c}/{n} = {c / n}"

        def first_time(pred) -> str:
            for r in phase_rows:
                if pred(r):
                    return str(r["seconds_from_phase_start"])
            return "none"

        tables.append(
            {
                "phase": key,
                "title": title,
                "n_heartbeats": n,
                "focused": pct("FOCUSED"),
                "distracted": pct("DISTRACTED"),
                "unknown": pct("UNKNOWN"),
                "seconds_to_first_distracted": first_time(lambda r: r["verdict"] == "DISTRACTED"),
                "seconds_to_first_intervention": first_time(
                    lambda r: r["intervention_fired"] == "true"
                ),
                "first_intervention_tier": next(
                    (
                        r["intervention_tier"]
                        for r in phase_rows
                        if r["intervention_fired"] == "true"
                    ),
                    "none",
                ),
            }
        )
    return tables


def main() -> None:
    headers, module_id = login_and_module()
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise SystemExit("Could not open a webcam.")

    start_status, start_body = http_json(
        "POST",
        f"{API}/api/session/start",
        {"module_id": module_id, "is_monitored": True},
        headers=headers,
        timeout=120,
    )
    if start_status != 201:
        cap.release()
        raise SystemExit(f"session start failed {start_status} {start_body}")
    session_id = start_body["session_id"]
    print(f"session_id={session_id} module_id={module_id} api={API}", flush=True)

    rows: list[dict] = []
    state = {"phase_i": -1, "phase_t0": None, "next_hb": None, "mode": "ready"}

    root = tk.Tk()
    root.title("Luma developer self-test — single adult participant")
    root.geometry("1100x700")
    title = tk.Label(root, text="Developer self-test, single adult participant", font=("Segoe UI", 16, "bold"))
    title.pack(pady=8)
    prompt = tk.Label(root, text="", font=("Segoe UI", 22, "bold"), wraplength=1000, justify="center")
    prompt.pack(pady=8)
    body = tk.Label(root, text="", font=("Segoe UI", 14), wraplength=1000, justify="left")
    body.pack(pady=6)
    reading = tk.Label(
        root,
        text=READING,
        font=("Segoe UI", 12),
        wraplength=1000,
        justify="left",
        fg="#1a1a1a",
    )
    clock = tk.Label(root, text="", font=("Consolas", 18))
    clock.pack(pady=8)
    status = tk.Label(root, text="", font=("Consolas", 11))
    status.pack(pady=4)

    def begin_phase(i: int) -> None:
        state["phase_i"] = i
        state["phase_t0"] = time.perf_counter()
        state["next_hb"] = state["phase_t0"]
        state["mode"] = "phase"
        key, dur, heading, text = PHASES[i]
        prompt.config(text=f"{heading}")
        body.config(text=text)
        reading.pack(pady=8) if key.startswith("read") else reading.pack_forget()

    def begin_transition() -> None:
        state["mode"] = "transition"
        state["phase_t0"] = time.perf_counter()
        prompt.config(text="Next phase in 5 s")
        body.config(text="Move into the position described next. No heartbeat is sent during this gap.")
        reading.pack_forget()

    def tick() -> None:
        now = time.perf_counter()
        if state["mode"] == "ready":
            clock.config(text="Press Start when you are seated and the camera can see you.")
        elif state["mode"] == "transition":
            left = 5.0 - (now - state["phase_t0"])
            clock.config(text=f"transition {left:.1f}s")
            if left <= 0:
                begin_phase(state["phase_i"] + 1)
        elif state["mode"] == "phase":
            key, dur, _heading, _text = PHASES[state["phase_i"]]
            elapsed = now - state["phase_t0"]
            clock.config(text=f"{key}  {elapsed:.1f}s / {dur}s")
            if elapsed >= dur:
                if state["phase_i"] + 1 >= len(PHASES):
                    state["mode"] = "done"
                    prompt.config(text="Protocol complete")
                    body.config(text="You can close this window. The summary is in the console and raw CSV.")
                    clock.config(text="")
                else:
                    begin_transition()
            elif now >= state["next_hb"]:
                state["next_hb"] = now + INTERVAL_S
                ok, frame = cap.read()
                ts = datetime.now(timezone.utc).isoformat()
                rec = {
                    "timestamp_utc": ts,
                    "phase": key,
                    "seconds_from_phase_start": elapsed,
                    "verdict": "",
                    "confidence": "",
                    "reason": "",
                    "ml_mode": "",
                    "intervention_fired": "",
                    "intervention_tier": "",
                    "intervention_type": "",
                    "http_status": "",
                    "error": "",
                    # Additive diagnostics (heartbeat diagnostics object); older CSVs omit these.
                    "inference_path": "",
                    "gaze_label": "",
                    "head_pose_yaw": "",
                    "head_pose_pitch": "",
                    "head_pose_roll": "",
                    "distract_prob": "",
                    "face_box_px": "",
                    "pose_baseline_yaw": "",
                    "pose_baseline_pitch": "",
                    "fusion_threshold": "",
                }
                if not ok:
                    rec["error"] = "camera_read_failed"
                else:
                    try:
                        hb_status, data = http_json(
                            "POST",
                            f"{API}/api/session/{session_id}/heartbeat",
                            {
                                "image": jpeg_data_url(frame),
                                "is_quiz_context": False,
                            },
                            headers=headers,
                            timeout=30,
                        )
                        rec["http_status"] = str(hb_status)
                        rec["verdict"] = str(data.get("verdict"))
                        rec["confidence"] = "" if data.get("confidence") is None else str(data.get("confidence"))
                        rec["reason"] = "" if data.get("reason") is None else str(data.get("reason"))
                        rec["ml_mode"] = "" if data.get("ml_mode") is None else str(data.get("ml_mode"))
                        fired = bool(data.get("intervention_triggered"))
                        rec["intervention_fired"] = "true" if fired else "false"
                        inter = data.get("intervention") or {}
                        rec["intervention_tier"] = "" if inter.get("tier") is None else str(inter.get("tier"))
                        rec["intervention_type"] = "" if inter.get("intervention_type") is None else str(inter.get("intervention_type"))
                        diag = data.get("diagnostics") or {}
                        rec["inference_path"] = "" if diag.get("inference_path") is None else str(diag.get("inference_path"))
                        rec["gaze_label"] = "" if diag.get("gaze_label") is None else str(diag.get("gaze_label"))
                        rec["head_pose_yaw"] = "" if diag.get("head_pose_yaw") is None else str(diag.get("head_pose_yaw"))
                        rec["head_pose_pitch"] = "" if diag.get("head_pose_pitch") is None else str(diag.get("head_pose_pitch"))
                        rec["head_pose_roll"] = "" if diag.get("head_pose_roll") is None else str(diag.get("head_pose_roll"))
                        rec["distract_prob"] = "" if diag.get("distract_prob") is None else str(diag.get("distract_prob"))
                        box = diag.get("face_box_px")
                        rec["face_box_px"] = "" if box is None else str(box)
                        rec["pose_baseline_yaw"] = (
                            ""
                            if diag.get("pose_baseline_yaw") is None
                            else str(diag.get("pose_baseline_yaw"))
                        )
                        rec["pose_baseline_pitch"] = (
                            ""
                            if diag.get("pose_baseline_pitch") is None
                            else str(diag.get("pose_baseline_pitch"))
                        )
                        rec["fusion_threshold"] = (
                            ""
                            if diag.get("fusion_threshold") is None
                            else str(diag.get("fusion_threshold"))
                        )
                    except Exception as exc:
                        rec["error"] = str(exc)
                rows.append(rec)
                status.config(
                    text=f"{rec['verdict']} conf={rec['confidence']} ml={rec['ml_mode']} "
                    f"intervention={rec['intervention_fired']} tier={rec['intervention_tier']} {rec['error']}"
                )
        root.after(100, tick)

    def on_start() -> None:
        if state["mode"] == "ready":
            begin_phase(0)
            start_btn.config(state="disabled")

    def on_close() -> None:
        try:
            http_json(
                "POST",
                f"{API}/api/session/{session_id}/stop",
                {},
                headers=headers,
                timeout=30,
            )
        except Exception as exc:
            print("stop failed", exc, flush=True)
        cap.release()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        csv_path = OUT / f"live_webcam_selftest_{stamp}.csv"
        if rows:
            with csv_path.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)
        table = summarise(rows)
        print("LABEL: developer self-test, single adult participant", flush=True)
        print(f"LOG: {csv_path if rows else 'no heartbeats'}", flush=True)
        for row in table:
            print(row, flush=True)
        root.destroy()

    start_btn = tk.Button(root, text="Start protocol", font=("Segoe UI", 14), command=on_start)
    start_btn.pack(pady=8)
    prompt.config(text="Ready")
    body.config(
        text="Single adult participant. The first phase is 60 s of normal reading, "
        "including the words at the screen edges. Press Start when seated."
    )
    root.protocol("WM_DELETE_WINDOW", on_close)
    root.after(100, tick)
    root.mainloop()


if __name__ == "__main__":
    main()
