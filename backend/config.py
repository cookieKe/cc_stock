from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./stock.db"
    akshare_enabled: bool = True
    tushare_enabled: bool = False
    tushare_token: str = ""
    scan_batch_size: int = 50
    scan_schedule_hour: int = 15
    scan_schedule_minute: int = 30
    risk_free_rate: float = 0.025
    benchmark_symbol: str = "000300"
    im_webhook_url: str = ""
    im_bot_type: str = "wecom"
    api_retry_count: int = 3
    api_retry_backoff: float = 1.5

    model_config = {"env_file": ".env.dev", "extra": "ignore"}


settings = Settings()
