from typing import Optional, List
from pydantic import BaseModel, Field, field_validator, model_validator

class SubjectCreateSchema(BaseModel):
    title: str = Field(..., min_length=1, max_length=150)
    description: Optional[str] = None
    grade_level_id: int

class SubjectUpdateSchema(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=150)
    description: Optional[str] = None
    grade_level_id: Optional[int] = None
    is_archived: Optional[bool] = None

class ModuleCreateSchema(BaseModel):
    subject_id: Optional[int] = None
    title: str = Field(..., min_length=1, max_length=150)
    description: Optional[str] = None
    sequence_order: Optional[int] = Field(None, ge=1)

class ModuleUpdateSchema(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=150)
    description: Optional[str] = None
    sequence_order: Optional[int] = Field(None, ge=1)
    is_archived: Optional[bool] = None


class MilestoneItemSchema(BaseModel):
    question: str = Field(..., min_length=1)
    options: List[str] = Field(..., min_length=2, max_length=6)
    correct_option: int = Field(0, ge=0)
    hint_text: Optional[str] = None
    sequence_order: Optional[int] = Field(None, ge=1)

    @model_validator(mode="after")
    def validate_correct_index(self):
        if self.correct_option >= len(self.options):
            raise ValueError("correct_option must be a valid index into options")
        return self


class MaterialCreateSchema(BaseModel):
    title: str = Field(..., min_length=1, max_length=150)
    content_type: str = Field(..., description="Must be 'video', 'document', 'quiz', or 'other'")
    file_url: Optional[str] = Field(None, max_length=500)
    quiz_id: Optional[int] = None
    summary: Optional[str] = None
    milestones: Optional[List[MilestoneItemSchema]] = None

    @field_validator("content_type")
    @classmethod
    def validate_content_type(cls, v: str) -> str:
        allowed = {"video", "document", "quiz", "other"}
        if v.lower() not in allowed:
            raise ValueError(f"content_type must be one of {sorted(allowed)}")
        return v.lower()

    @model_validator(mode="after")
    def validate_quiz_id_consistency(self):
        if self.content_type == "quiz" and not self.quiz_id:
            raise ValueError("quiz_id is required when content_type is 'quiz'")
        if self.content_type != "quiz" and self.quiz_id is not None:
            raise ValueError("quiz_id must be None when content_type is not 'quiz'")
        return self


class MaterialUpdateSchema(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=150)
    content_type: Optional[str] = None
    file_url: Optional[str] = Field(None, max_length=500)
    quiz_id: Optional[int] = None
    summary: Optional[str] = None
    milestones: Optional[List[MilestoneItemSchema]] = None

    @field_validator("content_type")
    @classmethod
    def validate_content_type(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        allowed = {"video", "document", "quiz", "other"}
        if v.lower() not in allowed:
            raise ValueError(f"content_type must be one of {sorted(allowed)}")
        return v.lower()


class GeneratePackSchema(BaseModel):
    description: str = Field(..., min_length=1)
    title: Optional[str] = Field(None, max_length=150)
    num_questions: Optional[int] = Field(3, ge=1, le=8)
