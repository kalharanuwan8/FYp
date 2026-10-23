from app.schemas.auth_schema import LoginSchema, RegisterSchema
from app.schemas.course_schema import (
    SubjectCreateSchema,
    SubjectUpdateSchema,
    ModuleCreateSchema,
    ModuleUpdateSchema,
    MaterialCreateSchema,
)
from app.schemas.quiz_schema import (
    QuizCreateSchema,
    QuestionCreateSchema,
    OptionCreateSchema,
    AttemptSubmitSchema,
    AnswerSubmitSchema,
)

__all__ = [
    "LoginSchema",
    "RegisterSchema",
    "SubjectCreateSchema",
    "SubjectUpdateSchema",
    "ModuleCreateSchema",
    "ModuleUpdateSchema",
    "MaterialCreateSchema",
    "QuizCreateSchema",
    "QuestionCreateSchema",
    "OptionCreateSchema",
    "AttemptSubmitSchema",
    "AnswerSubmitSchema",
]
