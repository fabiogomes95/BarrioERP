from functools import lru_cache
from typing import Literal

from pydantic import PostgresDsn, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    APP_NAME: str = "Barrio ERP"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = False
    SECRET_KEY: str
    ALLOWED_HOSTS: list[str] | None = None  # None → usa default por ambiente

    # Database
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    DATABASE_POOL_PRE_PING: bool = True

    # Onboarding
    # Chave exigida no header X-Onboarding-Secret para criar um novo tenant.
    # Sem default: a aplicação não inicia sem este valor no .env.
    ONBOARDING_SECRET: str

    # Recuperação de senha
    # Código fixo (compartilhado entre todos os usuários) que permite
    # redefinir a senha direto na tela de login, sem precisar de outro
    # admin disponível nem de e-mail/SMS configurado. Quem souber o código
    # consegue redefinir a senha de qualquer e-mail cadastrado — guarde-o
    # como uma senha mestra.
    PASSWORD_RECOVERY_CODE: str

    # Auth
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ALGORITHM: str = "HS256"

    # Pagination
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100

    # Timezone
    TIMEZONE: str = "America/Sao_Paulo"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def database_url_sync(self) -> str:
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def cors_origins(self) -> list[str]:
        """Retorna origens permitidas para CORS, com default seguro por ambiente."""
        if self.ALLOWED_HOSTS is not None:
            return self.ALLOWED_HOSTS
        if self.is_production:
            return ["http://localhost:5173", "http://localhost:8000"]
        return ["*"]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
