import os
import re
import time
import random
import json as json_module
from pathlib import Path
from datetime import datetime, timezone

from openai import OpenAI

from src.llm.schema import BookRecord, EnrichmentResult


# ---------- Stub mode ----------

def get_stub_response(book: BookRecord) -> EnrichmentResult:
    """Hard-coded valid output. Zero model calls. Used when LLM_STUB=1."""
    return EnrichmentResult(
        category="fiction",
        summary=f"A book titled '{book.title}'.",
        quality_flags=[] if book.description else ["missing_description"],
        confidence=0.5,
    )


def is_stub_mode() -> bool:
    return os.getenv("LLM_STUB", "0") == "1"


# ---------- Prompt loading ----------

PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "enrich-v1.md"


def build_prompt(book: BookRecord) -> tuple[str, str]:
    """Returns (system_prompt, user_message) - split per the wall between
    trusted instructions and per-request data."""
    template = PROMPT_PATH.read_text(encoding="utf-8")

    # Everything above the final heading is fixed instruction text.
    system_part, _, _ = template.partition("# Book record to classify")

    # The actual record - this is the "data," kept out of the system prompt.
    user_message = (
        f"title: {book.title}\n"
        f"description: {book.description}\n"
        f"rating_text: {book.rating_text}\n"
        f"price_gbp: {book.price_gbp}"
    )

    return system_part.strip(), user_message


# ---------- Config / constants ----------

TIMEOUT_SECONDS = 30
MAX_RETRIES = 2  # total attempts = 1 initial + up to 2 retries = 3
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

QUARANTINE_PATH = Path(__file__).resolve().parent.parent.parent / "logs" / "quarantine.jsonl"
CALL_LOG_PATH = Path(__file__).resolve().parent.parent.parent / "logs" / "calls.jsonl"
PROMPT_VERSION = "enrich-v1"  # bump this string when the prompt file changes


# ---------- Kill switch / client setup ----------

def is_llm_enabled() -> bool:
    """Kill switch. False means: don't touch the model at all, fail fast
    with a clear signal. Someone non-technical can flip this in .env
    without needing a deploy or a code change."""
    return os.getenv("LLM_ENABLED", "true").lower() == "true"


def _get_client() -> OpenAI:
    return OpenAI(
        base_url=os.getenv("LLM_BASE_URL"),
        api_key=os.getenv("LLM_API_KEY"),
        timeout=TIMEOUT_SECONDS,
    )


# ---------- Retry wrapper ----------

def _call_with_retry(client: OpenAI, **kwargs) -> tuple[str, dict]:
    """Wraps a single chat completion call with retry-on-transient-error.
    Returns (content, usage_dict) so callers can log token counts.

    Retries only on 5xx/429 (transient) - never on 4xx auth/bad-request
    errors, since those won't fix themselves by waiting."""
    last_exception = None

    for attempt in range(MAX_RETRIES + 1):
        start = time.monotonic()
        try:
            response = client.chat.completions.create(**kwargs)
            duration_ms = (time.monotonic() - start) * 1000
            usage = {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else None,
                "completion_tokens": response.usage.completion_tokens if response.usage else None,
                "duration_ms": round(duration_ms, 1),
            }
            return response.choices[0].message.content, usage

        except Exception as e:
            status_code = getattr(e, "status_code", None)
            last_exception = e

            is_retryable = status_code in RETRYABLE_STATUS_CODES
            is_last_attempt = attempt == MAX_RETRIES

            if not is_retryable or is_last_attempt:
                raise

            # Exponential backoff with jitter: wait longer each retry,
            # plus a small random offset so simultaneous failed requests
            # don't all retry at the exact same instant.
            backoff = (2 ** attempt) + random.uniform(0, 0.5)
            time.sleep(backoff)

    raise last_exception


# ---------- Model calls ----------

def call_llm(book: BookRecord) -> tuple[str, dict]:
    """Calls the real model, with timeout + retry + usage tracking.
    Returns (raw_text, usage) - usage feeds the cost log."""
    if not is_llm_enabled():
        raise RuntimeError("LLM_ENABLED is false - kill switch is active")

    client = _get_client()
    system_prompt, user_message = build_prompt(book)

    return _call_with_retry(
        client,
        model=os.getenv("LLM_MODEL"),
        temperature=0,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )


def strip_fences(text: str) -> str:
    """Models often wrap JSON in ```json ... ``` fences by default.
    Strip defensively rather than assuming they won't appear -
    Stage 2 already showed us the model CAN return clean JSON, but
    that's not a guarantee across every input."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def call_llm_repair(book: BookRecord, broken_output: str, error: str) -> tuple[str, dict]:
    """One repair attempt: replay the conversation with the model's own
    broken answer plus the exact validation error, and ask it to fix it.
    Same timeout/retry/usage-tracking treatment as the first call."""
    if not is_llm_enabled():
        raise RuntimeError("LLM_ENABLED is false - kill switch is active")

    client = _get_client()
    system_prompt, user_message = build_prompt(book)

    repair_instruction = (
        f"Your previous response could not be parsed or validated.\n\n"
        f"The error was: {error}\n\n"
        f"Return ONLY a corrected JSON object matching the required schema. "
        f"No markdown fences, no explanation, no extra text."
    )

    return _call_with_retry(
        client,
        model=os.getenv("LLM_MODEL"),
        temperature=0,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": broken_output},
            {"role": "user", "content": repair_instruction},
        ],
    )


# ---------- Logging ----------

def write_quarantine(book: BookRecord, raw_output: str, error: str) -> None:
    """Two failures land here instead of crashing the request or leaking
    raw model text to the caller. Append-only log - every failure is
    evidence for later, never silently dropped."""
    QUARANTINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "input": book.model_dump(),
        "raw_output": raw_output,
        "error": error,
    }
    with open(QUARANTINE_PATH, "a", encoding="utf-8") as f:
        f.write(json_module.dumps(entry) + "\n")


def log_call(usage: dict, repair_count: int, success: bool) -> None:
    """Every call logs: prompt version, model, tokens in/out, duration ms,
    repair count. You cannot manage what you do not measure - this is
    what eventually answers 'how much would this cost at 10,000 req/day'."""
    CALL_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "prompt_version": PROMPT_VERSION,
        "model": os.getenv("LLM_MODEL"),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "duration_ms": usage.get("duration_ms"),
        "repair_count": repair_count,
        "success": success,
    }
    with open(CALL_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json_module.dumps(entry) + "\n")