from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean
from backend.database import Base


class Stock(Base):
    __tablename__ = "stocks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(10), unique=True, index=True, nullable=False)
    name = Column(String(20), nullable=False)
    exchange = Column(String(4), default="SH")
    industry = Column(String(50), default="")
    listed_date = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    updated_at = Column(DateTime, nullable=True)
