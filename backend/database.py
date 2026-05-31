from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from backend.config import settings

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
    echo=False,
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from backend.models import stock, market_data, financials, strategy, scan_result, watchlist, backtest, notification  # noqa: F401
    Base.metadata.create_all(bind=engine)
    # 迁移: watchlist 新增 source 列
    try:
        with engine.begin() as conn:
            if "sqlite" in settings.database_url:
                conn.execute(text("ALTER TABLE watchlist ADD COLUMN source VARCHAR(50) DEFAULT '手动'"))
            else:
                conn.execute(text("ALTER TABLE watchlist ADD COLUMN IF NOT EXISTS source VARCHAR(50) DEFAULT '手动'"))
    except Exception:
        pass
    # 迁移: watchlist 新增 target_price / stop_loss_price / sell_price
    for col_name in ['target_price', 'stop_loss_price', 'sell_price']:
        try:
            with engine.begin() as conn:
                if "sqlite" in settings.database_url:
                    conn.execute(text(f"ALTER TABLE watchlist ADD COLUMN {col_name} FLOAT"))
                else:
                    conn.execute(text(f"ALTER TABLE watchlist ADD COLUMN IF NOT EXISTS {col_name} FLOAT"))
        except Exception:
            pass
