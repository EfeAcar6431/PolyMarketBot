from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    polymarket_private_key: str = ""
    openai_api_key: str = ""
    odds_api_key: str = ""
    polymarket_chain_id: int = 137
    agent_scan_interval: int = 300
    max_position_size: float = 50.0
    max_total_exposure: float = 500.0
    max_daily_loss: float = 100.0
    trade_cooldown_seconds: int = 60
    database_url: str = "data.db"

    model_config = {"env_file": "../.env", "env_file_encoding": "utf-8"}


settings = Settings()
