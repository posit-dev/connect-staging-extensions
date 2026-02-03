"""
Database models and connection management for Jaeger backend.

All timestamps are stored as INTEGER microseconds since Unix epoch.
"""

import os
from datetime import datetime
from typing import Generator

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker

# Database configuration
DB_PATH = os.getenv("JAEGER_DB_PATH", "./jaeger.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

# SQLAlchemy setup
Base = declarative_base()
engine = None
SessionLocal = None


# Models
class Trace(Base):
    """Trace-level metadata."""

    __tablename__ = "traces"

    trace_id = Column(String(32), primary_key=True)  # 32 hex chars
    start_time = Column(BigInteger, nullable=False, index=True)  # microseconds
    end_time = Column(BigInteger, nullable=False)  # microseconds
    duration = Column(BigInteger, nullable=False)  # microseconds
    service_name = Column(String(255), nullable=False, index=True)
    root_operation = Column(String(255), nullable=False)
    span_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    spans = relationship("Span", back_populates="trace", cascade="all, delete-orphan")
    resource_attributes = relationship(
        "ResourceAttribute", back_populates="trace", cascade="all, delete-orphan"
    )


class Span(Base):
    """Individual span within a trace."""

    __tablename__ = "spans"

    trace_id = Column(
        String(32), ForeignKey("traces.trace_id", ondelete="CASCADE"), nullable=False, primary_key=True
    )
    span_id = Column(String(16), nullable=False, primary_key=True)  # 16 hex chars
    parent_span_id = Column(String(16), nullable=True)
    operation_name = Column(String(255), nullable=False, index=True)
    service_name = Column(String(255), nullable=False, index=True)
    start_time = Column(BigInteger, nullable=False)  # microseconds
    duration = Column(BigInteger, nullable=False)  # microseconds
    span_kind = Column(String(50), nullable=True)  # INTERNAL, SERVER, CLIENT, etc.
    status_code = Column(String(50), nullable=True)  # UNSET, OK, ERROR
    status_message = Column(Text, nullable=True)

    # Relationships
    trace = relationship("Trace", back_populates="spans")
    # Note: attributes and events use manual joins due to composite key limitations in SQLite


class SpanAttribute(Base):
    """Key-value attributes (tags) on spans."""

    __tablename__ = "span_attributes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trace_id = Column(String(32), nullable=False)
    span_id = Column(String(16), nullable=False)
    key = Column(String(255), nullable=False, index=True)
    value = Column(Text, nullable=False)
    value_type = Column(String(20), default="string")  # string, int, float, bool

    __table_args__ = (Index("idx_span_attributes_key_value", "key", "value"),)

    # Note: SQLAlchemy doesn't enforce composite foreign keys in SQLite
    # But the relationship is maintained through trace_id + span_id matching


class SpanEvent(Base):
    """Events (logs) within spans."""

    __tablename__ = "span_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trace_id = Column(String(32), nullable=False)
    span_id = Column(String(16), nullable=False)
    timestamp = Column(BigInteger, nullable=False)  # microseconds
    name = Column(String(255), nullable=False)

    # Note: SQLAlchemy doesn't enforce composite foreign keys in SQLite
    # But the relationship is maintained through trace_id + span_id matching

    # Relationships
    attributes = relationship("EventAttribute", back_populates="event", cascade="all, delete-orphan")


class EventAttribute(Base):
    """Attributes on span events."""

    __tablename__ = "event_attributes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(Integer, ForeignKey("span_events.id", ondelete="CASCADE"), nullable=False)
    key = Column(String(255), nullable=False)
    value = Column(Text, nullable=False)

    # Relationship
    event = relationship("SpanEvent", back_populates="attributes")


class ResourceAttribute(Base):
    """Resource-level attributes per trace/service."""

    __tablename__ = "resource_attributes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trace_id = Column(String(32), ForeignKey("traces.trace_id", ondelete="CASCADE"), nullable=False)
    service_name = Column(String(255), nullable=False)
    key = Column(String(255), nullable=False)
    value = Column(Text, nullable=False)

    # Relationship
    trace = relationship("Trace", back_populates="resource_attributes")


class Service(Base):
    """Fast service listing."""

    __tablename__ = "services"

    name = Column(String(255), primary_key=True)
    last_seen = Column(DateTime, default=datetime.utcnow)

    # Relationship
    operations = relationship("Operation", back_populates="service", cascade="all, delete-orphan")


class Operation(Base):
    """Fast operation listing per service."""

    __tablename__ = "operations"

    service_name = Column(
        String(255), ForeignKey("services.name", ondelete="CASCADE"), nullable=False, primary_key=True
    )
    operation_name = Column(String(255), nullable=False, primary_key=True)
    span_kind = Column(String(50), nullable=True, primary_key=True)
    last_seen = Column(DateTime, default=datetime.utcnow)

    # Relationship
    service = relationship("Service", back_populates="operations")


# Connection management
def get_engine():
    """Get or create the SQLAlchemy engine singleton."""
    global engine
    if engine is None:
        engine = create_engine(
            DATABASE_URL,
            connect_args={"check_same_thread": False},  # Allow multi-threading with SQLite
            echo=False,
        )
    return engine


def init_db():
    """Initialize the database: create all tables and indexes."""
    engine = get_engine()
    Base.metadata.create_all(engine)

    # Create session maker
    global SessionLocal
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency to get a database session.

    Usage:
        @app.get("/endpoint")
        def endpoint(db: Session = Depends(get_db)):
            ...
    """
    if SessionLocal is None:
        init_db()

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
