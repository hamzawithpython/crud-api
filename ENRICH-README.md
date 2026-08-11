# LLM-Backed Enrichment (Week 6)

Part of the `crud-api` repo, built for the FlyRank AI Backend Engineering Internship. Adds `POST /enrich` to the existing FastAPI app from A1-A4. See the main [README](README.md) for setup, the base CRUD endpoints, and authentication.

`POST /enrich` classifies a scraped book record into a category, writes a one-sentence summary, and flags quality issues - using a local LLM (Ollama, gemma3:1b) rather than a hosted API. This connects to the Polite Scraper (a separate repo, `ai-backend-polite-scrapper`): scrape -> enrich -> flag for review, via a real connector script (`enrich_scraped_books.py`) that reads the scraper's actual `books.json` output and enriches all 60 real books.

---

## Why this design

The core idea mirrors LedgerLens: a system that knows what it doesn't know is more valuable than one that guesses confidently. Every model call goes through a defensive pipeline before anything reaches the caller:

1. **Contract before AI** - input and output are Pydantic schemas (`src/llm/schema.py`) with `Literal` types enforcing the closed category list. The schema is the enforcement mechanism, not the prompt.
2. **Prompt as a versioned file** - the system prompt lives in `prompts/enrich-v1.md` and `prompts/enrich-v2.md`, not as a string in code. Role, output shape, rules, when-unsure guidance, and examples are all spelled out explicitly, separate from the per-request book data (system vs. user message - the wall between trusted instructions and untrusted content).
3. **Parse, sanitize, validate, repair once, quarantine** - model output is treated as untrusted input, same principle as parsing scraped HTML. Markdown fences and known non-JSON quirks get cleaned defensively before parsing. If validation still fails, one repair attempt replays the conversation with the model's own broken output and the exact error, asking it to fix it. If that also fails, the failure is logged to `logs/quarantine.jsonl` and the caller gets a clean `422` - never a raw model dump, never a crash.
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

```
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=gemma3:1b
LLM_STUB=0
LLM_ENABLED=true
```

`LLM_STUB=1` returns a hard-coded valid response with zero model calls - used during development to test the endpoint contract without burning time on real inference.

---

## Provider

Ollama, running locally with `gemma3:1b`. Install from [ollama.com](https://ollama.com), then:
```powershell
ollama run gemma3:1b
```
No API costs during development, and swapping to a hosted provider later is a three-variable `.env` change, not a code change - the `openai` client library speaks the same request shape either way.

---

## Prompt versions

`prompts/enrich-v1.md` is the original spec. `prompts/enrich-v2.md` adds explicit rules discovered from testing against real scraped data:

- Never return `null` for `summary` - write the shortest honest English summary possible, even for non-English descriptions
- Never add fields beyond the four in the schema
- Use only valid JSON syntax (lowercase `true`/`false`/`null`, never Python-style `True`/`False`/`None`)
- Never escape characters JSON doesn't require escaping (apostrophes, underscores)

Both files are kept, not overwritten, so the two can be compared directly - the whole point of treating prompts as versioned specs rather than throwaway strings.

**A genuine finding from this process:** switching to v2 alone (before adding code-level defenses) briefly caused a *regression* - 57/60 real books passed versus v1's 58/60. Two new books failed that had passed cleanly under v1. The most likely explanation: a longer prompt with more rules can shift a small model's behavior on completely unrelated inputs, even at temperature 0, because the entire generation path depends on the full prompt context. This matches an already-documented lesson from the Prompt Ladder assignment and from LedgerLens: format instructions do not reliably override a model's underlying tendencies. The regression was resolved not by tuning the prompt further, but by adding a code-level fix (below) - isolating the real cause rather than guessing at more prompt wording changes.

---

## Eval results (hand-labeled accuracy)

8 hand-labeled cases in `evals/cases.json`, run against the live endpoint via `evals/run_eval.py`.

**Score: 5/8 - identical under both prompt v1 and v2**

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

**The score did not change between prompt versions, and the specific wrong answers are identical.** This is worth being precise about: the sanitizer and truncation fixes added after v1 improved *formatting reliability* (see the real-data pipeline results below), but did not change the model's underlying *category judgment* on ambiguous cases - and they were never designed to. Case 6 remains the most informative failure: the description was deliberately too short to classify confidently, and the model still classified confidently as `fiction` instead of flagging `low_confidence`, on both prompt versions. The model cannot be trusted to reliably know when it doesn't know - the schema-level enforcement and repair/quarantine safety net matter more than the model's self-reported confidence.

---

## Real-data pipeline test

`enrich_scraped_books.py` reads the Polite Scraper's actual `books.json` output (60 real scraped books, not synthetic test cases) and sends each one through the live `POST /enrich` endpoint, saving results to `books_enriched.json`.

**Why file-based, not a live connection to the scraper:** the scraper is a one-shot script with no running API of its own - it scrapes once and exits. The scraped data does not change between the scrape and the enrichment step, so a live server-to-server connection would add real infrastructure complexity (a second server to build and keep running) for a dataset that has no freshness requirement. This matches how the scraper was originally specified: `books.json` as the input source.

```powershell
python enrich_scraped_books.py "path\to\ai-backend-polite-scrapper\output\books.json"
```

**Results across iterations:**

| Version | Result | Notes |
|---------|--------|-------|
| v1 prompt | 58/60 | 2 quarantined: a French-language description that returned `summary: null`, and one JSON-escape bug (`\'`) on a long description |
| v2 prompt only (regression) | 57/60 | Foolproof Preserving fixed by the code-level sanitizer (below), but Aladdin still failed, and 2 *new* books failed with a different bug: overlong summaries exceeding the schema's 200-character limit |
| v2 prompt + JSON sanitizer + summary truncation (final) | **60/60**, 1/60 needed a silent repair, 0/60 quarantined | |

**Two code-level fixes, not prompt-only fixes, closed the gap:**

1. **JSON sanitizer** (`strip_fences` in `src/llm/client.py`) - strips markdown fences, and corrects two real, observed non-JSON patterns: Python-style capitalized `True`/`False`/`None` instead of JSON's lowercase equivalents, and unnecessary backslash-escapes before apostrophes and underscores. Both patterns were seen on real scraped data, not hypothesized.
2. **Summary truncation** (`truncate_summary` in `src/llm/client.py`) - the schema caps `summary` at 200 characters, but the model sometimes echoes multi-sentence chunks of a dense description instead of writing one sentence. Rather than reject an otherwise-correct classification over this formatting overshoot, the summary is truncated to a clean word boundary before validation. In all three cases this fixed, the model's *category* was already correct - only the summary length was wrong. Rejecting a correct classification over an unrelated formatting detail would have been the wrong tradeoff.

This mirrors the exact philosophy documented in Stage 3: fix the model's output where possible, don't just reject it. The one remaining repair (of 60) succeeded on its single retry, and quarantine - the last-resort safety net - was never triggered on the final run.

---

## Known limitations

- **The model cannot reliably flag its own uncertainty.** Confirmed twice: once anecdotally during manual testing (`confidence: 0.85` returned alongside a `low_confidence` flag - a direct contradiction), and once in the eval (Case 6, unchanged across both prompt versions). The system's safety net (schema enforcement, repair, quarantine) compensates for this; the model's self-reported confidence should not be trusted on its own.
- **Category overlap is not resolved by the schema.** `fiction` and `mystery` are not mutually exclusive in reality (a mystery novel is fiction), so some "failures" reflect a genuinely ambiguous ground truth rather than a clear model error.
- **Summary truncation is a mitigation, not a fix.** It prevents a good classification from being discarded, but the model still is not reliably following the "one sentence, 20 words" instruction on longer or denser descriptions - it is truncated after the fact, not generated correctly in the first place.
- **Non-English descriptions receive lower-quality summaries.** The v2 prompt explicitly asks for a fallback English summary rather than `null`, but no dedicated translation step exists - summaries on non-English descriptions are approximate at best.

---

## Testing

**Eval (accuracy against hand-labeled cases):**
```powershell
python evals\run_eval.py
```

**Real-data pipeline (formatting robustness against actual scraped output):**
```powershell
python enrich_scraped_books.py "path\to\books.json"
```

Both require the server running locally (`uvicorn main:app --reload`) and `LLM_STUB=0`.

---

## Project structure added

```
crud-api/
  src/
    routes/
      enrich.py
    llm/
      client.py
      schema.py
  prompts/
    enrich-v1.md
    enrich-v2.md
  evals/
    cases.json
    run_eval.py
  enrich_scraped_books.py
  books_enriched.json        (real output from the 60-book pipeline test)
  logs/
    quarantine.jsonl   (gitignored, created at runtime)
    calls.jsonl         (gitignored, created at runtime)
  JOB-CARD.md
```
