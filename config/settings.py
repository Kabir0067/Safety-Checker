import os
from dotenv import load_dotenv


load_dotenv()


class Settings:
    BOT_API = os.getenv("BOT_API")

    PGUSER = os.getenv("PGUSER")
    PGPASSWORD = os.getenv("PGPASSWORD")
    PGDATABASE = os.getenv("PGDATABASE")
    PGHOST = os.getenv("PGHOST")
    PGPORT = int(os.getenv("PGPORT", 5432))

    FEEDBACK_EMAIL = os.getenv("FEEDBACK_EMAIL")
    SMTP_USER = os.getenv("SMTP_USER")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
    SMTP_HOST = os.getenv("SMTP_HOST")
    SMTP_PORT = int(os.getenv("SMTP_PORT", 587))

    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    COMPANIES_HOUSE_API = os.getenv("COMPANIES_HOUSE_API")


settings = Settings()

