from datetime import datetime, date
from typing import Optional, List
from enum import Enum

from sqlalchemy import (
    CHAR,
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from sqlalchemy import Enum as SQLEnum

# Ensure this import path is correct based on your project structure
from db.database import Base 

# --- ENUMS ---

class UserRole(Enum):
    admin = "admin"
    dependent = "dependent"
    sponsor = "sponsor"

class SenderRole(Enum):
    assistant = "assistant"
    user = "user"

class StepProgressStatus(Enum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"

class TailType(Enum):
    STEP_QUESTION = "STEP_QUESTION"
    STEP_COMPLETION = "STEP_COMPLETION"

# --- ASSOCIATION TABLES ---

blocks_frames = Table(
    "blocks_frames", 
    Base.metadata, 
    Column("block_id", ForeignKey("blocks.id", ondelete="CASCADE"), primary_key=True),
    Column("frame_id", ForeignKey("frames.id", ondelete="CASCADE"), primary_key=True)
)

# --- MODELS ---

class User(Base):
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[Optional[str]] = mapped_column(String(64), unique=True, index=True)
    api_key: Mapped[Optional[str]] = mapped_column(CHAR(128), unique=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    user_role: Mapped[Optional[UserRole]] = mapped_column(
        SQLEnum(UserRole, name="user_role_enum", create_type=True),
        default=UserRole.dependent,
        server_default=UserRole.dependent.value,
    )
    personal_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    program_experience: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    sobriety_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    messages: Mapped[List["Message"]] = relationship(
        back_populates="user", cascade="all, delete"
    )
    frames: Mapped[List["Frame"]] = relationship(
        back_populates="user", cascade="all, delete"
    )


class Frame(Base):
    __tablename__ = "frames"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    emotion: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    weight: Mapped[Optional[float]] = mapped_column(default=0.0)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        server_default=text("TIMEZONE('utc', now())")
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    user: Mapped["User"] = relationship(back_populates="frames")
    blocks: Mapped[List["Block"]] = relationship(
        secondary=blocks_frames, 
        back_populates="frames"
    )


class Message(Base):
    __tablename__ = "messages"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sender_role: Mapped[Optional[SenderRole]] = mapped_column(
        SQLEnum(SenderRole, name="sender_role_enum", create_type=True)
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(
        server_default=text("TIMEZONE('utc', now())")
    )
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    user: Mapped["User"] = relationship(back_populates="messages")


class Block(Base):
    __tablename__ = "blocks"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[Optional[str]] = mapped_column(
        "label",  # DB column name override
        String(255),
        unique=True,
        index=True,
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(
        server_default=text("TIMEZONE('utc', now())")
    )

    frames: Mapped[List["Frame"]] = relationship(
        secondary=blocks_frames, 
        back_populates="blocks"
    )


class Step(Base):
    __tablename__ = "steps"

    id = Column(Integer, primary_key=True, index=True)
    index = Column(Integer, unique=True, nullable=False)
    
    # Connects to Question model
    questions = relationship("Question", back_populates="step", cascade="all, delete-orphan")


class Question(Base):
    # IMPORTANT: Table name matches ForeignKey in StepAnswer and Tail
    __tablename__ = "step_questions" 

    id = Column(Integer, primary_key=True, index=True)
    text = Column(Text, nullable=False)
    step_id = Column(Integer, ForeignKey("steps.id", ondelete="CASCADE"), nullable=False)

    # Relationships
    step = relationship("Step", back_populates="questions")
    answers = relationship("StepAnswer", back_populates="question", cascade="all, delete-orphan")
    tails = relationship("Tail", back_populates="question", cascade="all, delete-orphan")


class StepAnswer(Base):
    __tablename__ = "step_answers"
    
    table_args = (
        UniqueConstraint("user_id", "question_id", "version", name="uq_step_answer_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    step_id: Mapped[int] = mapped_column(ForeignKey("steps.id", ondelete="CASCADE"), index=True)
    # Matches 'step_questions' table name
    question_id: Mapped[int] = mapped_column(ForeignKey("step_questions.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    question: Mapped["Question"] = relationship(back_populates="answers")


class UserStep(Base):
    __tablename__ = "user_steps"
    
    table_args = (
        UniqueConstraint("user_id", "step_id", name="uq_user_step"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    step_id: Mapped[int] = mapped_column(ForeignKey("steps.id", ondelete="CASCADE"), index=True)
    status: Mapped[StepProgressStatus] = mapped_column(
        SQLEnum(StepProgressStatus, name="step_progress_status_enum", create_type=True),
        default=StepProgressStatus.NOT_STARTED,
        server_default=StepProgressStatus.NOT_STARTED.value,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class Tail(Base):
    __tablename__ = "tails"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    tail_type: Mapped[TailType] = mapped_column(
        SQLEnum(TailType, name="tail_type_enum", create_type=True),
        default=TailType.STEP_QUESTION,
        server_default=TailType.STEP_QUESTION.value,
    )
    step_id: Mapped[Optional[int]] = mapped_column(ForeignKey("steps.id", ondelete="CASCADE"), nullable=True, index=True)
    
    # Matches 'step_questions' table name
    step_question_id: Mapped[Optional[int]] = mapped_column(ForeignKey("step_questions.id", ondelete="CASCADE"), nullable=True, index=True)
    
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship()
    step: Mapped["Step"] = relationship()
    question: Mapped["Question"] = relationship(back_populates="tails")