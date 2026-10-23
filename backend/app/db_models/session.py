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
    # Atomic claim flag: only the first stop that flips this to True awards XP.
    xp_awarded = db.Column(db.Boolean, default=False, nullable=False)

    # Phase 2A — observed_v1 coverage snapshot (null on legacy sessions)
    focus_metric_version = db.Column(db.String(32), nullable=True)
    observed_focused_seconds = db.Column(db.Float, nullable=True)
    observed_distracted_seconds = db.Column(db.Float, nullable=True)
    unknown_seconds = db.Column(db.Float, nullable=True)
    monitoring_coverage_pct = db.Column(db.Float, nullable=True)
    # Null when no valid observed time (observed_v1); legacy sessions leave null too.
    focus_percentage = db.Column(db.Float, nullable=True)

    created_at = db.Column("created_at", db.DateTime, default=datetime.utcnow, nullable=False)

    student = db.relationship("Student", back_populates="sessions")
    module = db.relationship("Module", backref="sessions")
    observations = db.relationship(
        "MonitoringObservation",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="MonitoringObservation.observed_at",
    )

    def to_dict(self):
        return {
            "id": self.id,
            "student_id": self.student_id,
            "module_id": self.module_id,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "is_monitored": self.is_monitored,
            "focus_metric_version": self.focus_metric_version,
            "observed_focused_seconds": self.observed_focused_seconds,
            "observed_distracted_seconds": self.observed_distracted_seconds,
            "unknown_seconds": self.unknown_seconds,
            "monitoring_coverage_pct": self.monitoring_coverage_pct,
            "focus_percentage": self.focus_percentage,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class MonitoringObservation(db.Model):
    """
    Per-heartbeat monitoring sample for coverage accounting (Phase 2A).

    state is uppercase API form: FOCUSED | DISTRACTED | UNKNOWN.
    Stored as string (not the Postgres distraction_events enum) so UNKNOWN
    does not require altering that enum.
    """

    __tablename__ = "monitoring_observations"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=False, index=True)
    observed_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    state = db.Column(db.String(16), nullable=False)
    confidence = db.Column(db.Float, nullable=True)
    face_detected = db.Column(db.Boolean, nullable=True)
    ml_mode = db.Column(db.String(32), nullable=True)
    reason = db.Column(db.String(64), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    session = db.relationship("LearningSession", back_populates="observations")

    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "observed_at": self.observed_at.isoformat() if self.observed_at else None,
            "state": self.state,
            "confidence": self.confidence,
            "face_detected": self.face_detected,
            "ml_mode": self.ml_mode,
            "reason": self.reason,
        }
