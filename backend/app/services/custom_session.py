"""Student-owned files and the hidden module that anchors a custom monitoring session."""
from __future__ import annotations

import os

from app.db_models import GradeLevel, Module, Subject
from app.extensions import db

# Kept off course lists: archived, and the grade name is not "Grade 1".."Grade 12".
_INTERNAL_GRADE = "Internal"
_INTERNAL_SUBJECT = "__luma_custom_monitoring__"

VIDEO_EXTS = {"mp4", "webm", "mov", "mkv"}
IMAGE_EXTS = {"png", "jpg", "jpeg", "gif", "webp"}
AUDIO_EXTS = {"mp3", "wav", "m4a", "ogg"}
DOCUMENT_EXTS = {"pdf", "txt", "md", "csv", "doc", "docx", "ppt", "pptx"}
CUSTOM_EXTENSIONS = VIDEO_EXTS | IMAGE_EXTS | AUDIO_EXTS | DOCUMENT_EXTS


def content_kind_for(filename: str) -> str:
    ext = ""
    if filename and "." in filename:
        ext = filename.rsplit(".", 1)[1].lower()
    if ext in VIDEO_EXTS:
        return "video"
    if ext in IMAGE_EXTS:
        return "image"
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in DOCUMENT_EXTS:
        return "document"
    return "other"


def title_from_filename(filename: str) -> str:
    base = os.path.basename(filename or "Upload")
    stem = base.rsplit(".", 1)[0] if "." in base else base
    cleaned = stem.replace("_", " ").replace("-", " ").strip() or "Upload"
    return cleaned[:150]


def ensure_custom_module() -> Module:
    """One archived module shared by every custom session (sessions.module_id is required)."""
    grade = GradeLevel.query.filter_by(name=_INTERNAL_GRADE).first()
    if grade is None:
        grade = GradeLevel(name=_INTERNAL_GRADE)
        db.session.add(grade)
        db.session.flush()
    subject = Subject.query.filter_by(title=_INTERNAL_SUBJECT).first()
    if subject is None:
        subject = Subject(
            title=_INTERNAL_SUBJECT,
            description="Holder for student-uploaded monitoring sessions",
            grade_level_id=grade.id,
            is_archived=True,
        )
        db.session.add(subject)
        db.session.flush()
    elif not subject.is_archived:
        subject.is_archived = True
    module = (
        Module.query.filter_by(subject_id=subject.id, is_archived=True)
        .order_by(Module.id.asc())
        .first()
    )
    if module is None:
        module = Module(
            subject_id=subject.id,
            title="Custom monitoring",
            description="Student-uploaded material",
            sequence_order=1,
            is_archived=True,
        )
        db.session.add(module)
        db.session.flush()
    return module
