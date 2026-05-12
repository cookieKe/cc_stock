from sqlalchemy import Column, Integer, String, Float, Date, UniqueConstraint
from backend.database import Base


class MarketData(Base):
    __tablename__ = "market_data"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(10), index=True, nullable=False)
    trade_date = Column(Date, index=True, nullable=False)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
    amount = Column(Float, nullable=True)
    turnover = Column(Float, nullable=True)
    source = Column(String(20), default="akshare")

    __table_args__ = (
        UniqueConstraint("stock_code", "trade_date", name="uq_stock_date"),
    )
