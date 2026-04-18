from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from functions.ai_processing import AsyncAiProcessing, Provider
from tests.fixture_factory import SAFE_CONTRACT_TEXT


class AiProcessingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self) -> None:
        await AsyncAiProcessing.aclose()

    async def test_openrouter_candidates_stay_free_only_by_default(self) -> None:
        processor = AsyncAiProcessing(SAFE_CONTRACT_TEXT)

        with patch.object(
            processor,
            "_get_models",
            new=AsyncMock(return_value=[
                "google/gemma-3-4b-it:free",
                "google/gemini-2.5-flash-lite",
                "openai/gpt-oss-20b:free",
            ]),
        ):
            models = await processor._candidate_models(Provider("openrouter"))

        self.assertIn("google/gemma-3-4b-it:free", models)
        self.assertIn("openai/gpt-oss-20b:free", models)
        self.assertNotIn("google/gemini-2.5-flash-lite", models)

    async def test_groq_candidates_use_free_tier_allowlist(self) -> None:
        processor = AsyncAiProcessing(SAFE_CONTRACT_TEXT)

        with patch.object(
            processor,
            "_get_models",
            new=AsyncMock(return_value=[
                "groq/compound",
                "llama-3.1-8b-instant",
                "openai/gpt-oss-20b",
            ]),
        ):
            models = await processor._candidate_models(Provider("groq"))

        self.assertIn("llama-3.1-8b-instant", models)
        self.assertIn("openai/gpt-oss-20b", models)
        self.assertNotIn("groq/compound", models)

    async def test_provider_diagnostics_track_successful_provider(self) -> None:
        processor = AsyncAiProcessing(SAFE_CONTRACT_TEXT)

        async def fake_models(provider: Provider):
            return {
                "gemini": ["gemini-2.5-flash"],
                "groq": ["llama-3.3-70b-versatile"],
                "openrouter": [],
            }[provider.name]

        with patch.object(processor, "_candidate_models", side_effect=fake_models), \
             patch.object(processor, "_call_gemini", new=AsyncMock(return_value=None)), \
             patch.object(
                 processor,
                 "_call_openai_compatible",
                 new=AsyncMock(return_value={
                     "Contract Number": "TSCO-TEST-2026-01",
                     "Company Name": "TESCO PLC",
                     "Company Number": "00445790",
                     "Registered Address": "Tesco House, Shire Park, Kestrel Way, Welwyn Garden City, AL7 1GA, United Kingdom",
                     "Contact Details": "people.services@tesco.com",
                     "Responsible Person Full Name": None,
                     "Contract Date": "2026-04-10",
                     "Website Domain": "tesco.com",
                     "Suspicious Phrases Found": [],
                     "Text Style": "professional",
                 }),
             ):
            result = await processor.get_answer_json_dict()

        self.assertIsNotNone(result)
        diagnostics = processor.get_diagnostics()
        self.assertEqual(diagnostics["successful_provider"], "groq")
        self.assertTrue(diagnostics["free_only_mode"])
        self.assertFalse(diagnostics["fallback_used"])
        self.assertEqual(diagnostics["attempts"][-1]["status"], "success")

    async def test_local_fallback_is_reported_in_diagnostics(self) -> None:
        processor = AsyncAiProcessing(SAFE_CONTRACT_TEXT)

        with patch.object(processor, "_candidate_models", new=AsyncMock(return_value=[])):
            result = await processor.get_answer_json_dict()

        self.assertIsNotNone(result)
        diagnostics = processor.get_diagnostics()
        self.assertEqual(diagnostics["successful_provider"], "local_fallback")
        self.assertTrue(diagnostics["fallback_used"])
