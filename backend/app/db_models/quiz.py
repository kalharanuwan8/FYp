from datetime import datetime
from app.extensions import db

# Design Note:
# A quiz is linked to a module both directly via `Quiz.module_id` and indirectly via 
# `ModuleContent.quiz_id` (where module_contents has content_type='quiz').
# Application code should ensure both linkages remain consistent on creation.

class Quiz(db.Model):
    __tablename__ = "quizzes"

    id = db.Column(db.Integer, primary_key=True)
    module_id = db.Column(db.Integer, db.ForeignKey("modules.id"), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    module = db.relationship("Module", back_populates="quizzes")
    module_contents = db.relationship("ModuleContent", back_populates="quiz")
    questions = db.relationship("QuizQuestion", back_populates="quiz", cascade="all, delete-orphan", order_by="QuizQuestion.sequence_order")
    attempts = db.relationship("QuizAttempt", back_populates="quiz", cascade="all, delete-orphan")

    def to_dict(self, include_questions=False):
        data = {
            "id": self.id,
            "module_id": self.module_id,
            "title": self.title,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_questions:
            data["questions"] = [q.to_dict(include_options=True) for q in self.questions]
        return data


class QuizQuestion(db.Model):
    __tablename__ = "quiz_questions"

    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey("quizzes.id"), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    question_type = db.Column(db.String(15), nullable=False)  # 'multiple_choice', 'short_answer'
    correct_answer_text = db.Column(db.String(500), nullable=True)
    sequence_order = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    quiz = db.relationship("Quiz", back_populates="questions")
    options = db.relationship("QuizQuestionOption", back_populates="question", cascade="all, delete-orphan")

    def to_dict(self, include_options=False):
        data = {
            "id": self.id,
            "quiz_id": self.quiz_id,
            "question_text": self.question_text,
            "question_type": self.question_type,
            "correct_answer_text": self.correct_answer_text,
            "sequence_order": self.sequence_order,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_options:
            data["options"] = [opt.to_dict() for opt in self.options]
        return data


class QuizQuestionOption(db.Model):
    __tablename__ = "quiz_question_options"

    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey("quiz_questions.id"), nullable=False)
    option_text = db.Column(db.String(500), nullable=False)
    is_correct = db.Column(db.Boolean, default=False, nullable=False)

    # Relationships
    question = db.relationship("QuizQuestion", back_populates="options")

    def to_dict(self):
        return {
            "id": self.id,
            "question_id": self.question_id,
            "option_text": self.option_text,
            "is_correct": self.is_correct
        }


class QuizAttempt(db.Model):
    __tablename__ = "quiz_attempts"

    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey("quizzes.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=True)  # Telemetry session FK
    score = db.Column(db.Float, nullable=True)
    started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    completed_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    quiz = db.relationship("Quiz", back_populates="attempts")
    student = db.relationship("Student", backref="quiz_attempts")
    answers = db.relationship("QuizAnswer", back_populates="attempt", cascade="all, delete-orphan")

    def to_dict(self, include_answers=False):
        data = {
            "id": self.id,
            "quiz_id": self.quiz_id,
            "student_id": self.student_id,
            "session_id": self.session_id,
            "score": self.score,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
        if include_answers:
            data["answers"] = [ans.to_dict() for ans in self.answers]
        return data


class QuizAnswer(db.Model):
    __tablename__ = "quiz_answers"

    id = db.Column(db.Integer, primary_key=True)
    attempt_id = db.Column(db.Integer, db.ForeignKey("quiz_attempts.id"), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey("quiz_questions.id"), nullable=False)
    selected_option_id = db.Column(db.Integer, db.ForeignKey("quiz_question_options.id"), nullable=True)
    answer_text = db.Column(db.Text, nullable=True)
    is_correct = db.Column(db.Boolean, default=False, nullable=False)
    answered_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    attempt = db.relationship("QuizAttempt", back_populates="answers")
    question = db.relationship("QuizQuestion")
    selected_option = db.relationship("QuizQuestionOption")

    def to_dict(self):
        return {
            "id": self.id,
            "attempt_id": self.attempt_id,
            "question_id": self.question_id,
            "selected_option_id": self.selected_option_id,
            "answer_text": self.answer_text,
            "is_correct": self.is_correct,
            "answered_at": self.answered_at.isoformat() if self.answered_at else None
        }
