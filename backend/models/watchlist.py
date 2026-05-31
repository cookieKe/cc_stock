from sqlalchemy import Column, Integer, String, Float, Date, DateTime, Boolean
from sqlalchemy.sql import func
from backend.database import Base


class Watchlist(Base):
    __tablename__ = "watchlist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(10), index=True, nullable=False)
    stock_name = Column(String(20), nullable=False)
    added_date = Column(Date, nullable=False)
    added_price = Column(Float, nullable=False)
    latest_price = Column(Float, nullable=True)
    cumulative_return = Column(Float, nullable=True)
    holding_days = Column(Integer, nullable=True)
    highest_price = Column(Float, nullable=True)
    lowest_price = Column(Float, nullable=True)
    is_active = Column(Boolean, default=True)
    target_price = Column(Float, nullable=True, comment='预期价')
    stop_loss_price = Column(Float, nullable=True, comment='止损价')
    sell_price = Column(Float, nullable=True, comment='卖出价')
    notes = Column(String(500), default="")
    source = Column(String(50), default="手动")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
