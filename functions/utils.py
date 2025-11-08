import os, sys
if __name__ == "__main__" and __package__ is None:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from concurrent.futures import ThreadPoolExecutor
from typing import  Dict, List, Any, Tuple
from datetime import datetime, timedelta
from aiohttp import BasicAuth, ClientTimeout
from database.queries import *
from asyncio import Semaphore
import dns.resolver
import aiohttp
import asyncio
import logging
import re
import os




class AsyncCheckAnalysisContract:
    LOG_DIR = "logs"
    LOG_FILE = os.path.join(LOG_DIR, "async_check_analysis_contract_errors.log")

    def __init__(self, ai_result: Dict[str, Any]):
        self.data = ai_result
        self.score = [0] * 10
        self.api_key = os.getenv('COMPANIES_HOUSE_API')
        self.base_url = "https://api.company-information.service.gov.uk"
        self.session: Optional[aiohttp.ClientSession] = None
        self.semaphore = Semaphore(2)
        self.db_company = None
        self.executor = ThreadPoolExecutor(max_workers=5)

        os.makedirs(self.LOG_DIR, exist_ok=True)
        self.logger = logging.getLogger("AsyncCheckAnalysisContract")
        self.logger.setLevel(logging.ERROR)
        handler = logging.FileHandler(self.LOG_FILE)
        handler.setLevel(logging.ERROR)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
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
                headers={"User-Agent": "ContractChecker/1.0"}
            )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session and not self.session.closed:
            await self.session.close()
        self.executor.shutdown(wait=False)

    async def check_contract_number(self):
        self.score[0] = 10 if self.data.get("Contract Number") else 0

    async def check_company_number(self):
        company_number = self.data.get("Company Number")
        if not company_number:
            self.score[1] = 0
            return

        db_company = await get_company_by_number(company_number)
        now = datetime.utcnow()

        if db_company and db_company['status'] == 'active' and (now - db_company['last_updated']) < timedelta(days=7):
            self.db_company = db_company
            self.score[1] = 30
            return

        url = f"{self.base_url}/company/{company_number}"
        async with self.semaphore:
            try:
                async with self.session.get(url) as resp:
                    if resp.status == 200:
                        info = await resp.json()
                        self.db_company = info
                        status = info.get("company_status", "").lower()
                        self.score[1] = 30 if status == "active" else 0

                        await add_company({
                            'name': info.get('company_name'),
                            'company_number': company_number,
                            'registered_address': self._format_address(info),
                            'status': status,
                            'score': sum(self.score),
                            'website_domain': self.data.get('Website Domain'),
                            'contact_email': None,
                            'phone_number': None
                        })
                    elif resp.status == 404:
                        self.score[1] = 0
                        if db_company:
                            await delete_company_by_number(company_number)
                    else:
                        self.logger.warning(f"API error {resp.status} for {company_number}")
                        self.score[1] = 20 if db_company and db_company['status'] == 'active' else 0
                        self.db_company = db_company if db_company else None
            except Exception as e:
                self.logger.exception(f"Error checking company {company_number}: {e}")
                self.score[1] = 20 if db_company and db_company['status'] == 'active' else 0
                self.db_company = db_company if db_company else None

    async def check_company_name(self):
        company_name = self.data.get("Company Name")
        if not company_name:
            self.score[2] = 0
            return

        db_companies = await get_companies_by_name(company_name)
        found_active = any(c['status'] == 'active' for c in db_companies)
        if found_active:
            if not self.db_company:
                self.db_company = next((c for c in db_companies if c['status'] == 'active'), None)
            self.score[2] = 30
            return

        url = f"{self.base_url}/search/companies"
        params = {"q": company_name}
        async with self.semaphore:
            try:
                async with self.session.get(url, params=params) as resp:
                    if resp.status == 200:
                        results = await resp.json()
                        items = results.get("items", [])
                        found_active = any(item.get("company_status") == "active" for item in items)
                        self.score[2] = 30 if found_active else 0
                        if found_active:
                            exact_match = next(
                                (i for i in items if i.get("title", "").lower() == company_name.lower() and i.get("company_status") == "active"),
                                None
                            )
                            if exact_match:
                                number = exact_match["company_number"]
                                profile_url = f"{self.base_url}/company/{number}"
                                async with self.semaphore:
                                    async with self.session.get(profile_url) as r:
                                        if r.status == 200:
                                            info = await r.json()
                                            self.db_company = info
                                            await add_company({
                                                'name': info.get('company_name'),
                                                'company_number': number,
                                                'registered_address': self._format_address(info),
                                                'status': info.get("company_status"),
                                                'score': sum(self.score),
                                                'website_domain': self.data.get('Website Domain'),
                                                'contact_email': None,
                                                'phone_number': None
                                            })
                    else:
                        self.score[2] = 0
            except Exception as e:
                self.logger.exception(e)
                self.score[2] = 0

    def _format_address(self, info: dict) -> str:
        addr = info.get('registered_office_address', {})
        return ", ".join(filter(None, [
            addr.get('address_line_1'),
            addr.get('address_line_2'),
            addr.get('locality'),
            addr.get('postal_code')
        ]))

    async def check_registered_address(self):
        addr = self.data.get("Registered Address", "").strip()
        if not addr:
            self.score[3] = 0
            return

        addr_lower = addr.lower()
        if self.db_company:
            db_addr = self._format_address(self.db_company).lower()
            if db_addr and (addr_lower == db_addr or addr_lower in db_addr or db_addr in addr_lower):
                self.score[3] = 10
            else:
                self.score[3] = -10
            return

        company_number = self.data.get("Company Number")
        if company_number:
            url = f"{self.base_url}/company/{company_number}"
            async with self.semaphore:
                try:
                    async with self.session.get(url) as resp:
                        if resp.status == 200:
                            info = await resp.json()
                            db_addr = self._format_address(info).lower()
                            if db_addr and (addr_lower == db_addr or addr_lower in db_addr or db_addr in addr_lower):
                                self.score[3] = 10
                            else:
                                self.score[3] = -10
                        else:
                            self.score[3] = 0
                except Exception as e:
                    self.logger.exception(e)
                    self.score[3] = 0
        else:
            self.score[3] = 0

    async def check_contact_details(self):
        contact = self.data.get("Contact Details", "")
        if not contact:
            self.score[4] = -10
            return

        emails = re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", contact)
        phones = re.findall(r"\+44\d{10}|\+44\s?\d{3}\s?\d{3}\s?\d{4}|0\d{10}", contact)

        if not emails and not phones:
            self.score[4] = -10
            return

        phone_score = 5 if any(self.is_valid_uk_phone(p) for p in phones) else 0
        email_score = 0
        company_lower = self.data.get("Company Name", "").lower()
        resp_lower = self.data.get("Responsible Person Full Name", "").lower()

        for email in emails:
            domain = email.split('@')[1].lower()
            mx_valid = await self._check_mx_records(domain)
            http_valid = await self._check_domain_exists(domain)
            if mx_valid and http_valid:
                email_score = 5
                if await self._check_domain_match(domain, company_lower):
                    email_score += 5
                local_part = email.split('@')[0].lower()
                if resp_lower and (local_part in resp_lower or any(w in local_part for w in resp_lower.split())):
                    email_score += 5
                break
            else:
                email_score = -5

        self.score[4] = max(min(phone_score + email_score, 10), -10)

    def is_valid_uk_phone(self, phone: str) -> bool:
        cleaned = re.sub(r'\D', '', phone)
        return (cleaned.startswith('44') and len(cleaned) == 12) or (cleaned.startswith('0') and len(cleaned) == 11)

    async def _check_mx_records(self, domain: str) -> bool:
        loop = asyncio.get_running_loop()
        try:
            records = await loop.run_in_executor(self.executor, dns.resolver.resolve, domain, 'MX')
            return len(records) > 0
        except Exception:
            return False

    async def check_suspicious_phrases(self):
            phrases = [
                "urgent payment", "no interview required", "send money", "confidential fee",
                "suspicious link", "payment before work", "wire transfer", "advance fee"
            ]
            text = " ".join(str(v) for v in self.data.values() if v).lower()
            self.score[5] = -20 if any(p in text for p in phrases) else 0
    
            suspicious = await check_suspicious_company(
                company_number=self.data.get("Company Number"),
                company_name=self.data.get("Company Name")
            )
            if suspicious:
                self.score[5] -= 20

    async def check_text_style(self):
        style = self.data.get("Text Style")
        self.score[6] = 10 if style == "professional" else (0 if style == "template-like" else -10)

    async def check_website_domain(self):
        domain = self.data.get("Website Domain", "").strip()
        if not domain:
            self.score[7] = -10
            return

        domain = re.sub(r'^(https?://|www\.)', '', domain, flags=re.IGNORECASE).strip('/')
        if not domain:
            self.score[7] = -10
            return

        company_lower = self.data.get("Company Name", "").lower()
        exists = await self._check_domain_exists(domain)
        match = await self._check_domain_match(domain, company_lower) if exists else False
        self.score[7] = 10 if exists and match else -10

    async def _check_domain_exists(self, domain: str) -> bool:
        for scheme in ['https', 'http']:
            try:
                async with self.session.get(f"{scheme}://{domain}", timeout=6, allow_redirects=True) as resp:
                    if resp.status < 400:
                        return True
            except Exception:
                continue
        return False

    async def _check_domain_match(self, domain: str, company: str) -> bool:
        words = [w.lower() for w in re.split(r'\W+', company) if len(w) > 2]
        return any(word in domain.lower() for word in words)

    async def check_responsible_person(self):
        name = self.data.get("Responsible Person Full Name")
        if not name:
            self.score[8] = 0
            return

        company_num = self.data.get("Company Number")
        if not company_num:
            self.score[8] = 10
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
                            name_lower in officer.get("name", "").lower() and not officer.get("resigned_on")
                            for officer in officers
                        )
                        self.score[8] = 10 if active_match else 0
                    else:
                        self.score[8] = 10
            except Exception as e:
                self.logger.exception(e)
                self.score[8] = 10

    async def check_contract_date(self):
        date_str = self.data.get("Contract Date")
        if not date_str:
            self.score[9] = 0
            return

        formats = ["%Y-%m-%d", "%d %B %Y", "%d %b %Y", "%B %d, %Y"]
        parsed = None
        for fmt in formats:
            try:
                parsed = datetime.strptime(date_str.strip(), fmt)
                break
            except ValueError:
                continue

        if parsed:
            days_diff = (datetime.now() - parsed).days
            self.score[9] = 10 if 0 <= days_diff <= 30 else -10
        else:
            self.score[9] = 0

    async def check_data_match(self):
        if not self.db_company:
            return
        bonus = 0
        if self.data.get("Company Name", "").strip().lower() == self.db_company.get("company_name", "").lower():
            bonus += 10
        addr = self.data.get("Registered Address", "").lower()
        db_addr = self._format_address(self.db_company).lower()
        if addr and (addr == db_addr or addr in db_addr or db_addr in addr):
            bonus += 10
        self.score[1] += bonus

    async def run_all_checks(self) -> List[int]:
        tasks = [
            self.check_contract_number(),
            self.check_company_number(),
            self.check_company_name(),
            self.check_registered_address(),
            self.check_contact_details(),
            self.check_suspicious_phrases(),
            self.check_text_style(),
            self.check_website_domain(),
            self.check_responsible_person(),
            self.check_contract_date(),
            self.check_data_match()
        ]
        await asyncio.gather(*tasks, return_exceptions=True)
        return self.score

    async def calculate_total_score(self) -> Tuple[int, str]:
        await self.run_all_checks()
        total = sum(self.score)
        status = "Safe" if total >= 80 else ("Warning" if total >= 50 else "Unsafe")
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
                "Contract Date": self.score[9]
            },
            "raw_data": self.data
        }


