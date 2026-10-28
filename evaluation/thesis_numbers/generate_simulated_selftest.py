"""
Deterministic SIMULATED protocol CSV for thesis tables.

This is NOT measured webcam data. Labels come from fixed rules matching the
live self-test phase keys/durations in live_webcam_selftest.py.

  venvpy312\\Scripts\\python.exe evaluation\\thesis_numbers\\generate_simulated_selftest.py

Output: evaluation/thesis_numbers/raw/simulated_selftest_protocol.csv
Every row has protocol=SIMULATED and measured=false.
"""
from __future__ import annotations

import csv
from pathlib import Path

INTERVAL_S = 2.0
OUT = Path(__file__).resolve().parent / "raw"
OUT.mkdir(parents=True, exist_ok=True)

# Same phase keys/durations as live_webcam_selftest.PHASES
PHASES = [
    ("read_1", 60, "READ NORMALLY — 60 s"),
    ("phone", 30, "PHONE — 30 s"),
    ("away", 30, "HEAD AWAY — 30 s"),
    ("out_of_chair", 30, "OUT OF THE CHAIR — 30 s"),
    ("read_2", 60, "READ NORMALLY AGAIN — 60 s"),
]

# Deterministic expected labels (path B).
EXPECTED = {
    "read_1": "FOCUSED",
    "phone": "DISTRACTED",
    "away": "DISTRACTED",
    "out_of_chair": "UNKNOWN",
    "read_2": "FOCUSED",
}


def expected_reason(verdict: str) -> str:
    if verdict == "FOCUSED":
        return "simulated_focused_reading"
    if verdict == "DISTRACTED":
        return "simulated_distracted"
    return "simulated_no_person"


def build_rows() -> list[dict]:
    rows: list[dict] = []
    for key, dur, _title in PHASES:
        verdict = EXPECTED[key]
        n = int(dur / INTERVAL_S)
        for i in range(n):
            elapsed = round(i * INTERVAL_S, 3)
            rows.append(
                {
                    "timestamp_utc": f"SIMULATED+{key}+{elapsed:06.1f}s",
                    "phase": key,
                    "seconds_from_phase_start": elapsed,
                    "verdict": verdict,
                    "confidence": (
                        ""
                        if verdict == "UNKNOWN"
                        else ("0.90" if verdict == "FOCUSED" else "0.88")
                    ),
                    "reason": expected_reason(verdict),
                    "ml_mode": "simulated",
                    "intervention_fired": "false",
                    "intervention_tier": "",
                    "intervention_type": "",
                    "http_status": "simulated",
                    "error": "",
                    "inference_path": "simulated",
                    "gaze_label": "center" if verdict == "FOCUSED" else "",
                    "head_pose_yaw": "",
                    "head_pose_pitch": "",
                    "head_pose_roll": "",
                    "distract_prob": (
                        ""
                        if verdict == "UNKNOWN"
                        else ("0.10" if verdict == "FOCUSED" else "0.90")
                    ),
                    "face_box_px": "",
                    "protocol": "SIMULATED",
                    "measured": "false",
                }
            )
    return rows


def summarise(rows: list[dict]) -> list[dict]:
    tables = []
    for key, _dur, title in PHASES:
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
                "seconds_to_first_distracted": first_time(
                    lambda r: r["verdict"] == "DISTRACTED"
                ),
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
    rows = build_rows()
    csv_path = OUT / "simulated_selftest_protocol.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("LABEL: SIMULATED protocol — not measured", flush=True)
    print(f"LOG: {csv_path}", flush=True)
    print(f"rows={len(rows)} protocol=SIMULATED measured=false", flush=True)
    for row in summarise(rows):
        print(row, flush=True)


if __name__ == "__main__":
    main()
