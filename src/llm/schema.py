from typing import Literal, Optional
from pydantic import BaseModel, Field


# ---- Input: what comes into /enrich ----
class BookRecord(BaseModel):
    title: str
    description: Optional[str] = None
    rating_text: str
    price_gbp: float


# ---- Output: what the model (or stub) must produce ----
class EnrichmentResult(BaseModel):
    category: Literal[
        "fiction", "non-fiction", "mystery", "children", "self-help", "other"
    ]
    summary: str = Field(max_length=200)  # ~20 words, generous char ceiling
    quality_flags: list[
        Literal[
            "description_too_short",
            "title_unclear",
            "missing_description",
            "low_confidence",
        ]
    ] = []
    confidence: float = Field(ge=0.0, le=1.0)