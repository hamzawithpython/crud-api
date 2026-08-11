"""
Connector script: reads books.json produced by the Polite Scraper (A9,
a separate repo) and sends each book through this app's own POST /enrich
endpoint, saving the enriched results to a new file.

This is the actual "scrape -> enrich -> flag for review" pipeline the
Week 6 kickoff described. It is file-based by design, not a live
server-to-server call: the scraper is a one-shot script with no running
API of its own, and the scraped data does not change between the scrape
and the enrichment step, so there is nothing to gain from a live
connection over a simple file handoff.

Usage:
    python enrich_scraped_books.py path\\to\\books.json
    python enrich_scraped_books.py path\\to\\books.json --limit 5   # test on a few books first
"""

import argparse
import json
import sys
import time
import requests

ENRICH_URL = "http://localhost:8000/enrich"
HEALTH_URL = "http://localhost:8000/health"
OUTPUT_PATH = "books_enriched.json"
DELAY_BETWEEN_CALLS = 0.3  # seconds - polite pacing, not required but avoids hammering a local server


def check_server_is_up() -> None:
    """Fail fast and clearly if crud-api isn't running, rather than
    halfway through a 60-book run."""
    try:
        response = requests.get(HEALTH_URL, timeout=5)
        if response.status_code != 200:
            raise RuntimeError(f"/health returned {response.status_code}")
    except requests.RequestException as e:
        print(f"ERROR: Cannot reach {HEALTH_URL}")
        print(f"Is the server running? Start it with: uvicorn main:app --reload")
        print(f"Details: {e}")
        sys.exit(1)


def load_books(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def enrich_one(book: dict) -> dict:
    """Sends one book to /enrich. Extra scraper fields (product_url,
    price_text, availability_text, source_page, fetched_at) are ignored
    by the endpoint's schema - only title, description, rating_text,
    and price_gbp are read, but we keep the full original record in
    the output for traceability."""
    payload = {
        "title": book["title"],
        "description": book.get("description"),
        "rating_text": book["rating_text"],
        "price_gbp": book["price_gbp"],
    }

    try:
        response = requests.post(ENRICH_URL, json=payload, timeout=120)
    except requests.RequestException as e:
        return {**book, "enrichment_error": f"request failed: {e}"}

    if response.status_code != 200:
        return {**book, "enrichment_error": f"HTTP {response.status_code}: {response.text}"}

    enrichment = response.json()
    return {**book, "enrichment": enrichment}


def main():
    parser = argparse.ArgumentParser(description="Enrich scraped books via POST /enrich")
    parser.add_argument("books_path", help="Path to the scraper's books.json")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N books (for testing)")
    args = parser.parse_args()

    check_server_is_up()

    books = load_books(args.books_path)
    if args.limit:
        books = books[: args.limit]

    print(f"Loaded {len(books)} books from {args.books_path}")
    print(f"Sending each to {ENRICH_URL}\n")

    results = []
    error_count = 0

    for i, book in enumerate(books, start=1):
        result = enrich_one(book)
        results.append(result)

        if "enrichment_error" in result:
            error_count += 1
            print(f"[{i}/{len(books)}] FAILED: {book['title'][:50]} -> {result['enrichment_error'][:80]}")
        else:
            category = result["enrichment"]["category"]
            print(f"[{i}/{len(books)}] OK: {book['title'][:50]} -> {category}")

        time.sleep(DELAY_BETWEEN_CALLS)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n{'=' * 50}")
    print(f"Done. {len(books) - error_count}/{len(books)} enriched successfully.")
    print(f"Results saved to {OUTPUT_PATH}")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
