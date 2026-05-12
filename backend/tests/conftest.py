import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from backend.database import Base, get_db
from backend.main import app

TEST_DB_URL = "sqlite:///./test_stock.db"


@pytest.fixture(scope="function")
def db_session():
    engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def sample_stocks(db_session):
    from backend.models.stock import Stock
    stocks = [
        Stock(code="000001", name="平安银行", exchange="SZ", is_active=True),
        Stock(code="000002", name="万科A", exchange="SZ", is_active=True),
        Stock(code="600000", name="浦发银行", exchange="SH", is_active=True),
        Stock(code="000003", name="PT金田A", exchange="SZ", is_active=False),
    ]
    for s in stocks:
        db_session.add(s)
    db_session.commit()
    return stocks


@pytest.fixture(scope="function")
def sample_market_data(db_session, sample_stocks):
    from backend.models.market_data import MarketData
    from datetime import date, timedelta
    entries = []
    for i, s in enumerate(sample_stocks[:3]):
        for d in range(5):
            dt = date.today() - timedelta(days=d)
            entries.append(MarketData(
                stock_code=s.code,
                trade_date=dt,
                open=10.0 + i + d * 0.1,
                high=11.0 + i + d * 0.1,
                low=9.0 + i + d * 0.1,
                close=10.5 + i + d * 0.1,
                volume=1000000 * (i + 1),
                amount=10500000 * (i + 1),
                turnover=2.0 + i,
            ))
    for e in entries:
        db_session.add(e)
    db_session.commit()
    return entries
