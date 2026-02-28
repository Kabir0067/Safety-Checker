from typing import Optional, Dict, List, Any
from dotenv import load_dotenv
import asyncio
import aiohttp
import logging
import json
import os
import re
from datetime import datetime
from urllib.parse import urljoin
import demjson3  
import time

load_dotenv()

class AsyncAiProcessing:
    LOG_DIR = "logs"
    LOG_FILE = os.path.join(LOG_DIR, "async_ai_processing_errors.log")

    def __init__(self, contract: str):
        self.contract = contract
        # Backward-compatible env lookup: support both old and current variable names.
        self.gemini_api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_AI_API_KEY")
        self.groq_api_key = os.getenv("GROQ_API_KEY") or os.getenv("GROQ_AI_API_KEY")
        self.gemini_base_url = "https://generativelanguage.googleapis.com/v1beta/models"
        self.groq_base_url = "https://api.groq.com/openai/v1"
        self._available_models: Dict[str, List[str]] = {}
        self._model_cache = {}
        self._cache_expiry = {}
        
        self.prompt = f"""
            You are an AI contract analysis system specialized in UK companies.
            Analyze the given employment contract text and extract exactly the 10 fields listed below.
            Output must be valid JSON only, no explanations, no markdown, no extra text.
            CRITICAL REQUIREMENTS FOR COMPANY NAME EXTRACTION:
            - Extract the FULL LEGAL NAME of the company exactly as it appears in the contract
            - For UK companies, preserve the exact legal ending: Ltd, Limited, PLC, PLC., Public Limited Company, LLP, etc.
            - DO NOT abbreviate or modify the company name in any way
            - If multiple company names appear, use the one identified as the employer/contracting party
            - Preserve exact capitalization, spacing, and punctuation
            "Suspicious Phrases Found" → must be a list of these values (if found):
            ["urgent payment", "no interview required", "send money", "confidential fee", "suspicious link", "payment before work"]
            or null.
            "Text Style" → one of ["professional", "template-like", "unprofessional"] or null.
            Important rules for output:
            - All phone numbers must be in international format starting with '+' (e.g., +44XXXXXXXXXX)
            - All website domains must be clean (no 'https://', no 'www.') and valid for online check
            - Contract Date must be extracted from text and returned in the format "%Y-%m-%d"
            - If a field is missing or not found, set its value to null
            - Escape quotes inside string values so the JSON remains valid.
            - Use null, not "null" in strings.
            Extract and output:
            1. Contract Number
            2. Company Name → MUST BE EXACT LEGAL NAME WITH CORRECT UK SUFFIX
            3. Company Number
            4. Registered Address
            5. Contact Details
            6. Responsible Person Full Name
            7. Contract Date
            8. Website Domain
            9. Suspicious Phrases Found
            10. Text Style

            Return strictly JSON:

            {{
              "Contract Number": "...",
              "Company Name": "...",
              "Company Number": "...",
              "Registered Address": "...",
              "Contact Details": "...",
              "Responsible Person Full Name": "...",
              "Contract Date": "...",
              "Website Domain": "...",
              "Suspicious Phrases Found": null,
              "Text Style": "..."
            }}

            Contract text:
            \"\"\"{self.contract}\"\"\"
            """
        os.makedirs(self.LOG_DIR, exist_ok=True)
        self.logger = logging.getLogger("AsyncAiProcessing")
        self.logger.setLevel(logging.ERROR)
        handler = logging.FileHandler(self.LOG_FILE, encoding='utf-8')
        handler.setLevel(logging.ERROR)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        if self.logger.handlers:
            self.logger.handlers.clear()
        self.logger.addHandler(handler)

    async def _get_available_models(self, provider: str = "gemini") -> List[str]:
        if provider in self._available_models:
            return self._available_models.get(provider, [])

        if provider == "gemini":
            api_key = self.gemini_api_key
            base_url = self.gemini_base_url
            url = f"{base_url}?key={api_key}"
        else:
            api_key = self.groq_api_key
            base_url = self.groq_base_url
            url = f"{base_url}/models"

        if not api_key:
            return []

        headers = {"Authorization": f"Bearer {api_key}"} if provider == "groq" else {}

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, timeout=30, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        if provider == "gemini":
                            models = [
                                model["name"] for model in data.get("models", [])
                                if "generateContent" in model.get("supportedGenerationMethods", [])
                            ]
                        else:
                            models = [model["id"] for model in data.get("data", [])]
                        self._available_models[provider] = models
                        return models
                    else:
                        print(f"Warning: Хато дар гирифтани моделҳо: {response.status}")
                        return []
            except asyncio.TimeoutError:
                print("Error: Тайм-аут барои гирифтани моделҳо")
                self.logger.exception("Timeout while getting models")
                return []
            except Exception as e:
                print(f"Error: Хато дар гирифтани моделҳо: {e}")
                self.logger.exception(e)
                return []

    async def _get_best_free_model(self, provider: str = "gemini") -> Optional[str]:
        try:
            available_models = await self._get_available_models(provider)
            if not available_models:
                return None

            if provider == "gemini":
                stable_models = [m for m in available_models if "preview" not in m and "-exp" not in m]
                priority = [
                    "gemini-2.5-flash", "gemini-2.5-flash-lite",
                    "gemini-2.0-flash", "gemini-2.0-flash-lite",
                    "gemini-1.5-flash", "gemini-1.5-flash-8b",
                    "gemini-pro"
                ]
                for preferred in priority:
                    for model in stable_models:
                        if preferred in model:
                            return model
                if stable_models:
                    return stable_models[0]
                return available_models[0] if available_models else None
            else:
                normalized = [m.split('/')[-1] for m in available_models]
                priority = [
                    "llama-3.1-8b-instant",
                    "llama-3.1-70b-versatile",
                    "mixtral-8x7b-32768",
                    "gemma-7b-it",
                    "llama3-70b-8192",
                    "llama3-8b-8192"
                ]
                for preferred in priority:
                    if preferred in normalized:
                        return preferred
                return normalized[0] if normalized else None

        except Exception as e:
            print(f"Warning: Хато дар гирифтани рӯйхати моделҳо: {e}")
            self.logger.exception(e)
            return None

    def _clean_json(self, text: str) -> str:
        if not text:
            return ""

        text = re.sub(r'```json|```', '', text, flags=re.IGNORECASE).strip()

        start = text.find('{')
        end = text.rfind('}')
        if start == -1 or end == -1 or end <= start:
            return text
        json_part = text[start:end+1]

        def close_unterminated_strings(s: str) -> str:
            result = []
            i = 0
            in_string = False
            escape = False
            while i < len(s):
                if s[i] == '\\' and not escape:
                    escape = True
                elif s[i] == '"' and not escape:
                    in_string = not in_string
                elif s[i] == '"' and in_string and escape:
                    escape = False
                result.append(s[i])
                escape = False
                i += 1
            if in_string:
                result.append('"')
            return ''.join(result)

        json_part = close_unterminated_strings(json_part)

        def quote_unquoted_keys(s: str) -> str:
            def repl(match):
                before, key = match.groups()
                key_stripped = key.strip()
                if key_stripped.startswith('"') and key_stripped.endswith('"'):
                    return match.group(0)
                return f'{before} "{key_stripped}":'
            return re.sub(r'(\{|\,)\s*([A-Za-z][A-Za-z0-9_\-\s]*?)\s*:', repl, s)

        json_part = quote_unquoted_keys(json_part)

        return json_part

    def _validate_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        required_fields = [
            "Contract Number", "Company Name", "Company Number",
            "Registered Address", "Contact Details",
            "Responsible Person Full Name", "Contract Date",
            "Website Domain", "Suspicious Phrases Found", "Text Style"
        ]
        for field in required_fields:
            if field not in data:
                data[field] = None

        if not isinstance(data.get("Suspicious Phrases Found"), list):
            data["Suspicious Phrases Found"] = None

        valid_styles = ["professional", "template-like", "unprofessional"]
        if data.get("Text Style") not in valid_styles:
            data["Text Style"] = "professional"

        return data

    def _normalize_company_name(self, company_name: Optional[str]) -> Optional[str]:
        if not company_name:
            return None
            
        cleaned = re.sub(r'^\s*["\'\(\)\[\]\{\}]\s*|\s*["\'\(\)\[\]\{\}]\s*$', '', str(company_name).strip())
        
        # Фильтрация фиктивных названий компаний (BR-4 fix)
        placeholder_patterns = [
            r'ABC\s*Ltd', r'Sample\s*Company', r'Test\s*Company',
            r'Dummy\s*Company', r'Example\s*Company', r'Fake\s*Company'
        ]
        
        for pattern in placeholder_patterns:
            if re.search(pattern, cleaned, re.IGNORECASE):
                return None
        
        uk_suffixes = [
            'LTD', 'LIMITED', 'PLC', 'PLC.', 'PUBLIC LIMITED COMPANY', 
            'LLP', 'LIMITED LIABILITY PARTNERSHIP', 'LP', 'LIMITED PARTNERSHIP'
        ]
        
        for suffix in uk_suffixes:
            if cleaned.upper().endswith(suffix):
                return cleaned
        
        return cleaned

    def _clean_text_value(self, value: Any, max_len: int = 160) -> Optional[str]:
        if value is None:
            return None

        text = re.sub(r'\s+', ' ', str(value)).strip()
        if not text:
            return None
        if len(text) > max_len:
            return None
        return text

    def _looks_like_contract_blob(self, value: Optional[str]) -> bool:
        if not value:
            return False

        text = str(value)
        lowered = text.lower()
        markers = [
            "employment agreement",
            "whereas",
            "position and duties",
            "compensation",
            "term and termination",
            "confidentiality",
            "governing law",
        ]
        marker_hits = sum(1 for marker in markers if marker in lowered)
        return len(text) > 140 or '\n' in text or marker_hits >= 2

    def _extract_first_match(self, text: str, patterns: List[str], flags: int = re.IGNORECASE) -> Optional[str]:
        if not text:
            return None

        for pattern in patterns:
            match = re.search(pattern, text, flags)
            if match:
                return match.group(1).strip(" ,.;:()[]{}")
        return None

    def _extract_company_name_fallback(self, text: str) -> Optional[str]:
        patterns = [
            r'by and between:\s*([A-Za-z0-9&.,\'\-\s]{3,120}?(?:LTD|LIMITED|PLC|LLP|LP))(?:,|\s)',
            r'\b([A-Z][A-Z0-9&.,\'\-\s]{3,120}?(?:LTD|LIMITED|PLC|LLP|LP))\b',
            r'company\s*name\s*[:\-]\s*([A-Za-z0-9&.,\'\-\s]{3,120})',
        ]
        extracted = self._extract_first_match(text, patterns)
        return self._normalize_company_name(extracted) if extracted else None

    def _extract_company_number_fallback(self, text: str) -> Optional[str]:
        patterns = [
            r'company\s*(?:number|no\.?)\s*[:\-]?\s*([A-Za-z0-9]{5,12})',
            r'registered\s*(?:in\s*england\s*&\s*wales\s*\|\s*)?company\s*(?:number|no\.?)\s*[:\-]?\s*([A-Za-z0-9]{5,12})',
            r'\b(?:company|co)\s*#\s*([A-Za-z0-9]{5,12})',
        ]
        extracted = self._extract_first_match(text, patterns)
        if not extracted:
            return None

        cleaned = re.sub(r'[^A-Za-z0-9]', '', extracted).upper()
        return cleaned if re.match(r'^[A-Z0-9]{5,12}$', cleaned) else None

    def _extract_contract_number_fallback(self, text: str) -> Optional[str]:
        patterns = [
            r'contract\s*(?:reference|number|no\.?)\s*[:\-]?\s*([A-Za-z0-9\-_/]{4,50})',
            r'agreement\s*(?:reference|number|no\.?)\s*[:\-]?\s*([A-Za-z0-9\-_/]{4,50})',
        ]
        return self._extract_first_match(text, patterns)

    def _extract_domain_fallback(self, text: str) -> Optional[str]:
        patterns = [
            r'(?:company\s*)?website\s*[:\-]?\s*(?:https?://)?(?:www\.)?([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
            r'(?:https?://)?(?:www\.)?([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
            r'@([A-Za-z0-9.-]+\.[A-Za-z]{2,})',
        ]
        extracted = self._extract_first_match(text, patterns)
        if not extracted:
            return None

        domain = re.sub(r'^(https?://|www\.)', '', extracted, flags=re.IGNORECASE).strip().strip('/').strip('.')
        return domain.lower() if re.match(r'^[a-z0-9.-]+\.[a-z]{2,}$', domain, flags=re.IGNORECASE) else None

    def _parse_contract_date(self, raw_value: Any) -> Optional[str]:
        if raw_value is None:
            return None

        date_str = re.sub(r'\s+', ' ', str(raw_value)).strip()
        if not date_str:
            return None

        date_str = re.sub(r'(\d{1,2})(st|nd|rd|th)\b', r'\1', date_str, flags=re.IGNORECASE)

        formats = [
            "%Y-%m-%d",
            "%d/%m/%Y",
            "%d-%m-%Y",
            "%d.%m.%Y",
            "%d %B %Y",
            "%d %b %Y",
            "%B %d, %Y",
            "%b %d, %Y",
            "%d %B, %Y",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
            except Exception:
                continue

        return None

    def _normalize_output(self, data: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(data, dict):
            return {}

        contract_text = self.contract if isinstance(self.contract, str) else str(self.contract or "")

        company_name = self._normalize_company_name(data.get("Company Name"))
        company_name = self._clean_text_value(company_name, max_len=120)
        if self._looks_like_contract_blob(company_name):
            company_name = None
        if not company_name:
            company_name = self._extract_company_name_fallback(contract_text)
        data["Company Name"] = company_name

        company_number = self._clean_text_value(data.get("Company Number"), max_len=24)
        if company_number:
            company_number = re.sub(r'[^A-Za-z0-9]', '', company_number).upper()
            if not re.match(r'^[A-Z0-9]{5,12}$', company_number):
                company_number = None
        if not company_number:
            company_number = self._extract_company_number_fallback(contract_text)
        data["Company Number"] = company_number

        contract_number = self._clean_text_value(data.get("Contract Number"), max_len=64)
        if self._looks_like_contract_blob(contract_number):
            contract_number = None
        if not contract_number:
            contract_number = self._extract_contract_number_fallback(contract_text)
        data["Contract Number"] = contract_number

        if data.get("Contact Details"):
            text = str(data["Contact Details"])
            email_match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b', text)
            phone_match = re.search(r'\+44[\d\s]{10,}', text) 

            parts = []
            if email_match:
                parts.append(email_match.group(0))

            if phone_match:
                phone = re.sub(r'\s+', '', phone_match.group(0))
                if len(phone) <= 13:  
                    parts.append(phone)
            else:
                any_phone = re.search(r'(\+?\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{1,9})', text)
                if any_phone:
                    digits = re.sub(r'\D', '', any_phone.group(0))
                    if digits.startswith('44'):
                        digits = '44' + digits[2:12] if len(digits) > 12 else '44' + digits[2:]
                    elif digits.startswith('0'):
                        digits = '44' + digits[1:11]
                    else:
                        digits = '44' + digits[:10]
                    parts.append(f"+{digits}")

            data["Contact Details"] = ", ".join(parts) if parts else None
        else:
            data["Contact Details"] = None

        if data.get("Website Domain"):
            domain = str(data["Website Domain"]).strip()
            # Проверяем, не является ли это email
            if '@' not in domain:
                domain = re.sub(r'^(https?://|www\.)', '', domain, flags=re.IGNORECASE)
                domain = domain.split('/')[0].strip()
                data["Website Domain"] = domain if domain else None
            else:
                # Если это email, извлекаем доменную часть
                email_domain = domain.split('@')[1] if '@' in domain else domain
                data["Website Domain"] = email_domain
        else:
            data["Website Domain"] = None

        if not data.get("Website Domain") or self._looks_like_contract_blob(data.get("Website Domain")):
            data["Website Domain"] = self._extract_domain_fallback(contract_text)
        else:
            normalized_domain = re.sub(r'^(https?://|www\.)', '', str(data["Website Domain"]).strip(), flags=re.IGNORECASE)
            normalized_domain = normalized_domain.split('/')[0].strip().strip('.')
            data["Website Domain"] = normalized_domain.lower() if normalized_domain else None

        data["Contract Date"] = self._parse_contract_date(data.get("Contract Date"))
        if not data["Contract Date"]:
            date_fallback = self._extract_first_match(
                contract_text,
                [
                    r'(?:effective\s*date|date)\s*[:\-]?\s*((?:\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+\d{4})|(?:[A-Za-z]+\s+\d{1,2},\s+\d{4})|(?:\d{4}-\d{2}-\d{2}))',
                    r'as\s+of\s+((?:\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+\d{4}))',
                ],
            )
            data["Contract Date"] = self._parse_contract_date(date_fallback)

        if not isinstance(data.get("Suspicious Phrases Found"), list):
            data["Suspicious Phrases Found"] = None

        valid_styles = ["professional", "template-like", "unprofessional"]
        if data.get("Text Style") not in valid_styles:
            data["Text Style"] = "professional"

        required = [
            "Contract Number", "Company Name", "Company Number", "Registered Address",
            "Contact Details", "Responsible Person Full Name", "Contract Date",
            "Website Domain", "Suspicious Phrases Found", "Text Style"
        ]
        for field in required:
            if field not in data:
                data[field] = None

        return data

    async def _make_async_request(self, model_name: str, provider: str = "gemini", attempt: int = 0) -> Optional[Dict[str, Any]]:
        if attempt >= 3:
            return None

        if provider == "gemini":
            api_key = self.gemini_api_key
            model_id = model_name.split('/')[-1]
            url = f"{self.gemini_base_url}/{model_id}:generateContent?key={api_key}"
            payload = {
                "contents": [{"parts": [{"text": self.prompt}]}],
                "generationConfig": {
                    "temperature": 0.1, "topK": 40, "topP": 0.95, "maxOutputTokens": 2048
                }
            }
            headers = {"Content-Type": "application/json"}
        else:
            api_key = self.groq_api_key
            url = f"{self.groq_base_url}/chat/completions"
            model_name = model_name.split('/')[-1]
            payload = {
                "model": model_name,
                "messages": [{"role": "user", "content": self.prompt}],
                "temperature": 0.1, "top_p": 0.95, "max_tokens": 2048
            }
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, json=payload, timeout=60, headers=headers) as response:
                    if response.status == 429:
                        wait_time = min(5 * (attempt + 1), 15)
                        self.logger.warning(
                            "Rate limit hit from %s (attempt %s). Waiting %s seconds before retry.",
                            provider,
                            attempt + 1,
                            wait_time,
                        )
                        await asyncio.sleep(wait_time)
                        return await self._make_async_request(model_name, provider, attempt + 1)
                    if response.status == 503:
                        wait_time = min(3 * (attempt + 1), 12)
                        self.logger.warning(
                            "Service unavailable from %s (attempt %s). Waiting %s seconds before retry.",
                            provider,
                            attempt + 1,
                            wait_time,
                        )
                        await asyncio.sleep(wait_time)
                        return await self._make_async_request(model_name, provider, attempt + 1)
                    if response.status != 200:
                        error_text = await response.text()
                        print(f"Error: Хатои HTTP {response.status}: {error_text}")
                        return None

                    response_data = await response.json()

                    if provider == "gemini":
                        candidates = response_data.get("candidates", [])
                        if not candidates:
                            print("Warning: Ҷавоби холӣ аз Gemini")
                            return None
                        parts = candidates[0].get("content", {}).get("parts", [])
                        text = next((p["text"] for p in parts if "text" in p), None)
                        if not text:
                            print("Warning: Натиҷаи Gemini бидуни parts.text")
                            return None
                    else:
                        if not response_data.get("choices"):
                            print("Warning: Ҷавоби холӣ аз Groq")
                            return None
                        text = response_data["choices"][0]["message"]["content"]

                    return await self._process_response_text(text)

            except asyncio.TimeoutError:
                self.logger.warning("Timeout waiting for %s response on attempt %s", provider, attempt + 1)
                return await self._make_async_request(model_name, provider, attempt + 1)
            except Exception as e:
                print(f"Error: Хато дар дархост: {e}")
                self.logger.exception(e)
                return None

    async def _process_response_text(self, text: str) -> Optional[Dict[str, Any]]:
        if not text or not text.strip():
            return None
    
        cleaned = text.strip()
        cleaned = cleaned.replace('\ufeff', '') 
        cleaned = re.sub(r'[\u200b-\u200f\u202a-\u202e]', '', cleaned)  
        cleaned = re.sub(r'```(?:json)?|```', '', cleaned, flags=re.IGNORECASE).strip()
    
        start = cleaned.find('{')
        end = cleaned.rfind('}')
        
        # Попытка восстановить обрезанный JSON (BR-1 fix)
        if start != -1 and (end == -1 or end <= start):
            lines = cleaned.split('\n')
            brace_count = 0
            fixed_json = ""
            for line in lines:
                brace_count += line.count('{') - line.count('}')
                fixed_json += line + '\n'
                if brace_count == 0 and fixed_json.strip().endswith('}'):
                    cleaned = fixed_json.strip()
                    break
            else:
                # Если не удалось восстановить, пробуем другой подход
                if end == -1:
                    cleaned += '}'
                
        if start == -1 or cleaned.rfind('}') == -1:
            self.logger.error(f"No JSON brackets found. Text: {cleaned[:300]}")
            return None
            
        json_chars = []
        brace_count = 0
        in_string = False
        escape = False
        for idx in range(start, len(cleaned)):
            ch = cleaned[idx]
            json_chars.append(ch)

            if escape:
                escape = False
                continue

            if ch == '\\':
                escape = True
                continue

            if ch == '"':
                in_string = not in_string
                continue

            if not in_string:
                if ch == '{':
                    brace_count += 1
                elif ch == '}' and brace_count > 0:
                    brace_count -= 1
                    if brace_count == 0:
                        break

        if brace_count > 0:
            json_chars.extend('}' * brace_count)

        cleaned = ''.join(json_chars)
        cleaned = self._clean_json(cleaned)

        contact_pattern = re.compile(
            r'("Contact Details"\s*:\s*")(.+?)(")(?=\s*,\s*"(Responsible Person Full Name|Contract Date|Website Domain|Suspicious Phrases Found|Text Style))',
            re.DOTALL
        )

        def _sanitize_contact(match: re.Match) -> str:
            value = match.group(2)
            value = value.replace('"', '')
            value = value.replace('{', '').replace('}', '')
            value = re.sub(r'\s+', ' ', value).strip().rstrip(',')
            return f'{match.group(1)}{value}{match.group(3)}'

        cleaned = contact_pattern.sub(_sanitize_contact, cleaned)

        try:
            data = json.loads(cleaned)
            return self._normalize_output(data)
        except json.JSONDecodeError as e:
            self.logger.error(f"json error: {e} — cleaned: {cleaned[:300]}")
            try:
                data = demjson3.decode(cleaned, strict=False)
                if isinstance(data, dict):
                    return self._normalize_output(data)
            except Exception as e2:
                self.logger.error(f"demjson3 decode failed: {e2}")
        return None

    def _is_valid_result(self, result: Dict[str, Any]) -> bool:
        if not result:
            return False
        required_fields = [
            "Company Name",
            "Company Number",
            "Contract Number",
            "Website Domain",
            "Contract Date",
        ]
        return any(result.get(field) for field in required_fields)

    async def get_answer_json_dict(self) -> Optional[Dict[str, Any]]:
        try:
            if self.gemini_api_key:
                print("Target: Кӯшиши Gemini...")
                model_name = await self._get_best_free_model("gemini")
                if model_name:
                    result = await self._make_async_request(model_name, "gemini")
                    if result and self._is_valid_result(result):
                        print(result)
                        return result
                    else:
                        print("Warning: Gemini ҷавоб надод, гузариш ба Groq...")

            if self.groq_api_key:
                print("Target: Кӯшиши Groq...")
                model_name = await self._get_best_free_model("groq")
                if model_name:
                    result = await self._make_async_request(model_name, "groq")
                    if result and self._is_valid_result(result):
                        print(result)
                        return result
        
            print("Error: Ҳама кӯшишҳо номуваффақ шуданд")
            return None
        except Exception as e:
            self.logger.exception(f"Error in get_answer_json_dict: {e}")
            return None

    async def process_multiple_contracts(self, contracts: List[str]) -> List[Optional[Dict[str, Any]]]:
        tasks = [AsyncAiProcessing(c).get_answer_json_dict() for c in contracts]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [None if isinstance(r, Exception) else r for r in results]




# contract_real = """
# EMPLOYMENT AGREEMENT

# This Employment Agreement (the "Agreement") is entered into as of 15th October 2025 (the "Effective Date"), by and between:

# HSBC BANK PLC, a public limited company incorporated in England and Wales with company number 00014259, whose registered office is at 8 Canada Square, London, E14 5HQ, United Kingdom (the "Company"), and

# Mr. Kabir Rahmonov, residing at 15 St. James’s Street, London, SW1A 1EF, United Kingdom (the "Employee").

# WHEREAS, the Company desires to employ the Employee as a Junior Data Analyst, and the Employee desires to accept such employment on the terms and conditions set forth herein;

# NOW, THEREFORE, in consideration of the mutual promises and covenants contained herein, the parties agree as follows:

# 1. POSITION AND DUTIES
#    1.1 The Employee shall serve as Junior Data Analyst within the Global Banking and Markets Division, reporting to the Head of Data Analytics.
#    1.2 Start Date: 1 December 2025.
#    1.3 Place of Work: HSBC Bank PLC, 8 Canada Square, London, E14 5HQ, with the possibility of hybrid work (remote and office-based).
#    1.4 The Employee agrees to comply with all applicable HSBC Group policies, including Data Protection, Confidentiality, and Conduct Codes.

# 2. COMPENSATION
#    2.1 Base Salary: GBP 52,000 per annum, payable monthly in arrears via direct deposit.
#    2.2 Annual Performance Bonus: Up to 10% of base salary, based on individual and corporate performance metrics.
#    2.3 Pension Scheme: The Employee shall be entitled to participate in the Company’s contributory pension plan in accordance with its terms.
#    2.4 Other Benefits: Health insurance, employee assistance program, and annual leave of 25 working days per year.

# 3. CONTACT INFORMATION
#    Company Email: customerrelations@hsbc.com
#    HR Contact: Ms. Emma Richardson, HR Business Partner
#    Telephone: +44 (0)20 7991 8888
#    Company Website: https://www.hsbc.com

# 4. TERM AND TERMINATION
#    4.1 This Agreement shall continue until terminated by either party with three (3) months’ written notice.
#    4.2 The Company may terminate this Agreement immediately in the event of gross misconduct, fraud, data breach, or breach of confidentiality.
#    4.3 Upon termination, the Employee shall return all Company property and confidential information.

# 5. CONFIDENTIALITY AND INTELLECTUAL PROPERTY
#    5.1 All analyses, reports, datasets, models, and other intellectual property developed by the Employee in the course of employment shall remain the exclusive property of the Company.
#    5.2 The Employee agrees to sign a separate Non-Disclosure and Intellectual Property Assignment Agreement.

# 6. COMPLIANCE AND ETHICS
#    6.1 The Employee must at all times adhere to HSBC’s Global Standards on Financial Crime Risk and Anti-Money Laundering (AML) procedures.
#    6.2 Any violation of these standards may result in disciplinary action or termination.

# 7. GOVERNING LAW
#    This Agreement shall be governed by and construed in accordance with the laws of England and Wales. Any disputes shall be settled by arbitration in London under the rules of the London Court of International Arbitration (LCIA).

# IN WITNESS WHEREOF, the parties have executed this Agreement as of the Effective Date.

# HSBC BANK PLC
# /s/ Mr. Jonathan Evans
# Jonathan Evans, Director of Human Resources
# Date: 15 October 2025

# EMPLOYEE
# /s/ Kabir Rahmonov
# Kabir Rahmonov
# Date: 15 October 2025

# Contract Reference: HSBC-EMP-2025-214
# Registered in England & Wales | Company No. 00014259
# VAT No. GB 365 6845 14
# Registered Office: 8 Canada Square, London, E14 5HQ, United Kingdom
# """


# if __name__ == "__main__":
#     async def main():
#         processor = AsyncAiProcessing(contract = contract_real)
#         result = await processor.get_answer_json_dict()
#         print(json.dumps(result, indent=2, ensure_ascii=False))

#     asyncio.run(main())


