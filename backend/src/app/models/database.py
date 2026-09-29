"""
Database connection model for management database.

Stores database connection configurations.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, DateTime, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


class DBConnection(Base):
    """Database connection configuration model."""

    __tablename__ = "db_connections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    db_type: Mapped[str] = mapped_column(String(50), nullable=False)
    host: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    port: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    database_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    password: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    connection_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    extra_params: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    falkordb_graph_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def set_password(self, plain_password: str) -> None:
        """Store password as-is."""
        if plain_password:
            self.password = plain_password

    def get_password(self) -> Optional[str]:
        """Return stored password."""
        return self.password

    def to_dict(self, include_password: bool = False) -> dict:
        """Convert model to dictionary."""
        result = {
            "id": self.id,
            "name": self.name,
            "db_type": self.db_type,
            "host": self.host,
            "port": self.port,
            "database_name": self.database_name,
            "username": self.username,
            "connection_url": self.connection_url,
            "extra_params": self.extra_params,
            "falkordb_graph_id": self.falkordb_graph_id,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_password:
            result["password"] = self.get_password()
        return result


class BusinessMetric(Base):
    """Business metric definitions for a database connection."""

    __tablename__ = "business_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connection_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    formula: Mapped[str] = mapped_column(String(1000), nullable=False)
    related_table: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    filter_condition: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "connection_id": self.connection_id,
            "name": self.name,
            "formula": self.formula,
            "related_table": self.related_table,
            "filter_condition": self.filter_condition,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class QAPair(Base):
    """Q&A pairs for few-shot learning in NL2SQL."""

    __tablename__ = "qa_pairs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connection_id: Mapped[int] = mapped_column(Integer, nullable=False)
    question: Mapped[str] = mapped_column(String(2000), nullable=False)
    sql: Mapped[str] = mapped_column(String(4000), nullable=False)
    query_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    difficulty_level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=3)
    verified: Mapped[bool] = mapped_column(default=False)
    inject_nl2sql: Mapped[bool] = mapped_column(default=False)
    success_rate: Mapped[float] = mapped_column(default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "connection_id": self.connection_id,
            "question": self.question,
            "sql": self.sql,
            "query_type": self.query_type,
            "difficulty_level": self.difficulty_level,
            "verified": self.verified,
            "inject_nl2sql": self.inject_nl2sql,
            "success_rate": self.success_rate,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
