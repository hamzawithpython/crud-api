# LLM-Backed Enrichment (Week 6)

Part of the `crud-api` repo, built for the FlyRank AI Backend Engineering Internship. Adds `POST /enrich` to the existing FastAPI app from A1-A4. See the main [README](README.md) for setup, the base CRUD endpoints, and authentication.

`POST /enrich` classifies a scraped book record into a category, writes a one-sentence summary, and flags quality issues - using a local LLM (Ollama, gemma3:1b) rather than a hosted API. This chains onto the Polite Scraper (a separate repo): scrape -> enrich -> flag for review is a real pipeline, not a standalone demo.

---

## Why this design

The core idea mirrors LedgerLens: a system that knows what it doesn't know is more valuable than one that guesses confidently. Every model call goes through a defensive pipeline before anything reaches the caller:

1. **Contract before AI** - input and output are Pydantic schemas (`src/llm/schema.py`) with `Literal` types enforcing the closed category list. The schema is the enforcement mechanism, not the prompt.
2. **Prompt as a versioned file** - the system prompt lives in `prompts/enrich-v1.md`, not as a string in code. Role, output shape, rules, when-unsure guidance, and examples are all spelled out explicitly, separate from the per-request book data (system vs. user message - the wall between trusted instructions and untrusted content).
3. **Parse, validate, repair once, quarantine** - model output is treated as untrusted input, same principle as parsing scraped HTML. Markdown fences get stripped defensively. If parsing or validation fails, one repair attempt replays the conversation with the model's own broken output and the exact error, asking it to fix it. If that also fails, the failure is logged to `logs/quarantine.jsonl` and the caller gets a clean `422` - never a raw model dump, never a crash.
4. **Production guards** - 30 second timeout (the SDK default of 10 minutes is not a real timeout for an HTTP endpoint), retry only on `5xx`/`429` with exponential backoff and jitter (never retry a bad key or malformed request), and a kill switch (`LLM_ENABLED=false`) that returns `503` without touching the model at all.
5. **Cost logging** - every call logs prompt version, model, token counts, duration, and repair count to `logs/calls.jsonl`. This is what actually answers "how much would this cost at scale," rather than guessing.

---

## Endpoint

| Method | Path | Description | Success | Error cases |
|--------|------|-------------|---------|-------------|
| POST | `/enrich` | Classify a book record | 200 | 422 if model output fails validation after repair, 503 if LLM_ENABLED=false |

**Input:**
```json
{
  "title": "The Whimsical Garden",
  "description": "A collection of poems exploring childhood imagination.",
  "rating_text": "Four",
  "price_gbp": 12.99
}
```

**Output:**
```json
{
  "category": "children",
  "summary": "Poems about childhood and imagination.",
  "quality_flags": ["low_confidence"],
  "confidence": 0.85
}
```

---

## New environment variables

LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=gemma3:1b
LLM_STUB=0
LLM_ENABLED=true

`LLM_STUB=1` returns a hard-coded valid response with zero model calls - used during development to test the endpoint contract without burning time on real inference.

---

## Provider

Ollama, running locally with `gemma3:1b`. Install from [ollama.com](https://ollama.com), then:
```powershell
ollama run gemma3:1b
```
No API costs during development, and swapping to a hosted provider later is a three-variable `.env` change, not a code change - the `openai` client library speaks the same request shape either way.

---

## Eval results

8 hand-labelled cases in `evals/cases.json`, run against the live endpoint via `evals/run_eval.py`.

**Score: 5/8** (prompt version `enrich-v1`)

| Case | Type | Expected | Actual | Result |
|------|------|----------|--------|--------|
| 1 | obvious fiction | fiction | fiction | PASS |
| 2 | obvious non-fiction | non-fiction | non-fiction | PASS |
| 3 | ambiguous | mystery | fiction | FAIL |
| 4 | ambiguous | self-help | self-help | PASS |
| 5 | missing description | other | other | PASS |
| 6 | description too short | other | fiction | FAIL |
| 7 | genuinely unclear | other | other | PASS |
| 8 | category boundary | children | mystery | FAIL |

**What the failures actually show:**

- **Case 6 is the most important failure.** The description was deliberately too short to classify confidently - the expected behavior was `other` with a `description_too_short` flag. Instead the model classified confidently as `fiction`. This matches a calibration issue observed repeatedly during manual testing before the eval was even built: the model doesn't reliably act on its own uncertainty-flagging rules. In one earlier manual test it returned `quality_flags: ["low_confidence"]` alongside `confidence: 0.85` - a direct contradiction of its own prompt instructions. The eval turns that anecdote into a reproducible result.
- **Case 3** shows a tension in the category schema itself: `fiction` and `mystery` aren't mutually exclusive in reality (a mystery novel is fiction), so the model's answer isn't unreasonable, just less specific than expected.
- **Case 8** was flagged as a genuine judgment call before the eval ran - is a children's mystery `mystery` or `children`? The model picked the label I predicted someone might reasonably argue for. Counted as a failure against my chosen ground truth, but it's as much a labeling ambiguity as a model error.

**What didn't fail, and is worth noting anyway:** across all manual and eval testing, the parse-repair-quarantine pattern (Stage 3/4) recovered from every real parsing failure observed - `logs/quarantine.jsonl` has never received an entry. The one logged case of first-attempt failure (a stray markdown escape character, `\_`, inserted into a JSON field name) was fully corrected by the single repair attempt.

**Takeaway:** the model is a reasonable classifier on clear cases and a decent guesser on ambiguous ones, but it cannot be trusted to reliably flag its own uncertainty - the schema-level enforcement and repair/quarantine safety net matter more than the model's self-reported confidence.

---

## Testing

```powershell
python evals\run_eval.py
```

Requires the server running locally (`uvicorn main:app --reload`) and `LLM_STUB=0`.

---

## Project structure added

crud-api/
src/
routes/
enrich.py
llm/
client.py
schema.py
prompts/
enrich-v1.md
evals/
cases.json
run_eval.py
logs/
quarantine.jsonl (gitignored, created at runtime)
calls.jsonl (gitignored, created at runtime)
JOB-CARD.md

