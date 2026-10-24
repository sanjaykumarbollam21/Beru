import uuid
from datetime import datetime, timezone
from typing import Generator
from sqlalchemy import create_engine, Column, String, DateTime, Boolean, JSON, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, Session
from hub.config import settings

Base = declarative_base()

def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at = Column(DateTime(timezone=True), default=utcnow)

    devices = relationship("Device", back_populates="user", cascade="all, delete-orphan")
    pairing_codes = relationship("PairingCode", back_populates="user", cascade="all, delete-orphan")

class Device(Base):
    __tablename__ = "devices"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    platform = Column(String(50), nullable=False)  # "android", "windows", etc.
    token_hash = Column(String(64), nullable=False, index=True)
    capabilities = Column(JSON, default=list, nullable=False)  # list of strings
    last_seen = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="devices")

class PairingCode(Base):
    __tablename__ = "pairing_codes"

    code = Column(String(32), primary_key=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used = Column(Boolean, default=False, nullable=False)

    user = relationship("User", back_populates="pairing_codes")

class UserPreference(Base):
    __tablename__ = "user_preferences"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    key = Column(String(100), nullable=False, index=True)
    value = Column(JSON, nullable=False)
    source = Column(String(32), default="user", nullable=False)  # "user" or "learned"
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

class UserFact(Base):
    __tablename__ = "user_facts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    text = Column(String(500), nullable=False)
    created_at = Column(DateTime, default=utcnow)

class UserRoutine(Base):
    __tablename__ = "user_routines"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False, index=True)
    steps = Column(JSON, nullable=False)  # list of {"skill": str, "target": str, "params": dict}
    created_at = Column(DateTime, default=utcnow)

class CommandCorrection(Base):
    __tablename__ = "command_corrections"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    skill = Column(String(100), nullable=False, index=True)
    intended_target = Column(String(50), nullable=True)
    corrected_target = Column(String(50), nullable=False)
    timestamp = Column(DateTime, default=utcnow)
    suppressed_until = Column(DateTime, nullable=True)

class SkillSequenceLog(Base):
    __tablename__ = "skill_sequence_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    sequence_hash = Column(String(64), nullable=False, index=True)
    sequence_json = Column(JSON, nullable=False)
    date_str = Column(String(10), nullable=False, index=True)  # YYYY-MM-DD
    timestamp = Column(DateTime, default=utcnow)


connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
