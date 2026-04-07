21 commit
# Contract Safety Checker

Contract Safety Checker is a Telegram bot + admin panel that analyzes employment contracts, verifies company identity, and returns a verification-based decision (`SAFE`, `WARNING`, `HIGH_RISK`).

This repository is suitable for both:
- a real prototype for contract pre-screening;
- a graduation (thesis) project with practical implementation.

## 1) What the system does

1. Accepts contract input as file or text.
2. Extracts readable text (native parsing + OCR fallback).
3. Uses AI to extract structured contract fields.
4. Verifies company data via Companies House (number or name) + local cache.
5. Checks status, address match, email/domain signals, and template reuse.
6. Calculates identity confidence from verified signals and applies decision rules.
7. Saves results in SQLite and shows history/report in Telegram.

## 2) Core features

- Multi-format input: `.pdf`, `.docx`, `.xls`, `.xlsx`, `.csv`, `.txt`, images (`.jpg`, `.jpeg`, `.png`, `.bmp`, `.tiff`, `.webp`, `.jfif`)
- OCR pipeline (Tesseract + OpenCV preprocessing)
- AI extraction (Gemini + Groq + OpenRouter with automatic fallback)
- Companies House verification (number/name, status, address match)
- Email/domain validation (free providers + mismatch detection)
- Contract template hashing and reuse detection
- Verification-first risk engine with rule-based decisions
- Local data store (SQLite via SQLAlchemy)
- Telegram interface in 3 languages (`ru`, `tj`, `en`)
- Django admin panel for database monitoring
- Feedback sending via SMTP

## 3) Tech stack

- Python 3.11+
- Telegram: `pyTelegramBotAPI` (`AsyncTeleBot`)
- AI APIs: Google Gemini, Groq, OpenRouter (optional fallback)
- OCR and document processing: `pytesseract`, `opencv-python`, `PyMuPDF`, `pdf2image`, `python-docx`, `pandas`
- Data layer: `SQLAlchemy` + `aiosqlite` (SQLite)
- Admin panel: `Django`

## 4) Project structure

```text
Safety-Checker/
  main.py                     # Starts bot + Django admin together
  manage.py                   # Django management
  README.md
  requirements.txt
  .env

  bot/
    bot.py                    # Bot init, global constants/state
    handlers.py               # Telegram command handlers and workflow

  functions/
    file_processing.py        # PDF/DOCX/IMG/TXT/XLSX -> text pipeline
    ai_processing.py          # AI prompt + response normalization
    utils.py                  # Verification rules + scoring

  database/
    connection.py             # Async SQLite engine/session
    models.py                 # SQLAlchemy models
    queries.py                # CRUD/query functions
    migrate.py                # Creates SQLAlchemy tables
    app.db                    # SQLite database file

  panel/
  panel_app/                  # Django admin mapping for existing tables

  logs/                       # Runtime logs
  files/                      # Uploaded files (runtime)
  tmp/                        # OCR/intermediate temp files
```

## 5) Environment variables

Create a `.env` file in project root:

```env
# Required
BOT_API=123456789:telegram_bot_token
GEMINI_API_KEY=your_gemini_key

# Optional fallback AI
GROQ_API_KEY=your_groq_key
OPENROUTER_API_KEY=your_openrouter_key
OPENROUTER_APP_URL=https://your-app.example
OPENROUTER_APP_NAME=Safety-Checker

# Company verification API (recommended)
COMPANIES_HOUSE_API=your_companies_house_key

# SMTP (optional; required only for /feedback)
SMTP_USER=example@mail.com
SMTP_PASSWORD=your_password
SMTP_HOST=smtp.example.com
SMTP_PORT=587
FEEDBACK_EMAIL=owner@mail.com

# Django/admin options
DJANGO_SECRET_KEY=change-me
DJANGO_DEBUG=1
DJANGO_ALLOWED_HOSTS=*
DJANGO_TIME_ZONE=Asia/Dushanbe

# Auto-created admin user (first run)
DJANGO_ADMIN_USER=admin_checker
DJANGO_ADMIN_PASS=change_this_password
DJANGO_ADMIN_EMAIL=admin@example.com

# Admin server networking (main.py)
ADMIN_HOST=0.0.0.0
ADMIN_PORT=8001
ADMIN_PUBLIC_HOST=192.168.1.10
ADMIN_OPEN_FIREWALL=1

# Optional OCR override (Windows)
# TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
```

Notes:
- Backward compatibility is kept for old keys: `GEMINI_AI_API_KEY`, `GROQ_AI_API_KEY`, `OPEN_ROUTER`, `OPEN_ROUTER_API_KEY`.
- Maximum upload size is `10 MB`.

## 6) Installation

### 6.1 System prerequisites

- Python 3.11+
- Tesseract OCR installed
- Poppler (`pdftoppm`) for PDF-to-image fallback

Windows:
- Install Tesseract and optionally set `TESSERACT_CMD`
- Install Poppler and add its `bin` directory to `PATH`

Linux (example):

```bash
sudo apt-get update
sudo apt-get install -y tesseract-ocr poppler-utils
```

### 6.2 Python setup

```bash
python -m venv .venv
.venv\Scripts\activate         # Windows
pip install -r requirements.txt
```

### 6.3 Database initialization

```bash
python database/migrate.py
python manage.py migrate --noinput
```

## 7) Run the project

Main start command:

```bash
python main.py
```

`main.py` does:
- SQLAlchemy table init check;
- Django migrations;
- superuser ensure/create;
- starts Django admin and Telegram bot in one process manager.

After launch, admin URLs are printed in console.

## 8) Telegram commands

- `/start` - welcome + intro
- `/help` - usage guide
- `/about` - project details
- `/check` - upload file or send contract text
- `/report` - show personal check history
- `/language` - switch RU/TJ/EN
- `/feedback` - send feedback email
- `/buttons` - show inline main menu

## 9) Verification model (summary)

The system now follows a verification-first pipeline:

1. Extract the core contract identity fields needed for verification.
2. Verify the employer via Companies House using company number first, otherwise company name.
3. Enforce UK-only validation and compare the contract company name against the official record with a strict `>= 90%` similarity threshold.
4. Compare the contract address against the official registered address.
5. Check whether the contact email domain matches the known company domain and flag free email providers.
6. Calculate a light `identity_score` for confidence display only.
7. Always return a structured result with `SAFE`, `WARNING`, or `HIGH_RISK` plus explanation and key issues.

Identity confidence:
- `+50` verified active company
- `+20` address match (`>=70%` similarity)
- `+20` domain match
- `-20` free email provider
- `-20` domain mismatch

Hard risk rules:
- missing company name -> `HIGH_RISK`
- company not found in UK registry -> `HIGH_RISK`
- company is not UK-registered -> `HIGH_RISK`
- company name does not closely match official records -> `HIGH_RISK`
- dissolved or liquidation status -> `HIGH_RISK`

Warning rules:
- domain mismatch
- address mismatch
- free email provider
- missing employer email and address
- company lookup failure

Safe rule:
- company verified and no major warning flags

## 10) Data and security

- Data is stored locally in `database/app.db`.
- Files are processed in runtime folders (`files/`, `tmp/`) and cleanup is applied in workflow.
- External calls are made only to configured APIs (Gemini/Groq/Companies House/SMTP).
- For production: set strong admin password and restrict `DJANGO_ALLOWED_HOSTS`.

## 11) Verification and smoke test

Quick checks:

```bash
python -m py_compile main.py
python -m unittest tests.test_verification_logic -v
```

Then run:

```bash
python main.py
```

Test `/check` with:
- a contract that includes a company number;
- a contract with only company name;
- an email from a free provider (gmail/yahoo);
- a mismatching address.

## 12) Troubleshooting

- `BOT_API is not configured`:
  - Set `BOT_API` in `.env`.
- OCR fails:
  - Confirm `tesseract` installation and `TESSERACT_CMD` path.
- PDF OCR fallback fails:
  - Install Poppler (`pdftoppm`).
- AI extraction is empty:
  - Check `GEMINI_API_KEY` and API quota.
- Company checks fail:
  - Set valid `COMPANIES_HOUSE_API` key.

## 13) Current status and next improvements

Current state:
- Core flow is working: input -> extraction -> verification -> decision -> report history.

Recommended roadmap:
- Add automated tests for scoring and parsers.
- Add explicit role-based admin permissions.
- Add report export (PDF/CSV).
- Add queue/worker mode for heavy OCR tasks.

## 14) Portfolio presentation checklist

For portfolio/demo, include these screenshots:
- `[SCREENSHOT: Telegram /start and /check flow]`
- `[SCREENSHOT: File upload and result summary]`
- `[SCREENSHOT: Detailed /report page]`
- `[SCREENSHOT: Django admin (users, companies, checks)]`
- `[SCREENSHOT: Logs and runtime console]`

## 15) License

Educational and research use. Add your preferred open-source license if needed.
