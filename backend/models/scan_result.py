from sqlalchemy import Column, Integer, String, Float, Date, DateTime, Text
from sqlalchemy.sql import func
from backend.database import Base


class ScanResult(Base):
    __tablename__ = "scan_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scan_date = Column(Date, index=True, nullable=False)
    stock_code = Column(String(10), index=True, nullable=False)
    stock_name = Column(String(20), nullable=False)
    strategy_id = Column(Integer, nullable=False)
    strategy_name = Column(String(100), nullable=False)
    raw_score = Column(Float, nullable=False)
    weighted_score = Column(Float, nullable=False)
    rank = Column(Integer, nullable=False)
    detail = Column(Text, default="{}")
    created_at = Column(DateTime, server_default=func.now())
