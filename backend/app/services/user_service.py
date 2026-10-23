import bcrypt
from app.extensions import db
from app.db_models import User, Student, Teacher, GuardianConsent

def create_user_from_data(data, created_by_id=None):
    """
    Atomic helper to create a User and its associated role profile (Teacher/Student + GuardianConsent).
    Accepts either a validated RegisterSchema instance (e.g. from /register) or a dict of user attributes (from /bulk-import).
    Does NOT call db.session.commit() so callers can manage single or per-row transactions.
    Returns the newly created User model instance.
    """
    if hasattr(data, "model_dump"):
        payload = data.model_dump()
    elif isinstance(data, dict):
        payload = data
    else:
        payload = vars(data)

    email = payload.get("email")
    password = payload.get("password")
    role = payload.get("role")
    first_name = payload.get("first_name")
    last_name = payload.get("last_name")
    grade_level = payload.get("grade_level")
    guardian_name = payload.get("guardian_name")
    guardian_email = payload.get("guardian_email")

    hashed_pw = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    new_user = User(
        email=email,
        password=hashed_pw,
        role=role,
        first_name=first_name,
        last_name=last_name,
        created_by=created_by_id
    )
    db.session.add(new_user)
    db.session.flush()

    if role == "teacher":
        new_teacher = Teacher(user_id=new_user.id)
        db.session.add(new_teacher)

    elif role == "student":
        new_student = Student(user_id=new_user.id, grade_level=grade_level or None)
        db.session.add(new_student)
        db.session.flush()

        new_consent = GuardianConsent(
            student_id=new_student.id,
            guardian_name=guardian_name,
            guardian_email=str(guardian_email) if guardian_email else None,
            consent_given=False
        )
        db.session.add(new_consent)

    return new_user
