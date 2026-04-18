## Test Folder

This folder contains:

- `test_file_processing.py`: file-to-text coverage for `pdf`, `docx`, `txt`, `csv`, `xlsx`, and `png`
- `test_verification_logic.py`: address/email/domain/risk regression tests
- `test_ai_processing.py`: AI fallback and provider-diagnostics tests
- `test_end_to_end_pipeline.py`: text -> AI -> verification -> summary pipeline checks
- `live_provider_smoke.py`: real network smoke test for Gemini, Groq, OpenRouter, and Companies House

Generated assets are written to `tests/generated/` automatically by the tests.
