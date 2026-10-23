from typing import Optional, List, Literal
from pydantic import BaseModel, Field, model_validator

class OptionCreateSchema(BaseModel):
    option_text: str = Field(..., min_length=1, max_length=500)
    is_correct: bool = False

class QuestionCreateSchema(BaseModel):
    question_text: str = Field(..., min_length=1)
    question_type: Literal["multiple_choice", "short_answer"]
    sequence_order: int = Field(1, ge=1)
    correct_answer_text: Optional[str] = None
    options: Optional[List[OptionCreateSchema]] = None

    @model_validator(mode="after")
    def validate_question_type_requirements(self):
        q_type = self.question_type
        if q_type == "multiple_choice":
            if not self.options or len(self.options) < 2:
                raise ValueError("Multiple choice questions must have at least 2 options")
            correct_count = sum(1 for opt in self.options if opt.is_correct)
            if correct_count != 1:
                raise ValueError("Multiple choice questions must have exactly one correct option")
        elif q_type == "short_answer":
            if not self.correct_answer_text or not self.correct_answer_text.strip():
                raise ValueError("Short answer questions must provide a non-empty correct_answer_text")
        return self

class QuizCreateSchema(BaseModel):
    title: str = Field(..., min_length=1, max_length=150)
    questions: List[QuestionCreateSchema] = Field(..., min_length=1)

class AnswerSubmitSchema(BaseModel):
    question_id: int
    selected_option_id: Optional[int] = None
    answer_text: Optional[str] = None

class AttemptSubmitSchema(BaseModel):
    answers: List[AnswerSubmitSchema] = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_unique_question_ids(self):
        question_ids = [ans.question_id for ans in self.answers]
        if len(question_ids) != len(set(question_ids)):
            raise ValueError("Duplicate question_ids are not allowed in quiz submission answers")
        return self
