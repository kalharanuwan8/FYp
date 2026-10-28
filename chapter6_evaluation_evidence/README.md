# Chapter 6 evaluation evidence

Staging folder for thesis insertion. Contains the corrected system evaluation report and supporting artifacts from the 2026-10-23 run. No passwords, tokens, or raw camera media.

**Corrected report:** [SYSTEM_EVALUATION_REPORT.md](SYSTEM_EVALUATION_REPORT.md)  
(Canonical working copy in the repo: `dev/SYSTEM_EVALUATION_REPORT.md`.)

## Contents

| File / folder | Description |
|---------------|-------------|
| `SYSTEM_EVALUATION_REPORT.md` | Corrected Chapter 6 system evaluation report |
| `evaluated_configuration.json` | Evaluated build / config snapshot |
| `evaluation_results_run1.json` | Harness results — Run 1 |
| `evaluation_results_run2.json` | Harness results — Run 2 (from `logs/evaluation_results.json`) |
| `backend_pytest.txt` | Backend pytest log from the evaluation window |
| `analytics_fixtures.json` | Analytics fixture metadata used in the run |
| `heartbeat_rtt.csv` | Flask test-client heartbeat request-processing timings |
| `intervention_display_timing.csv` | Browser DemoPanel intervention display timings |
| `run_system_evaluation.py` | Evaluation harness script used for the run |
| `screenshots/` | BR-* UI screenshots (dashboard, player, analytics) |
| `api_samples/` | Saved HTTP response samples cited in the report |

Source tree: `dev/test_outputs/system_evaluation/2026-10-23/`.
