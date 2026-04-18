import os
import sys

if __name__ == "__main__" and __package__ is None:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from asyncio import Semaphore
from datetime import UTC, date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
import difflib
import hashlib
import logging
import re
from aiohttp import BasicAuth, ClientTimeout
from dotenv import load_dotenv

from database.queries import (
    add_company,
    delete_company_by_number,
    find_suspicious_entity_matches,
    get_companies_by_name,
    get_company_by_number,
    get_distinct_company_names_by_template,
)

load_dotenv()


class AsyncCheckAnalysisContract:
    LOG_DIR = "logs"
    LOG_FILE = os.path.join(LOG_DIR, "async_check_analysis_contract_errors.log")
    FREE_EMAIL_PROVIDERS = {
        "gmail.com",
        "yahoo.com",
        "outlook.com",
        "hotmail.com",
        "protonmail.com",
        "icloud.com",
        "mail.com",
        "aol.com",
        "live.com",
    }
    UK_COUNTRY_NAMES = {
        "uk",
        "u k",
        "united kingdom",
        "great britain",
        "england",
        "wales",
        "scotland",
        "northern ireland",
        "england and wales",
        "england & wales",
    }
    UK_JURISDICTIONS = {
        "england-wales",
        "england_and_wales",
        "england & wales",
        "scotland",
        "northern-ireland",
        "northern_ireland",
        "united-kingdom",
        "united_kingdom",
        "uk",
        "great-britain",
        "great_britain",
    }

    def __init__(self, ai_result: Dict[str, Any], raw_contract_text: str = ""):
        self.data = ai_result or {}
        self.raw_contract_text = raw_contract_text or ""
        self.api_key = os.getenv("COMPANIES_HOUSE_API")
        self.base_url = "https://api.company-information.service.gov.uk"
        self.session: Optional[aiohttp.ClientSession] = None
        self.semaphore = Semaphore(2)
        self.db_company: Optional[Dict[str, Any]] = None

        self.company_verified = False
        self.company_not_found = False
        self.company_lookup_failed = False
        self.company_name_missing = False
        self.company_not_uk = False
        self.company_name_mismatch = False
        self.company_inactive = False
        self.company_status: Optional[str] = None
        self.official_company_name: Optional[str] = None
        self.official_company_number: Optional[str] = None
        self.official_registered_address = ""
        self.official_country: Optional[str] = None
        self.official_jurisdiction: Optional[str] = None
        self.company_name_similarity: Optional[int] = None
        self.incorporation_date: Optional[date] = None

        self.contract_address = ""
        self.contract_website_domain = ""
        self.contact_emails: List[str] = []
        self.contact_phone_numbers: List[str] = []
        self.recruiter_name: Optional[str] = None

        self.address_match_score: Optional[int] = None
        self.address_match_ok = False
        self.address_mismatch = False
        self.address_missing = False

        self.email_domains: List[str] = []
        self.email_domain: Optional[str] = None
        self.company_domain: Optional[str] = None
        self.domain_match = False
        self.domain_mismatch = False
        self.website_domain_match = False
        self.free_email_provider = False
        self.email_missing = False
        self.low_identity_data = False
        self.missing_contact_details = False

        self.template_hash: Optional[str] = None
        self.template_reuse = False
        self.contract_date_warning = False
        self.suspicious_phrases_found = False
        self.suspicious_phrases: List[str] = []

        self.suspicious_identity_match = False
        self.suspicious_identity_fields: List[str] = []
        self.suspicious_identity_hits: List[Dict[str, Any]] = []

        self.identity_score = 0
        self.risk_level = "WARNING"
        self.risk_flags: List[str] = []
        self.reason_codes: List[str] = []
        self.reasons: List[str] = []
        self.explanation = ""

        os.makedirs(self.LOG_DIR, exist_ok=True)
        self.logger = logging.getLogger("AsyncCheckAnalysisContract")
        self.logger.setLevel(logging.ERROR)
        if not self.logger.handlers:
            handler = logging.FileHandler(self.LOG_FILE)
            handler.setLevel(logging.ERROR)
            handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
            self.logger.addHandler(handler)

    async def __aenter__(self):
        if not self.session or self.session.closed:
            auth = BasicAuth(login=self.api_key, password="") if self.api_key else None
            self.session = aiohttp.ClientSession(
                auth=auth,
                timeout=ClientTimeout(total=15),
                headers={"User-Agent": "ContractChecker/2.0"},
            )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session and not self.session.closed:
            await self.session.close()

    async def _ensure_session(self) -> None:
        """Make class resilient even when used without `async with`."""
        if self.session and not self.session.closed:
            return
        auth = BasicAuth(login=self.api_key, password="") if self.api_key else None
        self.session = aiohttp.ClientSession(
            auth=auth,
            timeout=ClientTimeout(total=15),
            headers={"User-Agent": "ContractChecker/2.0"},
        )

    def _flag(self, code: str) -> None:
        if code and code not in self.risk_flags:
            self.risk_flags.append(code)

    def _normalize_company_number(self, value: Any) -> str:
        if value is None:
            return ""
        return re.sub(r"\s+", "", str(value).strip().upper())

    def _normalize_company_name(self, value: Any) -> str:
        if value is None:
            return ""
        return re.sub(r"\s+", " ", str(value).strip())

    def _normalized_name_key(self, value: Any) -> str:
        text = self._normalize_company_name(value).lower()
        text = re.sub(r"[^a-z0-9& ]+", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def _normalize_status(self, value: Any) -> str:
        text = str(value or "").strip().lower()
        return re.sub(r"\s+", "_", text)

    def _is_inactive_status(self, status: Optional[str]) -> bool:
        normalized = self._normalize_status(status)
        if not normalized:
            return False
        return (
            normalized in {"dissolved", "liquidation", "liquidated"}
            or "liquidation" in normalized
            or "dissolved" in normalized
        )

    def _company_name_from_record(self, info: Optional[Dict[str, Any]]) -> str:
        if not info:
            return ""
        return str(info.get("company_name") or info.get("name") or info.get("title") or "").strip()

    def _format_address(self, info: Dict[str, Any]) -> str:
        if not info:
            return ""

        if isinstance(info.get("registered_office_address"), dict):
            address = info.get("registered_office_address", {})
            return ", ".join(
                filter(
                    None,
                    [
                        address.get("premises"),
                        address.get("address_line_1"),
                        address.get("address_line_2"),
                        address.get("locality"),
                        address.get("region"),
                        address.get("postal_code"),
                        address.get("country"),
                    ],
                )
            )

        direct = info.get("registered_address") or info.get("address_snippet")
        return str(direct).strip() if direct else ""

    def _extract_country(self, info: Optional[Dict[str, Any]]) -> str:
        if not info:
            return ""

        if isinstance(info.get("registered_office_address"), dict):
            country = info["registered_office_address"].get("country")
            if country:
                return str(country).strip()

        direct = info.get("country")
        return str(direct).strip() if direct else ""

    def _extract_jurisdiction(self, info: Optional[Dict[str, Any]]) -> str:
        if not info:
            return ""
        value = info.get("jurisdiction")
        return str(value).strip() if value else ""

    def _country_from_jurisdiction(self, jurisdiction: Optional[str]) -> Optional[str]:
        normalized = self._normalize_jurisdiction(jurisdiction)
        if normalized in {
            "england-wales",
            "england-and-wales",
            "scotland",
            "northern-ireland",
            "united-kingdom",
            "great-britain",
            "uk",
        }:
            return "UK"
        return None

    def _normalize_country(self, value: Any) -> str:
        text = str(value or "").strip().lower()
        text = text.replace(".", " ")
        text = text.replace("-", " ")
        return re.sub(r"\s+", " ", text).strip()

    def _normalize_jurisdiction(self, value: Any) -> str:
        text = str(value or "").strip().lower()
        text = text.replace(" ", "-")
        return re.sub(r"[-_]+", "-", text).strip("-")

    def _is_uk_company_record(self, info: Optional[Dict[str, Any]]) -> bool:
        if not info:
            return False

        jurisdiction = self._normalize_jurisdiction(self._extract_jurisdiction(info))
        if jurisdiction:
            return jurisdiction in {
                self._normalize_jurisdiction(value) for value in self.UK_JURISDICTIONS
            }

        country = self._normalize_country(self._extract_country(info))
        if country:
            return country in {
                self._normalize_country(value) for value in self.UK_COUNTRY_NAMES
            }

        # Companies House is a UK registry. If no explicit country metadata is
        # present, treat the record as UK unless there is a contrary signal.
        return True

    def _normalize_domain(self, value: Optional[str]) -> str:
        if not value:
            return ""
        domain = str(value).strip().lower()
        if "@" in domain:
            domain = domain.split("@", 1)[1]
        domain = re.sub(r"^(https?://|www\.)", "", domain, flags=re.IGNORECASE)
        domain = domain.split("/", 1)[0].strip().strip(".")
        return domain

    def _domains_match(self, email_domain: str, company_domain: str) -> bool:
        if not email_domain or not company_domain:
            return False
        return (
            email_domain == company_domain
            or email_domain.endswith("." + company_domain)
            or company_domain.endswith("." + email_domain)
        )

    def _normalize_address_text(self, text: str) -> str:
        cleaned = re.sub(r"[^\w\s]", " ", str(text or "").lower())
        return re.sub(r"\s+", " ", cleaned).strip()

    def _address_similarity(self, left: str, right: str) -> float:
        left_norm = self._normalize_address_text(left)
        right_norm = self._normalize_address_text(right)
        if not left_norm or not right_norm:
            return 0.0

        seq_ratio = difflib.SequenceMatcher(None, left_norm, right_norm).ratio()
        left_tokens = set(left_norm.split())
        right_tokens = set(right_norm.split())
        if not left_tokens or not right_tokens:
            token_ratio = 0.0
        else:
            token_ratio = len(left_tokens & right_tokens) / max(len(left_tokens), len(right_tokens))

        return max(seq_ratio, token_ratio)

    def _name_similarity(self, left: str, right: str) -> float:
        left_key = self._normalized_name_key(left)
        right_key = self._normalized_name_key(right)
        if not left_key or not right_key:
            return 0.0
        return difflib.SequenceMatcher(None, left_key, right_key).ratio()

    def _core_name_tokens(self, value: Any) -> set[str]:
        text = self._normalized_name_key(value)
        if not text:
            return set()

        # Ignore legal suffixes and weak words to compare brand/core terms.
        stop_words = {
            "ltd",
            "limited",
            "plc",
            "llp",
            "lp",
            "inc",
            "company",
            "co",
            "group",
            "holdings",
            "holding",
            "services",
            "service",
            "uk",
            "the",
            "and",
        }
        return {token for token in text.split() if token and token not in stop_words and len(token) > 1}

    def _extract_emails(self, text: str) -> List[str]:
        if not text:
            return []
        found = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
        seen = set()
        emails = []
        for email in found:
            normalized = email.strip()
            key = normalized.lower()
            if normalized and key not in seen:
                emails.append(normalized)
                seen.add(key)
        return emails

    def _normalize_phone(self, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        keep_plus = text.startswith("+")
        digits = re.sub(r"\D", "", text)
        if not digits:
            return ""
        return f"+{digits}" if keep_plus else digits

    def _extract_phone_numbers(self, text: str) -> List[str]:
        if not text:
            return []
        found = re.findall(r"\+?\d[\d\s().-]{7,}\d", text)
        seen = set()
        phones = []
        for phone in found:
            normalized = self._normalize_phone(phone)
            if normalized and normalized not in seen:
                phones.append(normalized)
                seen.add(normalized)
        return phones

    def _parse_date(self, value: Any) -> Optional[date]:
        if not value:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        text = str(value).strip()
        if not text:
            return None
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None

    def _normalize_contract_text_for_hash(self, text: str) -> str:
        return re.sub(r"\s+", " ", (text or "").strip())

    async def _fetch_company_profile(self, company_number: str) -> Tuple[Optional[Dict[str, Any]], Optional[int]]:
        url = f"{self.base_url}/company/{company_number}"
        async with self.semaphore:
            try:
                await self._ensure_session()
                async with self.session.get(url) as response:
                    if response.status == 200:
                        return await response.json(), response.status
                    return None, response.status
            except Exception as exc:
                self.logger.exception(f"Error checking company profile {company_number}: {exc}")
                return None, None

    async def _search_company_by_name(self, company_name: str) -> Optional[List[Dict[str, Any]]]:
        url = f"{self.base_url}/search/companies"
        async with self.semaphore:
            try:
                await self._ensure_session()
                async with self.session.get(url, params={"q": company_name}) as response:
                    if response.status != 200:
                        return None
                    result = await response.json()
                    return result.get("items", []) or []
            except Exception as exc:
                self.logger.exception(f"Error searching company name {company_name}: {exc}")
                return None

    # Jurisdiction → country mapping
    JURISDICTION_COUNTRY_MAP = {
        "england-wales": "UK",
        "england_and_wales": "UK",
        "england & wales": "UK",
        "scotland": "UK",
        "northern-ireland": "UK",
        "northern_ireland": "UK",
        "united-kingdom": "UK",
        "united_kingdom": "UK",
        "uk": "UK",
        "great-britain": "UK",
        "great_britain": "UK",
        "wales": "UK",
    }

    def _apply_company_record(self, info: Dict[str, Any]) -> None:
        self.db_company = info
        self.official_company_name = self._company_name_from_record(info) or None
        self.official_company_number = info.get("company_number") or self.data.get("Company Number")
        self.company_status = str(info.get("status") or info.get("company_status") or "unknown").lower()
        self.official_registered_address = self._format_address(info) or ""
        self.official_country = self._extract_country(info) or None
        self.official_jurisdiction = self._extract_jurisdiction(info) or None
        if not self.official_country and self.official_jurisdiction:
            self.official_country = self._country_from_jurisdiction(self.official_jurisdiction)
        self.incorporation_date = self._parse_date(info.get("incorporation_date") or info.get("date_of_creation"))

        # Map jurisdiction → country if country is missing
        if not self.official_country and self.official_jurisdiction:
            normalized_j = self._normalize_jurisdiction(self.official_jurisdiction)
            self.official_country = self.JURISDICTION_COUNTRY_MAP.get(normalized_j)

    async def _cache_company_info(self, info: Dict[str, Any], company_number: Optional[str]) -> None:
        await add_company(
            {
                "name": info.get("company_name") or info.get("name"),
                "company_number": company_number or info.get("company_number"),
                "registered_address": self._format_address(info) or info.get("registered_address"),
                "status": str(info.get("company_status") or info.get("status") or "unknown").lower(),
                "score": 0,
                "website_domain": self.data.get("Website Domain"),
                "contact_email": None,
                "phone_number": None,
                "country": self._extract_country(info) or self._country_from_jurisdiction(self._extract_jurisdiction(info)),
                "jurisdiction": self._extract_jurisdiction(info) or None,
                "incorporation_date": info.get("date_of_creation"),
            }
        )

    def _finalize_company_verification(self) -> None:
        self.company_inactive = self._is_inactive_status(self.company_status)

        self.company_not_uk = False
        record = self.db_company or {
            "country": self.official_country,
            "jurisdiction": self.official_jurisdiction,
        }
        if record:
            self.company_not_uk = not self._is_uk_company_record(record)
        if not self.official_country and not self.company_not_uk and (
            self.official_company_number or self.official_company_name
        ):
            # Companies House is a UK registry; when cached rows lose explicit
            # country metadata we still want a stable country value in reports.
            self.official_country = "UK"

        self.company_name_similarity = None
        self.company_name_mismatch = False
        input_name = self._normalize_company_name(self.data.get("Company Name"))
        official_name = self._normalize_company_name(self.official_company_name)
        if input_name and official_name:
            similarity = self._name_similarity(input_name, official_name)
            self.company_name_similarity = int(round(similarity * 100))
            input_tokens = self._core_name_tokens(input_name)
            official_tokens = self._core_name_tokens(official_name)
            shared_core_tokens = bool(input_tokens and official_tokens and (input_tokens & official_tokens))

            # If a valid company number was used and profile exists, be less strict on
            # legal-form differences (e.g., LTD vs PLC) as long as core brand tokens match.
            has_verified_number = bool(
                self._normalize_company_number(self.data.get("Company Number"))
                and self._normalize_company_number(self.official_company_number)
            )
            if has_verified_number:
                self.company_name_mismatch = (similarity < 0.55) and (not shared_core_tokens)
            else:
                self.company_name_mismatch = similarity < 0.9

        self.company_verified = (
            bool(official_name)
            and self.company_status == "active"
            and not any(
                [
                    self.company_name_missing,
                    self.company_not_found,
                    self.company_lookup_failed,
                    self.company_not_uk,
                    self.company_name_mismatch,
                    self.company_inactive,
                ]
            )
        )

    def _pick_company_domain(self) -> str:
        if not (self.company_verified or self.official_company_number or self.official_company_name):
            return ""
        candidates = [
            self.db_company.get("website_domain") if self.db_company else None,
            self.db_company.get("contact_email") if self.db_company else None,
        ]
        for candidate in candidates:
            domain = self._normalize_domain(candidate)
            if domain:
                return domain
        return ""

    def _collect_contact_signals(self) -> None:
        self.contract_address = str(self.data.get("Registered Address") or "").strip()
        self.contract_website_domain = self._normalize_domain(self.data.get("Website Domain"))

        contact_blob = "\n".join(
            filter(
                None,
                [
                    str(self.data.get("Contact Details") or "").strip(),
                    self.raw_contract_text,
                ],
            )
        )

        self.contact_emails = self._extract_emails(contact_blob)
        self.email_domains = [self._normalize_domain(email) for email in self.contact_emails]
        self.email_domains = [domain for domain in self.email_domains if domain]
        self.email_domain = self.email_domains[0] if self.email_domains else None

        self.contact_phone_numbers = self._extract_phone_numbers(contact_blob)
        recruiter = str(self.data.get("Responsible Person Full Name") or "").strip()
        self.recruiter_name = recruiter or None

        # Track missing data separately
        self.email_missing = not bool(self.email_domain)
        self.address_missing = not bool(self.contract_address)
        self.low_identity_data = self.email_missing and self.address_missing
        self.missing_contact_details = self.email_missing or self.address_missing
        if self.email_missing:
            self._flag("missing_email")
        if self.address_missing:
            self._flag("missing_address")
        if self.low_identity_data:
            self._flag("low_identity_data")

    async def verify_company(self) -> None:
        self.company_verified = False
        self.company_not_found = False
        self.company_lookup_failed = False
        self.company_name_missing = False
        self.company_not_uk = False
        self.company_name_mismatch = False
        self.company_inactive = False
        self.company_status = None
        self.official_company_name = None
        self.official_company_number = None
        self.official_registered_address = ""
        self.official_country = None
        self.official_jurisdiction = None
        self.company_name_similarity = None
        self.incorporation_date = None

        company_name = self._normalize_company_name(self.data.get("Company Name"))
        company_number = self._normalize_company_number(self.data.get("Company Number"))

        if not company_name:
            self.company_name_missing = True
            self._flag("company_name_missing")
            return

        self.data["Company Name"] = company_name

        if company_number:
            self.data["Company Number"] = company_number
            cached_company = await get_company_by_number(company_number)

            if cached_company:
                last_updated = cached_company.get("last_updated")
                reference_now = (
                    datetime.now(UTC) if getattr(last_updated, "tzinfo", None) else datetime.now(UTC).replace(tzinfo=None)
                )
                if isinstance(last_updated, datetime) and (reference_now - last_updated) < timedelta(days=30):
                    self._apply_company_record(cached_company)
                    self._finalize_company_verification()
                    return
                self._apply_company_record(cached_company)

            info, status_code = await self._fetch_company_profile(company_number)
            if info:
                self._apply_company_record(info)
                await self._cache_company_info(info, company_number)
            elif status_code == 404:
                self.company_not_found = True
                if cached_company:
                    await delete_company_by_number(company_number)
            elif status_code is None:
                if not cached_company:
                    self.company_lookup_failed = True
            elif cached_company:
                self.company_not_found = False
            else:
                self.company_not_found = True

            self._finalize_company_verification()
            return

        cached_companies = await get_companies_by_name(company_name)
        if cached_companies:
            active_cached = [item for item in cached_companies if str(item.get("status") or "").lower() == "active"]
            chosen = active_cached[0] if active_cached else cached_companies[0]
            last_updated = chosen.get("last_updated")
            reference_now = (
                datetime.now(UTC) if getattr(last_updated, "tzinfo", None) else datetime.now(UTC).replace(tzinfo=None)
            )
            if isinstance(last_updated, datetime) and (reference_now - last_updated) < timedelta(days=30):
                self._apply_company_record(chosen)
                self._finalize_company_verification()
                return

        items = await self._search_company_by_name(company_name)
        if items is None:
            self.company_lookup_failed = True
            return
        if not items:
            self.company_not_found = True
            return

        best_item = None
        best_score = -1.0
        best_uk_item = None
        best_uk_score = -1.0
        for item in items:
            score = self._name_similarity(company_name, item.get("title", ""))
            if score > best_score:
                best_item = item
                best_score = score
            if self._is_uk_company_record(item) and score > best_uk_score:
                best_uk_item = item
                best_uk_score = score

        chosen_item = best_uk_item or best_item
        if not chosen_item:
            self.company_not_found = True
            return

        company_number = chosen_item.get("company_number")
        info = None
        if company_number:
            info, _ = await self._fetch_company_profile(company_number)

        if info:
            self._apply_company_record(info)
            await self._cache_company_info(info, company_number)
            self.data["Company Number"] = company_number
        else:
            self.db_company = chosen_item
            self.official_company_name = self._company_name_from_record(chosen_item) or company_name
            self.official_company_number = company_number
            self.company_status = str(chosen_item.get("company_status") or "unknown").lower()
            self.official_registered_address = self._format_address(chosen_item) or ""
            self.official_country = self._extract_country(chosen_item) or None
            self.official_jurisdiction = self._extract_jurisdiction(chosen_item) or None
            if not self.official_country and self.official_jurisdiction:
                self.official_country = self._country_from_jurisdiction(self.official_jurisdiction)

            await add_company(
                {
                    "name": self.official_company_name,
                    "company_number": company_number,
                    "registered_address": self.official_registered_address,
                    "status": self.company_status,
                    "score": 0,
                    "website_domain": self.data.get("Website Domain"),
                    "contact_email": None,
                    "phone_number": None,
                    "country": self.official_country,
                    "jurisdiction": self.official_jurisdiction,
                    "incorporation_date": None,
                }
            )

        self._finalize_company_verification()

    async def check_address_match(self) -> None:
        self.address_match_score = None
        self.address_match_ok = False
        self.address_mismatch = False

        # If contract has no address, it's "missing" (already flagged in _collect_contact_signals)
        if not self.contract_address:
            return

        # If official address is unknown, can't compare
        if not self.official_registered_address:
            return

        similarity = self._address_similarity(self.contract_address, self.official_registered_address)
        self.address_match_score = int(round(similarity * 100))
        if self.address_match_score >= 70:
            self.address_match_ok = True
        else:
            self.address_mismatch = True
            self._flag("address_mismatch")

    async def check_email_domain(self) -> None:
        self.company_domain = self._pick_company_domain() or None
        self.domain_match = False
        self.domain_mismatch = False
        self.website_domain_match = False
        self.free_email_provider = False

        # If no email found at all, nothing to check — email_missing already flagged
        if not self.email_domains:
            return

        if any(domain in self.FREE_EMAIL_PROVIDERS for domain in self.email_domains):
            self.free_email_provider = True
            self._flag("free_email_provider")

        if self.contract_website_domain:
            self.website_domain_match = any(
                self._domains_match(domain, self.contract_website_domain)
                for domain in self.email_domains
            )

        if self.company_domain:
            if any(self._domains_match(domain, self.company_domain) for domain in self.email_domains):
                self.domain_match = True
            else:
                self.domain_mismatch = True
                self._flag("domain_mismatch")

    def _address_status(self) -> str:
        if self.address_missing:
            return "missing"
        if self.address_match_ok:
            return "matched"
        if self.address_mismatch:
            return "mismatch"
        if self.contract_address and not self.official_registered_address:
            return "unavailable_reference"
        return "unknown"

    def _email_status(self) -> str:
        return "missing" if self.email_missing else "present"

    def _domain_status(self) -> str:
        if self.email_missing:
            return "missing_email"
        if self.free_email_provider:
            return "free_provider"
        if self.domain_match:
            return "matched"
        if self.domain_mismatch:
            return "mismatch"
        if self.email_domain and not self.company_domain:
            return "unavailable_reference"
        return "unknown"

    async def check_template_reuse(self) -> None:
        self.template_hash = None
        self.template_reuse = False

        normalized_text = self._normalize_contract_text_for_hash(self.raw_contract_text)
        if not normalized_text:
            return

        self.template_hash = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
        previous_names = await get_distinct_company_names_by_template(self.template_hash)
        current_name = self._normalized_name_key(self.data.get("Company Name"))

        if not current_name or not previous_names:
            return

        previous_norm = {self._normalized_name_key(name) for name in previous_names if name}
        previous_norm = {name for name in previous_norm if name}
        if previous_norm and any(name != current_name for name in previous_norm):
            self.template_reuse = True
            self._flag("template_reuse")

    async def check_contract_date(self) -> None:
        self.contract_date_warning = False
        parsed = self._parse_date(self.data.get("Contract Date"))
        if not parsed:
            return

        today = datetime.now(UTC).date()
        if parsed > (today + timedelta(days=365)) or parsed < (today - timedelta(days=365 * 5)):
            self.contract_date_warning = True
            self._flag("contract_date_warning")

    async def check_suspicious_phrases(self) -> None:
        raw_phrases = self.data.get("Suspicious Phrases Found") or []
        if not isinstance(raw_phrases, list):
            raw_phrases = []

        seen = set()
        self.suspicious_phrases = []
        for phrase in raw_phrases:
            cleaned = str(phrase or "").strip()
            key = cleaned.lower()
            if cleaned and key not in seen:
                self.suspicious_phrases.append(cleaned)
                seen.add(key)

        self.suspicious_phrases_found = bool(self.suspicious_phrases)
        if self.suspicious_phrases_found:
            self._flag("suspicious_phrases_found")

    async def check_suspicious_identity_store(self) -> None:
        self.suspicious_identity_match = False
        self.suspicious_identity_fields = []
        self.suspicious_identity_hits = []

        matches = await find_suspicious_entity_matches(
            email_domain=self.email_domain,
            phone_number=self.contact_phone_numbers[0] if self.contact_phone_numbers else None,
            recruiter_name=self.recruiter_name,
            contract_template_hash=self.template_hash,
        )
        if not matches:
            return

        fields = set()
        trusted_matches = []
        for match in matches:
            # Older versions stored every WARNING as bot_auto, which polluted
            # legitimate domains. Only confirmed/manual or high-risk auto rows
            # should influence future checks.
            if str(match.get("source") or "").lower() == "bot_auto":
                continue
            trusted_matches.append(match)
            if self.email_domain and match.get("email_domain") and match["email_domain"].lower() == self.email_domain.lower():
                fields.add("email_domain")
            if self.contact_phone_numbers and match.get("phone_number") == self.contact_phone_numbers[0]:
                fields.add("phone_number")
            if self.recruiter_name and match.get("recruiter_name") and match["recruiter_name"].lower() == self.recruiter_name.lower():
                fields.add("recruiter_name")
            if self.template_hash and match.get("contract_template_hash") == self.template_hash:
                fields.add("contract_template_hash")

        if not fields:
            return

        self.suspicious_identity_match = True
        self.suspicious_identity_fields = sorted(fields)
        self.suspicious_identity_hits = trusted_matches
        self._flag("suspicious_identity_match")

        field_to_flag = {
            "email_domain": "known_suspicious_email_domain",
            "phone_number": "known_suspicious_phone_number",
            "recruiter_name": "known_suspicious_recruiter",
            "contract_template_hash": "known_suspicious_contract_template",
        }
        for field in self.suspicious_identity_fields:
            self._flag(field_to_flag[field])

    def _calculate_identity_score(self) -> int:
        score = 0
        has_registry_identity = self.company_verified or bool(self.official_company_name)
        if self.company_verified:
            score += 50
        elif has_registry_identity:
            score += 25
        if self.address_match_ok:
            score += 20
        elif self.contract_address:
            score += 5
        if has_registry_identity and self.domain_match:
            score += 15
        elif self.website_domain_match:
            score += 5
        if self.email_domain:
            score += 5
        if self.free_email_provider:
            score -= 15
        if self.domain_mismatch:
            score -= 15
        if self.address_mismatch:
            score -= 15
        if self.email_missing:
            score -= 10
        if self.address_missing:
            score -= 10
        if self.low_identity_data:
            score -= 10
        return max(0, min(100, score))

    def _build_reason_codes(self) -> List[str]:
        if self.risk_level == "SAFE":
            return ["verified_identity"]

        ordered = [
            "suspicious_phrases_found",
            "company_name_missing",
            "company_not_found",
            "company_not_uk",
            "company_name_mismatch",
            "company_not_active",
            "low_identity_data",
            "missing_email",
            "missing_address",
            "address_mismatch",
            "domain_mismatch",
            "free_email_provider",
            "company_lookup_failed",
            "known_suspicious_contract_template",
            "template_reuse",
            "known_suspicious_email_domain",
            "known_suspicious_phone_number",
            "known_suspicious_recruiter",
            "contract_date_warning",
        ]

        code_checks = {
            "suspicious_phrases_found": self.suspicious_phrases_found,
            "company_name_missing": self.company_name_missing,
            "company_not_found": self.company_not_found,
            "company_not_uk": self.company_not_uk,
            "company_name_mismatch": self.company_name_mismatch,
            "company_not_active": self.company_inactive,
            "missing_email": self.email_missing,
            "missing_address": self.address_missing,
            "address_mismatch": self.address_mismatch,
            "domain_mismatch": self.domain_mismatch,
            "free_email_provider": self.free_email_provider,
            "low_identity_data": self.low_identity_data,
            "company_lookup_failed": self.company_lookup_failed,
            "template_reuse": self.template_reuse,
            "contract_date_warning": self.contract_date_warning,
            "known_suspicious_contract_template": "contract_template_hash" in self.suspicious_identity_fields,
            "known_suspicious_email_domain": "email_domain" in self.suspicious_identity_fields,
            "known_suspicious_phone_number": "phone_number" in self.suspicious_identity_fields,
            "known_suspicious_recruiter": "recruiter_name" in self.suspicious_identity_fields,
        }

        return [code for code in ordered if code_checks.get(code, False)]

    def _reason_text(self, code: str) -> str:
        messages = {
            "company_name_missing": "No company name was found in the contract.",
            "company_not_found": "The company was not found in the UK registry.",
            "company_not_uk": "The company is not registered in the UK.",
            "company_name_mismatch": "The company name does not match official UK records.",
            "company_not_active": "The company is not active in the UK registry.",
            "suspicious_phrases_found": "The contract contains suspicious hiring or payment phrases.",
            "template_reuse": "This contract template was reused across different company names.",
            "domain_mismatch": "The contact email domain does not match the company domain.",
            "free_email_provider": "A free email provider is being used for employer contact.",
            "address_mismatch": "The contract address does not match the official registered address.",
            "missing_email": "No employer email was found in the contract.",
            "missing_address": "No employer address was provided in the contract.",
            "low_identity_data": "The contract is missing both an employer email and an address.",
            "company_lookup_failed": "The official company lookup could not be completed.",
            "contract_date_warning": "The contract date looks unusual.",
            "known_suspicious_email_domain": "This email domain has appeared in previous suspicious checks.",
            "known_suspicious_phone_number": "This phone number has appeared in previous suspicious checks.",
            "known_suspicious_recruiter": "This recruiter name has appeared in previous suspicious checks.",
            "known_suspicious_contract_template": "This contract hash has appeared in previous suspicious checks.",
            "verified_identity": "The company was verified and no critical identity mismatches were found.",
        }
        return messages.get(code, code.replace("_", " ").capitalize() + ".")

    def _determine_risk_level(self) -> str:
        # Phrases alone are not treated as hard fraud if Companies House confirms an
        # active employer match (mixed PDF/OCR text can otherwise flip results).
        phrase_hard = self.suspicious_phrases_found and not self.company_verified

        hard_risk = any(
            [
                phrase_hard,
                self.company_name_missing,
                self.company_not_found,
                self.company_not_uk,
                self.company_name_mismatch,
                self.company_inactive,
            ]
        )
        if hard_risk:
            return "HIGH_RISK"

        # Company is verified but missing critical identity data → HIGH_RISK
        # A real company with no verifiable contact info is a strong fraud signal
        if self.company_verified and self.low_identity_data:
            return "HIGH_RISK"

        warning = any(
            [
                self.domain_mismatch,
                self.address_mismatch,
                self.email_missing,
                self.address_missing,
                self.free_email_provider,
                self.company_lookup_failed,
                self.suspicious_phrases_found and self.company_verified,
            ]
        )
        if warning:
            return "WARNING"

        if self.company_verified:
            return "SAFE"

        return "WARNING"

    def _build_explanation(self) -> str:
        if self.risk_level == "HIGH_RISK":
            if self.suspicious_phrases_found:
                phrases = ", ".join(self.suspicious_phrases[:5])
                return f"The contract contains suspicious phrases: {phrases}."
            if self.company_name_missing:
                return "No employer company name was found, so the contract cannot be verified against the UK registry."
            if self.company_not_found:
                return "The employer could not be found in the UK registry, which is a strong fraud signal."
            if self.company_not_uk:
                return "The employer record found is not registered as a UK company."
            if self.company_name_mismatch:
                return "The company name in the contract does not closely match the official UK company record."
            if self.company_inactive:
                return "The employer exists in the UK registry but is not active."
            if self.company_verified and self.low_identity_data:
                issues = []
                if self.email_missing:
                    issues.append("employer email")
                if self.address_missing:
                    issues.append("verifiable contact details")
                missing = " and ".join(issues) if issues else "verifiable identity data"
                return (f"The company is registered and active in the UK. However, the contract does not include any {missing}. "
                        f"This makes it impossible to confirm the legitimacy of the offer and is a strong indicator of potential fraud.")
            return "The employer failed mandatory UK company verification checks."
        if self.risk_level == "WARNING":
            cleaned = [reason.rstrip(".") for reason in self.reasons[:4]]
            if self.company_verified and cleaned:
                return "The company is registered and active in the UK, but there are warning signs: " + "; ".join(cleaned) + "."
            if cleaned:
                return "The contract triggered warning signs during verification: " + "; ".join(cleaned) + "."
            return "The contract triggered warning signs during verification."
        if self.company_verified:
            if self.address_match_ok and self.domain_match:
                return "The company is registered and active in the UK, and the address and email domain match the official identity data."
            if self.address_match_ok:
                return "The company is registered and active in the UK, and the contract address matches the official record."
            if self.domain_match:
                return "The company is registered and active in the UK, and the email domain matches the company identity."
            return "The company is registered and active in the UK with no major identity warning flags."
        return "The company did not fail mandatory checks, but the verification result still needs manual review."

    async def run_all_checks(self) -> None:
        self.risk_flags = []
        self.reason_codes = []
        self.reasons = []
        self.explanation = ""

        self._collect_contact_signals()
        await self.verify_company()

        if self.company_not_found:
            self._flag("company_not_found")
        if self.company_not_uk:
            self._flag("company_not_uk")
        if self.company_name_mismatch:
            self._flag("company_name_mismatch")
        if self.company_inactive:
            self._flag("company_not_active")
        if self.company_lookup_failed:
            self._flag("company_lookup_failed")

        await self.check_address_match()
        await self.check_email_domain()
        await self.check_template_reuse()
        await self.check_contract_date()
        await self.check_suspicious_phrases()
        await self.check_suspicious_identity_store()

        self.identity_score = self._calculate_identity_score()
        self.risk_level = self._determine_risk_level()
        self.reason_codes = self._build_reason_codes()
        self.reasons = [self._reason_text(code) for code in self.reason_codes]
        self.explanation = self._build_explanation()

    async def get_detailed_report(self) -> Dict[str, Any]:
        await self.run_all_checks()
        return {
            "risk_level": self.risk_level,
            "status": self.risk_level,
            "identity_score": self.identity_score,
            "total_score": self.identity_score,
            "reason": self.reasons,
            "key_issues": self.reasons,
            "reason_codes": self.reason_codes,
            "key_issue_codes": self.reason_codes,
            "explanation": self.explanation,
            "company_verified": self.company_verified,
            "company_status": self.company_status or "unknown",
            "company_lookup_failed": self.company_lookup_failed,
            "company_not_uk": self.company_not_uk,
            "company_name_mismatch": self.company_name_mismatch,
            "company_name_similarity": self.company_name_similarity,
            "address_match": self.address_match_ok,
            "address_match_score": self.address_match_score,
            "address_status": self._address_status(),
            "email_status": self._email_status(),
            "email_domain": self.email_domain,
            "company_domain": self.company_domain,
            "domain_match": self.domain_match,
            "domain_status": self._domain_status(),
            "contract_website_domain": self.contract_website_domain or None,
            "website_domain_match": self.website_domain_match,
            "free_email_provider": self.free_email_provider,
            "low_identity_data": self.low_identity_data,
            "missing_contact_details": self.missing_contact_details,
            "risk_flags": self.risk_flags,
            "contract_template_hash": self.template_hash,
            "template_reuse": self.template_reuse,
            "contract_date_warning": self.contract_date_warning,
            "suspicious_phrases_found": self.suspicious_phrases_found,
            "suspicious_phrases": self.suspicious_phrases,
            "suspicious_identity_match": self.suspicious_identity_match,
            "suspicious_identity_fields": self.suspicious_identity_fields,
            "official_company_name": self.official_company_name,
            "official_company_number": self.official_company_number,
            "official_registered_address": self.official_registered_address,
            "official_country": self.official_country,
            "official_jurisdiction": self.official_jurisdiction,
            "incorporation_date": self.incorporation_date.isoformat() if self.incorporation_date else None,
            "detailed_scores": {
                "Risk Level": self.risk_level,
                "Identity Confidence Score": self.identity_score,
                "Company Verified": self.company_verified,
                "Company Name Present": not self.company_name_missing,
                "Company UK Match": not self.company_not_uk if self.official_company_name else None,
                "Company Name Matches Official Record": not self.company_name_mismatch if self.official_company_name else None,
                "Company Name Similarity": self.company_name_similarity,
                "Company Status": self.company_status or "unknown",
                "Company Lookup Failed": self.company_lookup_failed,
                "Official Company Name": self.official_company_name,
                "Official Company Number": self.official_company_number,
                "Official Registered Address": self.official_registered_address or None,
                "Official Country": self.official_country,
                "Official Jurisdiction": self.official_jurisdiction,
                "Address Match": self.address_match_ok if not self.address_missing else None,
                "Address Missing": self.address_missing,
                "Address Similarity": self.address_match_score,
                "Address Status": self._address_status(),
                "Email Domain": self.email_domain,
                "Email Missing": self.email_missing,
                "Email Status": self._email_status(),
                "Company Domain": self.company_domain,
                "Domain Match": self.domain_match if not self.email_missing else None,
                "Domain Status": self._domain_status(),
                "Contract Website Domain": self.contract_website_domain or None,
                "Email Website Match": self.website_domain_match if not self.email_missing else None,
                "Free Email Provider": self.free_email_provider if not self.email_missing else None,
                "Low Identity Data": self.low_identity_data,
                "Missing Contact Details": self.missing_contact_details,
                "Template Hash": self.template_hash,
                "Template Reuse": self.template_reuse,
                "Contract Date Warning": self.contract_date_warning,
                "Suspicious Phrases Found": self.suspicious_phrases,
                "Suspicious Identity Match": self.suspicious_identity_match,
                "Suspicious Identity Fields": self.suspicious_identity_fields,
                "Reason Codes": self.reason_codes,
                "Reasons": self.reasons,
                "Explanation": self.explanation,
                "Risk Flags": self.risk_flags,
            },
            "raw_data": self.data,
        }
