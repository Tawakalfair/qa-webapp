from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Integer, ForeignKey, DateTime, Boolean, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relasi: 1 User bisa punya banyak Project
    projects: Mapped[list["Project"]] = relationship(
        "Project", back_populates="owner", cascade="all, delete-orphan"
    )

class Project(Base):
    __tablename__ = "projects"
    # User A dan User B bisa punya proyek bernama "Default Project", tapi tidak boleh duplikat di user yang sama
    __table_args__ = (UniqueConstraint("user_id", "name", name="uix_user_project_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False) 
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    owner: Mapped["User"] = relationship("User", back_populates="projects")
    test_cases: Mapped[list["TestCase"]] = relationship(
        "TestCase", back_populates="project", cascade="all, delete-orphan"
    )

class CommandDefinition(Base):
    __tablename__ = "command_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    requires_selector: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_value: Mapped[bool] = mapped_column(Boolean, default=False)
    placeholder_selector: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    placeholder_value: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

class TestCase(Base):
    __tablename__ = "test_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    base_url: Mapped[str] = mapped_column(String(255), nullable=True)
    test_type: Mapped[str] = mapped_column(String(30), default="REGRESSION")
    reference_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    ut_theme: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    ut_function_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    ut_action: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ut_condition_1: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ut_condition_2: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ut_classification: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    ut_how_to_test: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ut_expected_results: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    project: Mapped["Project"] = relationship("Project", back_populates="test_cases")
    steps: Mapped[list["TestStep"]] = relationship(
        "TestStep", back_populates="test_case", cascade="all, delete-orphan"
    )
    runs: Mapped[list["TestRun"]] = relationship(
        "TestRun", back_populates="test_case", cascade="all, delete-orphan"
    )

class TestStep(Base):
    __tablename__ = "test_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    test_case_id: Mapped[int] = mapped_column(
        ForeignKey("test_cases.id", ondelete="CASCADE"), nullable=False
    )
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    command: Mapped[str] = mapped_column(String(50), nullable=False)
    target_selector: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    input_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    test_case: Mapped["TestCase"] = relationship("TestCase", back_populates="steps")

class TestRun(Base):
    __tablename__ = "test_runs"

    id: Mapped[str] = mapped_column(String(50), primary_key=True, index=True)
    test_case_id: Mapped[int] = mapped_column(
        ForeignKey("test_cases.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    video_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    error_log: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    executed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    test_case: Mapped["TestCase"] = relationship("TestCase", back_populates="runs")