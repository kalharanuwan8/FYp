"""
REPORT 9 Part 9 extras (live API):
  ST-14-rerun — fixed ui_preferences payload
  ST-18 — enabled tiers [] → no visual intervention on simulated trigger
  ST-19 — remediation >50% vs exactly 50% on a video-module quiz

Does not modify application code. Evidence under
evaluation/thesis_numbers/raw/report9_system/.
"""
from __future__ import annotations

import json
import os
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


def _req(method, path, token=None, body=None, timeout=60):
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
            return resp.status, parsed, ms
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        ms = (time.perf_counter() - t0) * 1000
        try:
            parsed = json.loads(raw) if raw else {"error": str(e)}
        except json.JSONDecodeError:
            parsed = {"error": raw or str(e)}
        return e.code, parsed, ms
    except Exception as e:
        ms = (time.perf_counter() - t0) * 1000
        return None, {"error": str(e)}, ms


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
    code, body, ms = _req("POST", "/api/auth/login", body={"email": email, "password": password})
    token = body.get("access_token") if isinstance(body, dict) else None
    return code, token, body, ms


def main():
    _, teacher_tok, _, _ = login(*TEACHER)
    _, student_tok, _, _ = login(*STUDENT)

    # ---- ST-14-rerun ----
    code_g, before, _ = _req("GET", "/api/student/profile", token=student_tok)
    before_prefs = (before.get("ui_preferences") or {}) if isinstance(before, dict) else {}
    want_theme = "sage"
    if before_prefs.get("theme") == "sage":
        want_theme = "calm-dark"
    patch = {"ui_preferences": {"theme": want_theme, "reduceMotion": True}}
    code_p, after_p, _ = _req("PATCH", "/api/student/profile", token=student_tok, body=patch)
    code_r, after_g, _ = _req("GET", "/api/student/profile", token=student_tok)
    after_prefs = (after_g.get("ui_preferences") or {}) if isinstance(after_g, dict) else {}
    theme_ok = (
        code_g == 200
        and code_p == 200
        and code_r == 200
        and after_prefs.get("theme") == want_theme
        and after_prefs.get("reduceMotion") is True
    )
    record(
        "ST-14-preferences-rerun",
        "no FR text yet",
        "GET/PATCH/GET profile with nested ui_preferences (PreferencesContext shape)",
        f"ui_preferences.theme={want_theme} and reduceMotion=true after reload",
        code_r,
        {"patch": patch, "before_prefs": before_prefs, "after_prefs": after_prefs, "patch_status": code_p},
        theme_ok,
        notes="Original ST-14 fail was test-defect top-level theme payload; see st-14-preferences-original-fail.json",
    )

    # ---- ST-18 empty tiers ----
    code_e, enr, _ = _req("GET", "/api/courses/my-enrollments", token=student_tok)
    enrollments = enr.get("enrollments") if isinstance(enr, dict) else []
    subject_id = enrollments[0]["id"] if enrollments else None
    module_id = None
    if subject_id:
        code_s, subj, _ = _req(f"GET", f"/api/courses/subjects/{subject_id}", token=student_tok)
        mods = (subj.get("modules") or []) if isinstance(subj, dict) else []
        # Prefer a module that has video (also used later); else first module
        for m in mods:
            contents = m.get("contents") or m.get("materials") or []
            if any(c.get("content_type") == "video" for c in contents):
                module_id = m["id"]
                break
        if module_id is None and mods:
            module_id = mods[0]["id"]

    # Teacher disables all visual tiers
    cfg_off = {
        "tier1_enabled": False,
        "tier2_enabled": False,
        "tier3_enabled": False,
        "tier4_enabled": False,
    }
    code_cfg, cfg_body, _ = _req(
        "PATCH",
        f"/api/courses/subjects/{subject_id}/intervention-config",
        token=teacher_tok,
        body=cfg_off,
    )
    enabled = cfg_body.get("enabled_tiers") if isinstance(cfg_body, dict) else None

    session_id = None
    triggers = []
    if code_cfg == 200 and enabled == [] and module_id:
        code_start, start_body, _ = _req(
            "POST",
            "/api/session/start",
            token=student_tok,
            body={"module_id": module_id, "is_monitored": True},
        )
        session_id = start_body.get("session_id") if isinstance(start_body, dict) else None
        if session_id:
            for tier in (1, 2, 3, 4):
                code_t, body_t, _ = _req(
                    "POST",
                    f"/api/session/{session_id}/trigger-intervention",
                    token=student_tok,
                    body={"tier": tier},
                )
                triggers.append(
                    {
                        "tier": tier,
                        "status": code_t,
                        "intervention_triggered": body_t.get("intervention_triggered")
                        if isinstance(body_t, dict)
                        else None,
                        "intervention": body_t.get("intervention") if isinstance(body_t, dict) else None,
                        "error": body_t.get("error") if isinstance(body_t, dict) else None,
                    }
                )
            _req("POST", f"/api/session/{session_id}/stop", token=student_tok, body={})

    # Restore tiers so demo subject is not left disabled
    code_on, cfg_on, _ = _req(
        "PATCH",
        f"/api/courses/subjects/{subject_id}/intervention-config",
        token=teacher_tok,
        body={
            "tier1_enabled": True,
            "tier2_enabled": True,
            "tier3_enabled": True,
            "tier4_enabled": True,
        },
    )

    no_visual = bool(triggers) and all(
        t["intervention_triggered"] is not True and t["intervention"] in (None, {}) for t in triggers
    )
    # Engine returns 409 when no enabled tier can fire
    statuses_ok = bool(triggers) and all(t["status"] in (409, 400) for t in triggers)
    st18_ok = (
        code_cfg == 200
        and enabled == []
        and session_id is not None
        and no_visual
        and statuses_ok
        and code_on == 200
    )
    record(
        "ST-18-empty-tiers-no-intervention",
        "no FR text yet",
        "teacher PATCH enabled_tiers=[]; new monitored session; trigger tiers 1–4 (simulated)",
        "config enabled_tiers=[]; each trigger has intervention_triggered false / no intervention payload",
        code_cfg,
        {
            "subject_id": subject_id,
            "module_id": module_id,
            "session_id": session_id,
            "config_after_disable": cfg_body,
            "triggers": triggers,
            "config_restored_status": code_on,
            "config_restored": cfg_on if isinstance(cfg_on, dict) else cfg_on,
        },
        st18_ok,
        notes="simulated triggers, not a person; tiers restored after case",
    )

    # ---- ST-19 remediation on video-module quiz ----
    # Single-attempt policy ⇒ two quizzes (gt50 and eq50).
    video_module_id = module_id
    stamp = datetime.now(timezone.utc).strftime("%H%M%S")
    two_q = [
        {
            "question_text": "R9 Q1",
            "question_type": "multiple_choice",
            "options": [
                {"option_text": "right", "is_correct": True},
                {"option_text": "wrong", "is_correct": False},
            ],
        },
        {
            "question_text": "R9 Q2",
            "question_type": "multiple_choice",
            "options": [
                {"option_text": "right", "is_correct": True},
                {"option_text": "wrong", "is_correct": False},
            ],
        },
    ]

    def _create_quiz(title_suffix):
        code, body, _ = _req(
            "POST",
            f"/api/courses/modules/{video_module_id}/quizzes",
            token=teacher_tok,
            body={"title": f"REPORT9 rem {title_suffix} {stamp}", "questions": two_q},
        )
        return code, body

    def _option_ids(q):
        opts = q.get("options") or []
        right = next((o["id"] for o in opts if o.get("is_correct")), None)
        wrong = next((o["id"] for o in opts if not o.get("is_correct")), None)
        return q["id"], right, wrong

    def _submit_pattern(quiz_body, use_wrong_both):
        quiz_id = quiz_body.get("id") if isinstance(quiz_body, dict) else None
        questions = quiz_body.get("questions") if isinstance(quiz_body, dict) else None
        if not quiz_id or not questions or len(questions) < 2:
            return {"error": "bad quiz", "quiz_id": quiz_id}
        q1_id, r1, w1 = _option_ids(questions[0])
        q2_id, r2, w2 = _option_ids(questions[1])
        answers = (
            [
                {"question_id": q1_id, "selected_option_id": w1},
                {"question_id": q2_id, "selected_option_id": w2},
            ]
            if use_wrong_both
            else [
                {"question_id": q1_id, "selected_option_id": r1},
                {"question_id": q2_id, "selected_option_id": w2},
            ]
        )
        code_a, att, _ = _req("POST", f"/api/courses/quizzes/{quiz_id}/attempts", token=student_tok)
        attempt_id = att.get("attempt_id") if isinstance(att, dict) else None
        code_s, sub, _ = _req(
            "POST",
            f"/api/courses/attempts/{attempt_id}/submit",
            token=student_tok,
            body={"answers": answers},
        )
        return {
            "quiz_id": quiz_id,
            "attempt_status": code_a,
            "submit_status": code_s,
            "correct_count": sub.get("correct_count") if isinstance(sub, dict) else None,
            "total_questions": sub.get("total_questions") if isinstance(sub, dict) else None,
            "score": sub.get("score") if isinstance(sub, dict) else None,
            "remediation": sub.get("remediation") if isinstance(sub, dict) else None,
            "submit_error": sub.get("error") if isinstance(sub, dict) else None,
        }

    code_gt, body_gt = _create_quiz("gt50")
    code_eq, body_eq = _create_quiz("eq50")
    gt50 = _submit_pattern(body_gt, use_wrong_both=True) if code_gt in (200, 201) else {"create_status": code_gt, "body": body_gt}
    eq50 = _submit_pattern(body_eq, use_wrong_both=False) if code_eq in (200, 201) else {"create_status": code_eq, "body": body_eq}

    gt_ok = (
        isinstance(gt50, dict)
        and gt50.get("submit_status") == 200
        and gt50.get("correct_count") == 0
        and gt50.get("total_questions") == 2
        and gt50.get("remediation") is not None
        and isinstance(gt50.get("remediation"), dict)
        and float(gt50["remediation"].get("error_rate", -1)) > 0.50
        and bool(gt50["remediation"].get("offers"))
    )
    eq_ok = (
        isinstance(eq50, dict)
        and eq50.get("submit_status") == 200
        and eq50.get("correct_count") == 1
        and eq50.get("total_questions") == 2
        and eq50.get("remediation") in (None, {})
    )
    record(
        "ST-19-remediation-error-rate-boundary",
        "no FR text yet",
        "two quizzes on video module (single-attempt policy); all-wrong vs 1/2 correct",
        ">50% wrong → remediation offer; exactly 50% → remediation null/absent",
        code_eq if code_eq is not None else code_gt,
        {
            "module_id": video_module_id,
            "gt50_create_status": code_gt,
            "eq50_create_status": code_eq,
            "gt50": gt50,
            "eq50": eq50,
            "prior_fail_note": "first Part9 attempt used one quiz; second attempt blocked by single-attempt policy (403)",
        },
        gt_ok and eq_ok,
        notes="threshold is strict greater-than 0.50; module must contain video; two quizzes required",
    )

    out = {
        "api": API,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "results": RESULTS,
        "pass": sum(1 for r in RESULTS if r["pass"]),
        "fail": sum(1 for r in RESULTS if not r["pass"]),
    }
    (EVIDENCE / "summary_part9.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps({"pass": out["pass"], "fail": out["fail"], "total": len(RESULTS)}, indent=2))


if __name__ == "__main__":
    main()
