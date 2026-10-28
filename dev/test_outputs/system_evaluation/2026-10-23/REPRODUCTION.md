# Reproduction commands (Chapter 6 system evaluation)

## Environment
- Backend venv: venvpy312
- Working dir for harness: backend/
- Evidence root: dev/test_outputs/system_evaluation/2026-10-23/

## Seed demo browser fixture (idempotent)
`
cd backend
..\\venvpy312\\Scripts\\python.exe seed_phase2a_demo.py
`
Requires backend/uploads/phase2a_demo.mp4 (gitignored media).

## Evaluation harness (Flask testing app; isolated emails *@luma.demo)
`
cd backend
..\\venvpy312\\Scripts\\python.exe ..\\dev\\test_outputs\\system_evaluation\\2026-10-23\\run_system_evaluation.py
`

## Backend regression suite
`
cd backend
..\\venvpy312\\Scripts\\python.exe -m pytest -q --tb=line
`

## Live servers (browser demos)
`
# terminal 1
cd backend && ..\\venvpy312\\Scripts\\python.exe wsgi.py
# terminal 2
cd frontend && npm run dev
`
Browser: http://localhost:5173
Demo login (no password in report body): see seed_phase2a_demo.py console output only.

## Fixture identifiers
- Eval emails: eval.student@luma.demo, eval.teacher@luma.demo, eval.admin@luma.demo, eval.noconsent@luma.demo
- Course: Eval System Course / Eval Module
- Browser demo: Phase 2A Demo Course / Demo Video Lesson
- Coverage metric: observed_v1; T_support=3.0; heartbeat intervalMs=2000
