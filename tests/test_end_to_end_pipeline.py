from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from bot.handlers import _build_pretty_summary
from functions.ai_processing import AsyncAiProcessing
from functions.file_processing import FileConvertToText
from functions.utils import AsyncCheckAnalysisContract
from tests.fixture_factory import SAFE_CONTRACT_TEXT, SUSPICIOUS_CONTRACT_TEXT, ensure_test_assets


class EndToEndPipelineTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.assets = ensure_test_assets()

    async def asyncTearDown(self) -> None:
        await AsyncAiProcessing.aclose()

    async def test_safe_text_pipeline_reaches_summary(self) -> None:
        converter = FileConvertToText()
        text_result = await converter.convert_to_text(str(self.assets["safe_txt"]))
        contract_text = text_result["text"]

        ai = AsyncAiProcessing(contract_text)
        with patch.object(ai, "_candidate_models", new=AsyncMock(return_value=[])):
            ai_result = await ai.get_answer_json_dict()

        async def fake_verify_company(self) -> None:
            self.company_verified = True
            self.company_status = "active"
            self.official_company_name = "TESCO PLC"
            self.official_company_number = "00445790"
            self.official_registered_address = "Tesco House, Shire Park, Kestrel Way, Welwyn Garden City, AL7 1GA, United Kingdom"
            self.official_country = "UK"
            self.db_company = {"website_domain": "tesco.com", "country": "UK"}

        with patch.object(AsyncCheckAnalysisContract, "verify_company", new=fake_verify_company), \
             patch.object(AsyncCheckAnalysisContract, "check_template_reuse", new=AsyncMock()), \
             patch.object(AsyncCheckAnalysisContract, "check_contract_date", new=AsyncMock()), \
             patch.object(AsyncCheckAnalysisContract, "check_suspicious_phrases", new=AsyncMock()), \
             patch.object(AsyncCheckAnalysisContract, "check_suspicious_identity_store", new=AsyncMock()):
            async with AsyncCheckAnalysisContract(ai_result, raw_contract_text=contract_text) as analysis:
                report = await analysis.get_detailed_report()

        summary = _build_pretty_summary("en", "txt", report, ai_result)
        self.assertIn("10 Key Checks", summary)
        self.assertIn("TESCO PLC", summary)
        self.assertIn("SAFE", report["risk_level"])

    async def test_suspicious_contract_pipeline_stays_high_risk(self) -> None:
        ai = AsyncAiProcessing(SUSPICIOUS_CONTRACT_TEXT)
        with patch.object(ai, "_candidate_models", new=AsyncMock(return_value=[])):
            ai_result = await ai.get_answer_json_dict()

        with patch.object(AsyncCheckAnalysisContract, "verify_company", new=AsyncMock()), \
             patch.object(AsyncCheckAnalysisContract, "check_template_reuse", new=AsyncMock()), \
             patch.object(AsyncCheckAnalysisContract, "check_contract_date", new=AsyncMock()), \
             patch.object(AsyncCheckAnalysisContract, "check_suspicious_identity_store", new=AsyncMock()):
            async with AsyncCheckAnalysisContract(ai_result, raw_contract_text=SUSPICIOUS_CONTRACT_TEXT) as analysis:
                report = await analysis.get_detailed_report()

        summary = _build_pretty_summary("en", "txt", report, ai_result)
        self.assertEqual(report["risk_level"], "HIGH_RISK")
        self.assertIn("10 Key Checks", summary)
        self.assertIn("quickstart-global-example.co.uk", summary)
