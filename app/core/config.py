from pydantic import BaseSettings


class Settings(BaseSettings):
    app_env: str = "local"

    class Config:
        env_file = ".env"


settings = Settings()
