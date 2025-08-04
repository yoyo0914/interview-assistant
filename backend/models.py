from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Text,
    DateTime,
    Boolean,
    ForeignKey,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import os

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./interview_assistant.db")
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    google_id = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    name = Column(String)
    access_token = Column(Text)
    refresh_token = Column(Text)
    token_expires_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 新增：同步狀態追蹤
    last_sync_at = Column(DateTime)

    emails = relationship("Email", back_populates="user")


class Email(Base):
    __tablename__ = "emails"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    gmail_id = Column(String, unique=True, index=True)
    thread_id = Column(String)
    subject = Column(String)
    sender = Column(String)
    recipient = Column(String)
    body_text = Column(Text)
    body_html = Column(Text)
    received_at = Column(DateTime)
    is_processed = Column(Boolean, default=False)
    is_interview_related = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="emails")
    interview_invitation = relationship(
        "InterviewInvitation", back_populates="email", uselist=False
    )


class InterviewInvitation(Base):
    __tablename__ = "interview_invitations"

    id = Column(Integer, primary_key=True, index=True)
    email_id = Column(Integer, ForeignKey("emails.id"))
    company_name = Column(String)
    position = Column(String)
    interview_date = Column(DateTime)
    interview_time = Column(String)
    interview_location = Column(String)
    interview_type = Column(String)  # online, onsite, phone
    interviewer_name = Column(String)
    interviewer_email = Column(String)
    additional_info = Column(Text)
    confidence_score = Column(Integer)  # AI confidence 0-100
    created_at = Column(DateTime, default=datetime.utcnow)

    email = relationship("Email", back_populates="interview_invitation")
    draft_replies = relationship("DraftReply", back_populates="interview_invitation")


class DraftReply(Base):
    __tablename__ = "draft_replies"

    id = Column(Integer, primary_key=True, index=True)
    interview_invitation_id = Column(Integer, ForeignKey("interview_invitations.id"))
    subject = Column(String)
    body = Column(Text)
    tone = Column(String)  # professional, friendly, formal
    is_sent = Column(Boolean, default=False)
    sent_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    interview_invitation = relationship(
        "InterviewInvitation", back_populates="draft_replies"
    )


# Create tables
def create_tables():
    Base.metadata.create_all(bind=engine)


# Database dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
