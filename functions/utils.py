import os
import sys

if __name__ == "__main__" and __package__ is None:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Dict, List, Any, Tuple, Optional
from asyncio import Semaphore
from aiohttp import BasicAuth, ClientTimeout
from database.queries import (
    add_company,
    check_suspicious_company,
    delete_company_by_number,
    get_companies_by_name,
    get_company_by_number,
)
import dns.resolver
import aiohttp
import asyncio
import logging
import re


class AsyncCheckAnalysisContract:
    LOG_DIR = "logs"
    LOG_FILE = os.path.join(LOG_DIR, "async_check_analysis_contract_errors.log")

    def __init__(self, ai_result: Dict[str, Any], raw_contract_text: str = ""):
        self.data = ai_result or {}
        self.raw_contract_text = raw_contract_text or ""
        self.score = [0] * 10
        self.api_key = os.getenv("COMPANIES_HOUSE_API")
        self.base_url = "https://api.company-information.service.gov.uk"
        self.session: Optional[aiohttp.ClientSession] = None
        self.semaphore = Semaphore(2)
        self.db_company: Optional[Dict[str, Any]] = None
        self.executor = ThreadPoolExecutor(max_workers=5)

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
        self.executor.shutdown(wait=False)

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

    def _is_strong_name_match(self, left: str, right: str) -> bool:
        l = self._normalized_name_key(left)
        r = self._normalized_name_key(right)
        return bool(l and r and l == r)

    def _is_weak_name_match(self, left: str, right: str) -> bool:
        l = self._normalized_name_key(left)
        r = self._normalized_name_key(right)
        if not l or not r:
            return False

        l_tokens = {t for t in l.split() if len(t) > 2}
        r_tokens = {t for t in r.split() if len(t) > 2}
        if not l_tokens or not r_tokens:
            return False

        overlap = len(l_tokens & r_tokens)
        baseline = min(len(l_tokens), len(r_tokens))
        return (overlap / baseline) >= 0.6

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

    def _address_matches(self, left: str, right: str) -> bool:
        left_norm = re.sub(r"\s+", " ", (left or "").strip().lower()).strip(" ,.")
        right_norm = re.sub(r"\s+", " ", (right or "").strip().lower()).strip(" ,.")
        if not left_norm or not right_norm:
            return False
        return (
            left_norm == right_norm
            or left_norm in right_norm
            or right_norm in left_norm
        )

    async def check_contract_number(self):
        self.score[0] = 10 if self.data.get("Contract Number") else 0

    async def check_company_number(self):
        company_number = self._normalize_company_number(self.data.get("Company Number"))
        if not company_number:
            self.score[1] = 0
            return

        self.data["Company Number"] = company_number
        db_company = await get_company_by_number(company_number)
        now = datetime.utcnow()

        if db_company and str(db_company.get("status", "")).lower() == "active":
            last_updated = db_company.get("last_updated")
            if isinstance(last_updated, datetime) and (now - last_updated) < timedelta(days=30):
                self.db_company = db_company
                self.score[1] = 30
                return
            self.db_company = db_company

        url = f"{self.base_url}/company/{company_number}"
        async with self.semaphore:
            try:
                async with self.session.get(url) as resp:
                    if resp.status == 200:
                        info = await resp.json()
                        status = str(info.get("company_status", "")).lower()
                        self.db_company = info
                        self.score[1] = 30 if status == "active" else -10

                        await add_company(
                            {
                                "name": info.get("company_name"),
                                "company_number": company_number,
                                "registered_address": self._format_address(info),
                                "status": status or "unknown",
                                "score": 0,
                                "website_domain": self.data.get("Website Domain"),
                                "contact_email": None,
                                "phone_number": None,
                            }
                        )
                    elif resp.status == 404:
                        self.score[1] = -10
                        if db_company:
                            await delete_company_by_number(company_number)
                    else:
                        self.score[1] = 20 if db_company and str(db_company.get("status", "")).lower() == "active" else 0
            except Exception as e:
                self.logger.exception(f"Error checking company number {company_number}: {e}")
                self.score[1] = 20 if db_company and str(db_company.get("status", "")).lower() == "active" else 0

    async def check_company_name(self):
        company_name = self._normalize_company_name(self.data.get("Company Name"))
        if not company_name:
            self.score[2] = 0
            return

        self.data["Company Name"] = company_name
        company_number = self.data.get("Company Number")

        if self.db_company:
            db_name = self._company_name_from_record(self.db_company)
            if self._is_strong_name_match(company_name, db_name):
                self.score[2] = 30
            elif self._is_weak_name_match(company_name, db_name):
                self.score[2] = 10
            else:
                self.score[2] = -20 if company_number else -10
            return

        db_companies = await get_companies_by_name(company_name)
        active_db_companies = [
            c for c in db_companies if str(c.get("status", "")).lower() == "active"
        ]
        if active_db_companies:
            exact_db = next(
                (
                    c
                    for c in active_db_companies
                    if self._is_strong_name_match(company_name, self._company_name_from_record(c))
                ),
                None,
            )
            if exact_db:
                self.db_company = exact_db
                self.score[2] = 25
            else:
                self.score[2] = max(self.score[2], 10)

        url = f"{self.base_url}/search/companies"
        params = {"q": company_name}
        try:
            async with self.semaphore:
                async with self.session.get(url, params=params) as resp:
                    if resp.status != 200:
                        return
                    results = await resp.json()
        except Exception as e:
            self.logger.exception(f"Error searching company name {company_name}: {e}")
            return

        items = results.get("items", [])
        active_items = [item for item in items if str(item.get("company_status", "")).lower() == "active"]
        if not active_items:
            if company_number and self.score[2] == 0:
                self.score[2] = -10
            return

        exact_match = next(
            (
                i
                for i in active_items
                if self._is_strong_name_match(company_name, i.get("title", ""))
            ),
            None,
        )
        weak_match = next(
            (
                i
                for i in active_items
                if self._is_weak_name_match(company_name, i.get("title", ""))
            ),
            None,
        )

        if exact_match:
            self.score[2] = max(self.score[2], 25)
            number = exact_match.get("company_number")
            if number:
                profile_url = f"{self.base_url}/company/{number}"
                try:
                    async with self.semaphore:
                        async with self.session.get(profile_url) as profile_resp:
                            if profile_resp.status == 200:
                                info = await profile_resp.json()
                                self.db_company = info
                                await add_company(
                                    {
                                        "name": info.get("company_name"),
                                        "company_number": number,
                                        "registered_address": self._format_address(info),
                                        "status": str(info.get("company_status", "")).lower() or "unknown",
                                        "score": 0,
                                        "website_domain": self.data.get("Website Domain"),
                                        "contact_email": None,
                                        "phone_number": None,
                                    }
                                )
                except Exception as e:
                    self.logger.exception(f"Error loading company profile {number}: {e}")
        elif weak_match:
            self.score[2] = max(self.score[2], 10)
        elif company_number and self.score[2] == 0:
            self.score[2] = -10

    async def check_registered_address(self):
        addr = str(self.data.get("Registered Address") or "").strip()
        if not addr:
            self.score[3] = 0
            return

        db_addr = ""
        if self.db_company:
            db_addr = self._format_address(self.db_company)

        if not db_addr and self.data.get("Company Number"):
            url = f"{self.base_url}/company/{self.data.get('Company Number')}"
            try:
                async with self.semaphore:
                    async with self.session.get(url) as resp:
                        if resp.status == 200:
                            info = await resp.json()
                            db_addr = self._format_address(info)
                            if not self.db_company:
                                self.db_company = info
            except Exception as e:
                self.logger.exception(f"Error checking registered address: {e}")

        if not db_addr:
            self.score[3] = 0
            return

        if self._address_matches(addr, db_addr):
            self.score[3] = 10
        else:
            self.score[3] = -10 if self.data.get("Company Number") else -5

    async def check_contact_details(self):
        contact = str(self.data.get("Contact Details") or "").strip()
        if not contact:
            self.score[4] = 0
            return

        emails = re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", contact)
        phones = re.findall(r"\+44\d{10}|\+44\s?\d{3}\s?\d{3}\s?\d{4}|0\d{10}", contact)

        if not emails and not phones:
            self.score[4] = -5
            return

        phone_score = 4 if any(self.is_valid_uk_phone(p) for p in phones) else 0
        email_score = 0
        company_lower = self._normalize_company_name(self.data.get("Company Name")).lower()
        resp_lower = str(self.data.get("Responsible Person Full Name") or "").lower()

        for email in emails:
            domain = email.split("@")[1].lower()
            mx_valid = await self._check_mx_records(domain)
            if not mx_valid:
                continue

            candidate = 4
            if company_lower and await self._check_domain_match(domain, company_lower):
                candidate += 4

            local_part = email.split("@")[0].lower()
            if resp_lower and (local_part in resp_lower or any(w in local_part for w in resp_lower.split())):
                candidate += 2

            email_score = max(email_score, min(candidate, 10))

        if emails and email_score == 0:
            email_score = -2

        self.score[4] = max(min(phone_score + email_score, 10), -5)

    def is_valid_uk_phone(self, phone: str) -> bool:
        cleaned = re.sub(r"\D", "", phone)
        return (cleaned.startswith("44") and len(cleaned) == 12) or (cleaned.startswith("0") and len(cleaned) == 11)

    async def _check_mx_records(self, domain: str) -> bool:
        loop = asyncio.get_running_loop()
        try:
            records = await loop.run_in_executor(self.executor, dns.resolver.resolve, domain, "MX")
            return len(records) > 0
        except Exception:
            return False

    async def check_suspicious_phrases(self):
        phrases = [
            "urgent payment",
            "no interview required",
            "send money",
            "confidential fee",
            "suspicious link",
            "payment before work",
            "wire transfer",
            "advance fee",
        ]

        structured_text = " ".join(str(v) for v in self.data.values() if v)
        blob = f"{structured_text}\n{self.raw_contract_text}".lower()
        self.score[5] = -20 if any(p in blob for p in phrases) else 0

        suspicious = await check_suspicious_company(
            company_number=self.data.get("Company Number"),
            company_name=self.data.get("Company Name"),
        )
        if suspicious:
            self.score[5] -= 25

    async def check_text_style(self):
        style = self.data.get("Text Style")
        # Style is informative, but should not outweigh factual verification signals.
        self.score[6] = 4 if style == "professional" else (0 if style == "template-like" else -8)

    async def check_website_domain(self):
        domain = str(self.data.get("Website Domain") or "").strip()
        if not domain:
            self.score[7] = 0
            return

        domain = re.sub(r"^(https?://|www\.)", "", domain, flags=re.IGNORECASE).strip("/")
        if not re.match(r"^[a-z0-9.-]+\.[a-z]{2,}$", domain, flags=re.IGNORECASE):
            self.score[7] = -5
            return

        exists = await self._check_domain_exists(domain)
        if not exists:
            self.score[7] = -5
            return

        company_lower = self._normalize_company_name(self.data.get("Company Name")).lower()
        if company_lower:
            match = await self._check_domain_match(domain, company_lower)
            self.score[7] = 10 if match else -5
        else:
            self.score[7] = 5

    async def _check_domain_exists(self, domain: str) -> bool:
        for scheme in ["https", "http"]:
            try:
                async with self.session.get(f"{scheme}://{domain}", timeout=6, allow_redirects=True) as resp:
                    if resp.status < 400:
                        return True
            except Exception:
                continue
        return False

    async def _check_domain_match(self, domain: str, company: str) -> bool:
        company_tokens = [w.lower() for w in re.split(r"\W+", company) if len(w) > 2]
        common = {"limited", "ltd", "plc", "llp", "company", "group", "services"}
        tokens = [w for w in company_tokens if w not in common]
        if not tokens:
            return False
        domain_lower = domain.lower()
        return any(token in domain_lower for token in tokens)

    async def check_responsible_person(self):
        name = str(self.data.get("Responsible Person Full Name") or "").strip()
        if not name:
            self.score[8] = 0
            return

        company_num = self._normalize_company_number(self.data.get("Company Number"))
        if not company_num:
            self.score[8] = 0
            return

        url = f"{self.base_url}/company/{company_num}/officers"
        params = {"items_per_page": 100}
        async with self.semaphore:
            try:
                async with self.session.get(url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        officers = data.get("items", [])
                        name_lower = name.lower()
                        active_match = any(
                            name_lower in str(officer.get("name", "")).lower()
                            and not officer.get("resigned_on")
                            for officer in officers
                        )
                        self.score[8] = 10 if active_match else 0
                    else:
                        self.score[8] = 0
            except Exception as e:
                self.logger.exception(f"Error checking responsible person: {e}")
                self.score[8] = 0

    async def check_contract_date(self):
        date_str = str(self.data.get("Contract Date") or "").strip()
        if not date_str:
            self.score[9] = 0
            return

        formats = [
            "%Y-%m-%d",
            "%d %B %Y",
            "%d %b %Y",
            "%B %d, %Y",
            "%d/%m/%Y",
            "%d-%m-%Y",
            "%d.%m.%Y",
        ]

        parsed: Optional[datetime] = None
        for fmt in formats:
            try:
                parsed = datetime.strptime(date_str, fmt)
                break
            except ValueError:
                continue

        if not parsed:
            self.score[9] = 0
            return

        days_diff = (datetime.utcnow().date() - parsed.date()).days
        if days_diff < -90:
            self.score[9] = -10
        elif days_diff < 0:
            self.score[9] = 0
        elif days_diff <= 180:
            self.score[9] = 10
        elif days_diff <= 3650:
            self.score[9] = 5
        else:
            self.score[9] = -5

    async def check_data_match(self):
        if not self.db_company:
            return

        bonus = 0
        company_number_present = bool(self.data.get("Company Number"))
        extracted_name = self._normalize_company_name(self.data.get("Company Name"))
        db_name = self._company_name_from_record(self.db_company)

        if extracted_name and db_name:
            if self._is_strong_name_match(extracted_name, db_name):
                bonus += 10
            elif company_number_present and not self._is_weak_name_match(extracted_name, db_name):
                bonus -= 20

        extracted_addr = str(self.data.get("Registered Address") or "").strip()
        db_addr = self._format_address(self.db_company)
        if extracted_addr and db_addr:
            if self._address_matches(extracted_addr, db_addr):
                bonus += 10
            elif company_number_present:
                bonus -= 10

        self.score[1] = max(min(self.score[1] + bonus, 40), -20)

    async def run_all_checks(self) -> List[int]:
        await self.check_company_number()
        await self.check_company_name()

        tasks = [
            self.check_contract_number(),
            self.check_registered_address(),
            self.check_contact_details(),
            self.check_suspicious_phrases(),
            self.check_text_style(),
            self.check_website_domain(),
            self.check_responsible_person(),
            self.check_contract_date(),
        ]
        await asyncio.gather(*tasks, return_exceptions=True)
        await self.check_data_match()
        return self.score

    async def calculate_total_score(self) -> Tuple[int, str]:
        await self.run_all_checks()
        raw_total = sum(self.score)
        total = max(0, min(100, raw_total))

        company_number_present = bool(self._normalize_company_number(self.data.get("Company Number")))
        company_number_verified = self.score[1] >= 25
        strong_company_identity = self.score[2] >= 20
        critical_mismatch = (
            self.score[1] < 0
            or self.score[2] < 0
            or self.score[3] <= -10
            or self.score[7] < 0
        )

        # Cap score if core identity verification is weak.
        if not company_number_present:
            total = min(total, 55)
        elif not company_number_verified:
            total = min(total, 65)
        elif not strong_company_identity:
            total = min(total, 70)

        if self.score[5] <= -40:
            status = "Unsafe"
        elif critical_mismatch:
            status = "Warning" if total >= 35 else "Unsafe"
        elif total >= 75 and company_number_verified and strong_company_identity:
            status = "Safe"
        elif total >= 45:
            status = "Warning"
        else:
            status = "Unsafe"

        if self.score[5] <= -20 and status == "Safe":
            status = "Warning"
        if (not company_number_present or not company_number_verified or not strong_company_identity) and status == "Safe":
            status = "Warning"

        return total, status

    async def get_detailed_report(self) -> Dict[str, Any]:
        total, status = await self.calculate_total_score()
        return {
            "total_score": total,
            "status": status,
            "detailed_scores": {
                "Contract Number": self.score[0],
                "Company Number": self.score[1],
                "Company Name": self.score[2],
                "Registered Address": self.score[3],
                "Contact Details": self.score[4],
                "Suspicious Phrases": self.score[5],
                "Text Style": self.score[6],
                "Website Domain": self.score[7],
                "Responsible Person": self.score[8],
                "Contract Date": self.score[9],
            },
            "raw_data": self.data,
        }
