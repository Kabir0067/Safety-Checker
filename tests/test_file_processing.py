from __future__ import annotations

import unittest

from functions.file_processing import FileConvertToText
from tests.fixture_factory import ensure_test_assets


class FileProcessingTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.assets = ensure_test_assets()

    async def asyncSetUp(self) -> None:
        self.converter = FileConvertToText()

    async def test_supported_contract_files_convert_to_text(self) -> None:
        expected_snippets = {
            "sample_docx": "TESCO PLC",
            "sample_pdf": "Urgent payment",
            "safe_txt": "TESCO PLC",
            "safe_csv": "TESCO PLC",
            "safe_xlsx": "TESCO PLC",
            "safe_png": "TESCO",
        }

        for key, snippet in expected_snippets.items():
            with self.subTest(asset=key):
                result = await self.converter.convert_to_text(str(self.assets[key]))
                self.assertEqual(result.get("status"), "success", result)
                text = result.get("text") or ""
                self.assertIn(snippet, text)
                self.assertGreater(len(text), 40)
