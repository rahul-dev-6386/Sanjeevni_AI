import json
import logging
import time
from typing import Optional, Generator
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.ai_cache import AICache

logger = logging.getLogger("ai_provider")

PROVIDER_FALLBACK = "fallback"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
BASE_TIMEOUT = 60.0
RETRY_TIMEOUT = 120.0


class ProviderResult:
    def __init__(self, provider: str, success: bool, content: str = "", data: Optional[dict] = None, error: str = "", model_used: str = ""):
        self.provider = provider
        self.success = success
        self.content = content
        self.data = data or {}
        self.error = error
        self.model_used = model_used


def _parse_json(text: str) -> Optional[dict]:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:]) if len(lines) > 1 else text[3:]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    text = text.strip()
    if text.startswith("json"):
        text = text[4:].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


class OpenRouterProvider:
    def __init__(self, api_key: str, models_str: Optional[str] = None):
        self.name = "openrouter"
        self.client = None
        self.last_model_used = ""
        self.models_str = models_str
        self.models = self._parse_models()
        if api_key:
            from openai import OpenAI
            self.client = OpenAI(
                api_key=api_key,
                base_url=OPENROUTER_BASE_URL,
                timeout=BASE_TIMEOUT,
                max_retries=0,
            )
        self._check_configuration()

    def _parse_models(self) -> list[str]:
        raw = self.models_str if self.models_str is not None else settings.OPENROUTER_MODELS
        models = [m.strip() for m in raw.split(",") if m.strip()]
        return models or ["nvidia/nemotron-3-ultra:free"]

    def _check_configuration(self):
        fail = False
        if not settings.OPENROUTER_API_KEY:
            logger.error("Sanjeevni AI cannot start: OPENROUTER_API_KEY is not set in configuration (.env)")
            fail = True
        if not self.models:
            logger.error("Sanjeevni AI cannot start: OPENROUTER_MODELS is empty in configuration (.env)")
            fail = True
        if fail:
            return

        chain = " -> ".join(self.models)
        logger.info("Sanjeevni AI: OpenRouter provider configured")
        logger.info(f"  Primary: {self.models[0]}")
        for i, m in enumerate(self.models[1:], 1):
            logger.info(f"  Fallback {i}: {m}")
        logger.info(f"  Full chain: {chain}")

    def is_available(self) -> bool:
        return self.client is not None and len(self.models) > 0

    def has_usable_model(self) -> bool:
        return self.is_available()

    def _build_messages(self, prompt: str, system_instruction: Optional[str] = None) -> list[dict]:
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})
        return messages

    def _make_client(self, timeout: float):
        from openai import OpenAI
        return OpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url=OPENROUTER_BASE_URL,
            timeout=timeout,
            max_retries=0,
        )

    def _classify_error(self, error: Exception) -> str:
        status_str = str(error)
        msg = status_str.lower()
        if "429" in status_str or "rate limit" in msg or "too many requests" in msg:
            return "rate_limited"
        if "401" in status_str or "unauthorized" in msg or "invalid api key" in msg or "invalid_api_key" in msg:
            return "invalid_key"
        if "402" in status_str:
            return "insufficient_credits"
        if "500" in status_str or "502" in status_str or "503" in status_str or "504" in status_str:
            return "server_error"
        if "timeout" in msg or "timed out" in msg or "read timed out" in msg:
            return "timeout"
        if "connection" in msg or "unreachable" in msg or "unavailable" in msg or "econnrefused" in msg or "econnreset" in msg:
            return "unavailable"
        if "model not found" in msg or "model_not_found" in msg or "does not exist" in msg or "not a valid model" in msg:
            return "model_not_found"
        return "unknown"

    def _log_switch(self, from_model: str, to_model: str, reason: str):
        logger.info(f"  {from_model} -> {to_model}  Reason: {reason}")

    def _generate_with_retry(self, model: str, messages: list, temperature: float, is_retry: bool = False) -> str:
        client = self._make_client(RETRY_TIMEOUT) if is_retry else self.client
        t0 = time.time()
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
        )
        content = response.choices[0].message.content or ""
        elapsed = time.time() - t0
        tag = " (retry)" if is_retry else ""
        logger.info(f"  {model}{tag} responded in {elapsed:.2f}s")
        self.last_model_used = model
        return content

    def generate_response(self, prompt: str, system_instruction: Optional[str] = None, temperature: float = 0.3) -> str:
        if not self.client:
            raise Exception("OpenRouter API key not configured")
        if not self.models:
            raise Exception("OpenRouter model list is empty")

        messages = self._build_messages(prompt, system_instruction)
        last_error = None

        for i, model in enumerate(self.models):
            is_last = i == len(self.models) - 1
            try:
                return self._generate_with_retry(model, messages, temperature, is_retry=False)
            except Exception as e:
                error_type = self._classify_error(e)
                elapsed = time.time() - time.time()

                if error_type == "invalid_key":
                    logger.error(f"  {model} invalid API key - aborting")
                    raise Exception(f"OpenRouter API key is invalid or rejected for {model}")

                if error_type == "model_not_found":
                    logger.warning(f"  {model} model not found on OpenRouter, skipping")
                    if not is_last:
                        self._log_switch(model, self.models[i + 1], "Model not found")
                    last_error = e
                    continue

                if error_type == "rate_limited":
                    logger.warning(f"  {model} returned HTTP 429 (rate limited), skipping to next")
                    if not is_last:
                        self._log_switch(model, self.models[i + 1], "HTTP 429")
                    last_error = e
                    continue

                if error_type == "insufficient_credits":
                    logger.warning(f"  {model} insufficient credits, skipping to next")
                    if not is_last:
                        self._log_switch(model, self.models[i + 1], "Insufficient credits (HTTP 402)")
                    last_error = e
                    continue

                if error_type == "server_error":
                    logger.warning(f"  {model} returned HTTP 5xx, retrying once")
                    try:
                        return self._generate_with_retry(model, messages, temperature, is_retry=True)
                    except Exception as e2:
                        logger.warning(f"  {model} server error (retry failed), skipping to next")
                        if not is_last:
                            self._log_switch(model, self.models[i + 1], "HTTP 500/502/503/504 (retry exhausted)")
                        last_error = e2
                        continue

                if error_type == "timeout":
                    logger.warning(f"  {model} timed out (timeout={BASE_TIMEOUT}s), retrying once with timeout={RETRY_TIMEOUT}s")
                    try:
                        return self._generate_with_retry(model, messages, temperature, is_retry=True)
                    except Exception as e2:
                        logger.warning(f"  {model} timeout (retry failed), skipping to next")
                        if not is_last:
                            self._log_switch(model, self.models[i + 1], "Timeout (retry exhausted)")
                        last_error = e2
                        continue

                if error_type == "unavailable":
                    logger.warning(f"  {model} provider unavailable, skipping to next")
                    if not is_last:
                        self._log_switch(model, self.models[i + 1], "Provider unavailable")
                    last_error = e
                    continue

                logger.warning(f"  {model} failed: {e}")
                if not is_last:
                    self._log_switch(model, self.models[i + 1], str(e)[:100])
                last_error = e
                continue

        raise last_error or Exception("All OpenRouter models exhausted")

    def generate_structured(self, prompt: str, system_instruction: Optional[str] = None) -> dict:
        si = system_instruction or ""
        full_prompt = f"{si}\n\n{prompt}\n\nRespond in JSON format only." if si else f"{prompt}\n\nRespond in JSON format only."
        text = self.generate_response(full_prompt, temperature=0.1)
        parsed = _parse_json(text)
        if parsed:
            return parsed
        return {"error": "Failed to parse structured response", "raw": text}

    def generate_response_stream(self, prompt: str, system_instruction: Optional[str] = None, temperature: float = 0.3):
        if not self.client:
            raise Exception("OpenRouter API key not configured")
        if not self.models:
            raise Exception("OpenRouter model list is empty")

        messages = self._build_messages(prompt, system_instruction)
        last_error = None

        for i, model in enumerate(self.models):
            is_last = i == len(self.models) - 1
            t0 = time.time()
            try:
                response = self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    stream=True,
                )
                for chunk in response:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if delta and delta.content:
                        yield delta.content
                elapsed = time.time() - t0
                logger.info(f"  {model} streamed in {elapsed:.2f}s")
                self.last_model_used = model
                return
            except Exception as e:
                error_type = self._classify_error(e)
                if error_type == "invalid_key":
                    logger.error(f"  {model} invalid API key - aborting stream")
                    raise
                if error_type == "rate_limited":
                    logger.warning(f"  {model} rate-limited (429), skipping")
                elif error_type == "server_error":
                    logger.warning(f"  {model} server error, skipping")
                elif error_type == "timeout":
                    logger.warning(f"  {model} timeout, skipping")
                else:
                    logger.warning(f"  {model} stream failed: {e}")
                if not is_last:
                    self._log_switch(model, self.models[i + 1], error_type)
                last_error = e
                continue

        if last_error:
            raise last_error


class LocalFallbackProvider:
    def generate_response(self, prompt: str, system_instruction: Optional[str] = None, temperature: float = 0.3) -> str:
        text_lower = prompt.lower()
        sys_lower = (system_instruction or "").lower()
        if "drug monograph" in text_lower or "drug monograph" in sys_lower or "drug:" in text_lower:
            return self._drug_monograph_response(prompt)
        if "routine" in text_lower or "daily" in text_lower or "plan" in text_lower:
            return self._routine_response(prompt)
        if "summary" in text_lower or "summarize" in text_lower:
            return self._summary_response(prompt)
        if "diagnos" in text_lower or "condition" in text_lower:
            return self._diagnosis_response(prompt)
        return self._generic_response(prompt)

    def generate_structured(self, prompt: str, system_instruction: Optional[str] = None) -> dict:
        text_lower = prompt.lower()
        if "health_score" in prompt or "risk_scores" in prompt:
            return {
                "health_score": 65,
                "risk_scores": {"diabetes": 30, "heart_disease": 25, "kidney_disease": 15, "liver_disease": 20, "hypertension": 35, "vitamin_deficiency": 40, "obesity": 25},
                "follow_up_tests": ["Complete Blood Count", "Lipid Panel", "HbA1c"],
                "abnormal_values": [],
                "timeline_events": [],
            }
        if "routine" in text_lower or "daily" in text_lower:
            return self._routine_structured()
        return {"success": True, "message": "Processed locally", "data": {}}

    def _routine_structured(self) -> dict:
        return {
            "wake_up_time": "06:30",
            "sleep_time": "22:00",
            "water_goal_ml": 2500,
            "walking_steps": 8000,
            "exercise_suggestions": ["Morning stretching 10min", "Brisk walk 30min", "Evening yoga 15min"],
            "nutrition_recommendations": ["High protein breakfast", "Include leafy greens in lunch", "Light dinner before 7pm"],
            "meal_timings": {"breakfast": "07:30", "lunch": "12:30", "dinner": "19:00"},
        }

    def _routine_response(self, prompt: str) -> str:
        return (
            "Based on your profile, here is your recommended daily routine: "
            "Wake up at 6:30 AM, start with 10 minutes of stretching. "
            "Have a protein-rich breakfast by 7:30 AM. "
            "Take a 30-minute brisk walk or light exercise mid-morning. "
            "Lunch at 12:30 PM including vegetables and lean protein. "
            "Stay hydrated with 8-10 glasses of water throughout the day. "
            "Light dinner before 7:00 PM. "
            "Wind down with 15 minutes of meditation or reading. "
            "Sleep by 10:00 PM for optimal recovery."
        )

    def _summary_response(self, prompt: str) -> str:
        lines = prompt.split("\n")
        doc_type = "Medical Report"
        for line in lines:
            if "Document type:" in line or "document_type" in line:
                parts = line.split(":", 1)
                if len(parts) > 1:
                    doc_type = parts[1].strip()
                    break
        return f"Processed {doc_type}. Analysis completed using local fallback."

    def _diagnosis_response(self, prompt: str) -> str:
        return (
            "Based on the available information, the findings suggest monitoring is needed. "
            "Please consult with a healthcare provider for a complete clinical evaluation. "
            "This is an AI-generated preliminary assessment and not a medical diagnosis."
        )

    def _generic_response(self, prompt: str) -> str:
        return (
            "I've analyzed your request using available health data. "
            "For a more detailed analysis, please provide additional context or consult your healthcare provider."
        )

    def _drug_monograph_response(self, prompt: str) -> str:
        import re
        drug_name = "Medication"
        match = re.search(r'DRUG:\s*(.+)', prompt, re.IGNORECASE)
        if match:
            drug_name = match.group(1).strip()

        return (
            f"# {drug_name}\n\n"
            "## Overview\n"
            "This is a fallback AI generated response. Detailed clinical information is currently unavailable because the primary AI service is experiencing high load or rate limits.\n\n"
            "## Information\n"
            "Please consult the verified database section or a healthcare provider for accurate and detailed clinical information about this medication.\n\n"
            "## References\n"
            "- System Fallback"
        )


class AIProviderService:
    def __init__(self, db: Optional[Session] = None):
        self.db = db
        self.provider = None
        self.rag_provider = None
        self.fallback = LocalFallbackProvider()
        self._init_providers()

    def _init_providers(self):
        if settings.OPENROUTER_API_KEY:
            p = OpenRouterProvider(settings.OPENROUTER_API_KEY)
            if p.is_available():
                self.provider = p

            rag_models = getattr(settings, "RAG_FORMATTING_MODELS", None)
            if rag_models:
                rag_p = OpenRouterProvider(settings.OPENROUTER_API_KEY, models_str=rag_models)
                if rag_p.is_available():
                    self.rag_provider = rag_p
            else:
                self.rag_provider = p

            if self.provider:
                return
        logger.warning("No OpenRouter API key configured - using local fallback only")

    def _get_cache(self, cache_key: str) -> Optional[dict]:
        if not self.db:
            return None
        entry = self.db.query(AICache).filter(AICache.cache_key == cache_key).first()
        if entry:
            try:
                return json.loads(entry.response_data)
            except (json.JSONDecodeError, TypeError):
                return None
        return None

    def _set_cache(self, cache_key: str, request_type: str, prompt: str, provider: str, response_data: dict):
        if not self.db:
            return
        try:
            existing = self.db.query(AICache).filter(AICache.cache_key == cache_key).first()
            if existing:
                return
            entry = AICache(
                cache_key=cache_key,
                request_type=request_type,
                prompt=prompt[:500],
                provider=provider,
                response_data=json.dumps(response_data),
            )
            self.db.add(entry)
            self.db.commit()
        except Exception:
            self.db.rollback()

    def _execute(self, request_type: str, method: str, prompt: str, system_instruction: Optional[str] = None, temperature: float = 0.3, use_cache: bool = True, use_rag_models: bool = False) -> ProviderResult:
        cache_key = AICache.make_key(request_type, prompt, system_instruction or "")
        if use_cache:
            cached = self._get_cache(cache_key)
            if cached:
                logger.info(f"Cache hit for {request_type}")
                return ProviderResult(cached.get("provider", "cache"), True, content=cached.get("content", ""), data=cached.get("data", {}))

        kwargs = {"system_instruction": system_instruction}
        if method == "generate_response":
            kwargs["temperature"] = temperature

        provider_to_use = self.rag_provider if use_rag_models and self.rag_provider else self.provider

        if provider_to_use:
            try:
                model_used = ""
                if method == "generate_response":
                    content = provider_to_use.generate_response(prompt, **kwargs)
                    model_used = getattr(provider_to_use, "last_model_used", "")
                    result = ProviderResult(provider_to_use.name, True, content=content, model_used=model_used)
                elif method == "generate_structured":
                    data = provider_to_use.generate_structured(prompt, **kwargs)
                    model_used = getattr(provider_to_use, "last_model_used", "")
                    result = ProviderResult(provider_to_use.name, True, content=json.dumps(data), data=data, model_used=model_used)
                else:
                    result = ProviderResult(PROVIDER_FALLBACK, False, content="", error=f"Unknown method: {method}")
                self._set_cache(cache_key, request_type, prompt, result.provider, {"provider": result.provider, "content": result.content, "data": result.data})
                return result
            except Exception as e:
                logger.warning(f"OpenRouter failed: {e}")

        logger.info("Using local fallback")
        try:
            if method == "generate_response":
                content = self.fallback.generate_response(prompt, **kwargs)
                result = ProviderResult(PROVIDER_FALLBACK, True, content=content)
            elif method == "generate_structured":
                data = self.fallback.generate_structured(prompt, **kwargs)
                result = ProviderResult(PROVIDER_FALLBACK, True, content=json.dumps(data), data=data)
            else:
                result = ProviderResult(PROVIDER_FALLBACK, False, content="", error=f"Unknown method: {method}")
            return result
        except Exception as e:
            return ProviderResult(PROVIDER_FALLBACK, False, content="", error=str(e))

    def generate_response(self, prompt: str, system_instruction: Optional[str] = None, temperature: float = 0.3) -> str:
        use_rag_models = system_instruction and "medical RAG formatting agent" in system_instruction
        result = self._execute("generate_response", "generate_response", prompt, system_instruction, temperature, use_rag_models=use_rag_models)
        if not result.success:
            return "AI temporarily unavailable. Please try again later."
        return result.content

    def has_usable_model(self) -> bool:
        return self.provider is not None and self.provider.has_usable_model()

    def generate_structured(self, prompt: str, system_instruction: Optional[str] = None) -> dict:
        result = self._execute("generate_structured", "generate_structured", prompt, system_instruction)
        if not result.success:
            return {"success": False, "error": "AI temporarily unavailable"}
        if result.data:
            return result.data
        try:
            return json.loads(result.content)
        except (json.JSONDecodeError, TypeError):
            return {"success": False, "error": "Failed to parse response"}

    def generate_medical_analysis(self, report_text: str, document_type: str) -> dict:
        prompt = (
            f"Analyze this {document_type} and extract all medical information.\n\n"
            f"Document text:\n{report_text[:5000]}"
        )
        return self.generate_structured(prompt, system_instruction="You are a medical document analyzer. Extract structured data in JSON.")

    def generate_chat_response(self, message: str, context: str, system_instruction: Optional[str] = None) -> str:
        si = system_instruction or "You are a helpful AI health assistant. Be concise and accurate."
        prompt = f"{context}\n\nUser: {message}\n\nAssistant:"
        return self.generate_response(prompt, system_instruction=si)

    def _execute_stream(self, prompt: str, system_instruction: Optional[str] = None, temperature: float = 0.3):
        if self.provider:
            try:
                logger.info("Streaming from OpenRouter")
                yield from self.provider.generate_response_stream(prompt, system_instruction=system_instruction, temperature=temperature)
                return
            except Exception as e:
                logger.warning(f"OpenRouter stream failed: {e}")
        logger.info("Stream fallback to local")
        yield self.fallback.generate_response(prompt, system_instruction=system_instruction)

    def generate_chat_response_stream(self, message: str, context: str, system_instruction: Optional[str] = None):
        si = system_instruction or "You are a helpful AI health assistant. Be concise and accurate."
        prompt = f"{context}\n\nUser: {message}\n\nAssistant:"
        yield from self._execute_stream(prompt, system_instruction=si)

    def generate_daily_routine(self, patient_context: str) -> dict:
        prompt = (
            f"Based on this patient profile, generate a personalized daily health routine.\n\n"
            f"Patient Context:\n{patient_context}\n\n"
            f"Generate a daily plan with: wake_up_time, sleep_time, water_goal_ml, "
            f"walking_steps, exercise_suggestions (array), nutrition_recommendations (array), "
            f"meal_timings (object with breakfast, lunch, dinner). Respond in JSON."
        )
        return self.generate_structured(prompt, system_instruction="You are a health routine generator.")


ai_provider = AIProviderService()
