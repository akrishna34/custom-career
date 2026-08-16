from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, create_engine
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import data_directory, database_path


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AccessSession(Base):
    __tablename__ = "access_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CareerInterviewSession(Base):
    __tablename__ = "career_interview_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(100), default="local-demo", index=True)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    current_topic: Mapped[str] = mapped_column(String(50), default="timeline")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CareerInterviewMessage(Base):
    __tablename__ = "career_interview_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(ForeignKey("career_interview_sessions.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class FactProposal(Base):
    __tablename__ = "fact_proposals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(ForeignKey("career_interview_sessions.id"), index=True)
    source_message_id: Mapped[str | None] = mapped_column(ForeignKey("career_interview_messages.id"), nullable=True)
    entity_type: Mapped[str] = mapped_column(String(30))
    summary: Mapped[str] = mapped_column(Text)
    proposed_data: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CareerRecord(Base):
    """A user-approved, source-traceable fact in the permanent Career Vault."""

    __tablename__ = "career_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    source_proposal_id: Mapped[str] = mapped_column(ForeignKey("fact_proposals.id"), unique=True)
    record_type: Mapped[str] = mapped_column(String(30), index=True)
    summary: Mapped[str] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ResumeDraft(Base):
    """A generated, user-owned resume draft. Source facts stay in CareerRecord."""

    __tablename__ = "resume_drafts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    resume_type: Mapped[str] = mapped_column(String(30), default="master", index=True)
    content: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


data_directory.mkdir(parents=True, exist_ok=True)
engine = create_engine(f"sqlite:///{database_path}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def initialize_database() -> None:
    """Create the local database file and future model tables."""
    Base.metadata.create_all(bind=engine)
