What it does: Classifies a scraped book record into a category, writes a
one-sentence summary, and flags quality issues.

Input: {
  "title": "string",
  "description": "string or null",
  "rating_text": "string",
  "price_gbp": number
}

Output: {
  "category": one of [fiction, non-fiction, mystery, children, self-help, other],
  "summary": "one sentence, max 20 words",
  "quality_flags": list of zero or more [description_too_short, title_unclear,
                   missing_description, low_confidence],
  "confidence": 0.0–1.0
}

It must never: invent a category outside the list · return free text in
category · add extra fields · guess when unsure

When unsure: return category "other" with confidence below 0.5 and add
"low_confidence" to quality_flags