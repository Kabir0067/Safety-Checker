from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from functions.ai_processing import AsyncAiProcessing
from functions.file_processing import FileConvertToText
from functions.utils import AsyncCheckAnalysisContract
from tests.fixture_factory import ensure_test_assets


async def _run_one(converter: FileConvertToText, label: str, path: Path) -> dict:
    text_result = await converter.convert_to_text(str(path))
    text = text_result.get("text") or ""
    if text_result.get("status") != "success":
        return {"asset": label, "status": "file_failed", "details": text_result}

    ai = AsyncAiProcessing(text)
    ai_result = await ai.get_answer_json_dict()
    if not ai_result:
        return {"asset": label, "status": "ai_failed", "ai": ai.get_diagnostics()}

    async with AsyncCheckAnalysisContract(ai_result, raw_contract_text=text) as analysis:
        report = await analysis.get_detailed_report()

    return {
        "asset": label,
        "status": "success",
        "file_source": text_result.get("metadata", {}).get("source"),
        "text_length": len(text),
        "ai_provider": ai.get_diagnostics().get("successful_provider"),
        "ai_model": ai.get_diagnostics().get("successful_model"),
        "risk_level": report.get("risk_level"),
        "identity_score": report.get("identity_score"),
        "company_name": ai_result.get("Company Name"),
        "email_domain": report.get("email_domain"),
        "address_status": report.get("address_status"),
        "domain_status": report.get("domain_status"),
    }


async def main() -> None:
    assets = ensure_test_assets()
    converter = FileConvertToText()
    asset_order = [
        ("sample_docx", assets["sample_docx"]),
        ("sample_pdf", assets["sample_pdf"]),
        ("safe_txt", assets["safe_txt"]),
        ("safe_csv", assets["safe_csv"]),
        ("safe_xlsx", assets["safe_xlsx"]),
        ("safe_png", assets["safe_png"]),
    ]

    results = []
    for label, path in asset_order:
        results.append(await _run_one(converter, label, path))

    print(json.dumps(results, indent=2))
    await AsyncAiProcessing.aclose()


if __name__ == "__main__":
    asyncio.run(main())
