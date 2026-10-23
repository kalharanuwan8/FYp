from datetime import datetime
from app.extensions import db


class LearningSession(db.Model):
    __tablename__ = "sessions"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    # Physical column kept as module_content_id for existing SQLite DBs; value is Module.id.
    module_id = db.Column(
        "module_content_id",
        db.Integer,
        db.ForeignKey("modules.id"),
        nullable=False,
    )
    start_time = db.Column("started_at", db.DateTime, default=datetime.utcnow, nullable=False)
    end_time = db.Column("ended_at", db.DateTime, nullable=True)
    is_monitored = db.Column("was_monitored", db.Boolean, default=True, nullable=False)
    created_at = db.Column("created_at", db.DateTime, default=datetime.utcnow, nullable=False)

    student = db.relationship("Student", back_populates="sessions")
    module = db.relationship("Module", backref="sessions")

    def to_dict(self):
        return {
            "id": self.id,
            "student_id": self.student_id,
            "module_id": self.module_id,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "is_monitored": self.is_monitored,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
