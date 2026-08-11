from fastapi import APIRouter, HTTPException
from src.llm.schema import BookRecord, EnrichmentResult
from src.llm.client import get_stub_response, is_stub_mode

router = APIRouter()


@router.post("/enrich", response_model=EnrichmentResult)
def enrich_book(book: BookRecord):
    if is_stub_mode():
        return get_stub_response(book)

    # Real model call comes in Stage 2/3 — for now, fail loudly
    # rather than silently, so it's obvious this path isn't built yet.
    raise HTTPException(
        status_code=501,
        detail="Real model path not implemented yet — set LLM_STUB=1",
    )