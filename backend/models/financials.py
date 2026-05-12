from sqlalchemy import Column, Integer, String, Float, Date, UniqueConstraint
from backend.database import Base


class Financials(Base):
    __tablename__ = "financials"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(10), index=True, nullable=False)
    report_date = Column(Date, nullable=False)
    pe = Column(Float, nullable=True)
    pb = Column(Float, nullable=True)
    ps = Column(Float, nullable=True)
    roe = Column(Float, nullable=True)
    roa = Column(Float, nullable=True)
    revenue_growth = Column(Float, nullable=True)
    profit_growth = Column(Float, nullable=True)
    market_cap = Column(Float, nullable=True)
    source = Column(String(20), default="akshare")

    __table_args__ = (
        UniqueConstraint("stock_code", "report_date", name="uq_stock_report"),
    )
