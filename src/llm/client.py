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

PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "enrich-v2.md"


def build_prompt(book: BookRecord) -> tuple[str, str]:
    """Returns (system_prompt, user_message) - split per the wall between
    trusted instructions and per-request data."""
    template = PROMPT_PATH.read_text(encoding="utf-8")

    system_part, _, _ = template.partition("# Book record to classify")

    user_message = (
        f"title: {book.title}\n"
        f"description: {book.description}\n"
        f"rating_text: {book.rating_text}\n"
        f"price_gbp: {book.price_gbp}"
    )

    return system_part.strip(), user_message


# ---------- Config / constants ----------

TIMEOUT_SECONDS = 30
MAX_RETRIES = 2
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

QUARANTINE_PATH = Path(__file__).resolve().parent.parent.parent / "logs" / "quarantine.jsonl"
CALL_LOG_PATH = Path(__file__).resolve().parent.parent.parent / "logs" / "calls.jsonl"
PROMPT_VERSION = "enrich-v2"  # bumped from v1 after real-data testing surfaced JSON-syntax bugs


# ---------- Kill switch / client setup ----------

def is_llm_enabled() -> bool:
    return os.getenv("LLM_ENABLED", "true").lower() == "true"


def _get_client() -> OpenAI:
    return OpenAI(
        base_url=os.getenv("LLM_BASE_URL"),
        api_key=os.getenv("LLM_API_KEY"),
        timeout=TIMEOUT_SECONDS,
    )


# ---------- Retry wrapper ----------

def _call_with_retry(client: OpenAI, **kwargs) -> tuple[str, dict]:
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

            backoff = (2 ** attempt) + random.uniform(0, 0.5)
            time.sleep(backoff)

    raise last_exception


# ---------- Model calls ----------

def call_llm(book: BookRecord) -> tuple[str, dict]:
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
    """Cleans up common ways gemma3:1b's raw output deviates from valid JSON,
    observed across real testing (not hypothetical):

    1. Markdown code fences wrapping the JSON (```json ... ```)
    2. Python-style capitalized True/False/None instead of JSON's lowercase
       true/false/null (seen on real scraped data, e.g. "title_unclear": True)
    3. Unnecessary backslash-escapes before characters JSON doesn't require
       escaping - apostrophes and underscores (seen on real scraped data,
       e.g. "there\\'s mischief", "quality\\_flags")

    This is a code-level fix rather than relying solely on prompt wording,
    because format instructions repeatedly lose to strong model priors on
    a small local model - the same lesson already documented from the
    v1 Prompt Ladder work and from LedgerLens's confidence calibration.

    Known limitation: the True/False/None word-boundary substitution could
    theoretically alter those words if they appear naturally inside a
    generated summary sentence (e.g. "her True calling"). Accepted tradeoff
    given how rarely capitalized True/False/None appears in normal prose
    versus how often it appears as a raw Python-style JSON value on this
    model.
    """
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    # Invalid escapes JSON doesn't require - strip the stray backslash.
    text = text.replace("\\_", "_")
    text = text.replace("\\'", "'")

    # Python-style booleans/None -> JSON equivalents, word-boundary safe.
    text = re.sub(r'(?<!["\w])True(?!["\w])', "true", text)
    text = re.sub(r'(?<!["\w])False(?!["\w])', "false", text)
    text = re.sub(r'(?<!["\w])None(?!["\w])', "null", text)

    return text.strip()

def truncate_summary(text: str, max_len: int = 200) -> str:
    """The schema caps summary length (~20 words, generous char ceiling),
    but gemma3:1b sometimes ignores the "one sentence, max 20 words"
    prompt rule and echoes multi-sentence chunks of the source
    description instead - especially on info-dense non-fiction and
    longer fairytale-style descriptions. Rather than reject an otherwise
    correct classification over this formatting overshoot (wasting a
    repair round-trip, or worse landing a good answer in quarantine),
    truncate to a clean word boundary. Same principle as strip_fences:
    fix the output, don't just crash on it.
    """
    if text is None or len(text) <= max_len:
        return text
    truncated = text[: max_len - 1].rsplit(" ", 1)[0]
    return truncated.rstrip(".,;: ") + "…"

def call_llm_repair(book: BookRecord, broken_output: str, error: str) -> tuple[str, dict]:
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


