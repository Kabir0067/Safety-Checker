# Contract Safety Checker — Telegram Bot

Employment contract fraud detection and reliability analysis for the UK. Upload a contract in multiple formats or paste text, the bot extracts key details, checks them via Companies House and local rules, scores the risk, and returns a clear verdict: Safe / Warning / Unsafe.

This README reflects the current codebase in this repository (uses pyTelegramBotAPI `AsyncTeleBot`) and follows the provided technical specification.

## Key Features
- **Multi-format intake**: .pdf, .doc/.docx, .xls/.xlsx, .csv, .jpg/.jpeg/.png/.bmp/.tiff/.webp, .txt (max 10 MB)
- **OCR for images/scans**: OpenCV + Tesseract with adaptive preprocessing and multiple psm/oem strategies
- **Structured data extraction**: AI (Google Gemini API) prompts to extract company info, contact details, dates, etc.
- **Companies House verification**: Company Number/Name checks, status validation, officers lookup (async via aiohttp)
- **Local database caching**: PostgreSQL for companies, user checks, suspicious companies
- **Scoring system**: Rule-based scoring to produce Safe/Warning/Unsafe
- **Multilingual UX**: RU/TJ/EN
- **Feedback**: Sends user feedback via SMTP email

## Tech Stack
- Python 3.11+
- Telegram: pyTelegramBotAPI `AsyncTeleBot` (telebot)
- AI: Google Gemini API (via REST). Optional: Groq API fallback (Llama/Mixtral)
- OCR & Docs: EasyOCR, OpenCV, Pillow, python-docx, aspose-words, pandas (CSV/Excel)
- HTTP: aiohttp
- DB: PostgreSQL + SQLAlchemy Async + asyncpg
- Env: python-dotenv

## Project Structure
```
Safety Checker/
  main.py                      # Entrypoint with robust polling loop
  bot/
    bot.py                     # AsyncTeleBot, shared state, file dir, converter
    handlers.py                # Commands: start, help, about, check, report, language, feedback
  config/
    settings.py                # Reads environment variables via dotenv
  functions/
    file_processing.py         # Conversion to text, OCR pipelines, size/format guards
    ai_processing.py           # Gemini API calls and extraction JSON schema
    utils.py                   # Companies House checks, scoring logic, domain/phone validation
  database/
    connection.py              # Async engine/session factory
    models.py                  # users, companies, user_checks, suspicious_companies
    queries.py                 # CRUD helpers & history fetch
    migrate.py                 # Create tables script
  files/                       # Uploaded files storage (gitignored)
  logs/                        # Error logs for processors (gitignored)
  .env                         # Environment variables (not committed)
  requirements.txt             # Project dependencies
  README.md
```

## Environment Variables (.env)
Create a `.env` file in the project root:
```
# Telegram
BOT_API=123456:telegram-bot-token

# PostgreSQL
PGUSER=postgres
PGPASSWORD=postgres
PGDATABASE=contract_checker
PGHOST=127.0.0.1
PGPORT=5432

# SMTP feedback
FEEDBACK_EMAIL=owner@example.com
SMTP_USER=smtp-user@example.com
SMTP_PASSWORD=your-smtp-password
SMTP_HOST=smtp.example.com
SMTP_PORT=587

# External APIs
GEMINI_API_KEY=your-google-gemini-api-key
GROQ_API_KEY=your-groq-api-key               # optional fallback
COMPANIES_HOUSE_API=your-companies-house-api-key

# Optional: Tesseract config if needed
# TESSDATA_PREFIX=C:\\Program Files\\Tesseract-OCR\\tessdata
```

## Installation
1. Install Python 3.11+ and PostgreSQL.
2. Install system dependency: Tesseract OCR
   - Windows: Install Tesseract OCR (add to PATH). Example: C:\Program Files\Tesseract-OCR
3. Create and activate a virtual environment.
4. Install Python deps:
   ```bash
   pip install -r requirements.txt
   ```
5. Create `.env` with the variables above.
6. Initialize database tables:
   ```bash
   python database/migrate.py
   ```

Note: The code uses `aspose-words` for PDF->DOCX conversion fallback. Ensure the package installs successfully (it is available from pip). For pure open-source-only environments, you can later replace this with alternative pipelines.

## Running the Bot
```bash
python main.py
```

`main.py` sets bot commands and starts `infinity_polling` with resilience against transient network errors.

## Telegram Commands
- **/start** — Welcome and quick intro
- **/help** — How to use, supported formats, tips
- **/about** — Features and approach
- **/check** — Start a new contract check; send a file or paste text
- **/report** — View history of checks and reports (as implemented in handlers)
- **/language** — RU / TJ / EN selection
- **/feedback** — Send feedback via email

## Supported Files and Limits
- Formats: .pdf, .doc/.docx, .xls/.xlsx, .csv, .jpg/.jpeg/.png/.bmp/.tiff/.webp, .txt
- Max file size: 10 MB (enforced in `functions/file_processing.py`)
- Tips:
  - Text-based PDFs/DOCX process faster than images
  - Images run through OCR and may take longer

## Data Extraction
- AI prompt (Gemini) extracts the following fields as JSON:
  - Contract Number
  - Company Name
  - Company Number
  - Registered Address
  - Contact Details
  - Responsible Person Full Name
  - Contract Date (normalized to YYYY-MM-DD when present)
  - Website Domain (normalized without scheme/www)
  - Suspicious Phrases Found
  - Text Style (professional/template-like/unprofessional)

## Verification Logic (Companies House + Local DB)
- If `Company Number` is present, fetch profile and status; cache in `companies` table
- If only `Company Name` is present, search Companies House and optionally fetch profile for an exact active match
- Officer check for responsible person
- Local DB used for caching and resilience when API is slow/unavailable

## Scoring System
Rules computed in `functions/utils.py` produce a total score and label:

1. Contract Number present → +10
2. Company Number verified via Companies House (active) → +30
3. Company Name resolved (active company) → +30
4. Contact details valid (phone/email/domain consistency) → +10 / −10
5. Suspicious phrases/blacklist → −20 (or more if blacklisted)
6. Text style (professional/template/unprofessional) → +10 / 0 / −10
7. Website domain exists and matches company → +10 / −10
8. Data match (company/address) with Companies House → up to +20 (applied via checks)
9. Responsible person present/verified → up to +10
10. Contract date recency (≤ 30 days) → +10 / −10

Interpretation:
- 80–100 → ✅ Safe
- 50–79 → ⚠️ Warning (manual review recommended)
- <50 → 🚨 Unsafe

## Database Schema
- `users`: Telegram users and language
- `companies`: cached Companies House data (name, number, address, status, website_domain, score)
- `user_checks`: history of checks with extracted fields, total score, rating, and detailed scores
- `suspicious_companies`: locally curated blacklist with evidence/source

Initialize tables:
```bash
python database/migrate.py
```

## Security and Rate Limiting
- File size/type validation before processing
- Optional throttling via user state and timeouts during `/check`
- Companies House API requests are limited and use small concurrency and caching
- Personal data is not stored beyond what’s required (see models)

## Deployment
- Any Python-capable host (e.g., VPS, Railway, Heroku with worker dyno)
- Requires persistent Postgres and outbound HTTPS to Companies House and Google APIs
- Configure environment variables on the platform

## Roadmap / Notes
- Current implementation uses `pyTelegramBotAPI` (`AsyncTeleBot`). The original spec mentions `aiogram`; migration is possible later.
- Optional: Generate PDF reports with `reportlab`/`weasyprint` (not implemented in this codebase yet).
- Optional: Scheduled sync of Companies House bulk data for faster local lookups.

## Admin Notes
- Add yourself as admin (feature present if admin handlers are enabled in code). First, obtain your Telegram ID by sending any message to the bot and logging it, or use a dedicated `/getid` handler if present.
- Then add the ID to the admins table (see database/migrate or use in-bot command if implemented).
- Use admin-only commands to retrieve reports if available.

## Troubleshooting
- aspose-words: Requires binary components from pip; if installation fails, ensure you are on a supported Python/OS version or replace PDF conversion with another library.
- EasyOCR model download: First run may download models; allow network access. To disable GPU, it is already set to CPU by default.
- Tesseract: Not required when using EasyOCR pipeline. If you add pytesseract, install Tesseract and set `TESSDATA_PREFIX` accordingly on Windows.
- Companies House API: Set COMPANIES_HOUSE_API; requests are rate-limited. The code caches results in PostgreSQL.
- SMTP: Ensure SMTP settings are correct to receive feedback via `/feedback`.

## RU: Краткая инструкция
- Отправьте команду `/check` и загрузите файл (.PDF/.DOCX/.XLSX/.CSV/.JPG/.PNG) или вставьте текст
- Дождитесь результата: бот извлечёт данные, проверит компанию и рассчитает баллы
- Итог: ✅ Безопасно | ⚠️ Требует внимания | 🚨 Рисковано

## TJ: Дастури кӯтоҳ
- Фармони `/check`–ро истифода баред ва файлро бор кунед ё матнро ворид намоед
- Натиҷа пас аз таҳлил: ✅ Бехатар | ⚠️ Бо эҳтиёт | 🚨 Хатарнок

---
Maintainers: set `FEEDBACK_EMAIL` to receive in-bot feedback via `/feedback`.
