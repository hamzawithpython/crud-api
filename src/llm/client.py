import os
from src.llm.schema import BookRecord, EnrichmentResult
from pathlib import Path
from openai import OpenAI

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