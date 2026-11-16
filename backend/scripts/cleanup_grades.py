"""
Normalise grade levels to exactly "Grade 1" .. "Grade 12".

  * ensures Grade 1-12 exist
  * reassigns subjects and students on any other grade to "Grade 1"
  * deletes the other grade rows

Dry-run by default (nothing is written); pass --apply to commit.

Run from the backend directory with the project's Python 3.12 venv:
    ..\\venvpy312\\Scripts\\python.exe scripts\\cleanup_grades.py            # dry run
    ..\\venvpy312\\Scripts\\python.exe scripts\\cleanup_grades.py --apply
"""

import argparse
import os
import sys

# Allow `python scripts/cleanup_grades.py` from the backend directory.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app  # noqa: E402
from app.db_models import GradeLevel, Student, Subject  # noqa: E402
from app.extensions import db  # noqa: E402

VALID_NAMES = [f"Grade {i}" for i in range(1, 13)]
FALLBACK_NAME = "Grade 1"


def cleanup_grades(apply: bool) -> dict:
    report = {
        "created": [],
        "subjects_reassigned": 0,
        "students_reassigned": 0,
        "deleted": [],
    }

    existing = {gl.name: gl for gl in GradeLevel.query.all()}
    for name in VALID_NAMES:
        if name not in existing:
            gl = GradeLevel(name=name)
            db.session.add(gl)
            existing[name] = gl
            report["created"].append(name)
    db.session.flush()  # assign ids to new rows (rolled back on dry-run)

    fallback = existing[FALLBACK_NAME]
    stray = [gl for name, gl in existing.items() if name not in VALID_NAMES]
    stray_ids = [gl.id for gl in stray]
    stray_names = [gl.name for gl in stray]

    if stray_ids:
        subjects = Subject.query.filter(Subject.grade_level_id.in_(stray_ids)).all()
        for subject in subjects:
            subject.grade_level_id = fallback.id
        report["subjects_reassigned"] = len(subjects)

    if stray_names:
        students = Student.query.filter(Student.grade_level.in_(stray_names)).all()
        for student in students:
            student.grade_level = FALLBACK_NAME
        report["students_reassigned"] = len(students)

    for gl in stray:
        db.session.delete(gl)
        report["deleted"].append(gl.name)

    if apply:
        db.session.commit()
    else:
        db.session.rollback()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Show what would change (default)")
    mode.add_argument("--apply", action="store_true", help="Write the changes to the database")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        report = cleanup_grades(apply=bool(args.apply))

    label = "APPLIED" if args.apply else "DRY RUN (no changes written; use --apply)"
    print(f"[cleanup_grades] {label}")
    print(f"  grades created      : {report['created'] or 'none'}")
    print(f"  subjects reassigned : {report['subjects_reassigned']} -> {FALLBACK_NAME}")
    print(f"  students reassigned : {report['students_reassigned']} -> {FALLBACK_NAME}")
    print(f"  grades deleted      : {report['deleted'] or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
