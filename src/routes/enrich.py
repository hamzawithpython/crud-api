import json
from fastapi import APIRouter, HTTPException
from src.llm.schema import BookRecord, EnrichmentResult
from src.llm.client import get_stub_response, is_stub_mode, call_llm

router = APIRouter()


@router.post("/enrich", response_model=EnrichmentResult)
def enrich_book(book: BookRecord):
    if is_stub_mode():
        return get_stub_response(book)

    raw_output = call_llm(book)

    try:
        data = json.loads(raw_output)
        return EnrichmentResult(**data)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "raw parse failed — expected before Stage 3 is built",
                "exception": str(e),
                "raw_model_output": raw_output,
            },
        )
