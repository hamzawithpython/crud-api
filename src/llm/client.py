import os
from src.llm.schema import BookRecord, EnrichmentResult
from pathlib import Path
from openai import OpenAI
import re
import json as json_module
from datetime import datetime, timezone


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



PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "enrich-v1.md"


def build_prompt(book: BookRecord) -> tuple[str, str]:
    """Returns (system_prompt, user_message) — split per the wall between
    trusted instructions and per-request data."""
    template = PROMPT_PATH.read_text(encoding="utf-8")

    # Everything above the final heading is fixed instruction text.
    system_part, _, _ = template.partition("# Book record to classify")

    # The actual record — this is the "data," kept out of the system prompt.
    user_message = (
        f"title: {book.title}\n"
        f"description: {book.description}\n"
        f"rating_text: {book.rating_text}\n"
        f"price_gbp: {book.price_gbp}"
    )

    return system_part.strip(), user_message


def call_llm(book: BookRecord) -> str:
    """Calls the real model. Returns raw text — not yet parsed or validated.
    That robustness is Stage 3's job, on purpose."""
    client = OpenAI(
        base_url=os.getenv("LLM_BASE_URL"),
        api_key=os.getenv("LLM_API_KEY"),
    )

    system_prompt, user_message = build_prompt(book)

    response = client.chat.completions.create(
        model=os.getenv("LLM_MODEL"),
        temperature=0,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )

    return response.choices[0].message.content


QUARANTINE_PATH = Path(__file__).resolve().parent.parent.parent / "logs" / "quarantine.jsonl"


def strip_fences(text: str) -> str:
    """Models often wrap JSON in ```json ... ``` fences by default.
    Strip defensively rather than assuming they won't appear —
    Stage 2 already showed us the model CAN return clean JSON, but
    that's not a guarantee across every input."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def call_llm_repair(book: BookRecord, broken_output: str, error: str) -> str:
    """One repair attempt: replay the conversation with the model's own
    broken answer plus the exact validation error, and ask it to fix it.
    Not versioned like enrich-v1.md — this is a mechanical follow-up
    built per-failure, not a reusable spec."""
    client = OpenAI(
        base_url=os.getenv("LLM_BASE_URL"),
        api_key=os.getenv("LLM_API_KEY"),
    )
    system_prompt, user_message = build_prompt(book)

    repair_instruction = (
        f"Your previous response could not be parsed or validated.\n\n"
        f"The error was: {error}\n\n"
        f"Return ONLY a corrected JSON object matching the required schema. "
        f"No markdown fences, no explanation, no extra text."
    )

    response = client.chat.completions.create(
        model=os.getenv("LLM_MODEL"),
        temperature=0,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": broken_output},
            {"role": "user", "content": repair_instruction},
        ],
    )
    return response.choices[0].message.content


def write_quarantine(book: BookRecord, raw_output: str, error: str) -> None:
    """Two failures land here instead of crashing the request or leaking
    raw model text to the caller. Append-only log — every failure is
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