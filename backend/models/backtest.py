from sqlalchemy import Column, Integer, String, Float, Date, DateTime, Text
from sqlalchemy.sql import func
from backend.database import Base


class Backtest(Base):
    __tablename__ = "backtests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id = Column(Integer, index=True, nullable=False)
    strategy_name = Column(String(100), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    total_return = Column(Float, nullable=False)
    annual_return = Column(Float, nullable=True)
    sharpe_ratio = Column(Float, nullable=True)
    max_drawdown = Column(Float, nullable=True)
    win_rate = Column(Float, nullable=True)
    profit_loss_ratio = Column(Float, nullable=True)
    benchmark_return = Column(Float, nullable=True)
    alpha = Column(Float, nullable=True)
    information_ratio = Column(Float, nullable=True)
    daily_nav = Column(Text, default="[]")
    trades = Column(Text, default="[]")
    created_at = Column(DateTime, server_default=func.now())
