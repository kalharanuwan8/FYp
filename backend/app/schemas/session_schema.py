from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator

class SessionStartSchema(BaseModel):
    module_id: int = Field(..., description="ID of the module being studied in this session")
    is_monitored: Optional[bool] = Field(True, description="Whether distraction monitoring is active")

class HeartbeatSchema(BaseModel):
    verdict: Optional[str] = Field(
        None,
        description="Ignored outside TESTING — server ML decides from image/features",
    )
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Inference confidence score")
    gaze_label: Optional[str] = Field(None, max_length=50, description="Gaze classification e.g. center, left, right, away")
    pose_angles_json: Optional[Dict[str, Any]] = Field(None, description="Head pose angles e.g. pitch, yaw, roll")
    engagement_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Calculated engagement score")
    image: Optional[str] = Field(None, description="Base64 encoded webcam JPEG frame for ML model evaluation")
    features: Optional[Dict[str, Any]] = Field(
        None, description="Optional precomputed window features when no image is sent"
    )
    is_quiz_context: Optional[bool] = Field(
        False, description="True when the student is currently in a quiz attempt"
    )
    noise_dbfs: Optional[float] = Field(
        None,
        ge=-100.0,
        le=0.0,
        description="On-device microphone RMS loudness in dBFS; no audio is uploaded",
    )
    lesson_audio_active: Optional[bool] = Field(
        False,
        description="True while lesson audio plays unmuted (mic hears the lesson, not the room)",
    )

    @field_validator("verdict")
    @classmethod
    def validate_verdict(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        v_upper = v.upper().strip()
        if v_upper not in {"DISTRACTED", "FOCUSED"}:
            raise ValueError("verdict must be either 'DISTRACTED' or 'FOCUSED'")
        return v_upper

class InterventionResponseSchema(BaseModel):
    intervention_id: int = Field(..., description="ID of the InterventionLog being responded to")
    user_response: str = Field(..., description="Response type: 'reengaged', 'ignored', or 'ended'")
    noise_action: Optional[str] = Field(
        None,
        description="For environment_noise_notice: 'headphones', 'move_environment', or 'continue_anyway'",
    )
    student_answer: Optional[str] = Field(None, description="Free-text or selected option label")
    selected_option: Optional[int] = Field(None, ge=0, description="0-based MC option index")
    milestone_item_id: Optional[int] = Field(None, description="Bank item used for grading")

    @field_validator("user_response")
    @classmethod
    def validate_response(cls, v: str) -> str:
        v_lower = v.lower().strip()
        allowed = {"reengaged", "ignored", "ended"}
        if v_lower not in allowed:
            raise ValueError(f"user_response must be one of {sorted(allowed)}")
        return v_lower

    @field_validator("noise_action")
    @classmethod
    def validate_noise_action(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        v_lower = v.lower().strip()
        allowed = {"headphones", "move_environment", "continue_anyway"}
        if v_lower not in allowed:
            raise ValueError(f"noise_action must be one of {sorted(allowed)}")
        return v_lower


class TriggerInterventionSchema(BaseModel):
    tier: int = Field(..., ge=1, le=4, description="Intervention tier to force (1-4)")
    is_quiz_context: Optional[bool] = Field(False)
