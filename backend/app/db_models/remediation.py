"""Post-quiz adaptive content re-delivery log."""

from datetime import datetime

from app.extensions import db


class RemediationEvent(db.Model):
    __tablename__ = "remediation_events"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    module_id = db.Column(db.Integer, db.ForeignKey("modules.id"), nullable=False)
    quiz_attempt_id = db.Column(
        db.Integer, db.ForeignKey("quiz_attempts.id"), nullable=False
    )
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=True)
    error_rate = db.Column(db.Float, nullable=False)
    focus_percentage = db.Column(db.Float, nullable=True)
    monitoring_coverage_pct = db.Column(db.Float, nullable=True)
    path = db.Column(db.String(32), nullable=False)  # different_format | guided_rewatch
    reason = db.Column(
        db.String(32), nullable=False
    )  # comprehension_likely | attention_likely | insufficient_monitoring
    content_shown = db.Column(db.JSON, nullable=True)
    student_choice = db.Column(db.String(32), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    choice_at = db.Column(db.DateTime, nullable=True)

    student = db.relationship("Student", backref="remediation_events")
    module = db.relationship("Module", backref="remediation_events")
    quiz_attempt = db.relationship("QuizAttempt", backref="remediation_events")

    def to_dict(self):
        return {
            "id": self.id,
            "student_id": self.student_id,
            "module_id": self.module_id,
            "quiz_attempt_id": self.quiz_attempt_id,
            "session_id": self.session_id,
            "error_rate": self.error_rate,
            "focus_percentage": self.focus_percentage,
            "monitoring_coverage_pct": self.monitoring_coverage_pct,
            "path": self.path,
            "reason": self.reason,
            "content_shown": self.content_shown,
            "student_choice": self.student_choice,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "choice_at": self.choice_at.isoformat() if self.choice_at else None,
        }
