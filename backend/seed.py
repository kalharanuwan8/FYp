import bcrypt
from app import create_app
from app.extensions import db
from app.db_models import User, Student, Teacher, GuardianConsent, GradeLevel

def seed_database():
    app = create_app()
    with app.app_context():
        db.create_all()

        # Seed Grade Levels (Grade 1 to Grade 12)
        default_grades = [f"Grade {i}" for i in range(1, 13)]
        for g_name in default_grades:
            if not GradeLevel.query.filter_by(name=g_name).first():
                db.session.add(GradeLevel(name=g_name))
        print("Seeded Grade Levels (Grade 1 - 12)")

        # Seed Admin
        if not User.query.filter_by(email="admin@luma.com").first():
            admin = User(
                email="admin@luma.com",
                password=bcrypt.hashpw(b"Admin123!", bcrypt.gensalt()).decode("utf-8"),
                role="admin",
                first_name="Luma",
                last_name="Admin"
            )
            db.session.add(admin)
            print("Created Admin: admin@luma.com / Admin123!")

        # Seed Teacher
        if not User.query.filter_by(email="teacher@luma.com").first():
            teacher_user = User(
                email="teacher@luma.com",
                password=bcrypt.hashpw(b"Teacher123!", bcrypt.gensalt()).decode("utf-8"),
                role="teacher",
                first_name="Sarah",
                last_name="Jenkins"
            )
            db.session.add(teacher_user)
            db.session.flush()
            teacher = Teacher(user_id=teacher_user.id)
            db.session.add(teacher)
            print("Created Teacher: teacher@luma.com / Teacher123!")

        # Seed Student
        if not User.query.filter_by(email="student@luma.com").first():
            student_user = User(
                email="student@luma.com",
                password=bcrypt.hashpw(b"Student123!", bcrypt.gensalt()).decode("utf-8"),
                role="student",
                first_name="Alex",
                last_name="Smith"
            )
            db.session.add(student_user)
            db.session.flush()
            student = Student(user_id=student_user.id)
            db.session.add(student)
            db.session.flush()
            consent = GuardianConsent(
                student_id=student.id,
                guardian_name="Robert Smith",
                guardian_email="robert.smith@example.com",
                consent_given=True
            )
            db.session.add(consent)
            print("Created Student: student@luma.com / Student123!")

        db.session.commit()
        print("Database seeding completed successfully!")

if __name__ == "__main__":
    seed_database()
