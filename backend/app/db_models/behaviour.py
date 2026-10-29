"""Behavioural (non-camera) observation events for DSM-5 inattention proxies."""

from datetime import datetime

from app.extensions import db


class BehaviourEvent(db.Model):
    """
    Record-only behavioural episode (currently DSM-1 idle on quiz/document).

    Camera distraction and noise notices stay on DistractionEvent / InterventionLog.
    """

    __tablename__ = "behaviour_events"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False, index=True)
    indicator = db.Column(db.String(32), nullable=False, default="idle")
    context = db.Column(db.String(32), nullable=False)  # quiz | document
    quiz_attempt_id = db.Column(db.Integer, db.ForeignKey("quiz_attempts.id"), nullable=True)
    module_content_id = db.Column(db.Integer, db.ForeignKey("module_contents.id"), nullable=True)
    started_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    duration_seconds = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    student = db.relationship("Student", backref="behaviour_events")

    def to_dict(self):
        return {
            "id": self.id,
            "student_id": self.student_id,
            "indicator": self.indicator,
            "context": self.context,
            "quiz_attempt_id": self.quiz_attempt_id,
            "module_content_id": self.module_content_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "duration_seconds": self.duration_seconds,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
