from sqlalchemy import Column, BigInteger, Integer, String, Text, Float, DateTime, ForeignKey, func
from pgvector.sqlalchemy import Vector

from app.core.database import Base


class UserReportChunk(Base):
    __tablename__ = "user_report_chunks"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    report_id = Column(Integer, ForeignKey("medical_reports.id", ondelete="CASCADE"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(2048))
    report_type = Column(String(100))
    hospital = Column(String(255))
    doctor = Column(String(255))
    report_date = Column(DateTime(timezone=True))
    page_number = Column(Integer)
    ocr_confidence = Column(Float)
    language = Column(String(10), default="en")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
