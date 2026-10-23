from datetime import datetime
from app.extensions import db

class DSMSummary(db.Model):
    __tablename__ = "dsm_summaries"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    sustained_inattention_count = db.Column(db.Integer, default=0, nullable=False)
    distraction_frequency_per_min = db.Column(db.Float, default=0.0, nullable=False)
    average_engagement_score = db.Column(db.Float, default=0.0, nullable=False)

    student = db.relationship("Student", backref="dsm_summaries")


class DistractionEvent(db.Model):
    """Open-episode distraction record. ended_at is set when verdict returns to FOCUSED.

    Postgres column uses enum monitoring_verdict ('focused', 'distracted').
    API/ML use UPPERCASE; persist lowercase to match the enum.
    """
    __tablename__ = "distraction_events"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=False)
    verdict = db.Column(
        db.Enum(
            "focused",
            "distracted",
            name="monitoring_verdict",
            create_type=False,
            validate_strings=True,
        ),
        nullable=False,
    )
    confidence = db.Column("confidence_score", db.Float, nullable=False)
    started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    ended_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column("created_at", db.DateTime, default=datetime.utcnow, nullable=False)

    session = db.relationship("LearningSession", backref="distraction_events")

    def duration_seconds(self, now=None) -> float:
        end = self.ended_at or now or datetime.utcnow()
        if not self.started_at:
            return 0.0
        return max(0.0, (end - self.started_at).total_seconds())


class InterventionLog(db.Model):
    __tablename__ = "intervention_logs"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=False)
    distraction_event_id = db.Column(
        db.Integer, db.ForeignKey("distraction_events.id"), nullable=True
    )
    triggered_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    tier = db.Column(db.Integer, nullable=False)
    intervention_type = db.Column(db.String(50), nullable=False)
    user_response = db.Column(db.String(50), nullable=True)  # reengaged | ignored | ended
    # For environment_noise_notice logs: headphones | move_environment | continue_anyway
    noise_action = db.Column(db.String(50), nullable=True)
    reengaged_in_seconds = db.Column(db.Float, nullable=True)

    session = db.relationship("LearningSession", backref="intervention_logs")
    distraction_event = db.relationship("DistractionEvent", backref="interventions")
    milestone_question = db.relationship(
        "MilestoneQuestion", back_populates="intervention", uselist=False, cascade="all, delete-orphan"
    )


class MilestoneQuestion(db.Model):
    __tablename__ = "milestone_questions"

    id = db.Column(db.Integer, primary_key=True)
    intervention_id = db.Column(
        db.Integer, db.ForeignKey("intervention_logs.id"), nullable=False, unique=True
    )
    generated_question = db.Column(db.Text, nullable=False)
    hint_text = db.Column(db.Text, nullable=True)
    student_answer = db.Column(db.Text, nullable=True)
    is_correct = db.Column(db.Boolean, nullable=True)
    milestone_item_id = db.Column(db.Integer, nullable=True)
    correct_option = db.Column(db.Integer, nullable=True)
    content_position_seconds = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    intervention = db.relationship("InterventionLog", back_populates="milestone_question")


class InterventionConfig(db.Model):
    """Per-subject tier enable/disable flags for micro-interventions."""
    __tablename__ = "intervention_configs"

    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(
        db.Integer, db.ForeignKey("subjects.id"), nullable=False, unique=True
    )
    tier1_enabled = db.Column(db.Boolean, default=True, nullable=False)
    tier2_enabled = db.Column(db.Boolean, default=True, nullable=False)
    tier3_enabled = db.Column(db.Boolean, default=True, nullable=False)
    tier4_enabled = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    subject = db.relationship("Subject", backref=db.backref("intervention_config", uselist=False))

    def to_dict(self):
        return {
            "id": self.id,
            "subject_id": self.subject_id,
            "tier1_enabled": self.tier1_enabled,
            "tier2_enabled": self.tier2_enabled,
            "tier3_enabled": self.tier3_enabled,
            "tier4_enabled": self.tier4_enabled,
            "enabled_tiers": self.enabled_tiers(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def enabled_tiers(self):
        flags = {
            1: self.tier1_enabled,
            2: self.tier2_enabled,
            3: self.tier3_enabled,
            4: self.tier4_enabled,
        }
        return [t for t, on in flags.items() if on]
