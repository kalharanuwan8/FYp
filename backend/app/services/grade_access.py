"""Match a student's current grade to the subjects they are allowed to see."""

from app.db_models import GradeLevel


def grade_level_for_student(student):
    """Resolve the GradeLevel row for a student, ignoring case and extra spaces."""
    if student is None:
        return None
    name = (getattr(student, "grade_level", None) or "").strip()
    if not name:
        return None
    exact = GradeLevel.query.filter_by(name=name).first()
    if exact:
        return exact
    return GradeLevel.query.filter(GradeLevel.name.ilike(name)).first()


def subject_visible_to_student(student, subject) -> bool:
    """True only when the subject is active and belongs to the student's grade."""
    if subject is None or getattr(subject, "is_archived", False):
        return False
    grade = grade_level_for_student(student)
    if grade is None:
        return False
    return subject.grade_level_id == grade.id
