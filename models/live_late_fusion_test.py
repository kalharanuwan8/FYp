"""
Live webcam test for the late-fusion stack (M1 + M2 + M3 → M4).

Uses staging weights only (checkpoints_late_fusion/). Does NOT change the
Flask monitoring pipeline (that still runs model6).

Usage (from the models/ directory):
  ..\\venvpy312\\Scripts\\python.exe -u live_late_fusion_test.py
  ..\\venvpy312\\Scripts\\python.exe -u live_late_fusion_test.py --camera 1

Controls:
  q  quit
  r  reset M4 buffer (screen map stays)
  c  calibrate gaze onto this monitor (9 dots + head phase)
"""
from __future__ import annotations

import argparse
import ctypes
import os
import sys
import time
from collections import deque
from pathlib import Path
from typing import Deque, List, Optional, Tuple

import cv2
import numpy as np

REPO = Path(__file__).resolve().parents[1]
MODELS = Path(__file__).resolve().parent
STAGE = MODELS / "outputs" / "checkpoints_late_fusion"

HEARTBEAT_SEC = 2.0
WINDOW_SIZE = 5
THRESHOLD = 0.75
OUT_SIZE = 224
JPEG_QUALITY = 70
WIN_NAME = "Luma late-fusion live test (staging weights)"

# Same 3x3 grid as ScreenCalibrationOverlay.jsx (5% inset).
INSET = 0.05
CALIB_DOTS = [
    (1 - INSET, INSET),
    (0.5, INSET),
    (INSET, INSET),
    (INSET, 0.5),
    (0.5, 0.5),
    (1 - INSET, 0.5),
    (INSET, 1 - INSET),
    (0.5, 1 - INSET),
    (1 - INSET, 1 - INSET),
]
DOT_MS = 2000
SETTLE_MS = 600
HEAD_MS = 4000
CALIB_SAMPLE_SEC = 0.12

FEAT_COLS = [
    "p_center_mean",
    "p_left_mean",
    "p_right_mean",
    "p_down_mean",
    "gaze_away_ratio",
    "yaw_mean",
    "pitch_mean",
    "roll_mean",
    "engagement_prob_mean",
]


def _configure_env() -> None:
    os.environ["GAZE_CKPT"] = str(STAGE / "model1_gaze" / "best.pt")
    os.environ["POSE_CKPT"] = str(STAGE / "model2_pose" / "best.pt")
    os.environ["ENG_CKPT"] = str(STAGE / "model4_engagement" / "model.pkl")
    os.environ["FUSION_CKPT"] = str(STAGE / "model5_fusion" / "model.pkl")
    for p in (str(REPO), str(MODELS), str(REPO / "backend")):
        if p not in sys.path:
            sys.path.insert(0, p)


def _center_square_224(frame_bgr: np.ndarray) -> np.ndarray:
    h, w = frame_bgr.shape[:2]
    side = min(h, w)
    x0 = (w - side) // 2
    y0 = (h - side) // 2
    crop = frame_bgr[y0 : y0 + side, x0 : x0 + side]
    return cv2.resize(crop, (OUT_SIZE, OUT_SIZE), interpolation=cv2.INTER_AREA)


def _jpeg_roundtrip(frame_bgr: np.ndarray) -> np.ndarray:
    ok, buf = cv2.imencode(
        ".jpg", frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]
    )
    if not ok:
        return frame_bgr
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def _screen_size() -> Tuple[int, int]:
    """Primary monitor size in pixels (this device)."""
    try:
        user32 = ctypes.windll.user32
        w = int(user32.GetSystemMetrics(0))
        h = int(user32.GetSystemMetrics(1))
        if w > 0 and h > 0:
            return w, h
    except Exception:
        pass
    return 1280, 720


def _draw_gaze_map(
    img: np.ndarray,
    sx: Optional[float],
    sy: Optional[float],
    on_screen: Optional[bool],
) -> None:
    """Small diagram of this monitor with the mapped gaze point."""
    h, w = img.shape[:2]
    mw, mh = 160, 90
    x0, y0 = w - mw - 12, h - mh - 52
    cv2.rectangle(img, (x0, y0), (x0 + mw, y0 + mh), (40, 40, 40), -1)
    cv2.rectangle(img, (x0, y0), (x0 + mw, y0 + mh), (220, 220, 220), 1)
    if sx is None or sy is None:
        cv2.putText(
            img, "no map", (x0 + 48, y0 + 50),
            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1, cv2.LINE_AA,
        )
        return
    px = int(x0 + min(1.0, max(0.0, float(sx))) * (mw - 1))
    py = int(y0 + min(1.0, max(0.0, float(sy))) * (mh - 1))
    color = (0, 220, 0) if on_screen else (0, 0, 255)
    cv2.circle(img, (px, py), 6, color, -1)


def _calib_canvas(
    sw: int,
    sh: int,
    target: Tuple[float, float],
    title: str,
    subtitle: str,
) -> np.ndarray:
    canvas = np.zeros((sh, sw, 3), dtype=np.uint8)
    px = int(round(target[0] * (sw - 1)))
    py = int(round(target[1] * (sh - 1)))
    cv2.circle(canvas, (px, py), 22, (0, 220, 255), -1)
    cv2.circle(canvas, (px, py), 6, (0, 0, 0), -1)
    cv2.putText(
        canvas, title, (40, 48),
        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2, cv2.LINE_AA,
    )
    cv2.putText(
        canvas, subtitle, (40, 84),
        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1, cv2.LINE_AA,
    )
    return canvas


def _run_screen_calibration(cap, scorer, screen_wh: Tuple[int, int], t_origin: float) -> dict:
    """Fullscreen 9-dot look plus a centre head phase. Fits ScreenGazeMapper."""
    sw, sh = screen_wh
    scorer.set_screen(
        {"w": float(sw), "h": float(sh), "inner_w": float(sw), "inner_h": float(sh), "dpr": 1.0}
    )
    scorer.start_calibration()
    cv2.setWindowProperty(WIN_NAME, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    phases = [
        (xy, DOT_MS, SETTLE_MS, f"Look at the star  {i}/9", "Keep your eyes on the yellow star")
        for i, xy in enumerate(CALIB_DOTS, 1)
    ]
    phases.append(
        (
            (0.5, 0.5),
            HEAD_MS,
            0,
            "Eyes on the centre star",
            "Slowly turn your head left and right, then nod",
        )
    )

    aborted = False
    for target, duration_ms, settle_ms, title, subtitle in phases:
        phase_start = time.perf_counter()
        last_sample = 0.0
        while True:
            elapsed_ms = (time.perf_counter() - phase_start) * 1000.0
            if elapsed_ms >= duration_ms:
                break
            ok, frame = cap.read()
            if not ok or frame is None:
                if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                    aborted = True
                    break
                continue
            canvas = _calib_canvas(sw, sh, target, title, subtitle)
            left = max(0.0, (duration_ms - elapsed_ms) / 1000.0)
            cv2.putText(
                canvas, f"{left:.1f}s   screen {sw}x{sh}", (40, sh - 40),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (180, 180, 180), 1, cv2.LINE_AA,
            )
            cv2.imshow(WIN_NAME, canvas)
            now = time.perf_counter()
            if elapsed_ms >= settle_ms and now - last_sample >= CALIB_SAMPLE_SEC:
                scorer.add_frame(
                    now - t_origin,
                    frame,
                    calib_target={"x": float(target[0]), "y": float(target[1])},
                )
                last_sample = now
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                aborted = True
                break
        if aborted:
            break

    cv2.setWindowProperty(WIN_NAME, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_NORMAL)
    if aborted:
        print("[live] calibration cancelled")
        return {"ok": False, "cancelled": True}
    status = scorer.finish_calibration()
    print(
        f"[live] calibration ok={status.get('ok')} residual={status.get('residual')} "
        f"dots={status.get('n_dots')} samples={status.get('n_samples')} "
        f"screen={sw}x{sh}"
    )
    return status


def _note_screen_gaze(scorer, frame, t_sec: float, state: dict) -> None:
    """Map this frame onto the calibrated screen. Does not affect M4."""
    f = scorer.add_frame(t_sec, frame)
    if f is None:
        return
    summary = scorer.gaze_summary()
    state["sx"] = summary.get("sx")
    state["sy"] = summary.get("sy")
    state["on_screen"] = summary.get("on_screen")
    state["calibrated"] = bool(summary.get("calibrated"))
    state["gaze_mode"] = summary.get("mode")


def _draw_panel(img: np.ndarray, lines: List[tuple], x: int = 10, y0: int = 28) -> None:
    """lines = [(text, (b,g,r)), ...]"""
    y = y0
    for text, color in lines:
        cv2.putText(
            img,
            text,
            (x, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 0, 0),
            3,
            cv2.LINE_AA,
        )
        cv2.putText(
            img,
            text,
            (x, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            color,
            1,
            cv2.LINE_AA,
        )
        y += 22


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--threshold", type=float, default=THRESHOLD)
    ap.add_argument("--heartbeat-sec", type=float, default=HEARTBEAT_SEC)
    args = ap.parse_args()

    _configure_env()
    from app.services.ml_service import MLService
    from src.features.live import LiveWindowScorer

    MLService._instance = None
    ml = MLService()
    screen_wh = _screen_size()
    scorer = LiveWindowScorer(window_sec=3.0, screen_gaze=True)
    scorer.set_screen(
        {
            "w": float(screen_wh[0]),
            "h": float(screen_wh[1]),
            "inner_w": float(screen_wh[0]),
            "inner_h": float(screen_wh[1]),
            "dpr": 1.0,
        }
    )
    t_origin = time.perf_counter()
    ml.window_size = WINDOW_SIZE
    ml.pose_baseline_frames = 8
    ml.fusion_feat_names = list(FEAT_COLS)
    thr = float(args.threshold)

    print(
        f"[live] device={ml.device} gaze={ml.gaze_model is not None} "
        f"pose={ml.pose_model is not None} eng={ml.eng_model is not None} "
        f"fusion={ml.fusion_model is not None} thr={thr} "
        f"screen={screen_wh[0]}x{screen_wh[1]}"
    )
    if ml.gaze_model is None or ml.pose_model is None:
        raise SystemExit("M1/M2 staging weights failed to load")
    if ml.fusion_model is None:
        raise SystemExit("M4 staging pack failed to load")

    sid = "live_late_fusion_test"
    ml.clear_session(sid)

    gaze_buf: Deque = deque(maxlen=WINDOW_SIZE)
    pose_buf: Deque = deque(maxlen=WINDOW_SIZE)
    lm_buf: Deque = deque(maxlen=WINDOW_SIZE)

    state = {
        "verdict": "WAITING",
        "prob": None,
        "gaze": "—",
        "yaw": 0.0,
        "pitch": 0.0,
        "roll": 0.0,
        "eng": 0.5,
        "face": False,
        "buf": 0,
        "reason": "warming up",
        "features": {},
        "sx": None,
        "sy": None,
        "on_screen": None,
        "calibrated": False,
        "gaze_mode": "fallback",
    }

    cap = cv2.VideoCapture(args.camera, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        raise SystemExit(f"Cannot open camera {args.camera}")

    # Prefer a modest capture size (matches planned late-fusion frontend).
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    last_beat = 0.0
    cv2.namedWindow(WIN_NAME, cv2.WINDOW_NORMAL)
    print(
        f"[live] window open — screen {screen_wh[0]}x{screen_wh[1]}. "
        "q=quit  r=reset M4  c=calibrate gaze to this screen"
    )
    print("[live] need ~5 valid face heartbeats (~10 s) before M4 votes")

    while True:
        ok, frame = cap.read()
        if not ok or frame is None:
            break

        display = frame.copy()
        now = time.time()

        if now - last_beat >= args.heartbeat_sec:
            last_beat = now
            prepared = _jpeg_roundtrip(_center_square_224(frame))
            _note_screen_gaze(scorer, frame, time.perf_counter() - t_origin, state)
            on_txt = (
                "ON SCREEN" if state.get("on_screen") is True
                else "OFF SCREEN" if state.get("on_screen") is False
                else "—"
            )
            if state.get("calibrated") and state.get("sx") is not None:
                print(
                    f"[{time.strftime('%H:%M:%S')}] screen gaze  "
                    f"sx={state['sx']:.3f} sy={state['sy']:.3f}  {on_txt}"
                )
            face_box = ml._detect_face(prepared)

            if face_box is None:
                # Body-without-face → DISTRACTED (same policy as predict_frame_image)
                frame_rgb = cv2.cvtColor(prepared, cv2.COLOR_BGR2RGB)
                lm_body = ml.extract_landmarks(frame_rgb, sid)
                if ml._landmarks_indicate_person(lm_body):
                    state.update(
                        {
                            "verdict": "DISTRACTED",
                            "prob": 0.85,
                            "face": False,
                            "reason": "body_no_face",
                            "gaze": "—",
                        }
                    )
                    print(f"[{time.strftime('%H:%M:%S')}] DISTRACTED  body_no_face")
                else:
                    state.update(
                        {
                            "verdict": "UNKNOWN",
                            "prob": None,
                            "face": False,
                            "reason": "no_face",
                            "gaze": "—",
                        }
                    )
                    print(f"[{time.strftime('%H:%M:%S')}] UNKNOWN  no_face")
            else:
                gaze_probs, pose_xyz, lm, meta = ml._infer_frame_signals(
                    prepared, sid, face_box=face_box
                )
                ml._update_pose_baseline(sid, pose_xyz)
                gaze_buf.append(gaze_probs)
                pose_buf.append(pose_xyz)
                lm_buf.append(lm)

                gaze_label = meta.get("gaze_label", "?")
                state["face"] = True
                state["gaze"] = f"{gaze_label}  c={gaze_probs[0]:.2f} l={gaze_probs[1]:.2f} r={gaze_probs[2]:.2f} d={gaze_probs[3]:.2f}"
                state["yaw"] = float(pose_xyz[0])
                state["pitch"] = float(pose_xyz[1])
                state["roll"] = float(pose_xyz[2])
                state["buf"] = len(gaze_buf)

                eng_prob = 0.5
                if ml.eng_model is not None and ml.eng_feature_cols and len(lm_buf) >= 2:
                    eng_feats = ml.compute_engagement_features(list(lm_buf))
                    eng_X = np.array(
                        [[eng_feats.get(c, 0.0) for c in ml.eng_feature_cols]],
                        dtype=np.float32,
                    )
                    try:
                        eng_prob = float(ml.eng_model.predict_proba(eng_X)[0, 1])
                    except Exception:
                        eng_prob = 0.5
                state["eng"] = eng_prob

                if len(gaze_buf) >= WINDOW_SIZE:
                    pose_for_score, yaw0, pitch0 = ml._centered_pose_buf(
                        sid, list(pose_buf)
                    )
                    saved = list(ml.fusion_feat_names)
                    ml.fusion_feat_names = list(FEAT_COLS)
                    try:
                        feat_vec = ml.build_fusion_features(
                            list(gaze_buf),
                            list(pose_for_score),
                            eng_prob,
                            lm_buf=list(lm_buf),
                        )
                    finally:
                        ml.fusion_feat_names = saved

                    proba = ml.fusion_model.predict_proba(feat_vec)[0]
                    dist_prob = float(proba[1] if len(proba) >= 2 else proba[0])
                    verdict = "DISTRACTED" if dist_prob >= thr else "FOCUSED"
                    state["verdict"] = verdict
                    state["prob"] = dist_prob
                    state["reason"] = "fusion"
                    state["features"] = {
                        name: float(feat_vec[0, i]) for i, name in enumerate(FEAT_COLS)
                    }
                    bl = (
                        f"base yaw={yaw0:.1f} pitch={pitch0:.1f}"
                        if yaw0 is not None
                        else "calibrating baseline"
                    )
                    print(
                        f"[{time.strftime('%H:%M:%S')}] {verdict:10s}  "
                        f"p={dist_prob:.3f}  eng={eng_prob:.2f}  "
                        f"gaze={gaze_label}  yaw={pose_xyz[0]:.1f}  {bl}"
                    )
                else:
                    state["verdict"] = "WARMUP"
                    state["prob"] = None
                    state["reason"] = f"buffer {len(gaze_buf)}/{WINDOW_SIZE}"
                    print(
                        f"[{time.strftime('%H:%M:%S')}] WARMUP  "
                        f"buf={len(gaze_buf)}/{WINDOW_SIZE}  gaze={gaze_label}"
                    )

        # Overlay
        v = state["verdict"]
        if v == "DISTRACTED":
            color = (0, 0, 255)
        elif v == "FOCUSED":
            color = (0, 200, 0)
        elif v == "UNKNOWN":
            color = (0, 165, 255)
        else:
            color = (200, 200, 0)

        prob_txt = "—" if state["prob"] is None else f"{state['prob']:.3f}"
        lines = [
            (f"VERDICT  {v}   p_distract={prob_txt}   thr={thr}", color),
            (f"M1 gaze  {state['gaze']}", (220, 220, 220)),
            (
                f"M2 pose  yaw={state['yaw']:.1f}  pitch={state['pitch']:.1f}  "
                f"roll={state['roll']:.1f}",
                (220, 220, 220),
            ),
            (f"M3 eng   p_engage={state['eng']:.3f}", (220, 220, 220)),
            (
                f"face={state['face']}  buf={state['buf']}/{WINDOW_SIZE}  "
                f"reason={state['reason']}",
                (180, 180, 180),
            ),
            (
                f"screen {screen_wh[0]}x{screen_wh[1]}  "
                + (
                    f"sx={state['sx']:.2f} sy={state['sy']:.2f}  "
                    + ("ON SCREEN" if state.get("on_screen") else "OFF SCREEN")
                    if state.get("calibrated") and state.get("sx") is not None
                    else "press c to map gaze onto this screen"
                ),
                (0, 220, 255) if state.get("on_screen") else (180, 180, 180),
            ),
            ("q=quit   r=reset M4   c=calibrate this screen", (140, 140, 140)),
        ]
        _draw_panel(display, lines)
        _draw_gaze_map(display, state.get("sx"), state.get("sy"), state.get("on_screen"))

        # Big verdict bar
        h, w = display.shape[:2]
        cv2.rectangle(display, (0, h - 40), (w, h), color, -1)
        cv2.putText(
            display,
            f"{v}   p={prob_txt}",
            (12, h - 12),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )

        cv2.imshow(WIN_NAME, display)
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        if key == ord("c"):
            status = _run_screen_calibration(cap, scorer, screen_wh, t_origin)
            state["calibrated"] = bool(status.get("ok"))
            if not status.get("ok"):
                state["sx"] = None
                state["sy"] = None
                state["on_screen"] = None
            last_beat = 0.0
            continue
        if key == ord("r"):
            gaze_buf.clear()
            pose_buf.clear()
            lm_buf.clear()
            ml.clear_session(sid)
            scorer.reset()
            state.update(
                {
                    "verdict": "WAITING",
                    "prob": None,
                    "buf": 0,
                    "reason": "reset",
                }
            )
            print("[live] reset M4 buffer (screen map kept)")

    cap.release()
    cv2.destroyAllWindows()
    ml.clear_session(sid)
    print("[live] done")


if __name__ == "__main__":
    main()
