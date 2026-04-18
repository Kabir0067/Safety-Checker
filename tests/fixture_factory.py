from __future__ import annotations

from pathlib import Path
import textwrap
from typing import Dict

import pandas as pd
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent.parent
GENERATED_DIR = ROOT / "tests" / "generated"

SAFE_CONTRACT_TEXT = """EMPLOYMENT AGREEMENT

This Employment Agreement is made on 10 April 2026 between TESCO PLC (Company No. 00445790), registered office Tesco House, Shire Park, Kestrel Way, Welwyn Garden City, AL7 1GA, United Kingdom, and Alex Morgan.

Position: Data Coordinator
Salary: GBP 36,000 per year
Contact: people.services@tesco.com
Phone: +44 1992 632222
Website: https://www.tesco.com

Contract Reference: TSCO-TEST-2026-01
"""

SUSPICIOUS_CONTRACT_TEXT = """REMOTE JOB OFFER AGREEMENT

No interview required.
Urgent payment is required to secure your job.
Send money before work to confirm onboarding.
A confidential fee of GBP 350 must be paid today.
Contact: onboarding@quickstart-global-example.co.uk
Phone: +44 20 7946 0958
Website: quickstart-global-example.co.uk
Reference: RJO-TEST-2026-01
"""


def _pick_font(size: int) -> ImageFont.ImageFont:
    font_candidates = [
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/calibri.ttf"),
        Path("C:/Windows/Fonts/segoeui.ttf"),
    ]
    for candidate in font_candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def ensure_test_assets() -> Dict[str, Path]:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)

    safe_txt = GENERATED_DIR / "safe_contract.txt"
    suspicious_txt = GENERATED_DIR / "suspicious_contract.txt"
    safe_csv = GENERATED_DIR / "safe_contract.csv"
    safe_xlsx = GENERATED_DIR / "safe_contract.xlsx"
    safe_png = GENERATED_DIR / "safe_contract.png"

    safe_txt.write_text(SAFE_CONTRACT_TEXT, encoding="utf-8")
    suspicious_txt.write_text(SUSPICIOUS_CONTRACT_TEXT, encoding="utf-8")

    table = pd.DataFrame(
        [
            {
                "contract_reference": "TSCO-TEST-2026-01",
                "company_name": "TESCO PLC",
                "company_number": "00445790",
                "registered_address": "Tesco House, Shire Park, Kestrel Way, Welwyn Garden City, AL7 1GA, United Kingdom",
                "contact_email": "people.services@tesco.com",
                "website": "tesco.com",
                "contract_text": SAFE_CONTRACT_TEXT.replace("\n", " "),
            }
        ]
    )
    table.to_csv(safe_csv, index=False)
    table.to_excel(safe_xlsx, index=False)

    wrapped_blocks = []
    for block in SAFE_CONTRACT_TEXT.strip().split("\n\n"):
        wrapped_blocks.append(textwrap.fill(block, width=62))
    image_text = "\n\n".join(wrapped_blocks)

    image = Image.new("RGB", (2600, 1900), color="white")
    draw = ImageDraw.Draw(image)
    font = _pick_font(42)
    draw.multiline_text((80, 80), image_text, fill="black", font=font, spacing=16)
    image.save(safe_png)

    return {
        "safe_txt": safe_txt,
        "suspicious_txt": suspicious_txt,
        "safe_csv": safe_csv,
        "safe_xlsx": safe_xlsx,
        "safe_png": safe_png,
        "sample_docx": ROOT / "sample_contracts" / "TEST_SAFE_CONTRACT.docx",
        "sample_pdf": ROOT / "sample_contracts" / "TEST_SUSPICIOUS_CONTRACT.pdf",
    }
