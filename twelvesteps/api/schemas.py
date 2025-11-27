from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from db.models import User as UserModel


class ChatRequest(BaseModel):
    telegram_id: str
    message: str
    debug : bool


class ChatResponse(BaseModel):
    reply: str
    log : Optional[Log]
    
class Log(BaseModel):
    classification_result: str
    blocks_used: str
    plan : str
    prompt_changes : Optional[str]

    

class TelegramAuthRequest(BaseModel):
    telegram_id: str = Field(..., min_length=1)
    username: Optional[str] = None
    first_name: Optional[str] = None


class UserSchema(BaseModel):
    id: int
    telegram_id: str
    username: Optional[str] = None
    first_name: Optional[str] = None
    display_name: Optional[str] = None
    role: Optional[str] = None
    program_experience: Optional[str] = None
    sobriety_date: Optional[date] = None
    personal_prompt: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class TelegramAuthResponse(BaseModel):
    user: UserSchema
    is_new: bool
    access_token: str


class ProfileUpdateRequest(BaseModel):
    display_name: Optional[str] = Field(default=None)
    program_experience: Optional[str] = Field(default=None)
    sobriety_date: Optional[date] = Field(default=None)

class SosRequest(BaseModel):
    # Accepts integer or string to match your handle_chat signature
    telegram_id: int | str

class SosResponse(BaseModel):
    reply: str    

class OpenStepQuestion(BaseModel):
    step_id: int
    question_id: int

class AnswerRequest(BaseModel):
    text: str

class StepResponse(BaseModel):
    message: str
    is_completed: bool = False

class StatusTail(BaseModel):
    id: int
    type: str
    payload: Optional[dict[str, Any]] = None


class StatusResponse(BaseModel):
    current_step: Optional[int] = None
    current_step_status: Optional[str] = None
    open_step_question: Optional[OpenStepQuestion] = None
    tails: list[StatusTail] = Field(default_factory=list)


def build_user_schema(user: UserModel) -> UserSchema:
    role_value = user.user_role.name.upper() if user.user_role else None
    return UserSchema(
        id=user.id,
        telegram_id=user.telegram_id,
        username=user.username,
        first_name=user.first_name,
        display_name=user.display_name,
        role=role_value,
        program_experience=user.program_experience,
        sobriety_date=user.sobriety_date,
        personal_prompt=user.personal_prompt,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )
