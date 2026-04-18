from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from functions.ai_processing import AsyncAiProcessing, Provider
from functions.file_processing import FileConvertToText
from functions.utils import AsyncCheckAnalysisContract
from tests.fixture_factory import ensure_test_assets


async def _provider_probe(contract_text: str, provider_name: str) -> dict:
    processor = AsyncAiProcessing(contract_text)
    provider = Provider(provider_name)
    models = await processor._candidate_models(provider)
    if not models:
        return {
            "provider": provider_name,
            "free_only_mode": processor.free_only_mode,
            "status": "missing_or_disabled",
            "model": None,
        }

    attempted = []
    for model in models:
        if provider_name == "gemini":
            result = await processor._call_gemini(model)
        else:
            result = await processor._call_openai_compatible(provider, model)

        ok = processor._is_valid_result(result)
        attempted.append({"model": model, "status": "success" if ok else "failed"})
        if ok:
            return {
                "provider": provider_name,
                "free_only_mode": processor.free_only_mode,
                "status": "success",
                "model": model,
                "result_keys": sorted((result or {}).keys()),
                "attempted": attempted,
            }

    return {
        "provider": provider_name,
        "free_only_mode": processor.free_only_mode,
        "status": "failed",
        "model": models[0],
        "result_keys": [],
        "attempted": attempted,
    }


async def main() -> None:
    assets = ensure_test_assets()
    converter = FileConvertToText()
    text_result = await converter.convert_to_text(str(assets["sample_docx"]))
    contract_text = text_result.get("text") or ""

    provider_checks = []
    for provider_name in ("gemini", "groq", "openrouter"):
        provider_checks.append(await _provider_probe(contract_text, provider_name))

    companies_house = {}
    async with AsyncCheckAnalysisContract({"Company Name": "TESCO PLC", "Company Number": "00445790"}) as analysis:
        _, status_code = await analysis._fetch_company_profile("00445790")
        companies_house = {
            "provider": "companies_house",
            "status_code": status_code,
            "status": "success" if status_code == 200 else "failed",
        }

    print(json.dumps({"providers": provider_checks, "companies_house": companies_house}, indent=2))
    await AsyncAiProcessing.aclose()


if __name__ == "__main__":
    asyncio.run(main())
