"""
Eval runner for POST /enrich.

Runs all cases in evals/cases.json against the live server, compares
the returned category to expected_category, and prints a score.

This does not grade summary quality, confidence calibration, or
quality_flags correctness - only category match. That's a known,
stated scope limit, not an oversight: category is the one field with
an objectively checkable right answer per case. The others are softer
judgments better caught by manual review (see the calibration issues
already documented from Stage 2/3 testing).
"""

import json
import sys
import time
import requests

CASES_PATH = "evals/cases.json"
ENDPOINT = "http://localhost:8000/enrich"
PROMPT_VERSION = "enrich-v1"  # keep in sync with src/llm/client.py


def load_cases() -> list[dict]:
    with open(CASES_PATH, encoding="utf-8") as f:
        return json.load(f)


def run_case(case: dict) -> dict:
    """Returns a result dict: pass/fail, actual vs expected, any error."""
    try:
        response = requests.post(ENDPOINT, json=case["input"], timeout=60)
    except requests.RequestException as e:
        return {
            "id": case["id"],
            "case_type": case["case_type"],
            "passed": False,
            "expected": case["expected_category"],
            "actual": None,
            "error": f"request failed: {e}",
        }

    if response.status_code != 200:
        return {
            "id": case["id"],
            "case_type": case["case_type"],
            "passed": False,
            "expected": case["expected_category"],
            "actual": None,
            "error": f"HTTP {response.status_code}: {response.text}",
        }

    data = response.json()
    actual = data.get("category")
    passed = actual == case["expected_category"]

    return {
        "id": case["id"],
        "case_type": case["case_type"],
        "passed": passed,
        "expected": case["expected_category"],
        "actual": actual,
        "error": None,
    }


def main():
    cases = load_cases()
    results = []

    print(f"Running {len(cases)} eval cases against {ENDPOINT}")
    print(f"Prompt version: {PROMPT_VERSION}\n")

    for case in cases:
        result = run_case(case)
        results.append(result)

        status = "PASS" if result["passed"] else "FAIL"
        line = f"[{status}] Case {result['id']} ({result['case_type']}): expected={result['expected']}, actual={result['actual']}"
        if result["error"]:
            line += f" | error: {result['error']}"
        print(line)

        time.sleep(0.2)  # small pause between calls, not strictly required but polite to the local server

    passed_count = sum(1 for r in results if r["passed"])
    total = len(results)

    print(f"\n{'=' * 50}")
    print(f"Score: {passed_count}/{total}")
    print(f"Prompt version: {PROMPT_VERSION}")
    print(f"{'=' * 50}")

    if passed_count < total:
        print("\nFailed cases:")
        for r in results:
            if not r["passed"]:
                print(f"  - Case {r['id']} ({r['case_type']}): expected {r['expected']}, got {r['actual']}")

    sys.exit(0 if passed_count == total else 1)


if __name__ == "__main__":
    main()