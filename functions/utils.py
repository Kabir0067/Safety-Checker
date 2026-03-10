import os
import sys

if __name__ == "__main__" and __package__ is None:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta, date
from typing import Dict, List, Any, Tuple, Optional
from asyncio import Semaphore
from aiohttp import BasicAuth, ClientTimeout
from database.queries import (
    add_company,
    get_companies_by_name,
    get_company_by_number,
    check_suspicious_company,
    delete_company_by_number,
    get_distinct_company_names_by_template,
)
import aiohttp
import asyncio
import logging
import re
import hashlib
import difflib


class AsyncCheckAnalysisContract:
    LOG_DIR = "logs"
    LOG_FILE = os.path.join(LOG_DIR, "async_check_analysis_contract_errors.log")

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
        self.company_high_risk = False
        self.company_lookup_failed = False
        self.company_status: Optional[str] = None
        self.official_company_name: Optional[str] = None
        self.official_company_number: Optional[str] = None
        self.official_registered_address: str = ""
        self.incorporation_date: Optional[date] = None

        self.address_match_score: Optional[int] = None
        self.address_match_ok = False
        self.address_mismatch = False

        self.email_domain: Optional[str] = None
        self.company_domain: Optional[str] = None
        self.domain_match = False
        self.domain_mismatch = False
        self.free_email_provider = False

        self.template_hash: Optional[str] = None
        self.template_reuse = False
        self.contract_date_warning = False
        self.manual_blacklist = False
        self.risk_flags: List[str] = []

        os.makedirs(self.LOG_DIR, exist_ok=True)
        self.logger = logging.getLogger("AsyncCheckAnalysisContract")
        self.logger.setLevel(logging.ERROR)
        handler = logging.FileHandler(self.LOG_FILE)
        handler.setLevel(logging.ERROR)
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        handler.setFormatter(formatter)
        if not self.logger.handlers:
            self.logger.addHandler(handler)

    async def __aenter__(self):
        if not self.session or self.session.closed:
            auth = BasicAuth(login=self.api_key, password="") if self.api_key else None
            timeout = ClientTimeout(total=15)
            self.session = aiohttp.ClientSession(
                auth=auth,
                timeout=timeout,
                headers={"User-Agent": "ContractChecker/1.0"},
            )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session and not self.session.closed:
            await self.session.close()

    def _normalize_company_number(self, value: Any) -> str:
        if value is None:
            return ""
        return re.sub(r"\s+", "", str(value).strip().upper())

    def _normalize_company_name(self, value: Any) -> str:
        if value is None:
            return ""
        text = str(value).strip()
        text = re.sub(r"\s+", " ", text)
        return text

    def _normalized_name_key(self, value: Any) -> str:
        text = self._normalize_company_name(value).lower()
        text = re.sub(r"[^a-z0-9& ]+", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _company_name_from_record(self, info: Optional[Dict[str, Any]]) -> str:
        if not info:
            return ""
        return str(info.get("company_name") or info.get("name") or "").strip()

    def _format_address(self, info: Dict[str, Any]) -> str:
        if not info:
            return ""

        if isinstance(info.get("registered_office_address"), dict):
            addr = info.get("registered_office_address", {})
            return ", ".join(
                filter(
                    None,
                    [
                        addr.get("address_line_1"),
                        addr.get("address_line_2"),
                        addr.get("locality"),
                        addr.get("postal_code"),
                    ],
                )
            )

        direct = info.get("registered_address")
        if direct:
            return str(direct).strip()
        return ""

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
        if email_domain == company_domain:
            return True
        if email_domain.endswith("." + company_domain):
            return True
        if company_domain.endswith("." + email_domain):
            return True
        return False

    def _normalize_address_text(self, text: str) -> str:
        cleaned = re.sub(r"[^\w\s]", " ", str(text or "").lower())
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

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
        l = self._normalized_name_key(left)
        r = self._normalized_name_key(right)
        if not l or not r:
            return 0.0
        return difflib.SequenceMatcher(None, l, r).ratio()

    def _extract_emails(self, text: str) -> List[str]:
        if not text:
            return []
        found = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
        seen = set()
        emails = []
        for email in found:
            e = email.strip()
            if e and e not in seen:
                emails.append(e)
                seen.add(e)
        return emails

    def _extract_phone_numbers(self, text: str) -> List[str]:
        if not text:
            return []
        found = re.findall(r"\+?\d[\d\s().-]{7,}\d", text)
        seen = set()
        phones = []
        for phone in found:
            p = re.sub(r"\s+", " ", phone).strip()
            if p and p not in seen:
                phones.append(p)
                seen.add(p)
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
                async with self.session.get(url) as resp:
                    if resp.status == 200:
                        return await resp.json(), resp.status
                    return None, resp.status
            except Exception as e:
                self.logger.exception(f"Error checking company profile {company_number}: {e}")
        return None, None

    async def _search_company_by_name(self, company_name: str) -> Optional[List[Dict[str, Any]]]:
        url = f"{self.base_url}/search/companies"
        params = {"q": company_name}
        async with self.semaphore:
            try:
                async with self.session.get(url, params=params) as resp:
                    if resp.status != 200:
                        return None
                    results = await resp.json()
                    return results.get("items", []) or []
            except Exception as e:
                self.logger.exception(f"Error searching company name {company_name}: {e}")
        return None

    def _apply_company_record(self, info: Dict[str, Any]) -> None:
        self.db_company = info
        self.official_company_name = self._company_name_from_record(info) or None
        self.official_company_number = info.get("company_number") or self.data.get("Company Number")
        self.company_status = str(info.get("status") or info.get("company_status") or "unknown").lower()
        self.official_registered_address = self._format_address(info) or info.get("registered_address") or ""
        self.incorporation_date = self._parse_date(info.get("incorporation_date") or info.get("date_of_creation"))

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
                "incorporation_date": info.get("date_of_creation"),
            }
        )

    async def verify_company(self) -> None:
        self.company_verified = False
        self.company_not_found = False
        self.company_status = None
        self.company_high_risk = False
        self.company_lookup_failed = False
        self.official_company_name = None
        self.official_company_number = None
        self.official_registered_address = ""
        self.incorporation_date = None

        company_number = self._normalize_company_number(self.data.get("Company Number"))
        company_name = self._normalize_company_name(self.data.get("Company Name"))

        if company_number:
            self.data["Company Number"] = company_number
            db_company = await get_company_by_number(company_number)
            now = datetime.utcnow()
            if db_company:
                last_updated = db_company.get("last_updated")
                if isinstance(last_updated, datetime) and (now - last_updated) < timedelta(days=30):
                    self._apply_company_record(db_company)
                    self.company_verified = self.company_status == "active"
                    return
                self._apply_company_record(db_company)

            info, status_code = await self._fetch_company_profile(company_number)
            if info:
                self._apply_company_record(info)
                await self._cache_company_info(info, company_number)
            elif status_code == 404:
                self.company_not_found = True
                if db_company:
                    await delete_company_by_number(company_number)
            elif status_code is None:
                if not db_company:
                    self.company_lookup_failed = True
            elif db_company:
                self.company_not_found = False
            else:
                self.company_not_found = True

            self.company_verified = self.company_status == "active"
            return

        if not company_name:
            self.company_not_found = True
            return

        self.data["Company Name"] = company_name

        db_companies = await get_companies_by_name(company_name)
        if db_companies:
            active_db = [
                c for c in db_companies if str(c.get("status", "")).lower() == "active"
            ]
            pick = active_db[0] if active_db else db_companies[0]
            last_updated = pick.get("last_updated")
            if isinstance(last_updated, datetime) and (datetime.utcnow() - last_updated) < timedelta(days=30):
                self._apply_company_record(pick)
                self.company_verified = self.company_status == "active"
                return

        items = await self._search_company_by_name(company_name)
        if items is None:
            self.company_lookup_failed = True
            return
        if not items:
            self.company_not_found = True
            return

        best_item = None
        best_score = 0.0
        for item in items:
            score = self._name_similarity(company_name, item.get("title", ""))
            if score > best_score:
                best_score = score
                best_item = item

        if not best_item or best_score < 0.7:
            self.company_not_found = True
            return

        number = best_item.get("company_number")
        info = None
        if number:
            info, status_code = await self._fetch_company_profile(number)
        else:
            status_code = None

        if info:
            self._apply_company_record(info)
            await self._cache_company_info(info, number)
            if not self.data.get("Company Number") and number:
                self.data["Company Number"] = number
        else:
            self.db_company = best_item
            self.official_company_name = best_item.get("title") or company_name
            self.official_company_number = number
            self.company_status = str(best_item.get("company_status") or "unknown").lower()
            self.official_registered_address = str(best_item.get("address_snippet") or "").strip()

            await add_company(
                {
                    "name": self.official_company_name,
                    "company_number": number,
                    "registered_address": self.official_registered_address,
                    "status": self.company_status,
                    "score": 0,
                    "website_domain": self.data.get("Website Domain"),
                    "contact_email": None,
                    "phone_number": None,
                    "incorporation_date": None,
                }
            )

        self.company_verified = self.company_status == "active"

    async def check_manual_blacklist(self) -> None:
        try:
            suspicious = await check_suspicious_company(
                company_number=self.data.get("Company Number"),
                company_name=self.data.get("Company Name"),
            )
            if suspicious:
                self.manual_blacklist = True
                self.risk_flags.append("suspicious_company_listed")
        except Exception as e:
            self.logger.exception(f"Error checking suspicious companies list: {e}")

    async def check_address_match(self) -> None:
        self.address_match_score = None
        self.address_match_ok = False
        self.address_mismatch = False

        contract_address = str(self.data.get("Registered Address") or "").strip()
        official_address = str(self.official_registered_address or "").strip()
        if not contract_address or not official_address:
            return

        similarity = self._address_similarity(contract_address, official_address)
        score = int(round(similarity * 100))
        self.address_match_score = score
        if score >= 70:
            self.address_match_ok = True
        else:
            self.address_mismatch = True
            self.risk_flags.append("address_mismatch")

    async def check_email_domain(self) -> None:
        self.email_domain = None
        self.company_domain = None
        self.domain_match = False
        self.domain_mismatch = False
        self.free_email_provider = False

        contact = str(self.data.get("Contact Details") or "").strip()
        emails = self._extract_emails(contact)
        if not emails:
            emails = self._extract_emails(self.raw_contract_text)

        domains = [self._normalize_domain(e) for e in emails]
        domains = [d for d in domains if d]
        if domains:
            self.email_domain = domains[0]

        self.company_domain = self._normalize_domain(self.data.get("Website Domain"))

        free_providers = {
            "gmail.com",
            "yahoo.com",
            "outlook.com",
            "hotmail.com",
            "protonmail.com",
        }

        if any(d in free_providers for d in domains):
            self.free_email_provider = True
            self.risk_flags.append("free_email_provider")

        if domains and self.company_domain:
            if any(self._domains_match(d, self.company_domain) for d in domains):
                self.domain_match = True
            else:
                self.domain_mismatch = True
                self.risk_flags.append("domain_mismatch")

    async def check_template_reuse(self) -> None:
        self.template_hash = None
        self.template_reuse = False

        normalized = self._normalize_contract_text_for_hash(self.raw_contract_text)
        if not normalized:
            return

        self.template_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        previous_names = await get_distinct_company_names_by_template(self.template_hash)
        current_name = self._normalized_name_key(self.data.get("Company Name"))

        if not current_name or not previous_names:
            return

        previous_norm = {self._normalized_name_key(n) for n in previous_names if n}
        previous_norm = {n for n in previous_norm if n}
        if previous_norm and any(n != current_name for n in previous_norm):
            self.template_reuse = True
            self.risk_flags.append("template_reuse")

    async def check_contract_date(self) -> None:
        self.contract_date_warning = False
        raw_date = self.data.get("Contract Date")
        parsed = self._parse_date(raw_date)
        if not parsed:
            return

        today = datetime.utcnow().date()
        if parsed > (today + timedelta(days=365)):
            self.contract_date_warning = True
            self.risk_flags.append("contract_date_too_future")
        elif parsed < (today - timedelta(days=365 * 5)):
            self.contract_date_warning = True
            self.risk_flags.append("contract_date_too_old")

    def _compute_total_score(self) -> int:
        total = 0
        if self.company_verified:
            total += 40
        if self.address_match_ok:
            total += 20
        if self.domain_match:
            total += 10
        if self.company_not_found:
            total -= 50
        if self.company_high_risk:
            total -= 40
        if self.domain_mismatch:
            total -= 20
        if self.free_email_provider:
            total -= 15
        if self.address_mismatch:
            total -= 20
        return max(0, min(100, total))

    async def run_all_checks(self) -> None:
        self.risk_flags = []
        self.manual_blacklist = False

        await self.verify_company()

        status = (self.company_status or "").lower()
        if status in {"dissolved", "liquidation"} or "liquidation" in status:
            self.company_high_risk = True
            self.risk_flags.append("company_dissolved")
        elif self.company_not_found:
            self.risk_flags.append("company_not_found")
        elif self.company_lookup_failed:
            self.risk_flags.append("company_lookup_failed")

        await asyncio.gather(
            self.check_address_match(),
            self.check_email_domain(),
            self.check_template_reuse(),
            self.check_contract_date(),
            self.check_manual_blacklist(),
        )

    async def calculate_total_score(self) -> Tuple[int, str]:
        await self.run_all_checks()
        total = self._compute_total_score()

        if self.company_not_found or self.company_high_risk or self.manual_blacklist:
            status = "Unsafe"
        elif total >= 60:
            status = "Safe"
        elif total >= 30:
            status = "Warning"
        else:
            status = "Unsafe"

        if self.template_reuse and status == "Safe":
            status = "Warning"
        if self.contract_date_warning and status == "Safe":
            status = "Warning"
        if (
            self.company_lookup_failed
            and status == "Unsafe"
            and not self.company_not_found
            and not self.company_high_risk
            and not self.manual_blacklist
        ):
            status = "Warning"

        return total, status

    async def get_detailed_report(self) -> Dict[str, Any]:
        total, status = await self.calculate_total_score()
        return {
            "total_score": total,
            "status": status,
            "company_verified": self.company_verified,
            "company_status": self.company_status or "unknown",
            "company_lookup_failed": self.company_lookup_failed,
            "address_match_score": self.address_match_score,
            "email_domain": self.email_domain,
            "risk_flags": self.risk_flags,
            "contract_template_hash": self.template_hash,
            "template_reuse": self.template_reuse,
            "contract_date_warning": self.contract_date_warning,
            "official_company_name": self.official_company_name,
            "official_company_number": self.official_company_number,
            "official_registered_address": self.official_registered_address,
            "incorporation_date": self.incorporation_date.isoformat() if self.incorporation_date else None,
            "detailed_scores": {
                "Company Verified": self.company_verified,
                "Company Status": self.company_status or "unknown",
                "Company Lookup Failed": self.company_lookup_failed,
                "Address Match Score": self.address_match_score,
                "Email Domain": self.email_domain,
                "Company Domain": self.company_domain,
                "Domain Match": self.domain_match,
                "Free Email Provider": self.free_email_provider,
                "Template Hash": self.template_hash,
                "Template Reuse": self.template_reuse,
                "Contract Date Warning": self.contract_date_warning,
                "Risk Flags": self.risk_flags,
            },
            "raw_data": self.data,
        }
