import os
from src.llm.schema import BookRecord, EnrichmentResult


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