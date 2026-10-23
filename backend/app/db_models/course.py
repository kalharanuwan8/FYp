from datetime import datetime
from app.extensions import db

class GradeLevel(db.Model):
    __tablename__ = "grade_levels"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name
        }


class Subject(db.Model):
    __tablename__ = "subjects"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    grade_level_id = db.Column(db.Integer, db.ForeignKey("grade_levels.id"), nullable=False)
    is_archived = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    grade_level = db.relationship("GradeLevel", backref="subjects")
    teacher_subjects = db.relationship("TeacherSubject", back_populates="subject", cascade="all, delete-orphan")
    modules = db.relationship("Module", back_populates="subject", cascade="all, delete-orphan", order_by="Module.sequence_order")

    def to_dict(self, include_modules=False):
        data = {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "grade_level_id": self.grade_level_id,
            "grade_level_name": self.grade_level.name if self.grade_level else None,
            "is_archived": self.is_archived,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_modules:
            data["modules"] = [m.to_dict(include_contents=True) for m in self.modules if not m.is_archived]
        return data


class TeacherSubject(db.Model):
    __tablename__ = "teacher_subjects"

    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("teachers.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    teacher = db.relationship("Teacher", back_populates="subjects")
    subject = db.relationship("Subject", back_populates="teacher_subjects")

    def to_dict(self):
        return {
            "id": self.id,
            "teacher_id": self.teacher_id,
            "subject_id": self.subject_id,
            "assigned_at": self.assigned_at.isoformat() if self.assigned_at else None
        }


class Module(db.Model):
    __tablename__ = "modules"

    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    sequence_order = db.Column(db.Integer, nullable=False, default=1)
    is_archived = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    subject = db.relationship("Subject", back_populates="modules")
    contents = db.relationship("ModuleContent", back_populates="module", cascade="all, delete-orphan")
    quizzes = db.relationship("Quiz", back_populates="module", cascade="all, delete-orphan")

    def to_dict(self, include_contents=False):
        data = {
            "id": self.id,
            "subject_id": self.subject_id,
            "title": self.title,
            "description": self.description,
            "sequence_order": self.sequence_order,
            "is_archived": self.is_archived,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_contents:
            data["contents"] = [c.to_dict(include_milestones=True) for c in self.contents]
        return data


class ModuleContent(db.Model):
    __tablename__ = "module_contents"

    id = db.Column(db.Integer, primary_key=True)
    module_id = db.Column(db.Integer, db.ForeignKey("modules.id"), nullable=False)
    content_type = db.Column(db.String(8), nullable=False)  # 'video', 'document', 'quiz', 'other'
    title = db.Column(db.String(150), nullable=False)
    file_url = db.Column(db.String(500), nullable=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey("quizzes.id"), nullable=True)
    summary = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    module = db.relationship("Module", back_populates="contents")
    quiz = db.relationship("Quiz", back_populates="module_contents")
    milestone_items = db.relationship(
        "ModuleMilestoneItem",
        back_populates="module_content",
        cascade="all, delete-orphan",
        order_by="ModuleMilestoneItem.sequence_order",
    )

    def to_dict(self, include_milestones=False):
        data = {
            "id": self.id,
            "module_id": self.module_id,
            "content_type": self.content_type,
            "title": self.title,
            "file_url": self.file_url,
            "quiz_id": self.quiz_id,
            "summary": self.summary,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_milestones:
            data["milestones"] = [
                m.to_dict() for m in self.milestone_items if m.is_active
            ]
        return data


class ModuleMilestoneItem(db.Model):
    """Teacher-approved milestone quiz item for a learning material."""
    __tablename__ = "module_milestone_items"

    id = db.Column(db.Integer, primary_key=True)
    module_content_id = db.Column(
        db.Integer, db.ForeignKey("module_contents.id"), nullable=False
    )
    question = db.Column(db.Text, nullable=False)
    options_json = db.Column(db.JSON, nullable=False, default=list)
    correct_option = db.Column(db.Integer, nullable=False, default=0)
    hint_text = db.Column(db.Text, nullable=True)
    sequence_order = db.Column(db.Integer, nullable=False, default=1)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    module_content = db.relationship("ModuleContent", back_populates="milestone_items")

    def to_dict(self):
        return {
            "id": self.id,
            "module_content_id": self.module_content_id,
            "question": self.question,
            "options": self.options_json or [],
            "correct_option": self.correct_option,
            "hint_text": self.hint_text,
            "sequence_order": self.sequence_order,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Enrollment(db.Model):
    __tablename__ = "enrollments"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=False)
    enrolled_at = db.Column(db.DateTime, default=datetime.utcnow)

    student = db.relationship("Student", back_populates="enrollments")
    subject = db.relationship("Subject", backref="enrollments")
