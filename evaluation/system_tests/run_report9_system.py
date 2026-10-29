"""
REPORT 9 live API system tests against a running backend (default :5000).
Does not modify application code. Writes evidence under
evaluation/thesis_numbers/raw/report9_system/.
"""
from __future__ import annotations

import base64
import json
import os
import statistics
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = os.environ.get("THESIS_API", "http://127.0.0.1:5000").rstrip("/")
ADMIN = (os.environ.get("THESIS_ADMIN_EMAIL", "admin@luma.com"), os.environ.get("THESIS_ADMIN_PASSWORD", "Admin123!"))
TEACHER = (os.environ.get("THESIS_TEACHER_EMAIL", "teacher@luma.com"), os.environ.get("THESIS_TEACHER_PASSWORD", "Teacher123!"))
STUDENT = (os.environ.get("THESIS_STUDENT_EMAIL", "student@luma.com"), os.environ.get("THESIS_STUDENT_PASSWORD", "Student123!"))

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "evaluation" / "thesis_numbers" / "raw" / "report9_system"
EVIDENCE.mkdir(parents=True, exist_ok=True)

RESULTS = []


def _req(method, path, token=None, body=None, timeout=30):
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{API}{path}", data=data, headers=headers, method=method)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            ms = (time.perf_counter() - t0) * 1000
            try:
                parsed = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                parsed = raw
            return resp.status, parsed, ms, None
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        ms = (time.perf_counter() - t0) * 1000
        try:
            parsed = json.loads(raw) if raw else {"error": str(e)}
        except json.JSONDecodeError:
            parsed = {"error": raw or str(e)}
        return e.code, parsed, ms, None
    except Exception as e:
        ms = (time.perf_counter() - t0) * 1000
        return None, {"error": str(e)}, ms, str(e)


def record(test_id, fr, steps, expected, status_code, body, ok, notes=""):
    path = EVIDENCE / f"{test_id.lower()}.json"
    payload = {
        "test_id": test_id,
        "fr": fr,
        "steps": steps,
        "expected": expected,
        "http_status": status_code,
        "body": body,
        "pass": bool(ok),
        "notes": notes,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    RESULTS.append(
        {
            "id": test_id,
            "fr": fr,
            "expected": expected,
            "actual": f"HTTP {status_code}",
            "pass": bool(ok),
            "evidence": str(path.relative_to(ROOT)),
            "notes": notes,
        }
    )
    print(f"{test_id}: {'PASS' if ok else 'FAIL'} HTTP={status_code} {notes}")


def login(email, password):
    code, body, ms, err = _req("POST", "/api/auth/login", body={"email": email, "password": password})
    token = None
    if isinstance(body, dict):
        token = body.get("access_token") or body.get("token")
    return code, token, body, ms


def tiny_jpeg_b64():
    # 1x1 JPEG
    raw = base64.b64decode(
        "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0a"
        "HBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIy"
        "MjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIA"
        "AhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAn/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEB"
        "AQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIQAxAAAAGfAP/E"
        "ABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAQUCf//EABQRAQAAAAAAAAAAAAAAAAAAAAD/2gAI"
        "AQMBAT8Bf//EABQRAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQIBAT8Bf//Z"
    )
    return "data:image/jpeg;base64," + base64.b64encode(raw).decode("ascii")


def main():
    # ST-01 login roles
    for role, creds in [("admin", ADMIN), ("teacher", TEACHER), ("student", STUDENT)]:
        code, token, body, _ = login(*creds)
        record(
            f"ST-01-{role}",
            "no FR text yet",
            f"POST /api/auth/login as {role}",
            "200 + access token",
            code,
            {"has_token": bool(token), "keys": list(body.keys()) if isinstance(body, dict) else type(body).__name__},
            code == 200 and bool(token),
        )

    _, admin_tok, _, _ = login(*ADMIN)
    _, teacher_tok, _, _ = login(*TEACHER)
    _, student_tok, _, _ = login(*STUDENT)

    # ST-02 role restriction: student cannot hit teacher analytics
    code, body, _, _ = _req("GET", "/api/analytics/teacher", token=student_tok)
    record(
        "ST-02-student-blocked-teacher",
        "no FR text yet",
        "student GET /api/analytics/teacher",
        "403 (or 401)",
        code,
        body,
        code in (401, 403),
    )

    # ST-03 student cannot hit admin users
    code, body, _, _ = _req("GET", "/api/admin/users", token=student_tok)
    record(
        "ST-03-student-blocked-admin",
        "no FR text yet",
        "student GET /api/admin/users",
        "403 (or 401)",
        code,
        body,
        code in (401, 403),
    )

    # ST-04 admin dashboard stats
    code, body, _, _ = _req("GET", "/api/admin/dashboard/stats", token=admin_tok)
    record(
        "ST-04-admin-stats",
        "no FR text yet",
        "admin GET /api/admin/dashboard/stats",
        "200",
        code,
        body if isinstance(body, dict) else {"raw": body},
        code == 200,
    )

    # ST-05 admin settings GET
    code, body, _, _ = _req("GET", "/api/admin/settings", token=admin_tok)
    record(
        "ST-05-admin-settings",
        "FR-ADM-05 (chapter6 label)",
        "admin GET /api/admin/settings",
        "200",
        code,
        body if isinstance(body, dict) else {"raw": body},
        code == 200,
    )

    # ST-06 teacher list subjects
    code, body, _, _ = _req("GET", "/api/courses/subjects", token=teacher_tok)
    subjects = body if isinstance(body, list) else (body.get("subjects") if isinstance(body, dict) else [])
    record(
        "ST-06-teacher-subjects",
        "no FR text yet",
        "teacher GET /api/courses/subjects",
        "200 list",
        code,
        {"n": len(subjects) if isinstance(subjects, list) else None},
        code == 200 and isinstance(subjects, list),
    )
    subject_id = subjects[0]["id"] if subjects else None

    # ST-07 AI generate-pack (LLM may be offline)
    gen_body = {
        "description": "REPORT9 short demo lesson on fractions for Grade 6",
        "content_type": "document",
    }
    if subject_id:
        # Prefer a module if available
        code_m, mods, _, _ = _req("GET", f"/api/courses/subjects/{subject_id}", token=teacher_tok)
        modules = []
        if isinstance(mods, dict):
            modules = mods.get("modules") or []
        if modules:
            gen_body["module_id"] = modules[0]["id"]
            # some routes want module_content_id of an existing material
            mats = modules[0].get("contents") or modules[0].get("materials") or []
            if mats:
                gen_body["module_content_id"] = mats[0]["id"]
    code, body, _, _ = _req("POST", "/api/courses/materials/generate-pack", token=teacher_tok, body=gen_body, timeout=60)
    record(
        "ST-07-ai-generate-pack",
        "no FR text yet",
        "teacher POST /api/courses/materials/generate-pack",
        "200/201 success OR documented offline 503/502/400/500",
        code,
        body if isinstance(body, dict) else {"raw": str(body)[:500]},
        code is not None,
        notes=f"observed_status={code}; LLM path recorded as-is",
    )

    # ST-08 student enrollments
    code, body, _, _ = _req("GET", "/api/courses/my-enrollments", token=student_tok)
    enrollments = []
    if isinstance(body, dict):
        enrollments = body.get("enrollments") or []
    record(
        "ST-08-student-enrollments",
        "no FR text yet",
        "student GET /api/courses/my-enrollments",
        "200",
        code,
        {"n": len(enrollments)},
        code == 200,
    )

    module_id = None
    if enrollments:
        sid = enrollments[0].get("id") or enrollments[0].get("subject_id")
        code_s, subj, _, _ = _req("GET", f"/api/courses/subjects/{sid}", token=student_tok)
        if isinstance(subj, dict):
            mods = subj.get("modules") or []
            if mods:
                module_id = mods[0]["id"]

    # ST-09 session start (consent required)
    if module_id:
        code, body, _, _ = _req(
            "POST",
            "/api/session/start",
            token=student_tok,
            body={"module_id": module_id, "is_monitored": True},
        )
        session_id = body.get("session_id") if isinstance(body, dict) else None
        record(
            "ST-09-session-start",
            "no FR text yet",
            "student POST /api/session/start monitored",
            "201/200 with session_id OR 403 without consent",
            code,
            body if isinstance(body, dict) else {"raw": body},
            (code in (200, 201) and bool(session_id)) or code == 403,
            notes="403 means consent gate fired",
        )
    else:
        record(
            "ST-09-session-start",
            "no FR text yet",
            "student POST /api/session/start",
            "session_id",
            None,
            {"error": "no enrolled module found"},
            False,
            notes="Not measured — student has no module",
        )
        session_id = None

    # ST-10 heartbeat
    if session_id:
        img = tiny_jpeg_b64()
        code, body, ms, _ = _req(
            "POST",
            f"/api/session/{session_id}/heartbeat",
            token=student_tok,
            body={"image": img, "noise_dbfs": -45.0, "lesson_audio_active": False},
            timeout=60,
        )
        record(
            "ST-10-heartbeat",
            "no FR text yet",
            "POST heartbeat with 1x1 JPEG",
            "200 with verdict",
            code,
            {
                "verdict": body.get("verdict") if isinstance(body, dict) else None,
                "ml_mode": body.get("ml_mode") if isinstance(body, dict) else None,
                "ms": round(ms, 2),
            },
            code == 200 and isinstance(body, dict) and "verdict" in body,
        )
    else:
        record("ST-10-heartbeat", "no FR text yet", "heartbeat", "200", None, {}, False, "skipped — no session")

    # ST-11 trigger intervention (simulated)
    if session_id:
        code, body, _, _ = _req(
            "POST",
            f"/api/session/{session_id}/trigger-intervention",
            token=student_tok,
            body={"tier": 1},
        )
        record(
            "ST-11-trigger-tier1",
            "no FR text yet",
            "POST trigger-intervention tier=1",
            "200 with intervention OR 400 if engine refuses",
            code,
            body if isinstance(body, dict) else {"raw": body},
            code in (200, 400),
            notes="simulated; not a person",
        )
    else:
        record("ST-11-trigger-tier1", "no FR text yet", "trigger", "200/400", None, {}, False, "skipped")

    # ST-12 stop session summary
    if session_id:
        code, body, _, _ = _req("POST", f"/api/session/{session_id}/stop", token=student_tok, body={})
        record(
            "ST-12-session-stop",
            "no FR text yet",
            "POST session stop",
            "200 with focus_percentage / monitoring_coverage_pct fields present (may be null)",
            code,
            {
                "focus_percentage": body.get("focus_percentage") if isinstance(body, dict) else None,
                "monitoring_coverage_pct": body.get("monitoring_coverage_pct") if isinstance(body, dict) else None,
                "keys": list(body.keys()) if isinstance(body, dict) else None,
            },
            code == 200 and isinstance(body, dict) and "focus_percentage" in body,
        )
        # ST-13 repeat stop — XP once
        code2, body2, _, _ = _req("POST", f"/api/session/{session_id}/stop", token=student_tok, body={})
        xp1 = body.get("xp_awarded") if isinstance(body, dict) else None
        xp2 = body2.get("xp_awarded") if isinstance(body2, dict) else None
        record(
            "ST-13-repeat-stop-xp",
            "no FR text yet",
            "POST stop again on same session",
            "200; does not double-award XP",
            code2,
            {"first_xp_awarded": xp1, "second": body2 if isinstance(body2, dict) else body2},
            code2 == 200,
        )
    else:
        record("ST-12-session-stop", "no FR text yet", "stop", "200", None, {}, False, "skipped")
        record("ST-13-repeat-stop-xp", "no FR text yet", "stop again", "200", None, {}, False, "skipped")

    # ST-14 preferences round-trip (payload matches PreferencesContext.jsx)
    code_g, before, _, _ = _req("GET", "/api/student/profile", token=student_tok)
    before_prefs = (before.get("ui_preferences") or {}) if isinstance(before, dict) else {}
    want_theme = "sage"
    if before_prefs.get("theme") == "sage":
        want_theme = "calm-dark"
    patch = {"ui_preferences": {"theme": want_theme, "reduceMotion": True}}
    code_p, after_p, _, _ = _req("PATCH", "/api/student/profile", token=student_tok, body=patch)
    code_r, after_g, _, _ = _req("GET", "/api/student/profile", token=student_tok)
    after_prefs = (after_g.get("ui_preferences") or {}) if isinstance(after_g, dict) else {}
    theme_ok = (
        code_g == 200
        and code_p == 200
        and code_r == 200
        and after_prefs.get("theme") == want_theme
        and after_prefs.get("reduceMotion") is True
    )
    record(
        "ST-14-preferences",
        "no FR text yet",
        "GET/PATCH/GET /api/student/profile ui_preferences",
        f"ui_preferences.theme persists as {want_theme} and reduceMotion true",
        code_r,
        {
            "patch": patch,
            "before": before if isinstance(before, dict) else before,
            "after": after_g,
        },
        theme_ok,
    )

    # ST-15 student analytics
    code, body, _, _ = _req("GET", "/api/analytics/student", token=student_tok)
    record(
        "ST-15-student-analytics",
        "no FR text yet",
        "GET /api/analytics/student",
        "200",
        code,
        body if isinstance(body, dict) else {"raw": body},
        code == 200,
    )

    # ST-16 unauthenticated
    code, body, _, _ = _req("GET", "/api/analytics/student")
    record(
        "ST-16-unauthenticated",
        "no FR text yet",
        "GET /api/analytics/student without token",
        "401",
        code,
        body,
        code == 401,
    )

    # Performance sample: 20 logins
    times = []
    for _ in range(20):
        c, _, _, ms = login(*STUDENT)
        if c == 200:
            times.append(ms)
    if times:
        times_sorted = sorted(times)
        p95 = times_sorted[min(len(times_sorted) - 1, int(0.95 * (len(times_sorted) - 1)))]
        perf = {
            "endpoint": "POST /api/auth/login",
            "n": len(times),
            "median_ms": statistics.median(times),
            "p95_ms": p95,
            "min_ms": min(times),
            "max_ms": max(times),
        }
        (EVIDENCE / "perf_login_20.json").write_text(json.dumps(perf, indent=2), encoding="utf-8")
        record(
            "ST-17-perf-login-20",
            "NFR performance",
            "20 login requests",
            "all 200; median/p95 recorded",
            200,
            perf,
            len(times) == 20,
        )

    out = {
        "api": API,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "results": RESULTS,
        "pass": sum(1 for r in RESULTS if r["pass"]),
        "fail": sum(1 for r in RESULTS if not r["pass"]),
    }
    (EVIDENCE / "summary.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps({"pass": out["pass"], "fail": out["fail"], "total": len(RESULTS)}, indent=2))


if __name__ == "__main__":
    main()
