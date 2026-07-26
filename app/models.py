from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class CommandDefinition(Base):
    """
    Tabel Master Katalog Perintah Playwright yang tersedia di sistem.
    """
    __tablename__ = "command_definitions"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True)  # Kode instruksi, misal: CLICK, TYPE_TEXT
    label = Column(String)                          # Teks label UI, misal: "Klik Elemen"
    description = Column(String, nullable=True)     # Penjelasan singkat perintah
    requires_selector = Column(Boolean, default=True) # Apakah butuh Target Selector?
    requires_value = Column(Boolean, default=False)    # Apakah butuh Input Value?
    placeholder_selector = Column(String, nullable=True) # Contoh placeholder selector
    placeholder_value = Column(String, nullable=True)    # Contoh placeholder value

class TestCase(Base):
    """
    Tabel utama yang menyimpan nama Skenario Pengujian.
    """
    __tablename__ = "test_cases"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    base_url = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    steps = relationship("TestStep", back_populates="test_case", cascade="all, delete-orphan")
    runs = relationship("TestRun", back_populates="test_case", cascade="all, delete-orphan")

class TestStep(Base):
    """
    Tabel untuk menyimpan urutan perintah per skenario.
    """
    __tablename__ = "test_steps"

    id = Column(Integer, primary_key=True, index=True)
    test_case_id = Column(Integer, ForeignKey("test_cases.id"))
    step_order = Column(Integer)
    command = Column(String) 
    target_selector = Column(String, nullable=True) 
    input_value = Column(String, nullable=True) 

    test_case = relationship("TestCase", back_populates="steps")

class TestRun(Base):
    """
    Tabel untuk merekam hasil eksekusi (History).
    """
    __tablename__ = "test_runs"

    id = Column(String, primary_key=True, index=True) 
    test_case_id = Column(Integer, ForeignKey("test_cases.id"))
    status = Column(String, default="PENDING") 
    video_url = Column(String, nullable=True)
    error_log = Column(String, nullable=True)
    executed_at = Column(DateTime, default=datetime.utcnow)

    test_case = relationship("TestCase", back_populates="runs")