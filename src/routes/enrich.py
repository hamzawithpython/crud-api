import json
from fastapi import APIRouter, HTTPException
from src.llm.schema import BookRecord, EnrichmentResult
from src.llm.client import (
    get_stub_response,
    is_stub_mode,
    call_llm,
    call_llm_repair,
    strip_fences,
    truncate_summary,
    write_quarantine,
    log_call,
)

router = APIRouter()


def parse_and_validate(raw_output: str) -> EnrichmentResult:
    """Strip, parse, validate. Raises on any failure - caller decides
    what happens next (repair vs. quarantine)."""
    cleaned = strip_fences(raw_output)
    data = json.loads(cleaned)
    if isinstance(data.get("summary"), str):
        data["summary"] = truncate_summary(data["summary"])
    return EnrichmentResult(**data)


@router.post("/enrich", response_model=EnrichmentResult)
def enrich_book(book: BookRecord):
    if is_stub_mode():
        return get_stub_response(book)

    try:
        raw_output, usage = call_llm(book)
    except RuntimeError as e:
        if "LLM_ENABLED" in str(e):
            raise HTTPException(status_code=503, detail="Enrichment is temporarily disabled")
        raise

    try:
        result = parse_and_validate(raw_output)
        log_call(usage, repair_count=0, success=True)
        return result
    except Exception as first_error:
        repaired_output, repair_usage = call_llm_repair(book, raw_output, str(first_error))
        try:
            result = parse_and_validate(repaired_output)
            log_call(repair_usage, repair_count=1, success=True)
            return result
        except Exception as second_error:
            log_call(repair_usage, repair_count=1, success=False)
            write_quarantine(book, repaired_output, str(second_error))
            raise HTTPException(
                status_code=422,
                detail="Model could not produce valid output after one repair attempt.",
            )