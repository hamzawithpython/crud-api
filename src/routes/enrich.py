import json
from fastapi import APIRouter, HTTPException
from src.llm.schema import BookRecord, EnrichmentResult
from src.llm.client import (
    get_stub_response,
    is_stub_mode,
    call_llm,
    call_llm_repair,
    strip_fences,
    write_quarantine,
)

router = APIRouter()


def parse_and_validate(raw_output: str) -> EnrichmentResult:
    """Strip, parse, validate. Raises on any failure - caller decides
    what happens next (repair vs. quarantine)."""
    cleaned = strip_fences(raw_output)
    data = json.loads(cleaned)          # may raise json.JSONDecodeError
    return EnrichmentResult(**data)      # may raise pydantic ValidationError


@router.post("/enrich", response_model=EnrichmentResult)
def enrich_book(book: BookRecord):
    if is_stub_mode():
        return get_stub_response(book)

    raw_output = call_llm(book)

    try:
        return parse_and_validate(raw_output)
    except Exception as first_error:
        repaired_output = call_llm_repair(book, raw_output, str(first_error))
        try:
            return parse_and_validate(repaired_output)
        except Exception as second_error:
            write_quarantine(book, repaired_output, str(second_error))
            raise HTTPException(
                status_code=422,
                detail="Model could not produce valid output after one repair attempt.",
            )