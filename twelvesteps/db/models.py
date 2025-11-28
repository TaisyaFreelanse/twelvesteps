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

class SessionType(Enum):
    STEPS = "STEPS"
    DAY = "DAY"
    CHAT = "CHAT"

class TemplateType(Enum):
    AUTHOR = "AUTHOR"
    CUSTOM = "CUSTOM"

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
    active_template_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("answer_templates.id", ondelete="SET NULL"), nullable=True, index=True
    )
    relapse_dates: Mapped[Optional[List[str]]] = mapped_column(
        JSON, nullable=True
    )  # JSON массив дат в формате YYYY-MM-DD
    sponsor_ids: Mapped[Optional[List[int]]] = mapped_column(
        JSON, nullable=True
    )  # JSON массив ID спонсоров
    custom_fields: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True
    )  # JSON для целей, важных людей, формата поддержки
    last_active: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # Обновляется при каждом взаимодействии через UserRepository
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
    session_contexts: Mapped[List["SessionContext"]] = relationship(
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
    title = Column(String(255), nullable=True)  # Название шага (например, "Принятие решения")
    description = Column(Text, nullable=True)  # Описание сути шага
    
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


class SessionContext(Base):
    __tablename__ = "session_contexts"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    session_type = Column(SQLEnum(SessionType, name="session_type_enum", create_type=True), nullable=False)
    context_data = Column(JSON, nullable=True)  # JSON field for flexible context storage
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationship to User
    user = relationship("User", back_populates="session_contexts")


class SessionState(Base):
    """
    Model for operational state tracking.
    Stores recent messages, daily snapshot, active blocks, pending topics, and group signals.
    """
    __tablename__ = "session_states"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recent_messages: Mapped[Optional[List[dict]]] = mapped_column(
        JSON, nullable=True
    )  # JSON массив с timestamp, text, tags
    daily_snapshot: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True
    )  # JSON: emotions, triggers, actions, health
    active_blocks: Mapped[Optional[List[str]]] = mapped_column(
        JSON, nullable=True
    )  # JSON массив строк
    pending_topics: Mapped[Optional[List[str]]] = mapped_column(
        JSON, nullable=True
    )  # JSON массив строк
    group_signals: Mapped[Optional[List[str]]] = mapped_column(
        JSON, nullable=True
    )  # JSON массив строк
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    
    # Relationship to User
    user: Mapped["User"] = relationship()


class FrameTracking(Base):
    """
    Model for tracking frame metadata and confirmation.
    Stores confirmed frames, candidates, tracking info, archetypes, and meta flags.
    """
    __tablename__ = "frame_tracking"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    confirmed: Mapped[Optional[List[dict]]] = mapped_column(
        JSON, nullable=True
    )  # JSON массив подтвержденных фреймов
    candidates: Mapped[Optional[List[dict]]] = mapped_column(
        JSON, nullable=True
    )  # JSON массив кандидатов
    tracking: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True
    )  # JSON: repetition_count объект, min_to_confirm число
    archetypes: Mapped[Optional[List[str]]] = mapped_column(
        JSON, nullable=True
    )  # JSON массив архетипов: victim, rescuer, judge и т.д.
    meta_flags: Mapped[Optional[List[str]]] = mapped_column(
        JSON, nullable=True
    )  # JSON массив: loop_detected, frame_shift, identity_conflict
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    
    # Relationship to User
    user: Mapped["User"] = relationship()


class QAStatus(Base):
    """
    Model for quality assurance status tracking.
    Tracks prompt inclusion, trace status, open threads, and rebuild requirements.
    """
    __tablename__ = "qa_status"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    last_prompt_included: Mapped[Optional[bool]] = mapped_column(
        Boolean, nullable=True, default=False
    )  # boolean
    trace_ok: Mapped[Optional[bool]] = mapped_column(
        Boolean, nullable=True, default=False
    )  # boolean
    open_threads: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, default=0
    )  # integer, количество незакрытых веток
    rebuild_required: Mapped[Optional[bool]] = mapped_column(
        Boolean, nullable=True, default=False
    )  # boolean
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    
    # Relationship to User
    user: Mapped["User"] = relationship()


class UserMeta(Base):
    """
    Model for user system metadata.
    Stores metasloy signals, prompt revision history, timezone, language, and data flags.
    One-to-one relationship with User.
    """
    __tablename__ = "user_meta"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )  # ForeignKey, unique (один к одному)
    metasloy_signals: Mapped[Optional[List[str]]] = mapped_column(
        JSON, nullable=True
    )  # JSON массив строк
    prompt_revision_history: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, default=0
    )  # integer, количество пересмотров промпта
    time_zone: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # string, например "UTC+3"
    language: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True, default='ru'
    )  # string, default='ru'
    data_flags: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True
    )  # JSON: encrypted boolean, anonymized boolean, retention_days integer
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    
    # Relationship to User (one-to-one)
    user: Mapped["User"] = relationship()


class TrackerSummary(Base):
    """
    Model for daily observation tracking.
    Stores thinking, feeling, behavior, relationships, and health data grouped by date.
    One summary per user per day (unique constraint on user_id, date).
    """
    __tablename__ = "tracker_summaries"
    
    table_args = (
        UniqueConstraint("user_id", "date", name="uq_tracker_summary_user_date"),
    )
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    thinking: Mapped[Optional[List[str]]] = mapped_column(
        JSON, nullable=True
    )  # JSON массив строк
    feeling: Mapped[Optional[List[str]]] = mapped_column(
        JSON, nullable=True
    )  # JSON массив строк
    behavior: Mapped[Optional[List[str]]] = mapped_column(
        JSON, nullable=True
    )  # JSON массив строк
    relationships: Mapped[Optional[List[str]]] = mapped_column(
        JSON, nullable=True
    )  # JSON массив строк
    health: Mapped[Optional[List[str]]] = mapped_column(
        JSON, nullable=True
    )  # JSON массив строк
    date: Mapped[date] = mapped_column(
        Date, nullable=False, index=True
    )  # date, для группировки по дням
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    
    # Relationship to User
    user: Mapped["User"] = relationship()


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


# --- ANSWER TEMPLATES ---

class AnswerTemplate(Base):
    __tablename__ = "answer_templates"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    template_type: Mapped[TemplateType] = mapped_column(
        SQLEnum(TemplateType, name="template_type_enum", create_type=True),
        default=TemplateType.CUSTOM,
        server_default=TemplateType.CUSTOM.value,
    )
    structure: Mapped[dict] = mapped_column(JSON, nullable=False)  # JSON структура шаблона
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    
    # Relationships
    user: Mapped[Optional["User"]] = relationship()


# --- PROFILE MODELS ---

class ProfileSection(Base):
    __tablename__ = "profile_sections"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)  # Название с эмодзи
    icon: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # Эмодзи иконка
    is_custom: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    
    # Relationships
    user: Mapped[Optional["User"]] = relationship()
    questions: Mapped[List["ProfileQuestion"]] = relationship(
        back_populates="section", cascade="all, delete-orphan", order_by="ProfileQuestion.order_index"
    )
    section_data: Mapped[List["ProfileSectionData"]] = relationship(
        back_populates="section", cascade="all, delete-orphan"
    )


class ProfileSectionData(Base):
    __tablename__ = "profile_section_data"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("profile_sections.id", ondelete="CASCADE"), index=True)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Свободный текст или JSON
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    
    # Relationships
    user: Mapped["User"] = relationship()
    section: Mapped["ProfileSection"] = relationship(back_populates="section_data")


class ProfileQuestion(Base):
    __tablename__ = "profile_questions"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("profile_sections.id", ondelete="CASCADE"), index=True)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0, index=True)
    is_optional: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    
    # Relationships
    section: Mapped["ProfileSection"] = relationship(back_populates="questions")
    answers: Mapped[List["ProfileAnswer"]] = relationship(
        back_populates="question", cascade="all, delete-orphan"
    )


class ProfileAnswer(Base):
    __tablename__ = "profile_answers"
    
    table_args = (
        UniqueConstraint("user_id", "question_id", "version", name="uq_profile_answer_version"),
    )
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("profile_questions.id", ondelete="CASCADE"), index=True)
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    
    # Relationships
    user: Mapped["User"] = relationship()
    question: Mapped["ProfileQuestion"] = relationship(back_populates="answers")