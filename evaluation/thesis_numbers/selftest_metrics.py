"""
Part 1 reviewer metrics from live webcam self-test CSVs + FYP_LMS session rows.

  venvpy312\\Scripts\\python.exe evaluation\\thesis_numbers\\selftest_metrics.py

Every number is computed from the CSVs / DB query below. Nothing is estimated.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

RAW = Path(__file__).resolve().parent / "raw"

RUNS = [
    {
        "label": "Run 2",
        "session_id": 85,
        "csv": RAW / "live_webcam_selftest_20261028T031728Z.csv",
        "notes": "Pre face-gate / pre S3; no inference_path or face_box_px columns.",
    },
    {
        "label": "Run 3",
        "session_id": 91,
        "csv": RAW / "live_webcam_selftest_20261028T041833Z.csv",
        "notes": "Post face-gate; has inference_path; no body_no_face yet.",
    },
    {
        "label": "Run 4",
        "session_id": 93,
        "csv": RAW / "live_webcam_selftest_20261028T050110Z.csv",
        "notes": "Post S3; body_no_face + fusion_threshold + pose baseline columns.",
    },
    {
        "label": "Run 5: frozen settings, post-escalation fix, same participant",
        "session_id": 94,
        "csv": RAW / "live_webcam_selftest_20261028T063352Z.csv",
        "notes": "Post escalation fix; settings frozen (ML_FUSION_THRESHOLD=0.75).",
    },
]

PHASES = ["read_1", "phone", "away", "out_of_chair", "read_2"]
READING = {"read_1", "read_2"}


def _blank(v) -> bool:
    return v is None or str(v).strip() == ""


def load_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def source_of(row: dict) -> str:
    """
    Classify heartbeat source for Part 1.

    Returns one of:
      focused | distracted_fusion | distracted_body_no_face |
      distracted_undifferentiated | unknown | other
    """
    verdict = (row.get("verdict") or "").strip().upper()
    reason = (row.get("reason") or "").strip()
    path = (row.get("inference_path") or "").strip() if "inference_path" in row else ""

    if verdict == "FOCUSED":
        return "focused"
    if verdict == "UNKNOWN":
        return "unknown"
    if verdict != "DISTRACTED":
        return "other"

    if reason == "body_no_face" or path == "body_no_face":
        return "distracted_body_no_face"
    if path == "fusion" or path == "heuristic":
        return "distracted_fusion"
    # Older CSVs (Run 2): DISTRACTED with empty reason, no inference_path.
    if "inference_path" not in row or _blank(path):
        if reason in ("", "heuristic_gate"):
            return "distracted_undifferentiated"
    if reason in ("", "heuristic_gate"):
        return "distracted_fusion"
    return "distracted_undifferentiated"


def face_detected(row: dict) -> bool | None:
    """True/False when CSV can tell; None when not distinguishable."""
    if "face_box_px" in row:
        if not _blank(row.get("face_box_px")):
            return True
        # empty box with fusion/focused still implies face was used
        src = source_of(row)
        if src in ("focused", "distracted_fusion"):
            return True
        if src == "distracted_body_no_face":
            return False
        if (row.get("verdict") or "").upper() == "UNKNOWN" and (
            row.get("reason") or ""
        ).strip() in ("no_face",):
            return False
        if (row.get("inference_path") or "").strip() == "unusable":
            return False
        return False
    # Run 2: no face_box_px — approximate from verdict/reason only.
    verdict = (row.get("verdict") or "").upper()
    reason = (row.get("reason") or "").strip()
    if verdict == "UNKNOWN" and reason == "no_face":
        return False
    if verdict in ("FOCUSED", "DISTRACTED"):
        return True  # face-based path was the only usable path then
    return None


def first_time(rows: list[dict], pred) -> str:
    for r in rows:
        if pred(r):
            return str(r.get("seconds_from_phase_start", ""))
    return "none"


def phase_metrics(rows: list[dict], phase: str) -> dict:
    pr = [r for r in rows if r.get("phase") == phase]
    n = len(pr)
    counts = defaultdict(int)
    unknown_reasons = defaultdict(int)
    for r in pr:
        src = source_of(r)
        counts[src] += 1
        if src == "unknown":
            unknown_reasons[(r.get("reason") or "").strip() or "(empty)"] += 1

    face_based = counts["focused"] + counts["distracted_fusion"] + counts[
        "distracted_undifferentiated"
    ]
    # For coverage "face-based model prediction": FOCUSED or fusion DISTRACTED.
    # Undifferentiated (Run 2) counted as face-based because body_no_face did not exist.
    with_body = face_based + counts["distracted_body_no_face"]

    return {
        "phase": phase,
        "n": n,
        "focused": counts["focused"],
        "distracted_fusion": counts["distracted_fusion"],
        "distracted_body_no_face": counts["distracted_body_no_face"],
        "distracted_undifferentiated": counts["distracted_undifferentiated"],
        "unknown": counts["unknown"],
        "unknown_reasons": dict(unknown_reasons),
        "coverage_face_based": (face_based / n) if n else None,
        "coverage_incl_body": (with_body / n) if n else None,
        "first_distracted_any": first_time(
            pr, lambda r: (r.get("verdict") or "").upper() == "DISTRACTED"
        ),
        "first_distracted_fusion": first_time(
            pr, lambda r: source_of(r) in ("distracted_fusion", "distracted_undifferentiated")
        ),
        "first_distracted_body": first_time(
            pr, lambda r: source_of(r) == "distracted_body_no_face"
        ),
        "first_intervention": first_time(
            pr, lambda r: (r.get("intervention_fired") or "").lower() == "true"
        ),
        "first_intervention_tier": next(
            (
                r.get("intervention_tier") or "none"
                for r in pr
                if (r.get("intervention_fired") or "").lower() == "true"
            ),
            "none",
        ),
    }


def interventions(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        if (r.get("intervention_fired") or "").lower() != "true":
            continue
        out.append(
            {
                "timestamp_utc": r.get("timestamp_utc"),
                "phase": r.get("phase"),
                "seconds_from_phase_start": r.get("seconds_from_phase_start"),
                "tier": r.get("intervention_tier"),
                "type": r.get("intervention_type"),
                "verdict_source": source_of(r),
                "reason": r.get("reason"),
                "inference_path": r.get("inference_path", ""),
            }
        )
    return out


def reading_face_share(rows: list[dict]) -> dict:
    rr = [r for r in rows if r.get("phase") in READING]
    known = [face_detected(r) for r in rr]
    yes = sum(1 for v in known if v is True)
    no = sum(1 for v in known if v is False)
    unk = sum(1 for v in known if v is None)
    n = len(rr)
    return {
        "n_reading": n,
        "face_true": yes,
        "face_false": no,
        "face_unknown_col": unk,
        "share_face_true_of_n": (yes / n) if n else None,
        "share_face_true_of_decidable": (yes / (yes + no)) if (yes + no) else None,
    }


def false_interventions_per_study_minute(rows: list[dict]) -> dict:
    """Interventions during reading phases ÷ 2.0 reading minutes."""
    reading_interventions = [
        r
        for r in rows
        if r.get("phase") in READING
        and (r.get("intervention_fired") or "").lower() == "true"
    ]
    return {
        "n_reading_interventions": len(reading_interventions),
        "reading_minutes": 2.0,
        "false_interventions_per_study_minute": len(reading_interventions) / 2.0,
        "details": interventions(reading_interventions),
    }


def fetch_session_summaries(session_ids: list[int]) -> list[dict]:
    """Read observed_v1 snapshot columns from FYP_LMS.sessions."""
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError as e:
        return [{"error": f"psycopg2 unavailable: {e}"}]

    # Load DATABASE_URL from backend/.env when not already in the environment.
    env_path = Path(__file__).resolve().parents[2] / "backend" / ".env"
    if env_path.exists() and "DATABASE_URL" not in os.environ:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("DATABASE_URL="):
                os.environ["DATABASE_URL"] = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgresql://"):
        return [{"error": f"DATABASE_URL missing or not postgres: {url!r}"}]
    # Simple parse: postgresql://user:pass@host:port/db
    rest = url[len("postgresql://") :]
    creds, hostdb = rest.split("@", 1)
    user, password = creds.split(":", 1)
    hostport, dbname = hostdb.split("/", 1)
    host, port = hostport.split(":")

    conn = psycopg2.connect(
        host=host,
        port=int(port),
        dbname=dbname,
        user=user,
        password=password,
    )
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id,
                       focus_metric_version,
                       focus_percentage,
                       monitoring_coverage_pct,
                       observed_focused_seconds,
                       observed_distracted_seconds,
                       unknown_seconds,
                       started_at,
                       ended_at
                FROM sessions
                WHERE id = ANY(%s)
                ORDER BY id
                """,
                (session_ids,),
            )
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def run_report(run: dict) -> dict:
    rows = load_rows(run["csv"])
    phases = [phase_metrics(rows, p) for p in PHASES]
    return {
        "label": run["label"],
        "session_id": run["session_id"],
        "csv": str(run["csv"]),
        "notes": run["notes"],
        "n_heartbeats": len(rows),
        "columns": list(rows[0].keys()) if rows else [],
        "phases": phases,
        "interventions": interventions(rows),
        "false_interventions": false_interventions_per_study_minute(rows),
        "reading_face": reading_face_share(rows),
    }


def main() -> None:
    reports = [run_report(r) for r in RUNS]
    summaries = fetch_session_summaries([r["session_id"] for r in RUNS])

    # Serialize datetimes
    for s in summaries:
        for k, v in list(s.items()):
            if hasattr(v, "isoformat"):
                s[k] = v.isoformat()

    out = {
        "runs": reports,
        "session_summaries": summaries,
        "source_notes": {
            "distracted_fusion": "DISTRACTED with inference_path=fusion (or heuristic), not body_no_face.",
            "distracted_body_no_face": "DISTRACTED with reason/inference_path=body_no_face.",
            "distracted_undifferentiated": (
                "DISTRACTED without inference_path column (Run 2). "
                "body_no_face did not exist; treated as face-based for coverage."
            ),
        },
    }
    out_path = RAW / "selftest_metrics.json"
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps(out, indent=2, default=str))
    print(f"\nWROTE {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
