from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    NEWSAPI_KEY: str
    GOOGLE_API_KEY: str
    OPENAI_API_KEY: str
    LINE_CHANNEL_ACCESS_TOKEN: str
    LINE_CHANNEL_SECRET: str
    ADMIN_LINE_IDS: str
    GOOGLE_CREDENTIALS_JSON: str
    BASE_URL: str
    STRIPE_API_KEY: str
    STRIPE_ENDPOINT_SECRET: str
    STRIPE_PRICE_ID: str
    DB_URI: str
    USER_REGISTRATION_REQUIRED: bool
    DATABASE_URL: str
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    DEBUG: bool = True
    ADMIN_API_KEY: str

    class Config:
        env_file = ".env"
        extra = "allow"

settings = Settings()
