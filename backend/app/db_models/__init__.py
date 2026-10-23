"""
Import every model module here so SQLAlchemy's mapper registry resolves
string-based relationship references correctly.
"""

from app.db_models.user import User, Student, Teacher, GuardianConsent
from app.db_models.course import (
    GradeLevel,
    Subject,
    TeacherSubject,
    Module,
    ModuleContent,
    ModuleMilestoneItem,
    Enrollment,
)
from app.db_models.quiz import Quiz, QuizQuestion, QuizQuestionOption, QuizAttempt, QuizAnswer
from app.db_models.session import LearningSession, MonitoringObservation
from app.db_models.analytics import (
    DistractionEvent,
    InterventionLog,
    DSMSummary,
    MilestoneQuestion,
    InterventionConfig,
)
from app.db_models.system_setting import SystemSetting
from app.db_models.gamification import StudentProgress, Badge, StudentBadge

__all__ = [
    "User",
    "Student",
    "Teacher",
    "GuardianConsent",
    "GradeLevel",
    "Subject",
    "TeacherSubject",
    "Module",
    "ModuleContent",
    "ModuleMilestoneItem",
    "Enrollment",
    "Quiz",
    "QuizQuestion",
    "QuizQuestionOption",
    "QuizAttempt",
    "QuizAnswer",
    "LearningSession",
    "MonitoringObservation",
    "DistractionEvent",
    "InterventionLog",
    "DSMSummary",
    "MilestoneQuestion",
    "InterventionConfig",
    "SystemSetting",
    "StudentProgress",
    "Badge",
    "StudentBadge",
]