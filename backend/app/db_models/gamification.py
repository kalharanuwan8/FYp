"""Gamification models: XP, streaks, badges for ADHD-friendly student UI."""

from datetime import date, datetime
from app.extensions import db


class StudentProgress(db.Model):
    __tablename__ = "student_progress"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer, db.ForeignKey("students.id"), unique=True, nullable=False
    )
    xp = db.Column(db.Integer, default=0, nullable=False)
    level = db.Column(db.Integer, default=1, nullable=False)
    current_streak = db.Column(db.Integer, default=0, nullable=False)
    longest_streak = db.Column(db.Integer, default=0, nullable=False)
    last_active_date = db.Column(db.Date, nullable=True)
    daily_goal_minutes = db.Column(db.Integer, default=20, nullable=False)
    today_focus_minutes = db.Column(db.Integer, default=0, nullable=False)
    total_focus_minutes = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    student = db.relationship("Student", backref=db.backref("progress", uselist=False))

    def to_dict(self):
        return {
            "xp": self.xp,
            "level": self.level,
            "current_streak": self.current_streak,
            "longest_streak": self.longest_streak,
            "last_active_date": (
                self.last_active_date.isoformat() if self.last_active_date else None
            ),
            "daily_goal_minutes": self.daily_goal_minutes,
            "today_focus_minutes": self.today_focus_minutes,
            "total_focus_minutes": self.total_focus_minutes,
            "xp_to_next_level": max(0, (self.level * 100) - (self.xp % (self.level * 100))),
        }


class Badge(db.Model):
    __tablename__ = "badges"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(64), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    icon = db.Column(db.String(32), default="⭐")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "description": self.description,
            "icon": self.icon,
        }


class StudentBadge(db.Model):
    __tablename__ = "student_badges"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    badge_id = db.Column(db.Integer, db.ForeignKey("badges.id"), nullable=False)
    earned_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("student_id", "badge_id", name="uq_student_badge"),
    )

    badge = db.relationship("Badge")
    student = db.relationship("Student", backref=db.backref("badges", lazy="dynamic"))

    def to_dict(self):
        return {
            "id": self.id,
            "badge": self.badge.to_dict() if self.badge else None,
            "earned_at": self.earned_at.isoformat() if self.earned_at else None,
        }
