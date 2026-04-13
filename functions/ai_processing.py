from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
import demjson3
from dotenv import load_dotenv

load_dotenv()


# -----------------------------
# Logging (safe: do NOT log contract text)
# -----------------------------
def _build_logger() -> logging.Logger:
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "async_ai_processing_errors.log")

    logger = logging.getLogger("AsyncAiProcessing")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not any(isinstance(h, RotatingFileHandler) for h in logger.handlers):
        handler = RotatingFileHandler(
            log_path,
            maxBytes=2_000_000,
            backupCount=5,
            encoding="utf-8",
        )
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        logger.addHandler(handler)

    return logger


# -----------------------------
# JSON Schema for structured outputs
# Separate schemas for Gemini (no union types) and OpenAI-compatible providers
# -----------------------------
_REQUIRED_FIELDS = [
    "Contract Number",
    "Company Name",
    "Company Number",
    "Registered Address",
    "Contact Details",
    "Responsible Person Full Name",
    "Contract Date",
    "Website Domain",
    "Suspicious Phrases Found",
    "Text Style",
]

_SUSPICIOUS_PHRASES = [
    "urgent payment",
    "no interview required",
    "send money",
    "confidential fee",
    "suspicious link",
    "payment before work",
]

GEMINI_FREE_MODEL_CANDIDATES = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
]

# OpenAI-compatible schema (Groq, OpenRouter) — uses json_object mode
OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "Contract Number": {"type": "string", "description": "Contract reference number or null string"},
        "Company Name": {"type": "string", "description": "Full legal company name"},
        "Company Number": {"type": "string", "description": "UK company registration number"},
        "Registered Address": {"type": "string", "description": "Company registered address"},
        "Contact Details": {"type": "string", "description": "Email and phone contacts"},
        "Responsible Person Full Name": {"type": "string", "description": "Person signing on behalf of company"},
        "Contract Date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
        "Website Domain": {"type": "string", "description": "Clean domain (no https/www)"},
        "Suspicious Phrases Found": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of suspicious phrases found, or empty array",
        },
        "Text Style": {
            "type": "string",
            "enum": ["professional", "template-like", "unprofessional"],
            "description": "Overall text style assessment",
        },
    },
    "required": _REQUIRED_FIELDS,
}

# Gemini-compatible schema — uses nullable + propertyOrdering
GEMINI_SCHEMA: Dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "Contract Number": {"type": "STRING", "nullable": True},
        "Company Name": {"type": "STRING", "nullable": True},
        "Company Number": {"type": "STRING", "nullable": True},
        "Registered Address": {"type": "STRING", "nullable": True},
        "Contact Details": {"type": "STRING", "nullable": True},
        "Responsible Person Full Name": {"type": "STRING", "nullable": True},
        "Contract Date": {"type": "STRING", "nullable": True, "description": "YYYY-MM-DD"},
        "Website Domain": {"type": "STRING", "nullable": True},
        "Suspicious Phrases Found": {
            "type": "ARRAY",
            "nullable": True,
            "items": {"type": "STRING"},
        },
        "Text Style": {
            "type": "STRING",
            "nullable": True,
            "enum": ["professional", "template-like", "unprofessional"],
        },
    },
    "required": _REQUIRED_FIELDS,
    "propertyOrdering": _REQUIRED_FIELDS,
}


# -----------------------------
# Provider config
# -----------------------------
@dataclass(frozen=True)
class Provider:
    name: str  # "gemini" | "groq" | "openrouter"


class AsyncAiProcessing:
    _session: Optional[aiohttp.ClientSession] = None
    _session_lock = asyncio.Lock()

    _models_cache: Dict[str, Tuple[float, List[str]]] = {}
    _provider_disabled_until: Dict[str, float] = {}
    _models_lock: Dict[str, asyncio.Lock] = {
        "gemini": asyncio.Lock(),
        "groq": asyncio.Lock(),
        "openrouter": asyncio.Lock(),
    }

    def __init__(self, contract: str):
        self.contract = contract or ""
        self.logger = _build_logger()

        self.gemini_api_key = os.getenv("GEMINI_AI_API_KEY") or os.getenv("GEMINI_API_KEY")
        self.groq_api_key = os.getenv("GROQ_AI_API_KEY") or os.getenv("GROQ_API_KEY")

        self.openrouter_api_key = (
            os.getenv("OPENROUTER_API_KEY")
            or os.getenv("OPEN_ROUTER")
            or os.getenv("OPEN_ROUTER_API_KEY")
        )

        self.openrouter_app_url = os.getenv("OPENROUTER_APP_URL", "").strip()
        self.openrouter_app_name = os.getenv("OPENROUTER_APP_NAME", "Safety-Checker").strip()

        self.gemini_base = "https://generativelanguage.googleapis.com/v1beta/models"
        self.groq_base = "https://api.groq.com/openai/v1"
        self.openrouter_base = "https://openrouter.ai/api/v1"

        self._ttl = int(os.getenv("AI_MODELS_CACHE_TTL_SEC", "900") or "900")

        self._system_prompt = self._build_system_prompt()

    def _env_model_candidates(self, *names: str) -> List[str]:
        candidates: List[str] = []
        for name in names:
            raw = os.getenv(name, "")
            if not raw:
                continue
            for item in re.split(r"[,;\s]+", raw):
                model = item.strip()
                if model:
                    candidates.append(model)
        return candidates

    def _dedupe_models(self, models: List[str]) -> List[str]:
        out: List[str] = []
        seen = set()
        for model in models:
            cleaned = str(model or "").strip()
            if not cleaned:
                continue
            key = cleaned.split("/")[-1]
            if key in seen:
                continue
            out.append(cleaned)
            seen.add(key)
        return out

    def _gemini_direct_candidates(self) -> List[str]:
        env_candidates = self._env_model_candidates("GEMINI_MODEL", "GEMINI_MODELS", "AI_GEMINI_MODELS")
        return self._dedupe_models(env_candidates + GEMINI_FREE_MODEL_CANDIDATES)

    # -----------------------------
    # Session
    # -----------------------------
    @classmethod
    async def _get_session(cls) -> aiohttp.ClientSession:
        async with cls._session_lock:
            if cls._session and not cls._session.closed:
                return cls._session
            timeout = aiohttp.ClientTimeout(total=70, connect=15, sock_read=60)
            connector = aiohttp.TCPConnector(limit=40, ttl_dns_cache=300)
            cls._session = aiohttp.ClientSession(timeout=timeout, connector=connector)
            return cls._session

    @classmethod
    async def aclose(cls) -> None:
        async with cls._session_lock:
            if cls._session and not cls._session.closed:
                await cls._session.close()
            cls._session = None

    # -----------------------------
    # Prompt
    # -----------------------------
    def _build_system_prompt(self) -> str:
        return (
            "You are an AI contract analysis system specialized in UK companies.\n"
            "Task: Extract exactly these 10 fields from an employment contract:\n"
            "Contract Number, Company Name, Company Number, Registered Address, Contact Details, "
            "Responsible Person Full Name, Contract Date, Website Domain, Suspicious Phrases Found, Text Style.\n"
            "Return ONLY valid JSON (no markdown, no explanations).\n"
            "Do not add extra keys. Do not rename keys.\n"
            "\n"
            "CRITICAL REQUIREMENTS FOR COMPANY NAME:\n"
            "- Extract FULL LEGAL NAME exactly as in the contract.\n"
            "- Preserve UK legal suffix exactly: Ltd, Limited, PLC, LLP, LP, etc.\n"
            "- Do NOT abbreviate or modify.\n"
            "- If multiple company names appear, choose the employer/contracting party.\n"
            "\n"
            "\"Suspicious Phrases Found\" must be a list of these exact values if found, otherwise an empty list:\n"
            f"{json.dumps(_SUSPICIOUS_PHRASES)}\n"
            "\n"
            "\"Text Style\" must be one of: [\"professional\", \"template-like\", \"unprofessional\"] or null.\n"
            "\n"
            "Rules:\n"
            "- Phone numbers must be in international format starting with '+' (e.g., +44...).\n"
            "- Website Domain must be clean (no https://, no www.).\n"
            "- Contract Date must be YYYY-MM-DD.\n"
            "- If a field is missing: null, except Suspicious Phrases Found must be [].\n"
        )

    # -----------------------------
    # Model discovery (cached)
    # -----------------------------
    async def _get_models(self, provider: Provider) -> List[str]:
        disabled_until = self._provider_disabled_until.get(provider.name, 0.0)
        if disabled_until > time.time():
            return []

        now = time.time()
        cached = self._models_cache.get(provider.name)
        if cached and cached[0] > now:
            return cached[1]

        lock = self._models_lock[provider.name]
        async with lock:
            cached = self._models_cache.get(provider.name)
            if cached and cached[0] > time.time():
                return cached[1]

            try:
                session = await self._get_session()
                models: List[str] = []

                if provider.name == "gemini":
                    if not self.gemini_api_key:
                        return []
                    url = f"{self.gemini_base}?key={self.gemini_api_key}"
                    async with session.get(url) as r:
                        if r.status == 403:
                            fallback_models = self._gemini_direct_candidates()
                            self.logger.warning(
                                "Gemini model list returned HTTP 403; using direct free Gemini candidates: %s",
                                ", ".join(fallback_models),
                            )
                            self._models_cache[provider.name] = (time.time() + min(self._ttl, 300), fallback_models)
                            return fallback_models
                        if r.status != 200:
                            fallback_models = self._gemini_direct_candidates()
                            self.logger.warning(
                                "Gemini models list failed: %s; using direct free Gemini candidates.",
                                r.status,
                            )
                            self._models_cache[provider.name] = (time.time() + min(self._ttl, 300), fallback_models)
                            return fallback_models
                        data = await r.json()
                    for m in data.get("models", []):
                        name = m.get("name", "")
                        methods = m.get("supportedGenerationMethods", []) or []
                        if name and "generateContent" in methods:
                            models.append(name)
                    models = self._dedupe_models(self._gemini_direct_candidates() + models)

                elif provider.name == "groq":
                    if not self.groq_api_key:
                        return []
                    url = f"{self.groq_base}/models"
                    headers = {"Authorization": f"Bearer {self.groq_api_key}"}
                    async with session.get(url, headers=headers) as r:
                        if r.status != 200:
                            self.logger.warning("Groq models list failed: %s", r.status)
                            return []
                        data = await r.json()
                    for m in data.get("data", []):
                        mid = m.get("id")
                        if mid:
                            models.append(str(mid))

                elif provider.name == "openrouter":
                    url = f"{self.openrouter_base}/models"
                    headers = {}
                    if self.openrouter_api_key:
                        headers["Authorization"] = f"Bearer {self.openrouter_api_key}"
                    async with session.get(url, headers=headers) as r:
                        if r.status != 200:
                            self.logger.warning("OpenRouter models list failed: %s", r.status)
                            return []
                        data = await r.json()
                    for m in data.get("data", []):
                        mid = m.get("id")
                        if mid:
                            models.append(str(mid))

                self._models_cache[provider.name] = (time.time() + self._ttl, models)
                return models

            except Exception as e:
                self.logger.exception("Model list error (%s): %s", provider.name, e)
                return []

    async def _pick_model(self, provider: Provider) -> Optional[str]:
        disabled_until = self._provider_disabled_until.get(provider.name, 0.0)
        if disabled_until > time.time():
            return None

        models = await self._get_models(provider)
        if provider.name == "gemini":
            priority = [
                "gemini-2.5-flash",
                "gemini-2.5-flash-lite",
                "gemini-2.0-flash",
                "gemini-1.5-flash",
                "gemini-pro",
            ]
            stable = [m for m in models if "preview" not in m and "-exp" not in m]
            for p in priority:
                for m in stable:
                    if p in m:
                        return m
            if stable:
                return stable[0]
            if models:
                return models[0]
            # If list endpoint is blocked (403), skip Gemini and fail over quickly.
            return None

        if provider.name == "groq":
            priority = [
                "llama-3.3-70b-versatile",
                "llama-3.1-70b-versatile",
                "llama-3.1-8b-instant",
                "mixtral-8x7b-32768",
                "gemma2-9b-it",
            ]
            normalized = [m.split("/")[-1] for m in models]
            for p in priority:
                if p in normalized:
                    return p
            if normalized:
                return normalized[0]
            return "llama-3.1-8b-instant"

        if provider.name == "openrouter":
            priority = [
                "google/gemini-2.5-flash-lite",
                "google/gemini-2.5-flash",
                "meta-llama/llama-3.3-70b-instruct",
                "mistralai/mistral-large",
            ]
            if models:
                for p in priority:
                    if p in models:
                        return p
            return "openrouter/auto"

        return None

    async def _candidate_models(self, provider: Provider) -> List[str]:
        if provider.name == "gemini":
            models = await self._get_models(provider)
            priority = self._gemini_direct_candidates() + [
                "gemini-2.5-flash",
                "gemini-2.5-flash-lite",
                "gemini-2.0-flash",
                "gemini-2.0-flash-lite",
                "gemini-1.5-flash",
            ]

            stable = [m for m in models if "preview" not in m and "-exp" not in m]
            ordered: List[str] = []
            for wanted in priority:
                for model in stable + models:
                    if wanted == model.split("/")[-1] or wanted in model:
                        ordered.append(model)
                ordered.append(wanted)
            ordered.extend(stable)
            ordered.extend(models)
            return self._dedupe_models(ordered)

        picked = await self._pick_model(provider)
        return [picked] if picked else []

    def _fallback_extract_from_text(self) -> Optional[Dict[str, Any]]:
        text = self.contract or ""
        if len(text.strip()) < 30:
            return None

        data: Dict[str, Any] = {k: None for k in OUTPUT_SCHEMA["required"]}

        data["Company Name"] = self._extract_company_name_fallback(text)
        data["Company Number"] = self._extract_company_number_fallback(text)
        data["Contract Number"] = self._extract_contract_number_fallback(text)
        data["Website Domain"] = self._extract_domain_fallback(text)
        data["Registered Address"] = self._extract_registered_address_fallback(text)
        data["Contact Details"] = self._extract_contact_details_fallback(text)
        data["Responsible Person Full Name"] = self._extract_responsible_person_fallback(text)

        raw_date = self._extract_first_match(
            text,
            [
                r"(?:effective\s*date|date)\s*[:\-]?\s*((?:\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+\d{4})|(?:[A-Za-z]+\s+\d{1,2},\s*\d{4})|(?:\d{4}-\d{2}-\d{2}))",
            ],
        )
        data["Contract Date"] = self._parse_contract_date(raw_date)

        suspicious = self._extract_suspicious_phrases(text)
        data["Suspicious Phrases Found"] = suspicious
        data["Text Style"] = "unprofessional" if suspicious else "professional"
        return self._normalize_output(data)

    # -----------------------------
    # Core request helpers
    # -----------------------------
    async def _post_json(self, url: str, payload: Dict[str, Any], headers: Dict[str, str]) -> Tuple[int, str, Optional[Dict[str, Any]]]:
        session = await self._get_session()
        async with session.post(url, json=payload, headers=headers) as r:
            text = await r.text()
            try:
                data = await r.json()
            except Exception:
                data = None
            return r.status, text, data

    async def _request_with_retry(
        self,
        provider: Provider,
        url: str,
        payload: Dict[str, Any],
        headers: Dict[str, str],
        max_attempts: int = 2,
    ) -> Optional[Dict[str, Any]]:
        safe_url = re.sub(r"(key=)[^&\s]+", r"\1REDACTED", url)
        for attempt in range(1, max_attempts + 1):
            try:
                status, raw_text, data = await self._post_json(url, payload, headers)

                if status in (429, 503):
                    # Fail fast for Gemini to avoid global timeout; fallback to other providers.
                    if provider.name == "gemini":
                        self.logger.warning(
                            "%s %s -> %s (attempt %s), skipping quickly to fallback provider",
                            provider.name, safe_url, status, attempt
                        )
                        return None

                    backoff = min(2 * attempt, 6)
                    self.logger.warning("%s %s -> %s (attempt %s), backoff %.1fs",
                                        provider.name, safe_url, status, attempt, backoff)
                    await asyncio.sleep(backoff)
                    continue

                if status != 200:
                    snippet = (raw_text or "")[:300].replace("\n", " ")
                    if provider.name == "gemini" and status == 403:
                        lowered = (raw_text or "").lower()
                        if "reported as leaked" in lowered or "api key not valid" in lowered or "permission_denied" in lowered:
                            self.logger.error(
                                "Gemini key rejected by Google (%s). Create a new Google AI Studio API key and update GEMINI_AI_API_KEY.",
                                snippet,
                            )
                            self._provider_disabled_until["gemini"] = time.time() + 600
                            return None
                    self.logger.error("%s HTTP %s: %s", provider.name, status, snippet)
                    return None

                return data

            except asyncio.TimeoutError:
                backoff = min(2 ** attempt, 10)
                self.logger.warning("%s timeout (attempt %s), backoff %ss", provider.name, attempt, backoff)
                await asyncio.sleep(backoff)
            except Exception as e:
                self.logger.exception("%s request error: %s", provider.name, e)
                return None

        return None

    # -----------------------------
    # Provider calls
    # -----------------------------
    async def _call_gemini(self, model_name: str) -> Optional[Dict[str, Any]]:
        if not self.gemini_api_key:
            return None
        if self._provider_disabled_until.get("gemini", 0.0) > time.time():
            return None

        model_id = model_name.split("/")[-1]
        url = f"{self.gemini_base}/{model_id}:generateContent?key={self.gemini_api_key}"

        payload = {
            "systemInstruction": {"parts": [{"text": self._system_prompt}]},
            "contents": [
                {"role": "user", "parts": [{"text": self.contract}]}
            ],
            "generationConfig": {
                "temperature": 0.1,
                "topK": 40,
                "topP": 0.95,
                "maxOutputTokens": 2048,
                "responseMimeType": "application/json",
                "responseSchema": GEMINI_SCHEMA,
            },
        }

        data = await self._request_with_retry(
            Provider("gemini"),
            url,
            payload,
            headers={"Content-Type": "application/json"},
            max_attempts=1,
        )
        if not data:
            return None

        try:
            candidates = data.get("candidates", []) or []
            parts = (candidates[0].get("content", {}) or {}).get("parts", []) if candidates else []
            text = next((p.get("text") for p in parts if isinstance(p, dict) and p.get("text")), None)
            return await self._process_response_text(text)
        except Exception as e:
            self.logger.exception("Gemini parse error: %s", e)
            return None

    async def _call_openai_compatible(self, provider: Provider, model: str) -> Optional[Dict[str, Any]]:
        if provider.name == "groq":
            if not self.groq_api_key:
                self.logger.warning("Groq skipped: GROQ_API_KEY / GROQ_AI_API_KEY not set in .env")
                return None
            url = f"{self.groq_base}/chat/completions"
            headers = {"Authorization": f"Bearer {self.groq_api_key}", "Content-Type": "application/json"}
        elif provider.name == "openrouter":
            if not self.openrouter_api_key:
                self.logger.warning("OpenRouter skipped: OPENROUTER_API_KEY / OPEN_ROUTER not set in .env")
                return None
            url = f"{self.openrouter_base}/chat/completions"
            headers = {"Authorization": f"Bearer {self.openrouter_api_key}", "Content-Type": "application/json"}
            if self.openrouter_app_url:
                headers["HTTP-Referer"] = self.openrouter_app_url
            if self.openrouter_app_name:
                headers["X-OpenRouter-Title"] = self.openrouter_app_name
        else:
            return None

        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": self.contract},
        ]

        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.1,
            "top_p": 0.95,
            "max_tokens": 2048,
            "response_format": {"type": "json_object"},
        }

        data = await self._request_with_retry(provider, url, payload, headers=headers)
        if not data:
            return None

        try:
            choices = data.get("choices") or []
            text = (((choices[0] or {}).get("message") or {}).get("content")) if choices else None
            return await self._process_response_text(text)
        except Exception as e:
            self.logger.exception("%s parse error: %s", provider.name, e)
            return None

    # -----------------------------
    # Robust response parsing + normalization
    # -----------------------------
    async def _process_response_text(self, text: Optional[str]) -> Optional[Dict[str, Any]]:
        if not text or not str(text).strip():
            return None

        cleaned = str(text).strip().replace("\ufeff", "")
        cleaned = re.sub(r"[\u200b-\u200f\u202a-\u202e]", "", cleaned)
        cleaned = re.sub(r"```(?:json)?|```", "", cleaned, flags=re.IGNORECASE).strip()

        try:
            data = json.loads(cleaned)
            if isinstance(data, dict):
                return self._normalize_output(data)
        except Exception:
            pass

        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            blob = cleaned[start : end + 1]
        else:
            blob = cleaned

        if blob.count("{") > blob.count("}"):
            blob += "}" * (blob.count("{") - blob.count("}"))

        try:
            data = json.loads(blob)
            if isinstance(data, dict):
                return self._normalize_output(data)
        except json.JSONDecodeError:
            try:
                data = demjson3.decode(blob, strict=False)
                if isinstance(data, dict):
                    return self._normalize_output(data)
            except Exception as e2:
                self.logger.warning("demjson3 decode failed: %s", e2)
                return None

        return None

    def _looks_like_contract_blob(self, value: Optional[str]) -> bool:
        if not value:
            return False
        text = str(value)
        lowered = text.lower()
        markers = [
            "employment agreement", "whereas", "position and duties",
            "compensation", "term and termination", "confidentiality", "governing law"
        ]
        marker_hits = sum(1 for m in markers if m in lowered)
        return len(text) > 140 or "\n" in text or marker_hits >= 2

    def _clean_text_value(self, value: Any, max_len: int = 160) -> Optional[str]:
        if value is None:
            return None
        text = re.sub(r"\s+", " ", str(value)).strip()
        if not text or len(text) > max_len:
            return None
        return text

    def _normalize_company_name(self, company_name: Optional[str]) -> Optional[str]:
        if not company_name:
            return None
        cleaned = re.sub(r'^\s*["\'\(\)\[\]\{\}]\s*|\s*["\'\(\)\[\]\{\}]\s*$',
                         "", str(company_name).strip())

        placeholders = [
            r"ABC\s*Ltd", r"Sample\s*Company", r"Test\s*Company",
            r"Dummy\s*Company", r"Example\s*Company", r"Fake\s*Company"
        ]
        for p in placeholders:
            if re.search(p, cleaned, re.IGNORECASE):
                return None

        return cleaned or None

    def _extract_first_match(self, text: str, patterns: List[str], flags: int = re.IGNORECASE) -> Optional[str]:
        for pattern in patterns:
            m = re.search(pattern, text or "", flags)
            if m:
                return m.group(1).strip(" ,.;:()[]{}")
        return None

    def _extract_company_name_fallback(self, text: str) -> Optional[str]:
        patterns = [
            r"by and between:\s*([A-Za-z0-9&.,'\-\s]{3,120}?(?:LTD|LIMITED|PLC|LLP|LP))(?:,|\s)",
            r"\b([A-Z][A-Z0-9&.,'\-\s]{3,120}?(?:LTD|LIMITED|PLC|LLP|LP))\b",
            r"company\s*name\s*[:\-]\s*([A-Za-z0-9&.,'\-\s]{3,120})",
        ]
        extracted = self._extract_first_match(text, patterns)
        return self._normalize_company_name(extracted) if extracted else None

    def _extract_company_number_fallback(self, text: str) -> Optional[str]:
        patterns = [
            r"company\s*(?:number|no\.?)\s*[:\-]?\s*([A-Za-z0-9]{5,12})",
            r"registered\s*(?:in\s*england\s*&\s*wales\s*\|\s*)?company\s*(?:number|no\.?)\s*[:\-]?\s*([A-Za-z0-9]{5,12})",
            r"\b(?:company|co)\s*#\s*([A-Za-z0-9]{5,12})",
        ]
        extracted = self._extract_first_match(text, patterns)
        if not extracted:
            return None
        cleaned = re.sub(r"[^A-Za-z0-9]", "", extracted).upper()
        return cleaned if re.match(r"^[A-Z0-9]{5,12}$", cleaned) else None

    def _extract_contract_number_fallback(self, text: str) -> Optional[str]:
        patterns = [
            r"contract\s*(?:reference|number|no\.?)\s*[:\-]?\s*([A-Za-z0-9\-_/]{4,50})",
            r"agreement\s*(?:reference|number|no\.?)\s*[:\-]?\s*([A-Za-z0-9\-_/]{4,50})",
            r"\breference\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9\-_/]{3,49})",
        ]
        extracted = self._extract_first_match(text, patterns)
        return None if self._is_bad_contract_number(extracted) else extracted

    def _is_bad_contract_number(self, value: Any) -> bool:
        text = self._clean_text_value(value, max_len=64)
        if not text:
            return True
        lowered = text.lower().strip()
        bad_words = {
            "interview",
            "agreement",
            "contract",
            "employment",
            "required",
            "number",
            "reference",
            "none",
            "null",
            "n/a",
        }
        if lowered in bad_words:
            return True
        if len(lowered.split()) > 2:
            return True
        if not re.search(r"\d", text):
            return True
        return not bool(re.match(r"^[A-Za-z0-9][A-Za-z0-9._/\-]{3,63}$", text))

    def _normalize_phone_for_output(self, raw_value: str) -> Optional[str]:
        raw = str(raw_value or "").strip()
        if not raw:
            return None
        digits = re.sub(r"\D", "", raw)
        if not digits:
            return None
        if raw.startswith("+"):
            if digits.startswith("440"):
                digits = "44" + digits[3:]
            return f"+{digits}"
        return digits if len(digits) >= 8 else None

    def _extract_contact_details_fallback(self, text: str) -> Optional[str]:
        emails = re.findall(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", text or "")
        phones = re.findall(r"\+\d[\d\s().-]{7,}\d", text or "")

        parts: List[str] = []
        seen = set()
        for email in emails:
            key = email.lower()
            if key not in seen:
                parts.append(email)
                seen.add(key)
                break
        for phone in phones:
            normalized = self._normalize_phone_for_output(phone)
            if normalized and normalized not in seen:
                parts.append(normalized)
                break
        return ", ".join(parts) if parts else None

    def _extract_registered_address_fallback(self, text: str) -> Optional[str]:
        if not text:
            return None

        patterns = [
            r"(?:registered\s+(?:office|address))\s*[:\-]?\s*([^\n]{10,280})",
            r"whose\s+registered\s+office\s+is\s+at\s+([^\n]{10,280})",
        ]
        raw = self._extract_first_match(text, patterns)
        if not raw:
            return None

        raw = re.split(r",\s+and\s+[A-Z][A-Za-z .'\-]{2,80}(?:\.|$)", raw, maxsplit=1)[0]
        raw = re.split(r"\s+and\s+(?:the\s+)?(?:employee|worker|contractor)\b", raw, maxsplit=1, flags=re.IGNORECASE)[0]
        raw = raw.strip(" ,.;:()[]{}")
        return self._clean_text_value(raw, max_len=260)

    def _extract_responsible_person_fallback(self, text: str) -> Optional[str]:
        extracted = self._extract_first_match(
            text,
            [
                r"(?:Responsible\s*Person|HR Contact|Contact Person|Signed\s+by)\s*[:\-]\s*(?:Mr\.|Ms\.|Mrs\.)?\s*([A-Za-z .'\-]{4,120})",
                r"\b(?:Mr|Ms|Mrs)\.\s*([A-Za-z .'\-]{3,80})",
            ],
        )
        return self._clean_text_value(extracted, max_len=120)

    def _extract_suspicious_phrases(self, text: str) -> List[str]:
        lowered = (text or "").lower()
        found = [phrase for phrase in _SUSPICIOUS_PHRASES if phrase in lowered]
        if "http://" in lowered or "https://" in lowered:
            suspicious_domains = ["bit.ly", "tinyurl", "t.me/", "telegram.me/", "wa.me/"]
            if any(domain in lowered for domain in suspicious_domains) and "suspicious link" not in found:
                found.append("suspicious link")
        return found

    def _extract_domain_fallback(self, text: str) -> Optional[str]:
        patterns = [
            r"(?:company\s*)?website\s*[:\-]?\s*(?:https?://)?(?:www\.)?([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})",
            r"(?:https?://)?(?:www\.)?([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})",
            r"@([A-Za-z0-9.-]+\.[A-Za-z]{2,})",
        ]
        extracted = self._extract_first_match(text, patterns)
        if not extracted:
            return None
        domain = re.sub(r"^(https?://|www\.)", "", extracted, flags=re.IGNORECASE).strip().strip("/").strip(".")
        return domain.lower() if re.match(r"^[a-z0-9.-]+\.[a-z]{2,}$", domain, flags=re.IGNORECASE) else None

    def _parse_contract_date(self, raw_value: Any) -> Optional[str]:
        if raw_value is None:
            return None
        date_str = re.sub(r"\s+", " ", str(raw_value)).strip()
        if not date_str:
            return None
        date_str = re.sub(r"(\d{1,2})(st|nd|rd|th)\b", r"\1", date_str, flags=re.IGNORECASE)

        formats = [
            "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
            "%d %B %Y", "%d %b %Y", "%B %d, %Y", "%b %d, %Y", "%d %B, %Y",
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

        contract_text = self.contract

        for k in OUTPUT_SCHEMA["required"]:
            data.setdefault(k, None)

        company_name = self._normalize_company_name(data.get("Company Name"))
        company_name = self._clean_text_value(company_name, max_len=120)
        if self._looks_like_contract_blob(company_name):
            company_name = None
        if not company_name:
            company_name = self._extract_company_name_fallback(contract_text)
        data["Company Name"] = company_name

        company_number = self._clean_text_value(data.get("Company Number"), max_len=24)
        if company_number:
            company_number = re.sub(r"[^A-Za-z0-9]", "", company_number).upper()
            if not re.match(r"^[A-Z0-9]{5,12}$", company_number):
                company_number = None
        if not company_number:
            company_number = self._extract_company_number_fallback(contract_text)
        data["Company Number"] = company_number

        contract_number = self._clean_text_value(data.get("Contract Number"), max_len=64)
        if self._looks_like_contract_blob(contract_number):
            contract_number = None
        if self._is_bad_contract_number(contract_number):
            contract_number = None
        if not contract_number:
            contract_number = self._extract_contract_number_fallback(contract_text)
        data["Contract Number"] = contract_number

        cd = data.get("Contact Details")
        if cd:
            text = str(cd)
            email = re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", text)
            phone = re.search(r"\+\d[\d\s]{8,}", text)
            parts = []
            if email:
                parts.append(email.group(0))
            if phone:
                normalized_phone = self._normalize_phone_for_output(phone.group(0))
                if normalized_phone:
                    parts.append(normalized_phone)
            data["Contact Details"] = ", ".join(parts) if parts else None
        else:
            data["Contact Details"] = None
        fallback_contact = self._extract_contact_details_fallback(contract_text)
        if data["Contact Details"] and fallback_contact:
            contact_parts = []
            seen_contacts = set()
            for chunk in f"{data['Contact Details']}, {fallback_contact}".split(","):
                chunk = chunk.strip()
                key = chunk.lower()
                if chunk and key not in seen_contacts:
                    contact_parts.append(chunk)
                    seen_contacts.add(key)
            data["Contact Details"] = ", ".join(contact_parts)
        elif not data["Contact Details"]:
            data["Contact Details"] = fallback_contact

        address = self._clean_text_value(data.get("Registered Address"), max_len=260)
        if self._looks_like_contract_blob(address):
            address = None
        if not address:
            address = self._extract_registered_address_fallback(contract_text)
        data["Registered Address"] = address

        responsible_person = self._clean_text_value(data.get("Responsible Person Full Name"), max_len=120)
        if self._looks_like_contract_blob(responsible_person):
            responsible_person = None
        if not responsible_person:
            responsible_person = self._extract_responsible_person_fallback(contract_text)
        data["Responsible Person Full Name"] = responsible_person

        wd = data.get("Website Domain")
        if wd:
            domain = str(wd).strip()
            if "@" in domain:
                domain = domain.split("@", 1)[1]
            domain = re.sub(r"^(https?://|www\.)", "", domain, flags=re.IGNORECASE)
            domain = domain.split("/", 1)[0].strip().strip(".")
            data["Website Domain"] = domain.lower() if domain else None
        else:
            data["Website Domain"] = None
        if not data["Website Domain"] or self._looks_like_contract_blob(data["Website Domain"]):
            data["Website Domain"] = self._extract_domain_fallback(contract_text)

        data["Contract Date"] = self._parse_contract_date(data.get("Contract Date"))
        if not data["Contract Date"]:
            fallback = self._extract_first_match(
                contract_text,
                [
                    r"(?:effective\s*date|date)\s*[:\-]?\s*((?:\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+\d{4})|"
                    r"(?:[A-Za-z]+\s+\d{1,2},\s+\d{4})|(?:\d{4}-\d{2}-\d{2}))",
                    r"as\s+of\s+((?:\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+\d{4}))",
                ],
            )
            data["Contract Date"] = self._parse_contract_date(fallback)

        ai_phrases = data.get("Suspicious Phrases Found")
        ai_phrase_set = set()
        if isinstance(ai_phrases, list):
            ai_phrase_set = {str(item).strip().lower() for item in ai_phrases if str(item).strip()}
        detected_phrases = set(self._extract_suspicious_phrases(contract_text))
        data["Suspicious Phrases Found"] = [
            phrase for phrase in _SUSPICIOUS_PHRASES
            if phrase in ai_phrase_set or phrase in detected_phrases
        ]

        valid_styles = ["professional", "template-like", "unprofessional"]
        if data.get("Text Style") not in valid_styles:
            data["Text Style"] = "unprofessional" if data["Suspicious Phrases Found"] else "professional"

        for key in OUTPUT_SCHEMA["required"]:
            if key in ("Suspicious Phrases Found",):
                continue
            if isinstance(data.get(key), str):
                data[key] = self._clean_text_value(data[key], max_len=220)

        return {key: data.get(key) for key in OUTPUT_SCHEMA["required"]}

    def _is_valid_result(self, result: Optional[Dict[str, Any]]) -> bool:
        if not result:
            return False
        primary_keys = ["Company Name", "Company Number", "Contract Number", "Website Domain", "Contract Date"]
        if any(result.get(k) for k in primary_keys):
            return True
        secondary_keys = ["Contact Details", "Registered Address", "Responsible Person Full Name"]
        return any(result.get(k) for k in secondary_keys) or bool(result.get("Suspicious Phrases Found"))

    # -----------------------------
    # Public API
    # -----------------------------
    async def get_answer_json_dict(self) -> Optional[Dict[str, Any]]:
        providers = [Provider("gemini"), Provider("groq"), Provider("openrouter")]

        for p in providers:
            models = await self._candidate_models(p)
            if not models:
                continue

            for model in models:
                if p.name == "gemini":
                    res = await self._call_gemini(model)
                else:
                    res = await self._call_openai_compatible(p, model)

                if self._is_valid_result(res):
                    return res

        fallback = self._fallback_extract_from_text()
        if self._is_valid_result(fallback):
            self.logger.warning("AI providers unavailable; local fallback extractor used.")
            return fallback

        self.logger.error("All providers failed (no valid result).")
        return None

    async def process_multiple_contracts(self, contracts: List[str]) -> List[Optional[Dict[str, Any]]]:
        max_conc = int(os.getenv("AI_MAX_CONCURRENCY", "3") or "3")
        sem = asyncio.Semaphore(max(1, max_conc))

        async def _one(c: str) -> Optional[Dict[str, Any]]:
            async with sem:
                return await AsyncAiProcessing(c).get_answer_json_dict()

        results = await asyncio.gather(*[_one(c) for c in contracts], return_exceptions=True)
        out: List[Optional[Dict[str, Any]]] = []
        for r in results:
            out.append(None if isinstance(r, Exception) else r)
        return out




# contract_real = """
# EMPLOYMENT AGREEMENT

# This Employment Agreement (the "Agreement") is entered into as of 15th October 2025 (the "Effective Date"), by and between:

# HSBC BANK PLC, a public limited company incorporated in England and Wales with company number 00014259, whose registered office is at 8 Canada Square, London, E14 5HQ, United Kingdom (the "Company"), and

# Mr. Kabir Rahmonov, residing at 15 St. James's Street, London, SW1A 1EF, United Kingdom (the "Employee").

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
#    2.3 Pension Scheme: The Employee shall be entitled to participate in the Company's contributory pension plan in accordance with its terms.
#    2.4 Other Benefits: Health insurance, employee assistance program, and annual leave of 25 working days per year.

# 3. CONTACT INFORMATION
#    Company Email: customerrelations@hsbc.com
#    HR Contact: Ms. Emma Richardson, HR Business Partner
#    Telephone: +44 (0)20 7991 8888
#    Company Website: https://www.hsbc.com

# 4. TERM AND TERMINATION
#    4.1 This Agreement shall continue until terminated by either party with three (3) months' written notice.
#    4.2 The Company may terminate this Agreement immediately in the event of gross misconduct, fraud, data breach, or breach of confidentiality.
#    4.3 Upon termination, the Employee shall return all Company property and confidential information.

# 5. CONFIDENTIALITY AND INTELLECTUAL PROPERTY
#    5.1 All analyses, reports, datasets, models, and other intellectual property developed by the Employee in the course of employment shall remain the exclusive property of the Company.
#    5.2 The Employee agrees to sign a separate Non-Disclosure and Intellectual Property Assignment Agreement.

# 6. COMPLIANCE AND ETHICS
#    6.1 The Employee must at all times adhere to HSBC's Global Standards on Financial Crime Risk and Anti-Money Laundering (AML) procedures.
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
#
#
# if __name__ == "__main__":
#     async def main():
#         processor = AsyncAiProcessing(contract=contract_real)
#         result = await processor.get_answer_json_dict()
#         print(json.dumps(result, indent=2, ensure_ascii=False))
#
#     asyncio.run(main())

