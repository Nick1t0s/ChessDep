from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode


class Settings(BaseSettings):
    database_url: str
    redis_url: str
    cookie_secure: bool = True
    allowed_origins: Annotated[list[str], NoDecode] = []
    session_ttl_days: int = 30
    testing: bool = False
    frontend_dir: str = "/frontend"

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def cookie_name(self) -> str:
        return "__Host-sid" if self.cookie_secure else "sid"


settings = Settings()
