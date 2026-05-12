from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.database import init_db
from backend.scheduler import start_scheduler, stop_scheduler

app = FastAPI(title="A股股票推荐系统", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()
    start_scheduler()


@app.on_event("shutdown")
def on_shutdown():
    stop_scheduler()


from backend.api.stocks import router as stocks_router
from backend.api.charts import router as charts_router
from backend.api.strategies import router as strategies_router
from backend.api.scans import router as scans_router
from backend.api.watchlist import router as watchlist_router
from backend.api.notifications import router as notifications_router
from backend.api.stats import router as stats_router

app.include_router(stocks_router)
app.include_router(charts_router)
app.include_router(strategies_router)
app.include_router(scans_router)
app.include_router(watchlist_router)
app.include_router(notifications_router)
app.include_router(stats_router)


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "0.1.0"}
