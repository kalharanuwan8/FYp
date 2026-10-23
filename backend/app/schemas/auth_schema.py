from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

class LoginSchema(BaseModel):
    email: EmailStr
    password: str

class RegisterSchema(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=72)
    first_name: str
    last_name: str
    role: str
    guardian_name: Optional[str] = None
    guardian_email: Optional[EmailStr] = None

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        role_clean = v.lower().strip()
        if role_clean not in ["teacher", "student"]:
            raise ValueError("Role must be 'teacher' or 'student'. Admin accounts cannot be created via registration.")
        return role_clean

    @model_validator(mode="after")
    def validate_guardian_fields(self):
        if self.role == "student":
            if not self.guardian_name or not self.guardian_name.strip():
                raise ValueError("guardian_name is required when role is 'student'.")
            if not self.guardian_email:
                raise ValueError("guardian_email is required when role is 'student'.")
        return self
