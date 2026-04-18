from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from functions.utils import AsyncCheckAnalysisContract


class VerificationLogicTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_contact_data_escalates_verified_company_to_high_risk(self) -> None:
        ai_result = {
            "Company Name": "TESCO PLC",
            "Company Number": "00445790",
            "Registered Address": None,
            "Contact Details": None,
            "Website Domain": "tesco.com",
        }

        async def fake_verify_company(self) -> None:
            self.company_verified = True
            self.company_status = "active"
            self.official_company_name = "TESCO PLC"
            self.official_company_number = "00445790"
            self.official_country = "UK"
            self.db_company = {"website_domain": "tesco.com", "country": "UK"}

        with patch.object(AsyncCheckAnalysisContract, "verify_company", new=fake_verify_company), \
             patch.object(AsyncCheckAnalysisContract, "check_template_reuse", new=AsyncMock()), \
             patch.object(AsyncCheckAnalysisContract, "check_contract_date", new=AsyncMock()), \
             patch.object(AsyncCheckAnalysisContract, "check_suspicious_phrases", new=AsyncMock()), \
             patch.object(AsyncCheckAnalysisContract, "check_suspicious_identity_store", new=AsyncMock()):
            async with AsyncCheckAnalysisContract(ai_result, raw_contract_text="TESCO PLC") as analysis:
                report = await analysis.get_detailed_report()

        self.assertEqual(report["risk_level"], "HIGH_RISK")
        self.assertIn("low_identity_data", report["reason_codes"])
        self.assertIn("missing_email", report["reason_codes"])
        self.assertIn("missing_address", report["reason_codes"])
        self.assertEqual(report["detailed_scores"]["Address Status"], "missing")
        self.assertEqual(report["detailed_scores"]["Email Status"], "missing")

    async def test_address_mismatch_is_not_reported_as_missing(self) -> None:
        ai_result = {
            "Company Name": "TESCO PLC",
            "Company Number": "00445790",
            "Registered Address": "1 Fake Street, London, W1 1AA",
            "Contact Details": "people.services@tesco.com",
            "Website Domain": "tesco.com",
        }

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
            async with AsyncCheckAnalysisContract(ai_result, raw_contract_text="people.services@tesco.com") as analysis:
                report = await analysis.get_detailed_report()

        self.assertFalse(report["detailed_scores"]["Address Missing"])
        self.assertEqual(report["detailed_scores"]["Address Status"], "mismatch")
        self.assertIn("address_mismatch", report["reason_codes"])
        self.assertNotIn("missing_address", report["reason_codes"])

    async def test_untrusted_contract_website_is_not_treated_as_company_domain(self) -> None:
        ai_result = {
            "Company Name": None,
            "Company Number": None,
            "Registered Address": None,
            "Contact Details": "onboarding@quickstart-global-example.co.uk",
            "Website Domain": "quickstart-global-example.co.uk",
        }

        with patch.object(AsyncCheckAnalysisContract, "verify_company", new=AsyncMock()), \
             patch.object(AsyncCheckAnalysisContract, "check_template_reuse", new=AsyncMock()), \
             patch.object(AsyncCheckAnalysisContract, "check_contract_date", new=AsyncMock()), \
             patch.object(AsyncCheckAnalysisContract, "check_suspicious_phrases", new=AsyncMock()), \
             patch.object(AsyncCheckAnalysisContract, "check_suspicious_identity_store", new=AsyncMock()):
            async with AsyncCheckAnalysisContract(ai_result, raw_contract_text=str(ai_result["Contact Details"])) as analysis:
                report = await analysis.get_detailed_report()

        self.assertIsNone(report["company_domain"])
        self.assertFalse(report["domain_match"])
        self.assertEqual(report["domain_status"], "unavailable_reference")
        self.assertTrue(report["website_domain_match"])

    async def test_suspicious_phrases_with_verified_company_is_warning_not_high(self) -> None:
        ai_result = {
            "Company Name": "TESCO PLC",
            "Company Number": "00445790",
            "Registered Address": "Tesco House, Shire Park, Kestrel Way, Welwyn Garden City, AL7 1GA, United Kingdom",
            "Contact Details": "people.services@tesco.com",
            "Website Domain": "tesco.com",
            "Suspicious Phrases Found": ["urgent payment"],
        }

        async def fake_verify_company(self) -> None:
            self.company_verified = True
            self.company_status = "active"
            self.official_company_name = "TESCO PLC"
            self.official_company_number = "00445790"
            self.official_registered_address = (
                "Tesco House, Shire Park, Kestrel Way, Welwyn Garden City, AL7 1GA, United Kingdom"
            )
            self.official_country = "UK"
            self.db_company = {"website_domain": "tesco.com", "country": "UK"}

        raw = "urgent payment clause " + (ai_result["Registered Address"] or "")

        with patch.object(AsyncCheckAnalysisContract, "verify_company", new=fake_verify_company), \
             patch.object(AsyncCheckAnalysisContract, "check_template_reuse", new=AsyncMock()), \
             patch.object(AsyncCheckAnalysisContract, "check_contract_date", new=AsyncMock()), \
             patch.object(AsyncCheckAnalysisContract, "check_suspicious_identity_store", new=AsyncMock()):
            async with AsyncCheckAnalysisContract(ai_result, raw_contract_text=raw) as analysis:
                report = await analysis.get_detailed_report()

        self.assertEqual(report["risk_level"], "WARNING")
        self.assertIn("suspicious_phrases_found", report["reason_codes"])

    async def test_country_defaults_to_uk_for_verified_registry_rows(self) -> None:
        ai_result = {
            "Company Name": "TESCO PLC",
            "Company Number": "00445790",
            "Registered Address": "Tesco House, Shire Park, Kestrel Way, Welwyn Garden City, AL7 1GA, United Kingdom",
            "Contact Details": "people.services@tesco.com",
            "Website Domain": "tesco.com",
        }

        async def fake_verify_company(self) -> None:
            self.company_verified = True
            self.company_status = "active"
            self.official_company_name = "TESCO PLC"
            self.official_company_number = "00445790"
            self.db_company = {}
            self._finalize_company_verification()

        with patch.object(AsyncCheckAnalysisContract, "verify_company", new=fake_verify_company), \
             patch.object(AsyncCheckAnalysisContract, "check_template_reuse", new=AsyncMock()), \
             patch.object(AsyncCheckAnalysisContract, "check_contract_date", new=AsyncMock()), \
             patch.object(AsyncCheckAnalysisContract, "check_suspicious_phrases", new=AsyncMock()), \
             patch.object(AsyncCheckAnalysisContract, "check_suspicious_identity_store", new=AsyncMock()):
            async with AsyncCheckAnalysisContract(ai_result, raw_contract_text=ai_result["Registered Address"]) as analysis:
                report = await analysis.get_detailed_report()

        self.assertEqual(report["official_country"], "UK")
