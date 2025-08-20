from __future__ import annotations
import json, re, os, time
from typing import Any, Dict, List

from google import genai
from google.genai.types import GenerateContentConfig

# -----------------------------
# CONFIG
# -----------------------------
URLS = [
    "https://www.trendyol.com/iphone-15-cep-telefonu-x-c103498-a292-v1218519",
    "https://www.hepsiburada.com/iphone-15-iphone-ios-telefonlar-xc-60005202-t3",
    "https://www.teknosa.com/iphone-15-c-100001001025",
]

MODEL = "gemini-2.5-flash"
TOOLS = [{"url_context": {}}]  # istersen {"google_search": {}} da eklenebilir

# Çıktılar
OUT_DIR = "outputs"
os.makedirs(OUT_DIR, exist_ok=True)

ANALYSIS_PROMPT_TEMPLATE = """
You are an SEO & e-commerce category page auditor.

Read this CATEGORY PAGE URL with the URL Context tool:
{url}

Return TWO parts:

PART 1 — MARKDOWN ANALYSIS (concise; <= 450 words)
Sections:
- Analyzed URL
- SEO structure: title tag (verbatim if visible), meta description (verbatim if visible), H1, notable H2/H3s, canonical (if detectable), robots/indexability signals.
- Faceted navigation & filters: list main filters (e.g., brand, storage, color, seller, price, rating, shipping, campaign). Note if multi-select, counts, and “clear all”.
- Sorting & pagination: available sort options (e.g., popularity, price asc/desc, newest); show pagination style (classic pages vs infinite scroll); show page-size if visible.
- Product list cards: fields present on cards (name, price, old price/discount, rating, reviewCount, seller/marketplace badge, shipping badge, installment info); note missing ones.
- Internal links: breadcrumbs items; key internal link modules (popular brands, related searches, promos).
- Structured data: detect JSON-LD / microdata types relevant to category (BreadcrumbList, ItemList, Product on cards). Mention found fields if evident.
- UX & content notes: trust signals, boilerplate text, legal info, FAQ, filters UX strengths/weaknesses.
- Gaps & opportunities: 8 bullets to outperform this page for “iPhone 15” category intent (SEO + CRO).

Use bullet points and be specific. If something is not visible in fetched HTML, write "not stated".

PART 2 — JSON SUMMARY (valid JSON only)
Provide a compact JSON object with this schema:
{{
  "url": "{url}",
  "title_tag": "string|null",
  "meta_description": "string|null",
  "h1": "string|null",
  "canonical": "string|null",
  "robots_indexable": "yes|no|unknown",
  "sort_options": ["..."],
  "pagination_type": "pages|infinite|unknown",
  "page_size": "number|null",
  "filters": ["brand","storage","color","price","rating","seller","shipping","campaign","other..."],
  "product_card_fields": ["name","price","old_price","discount","rating","reviewCount","seller","badges","installment","shipping","other..."],
  "breadcrumbs": ["..."],
  "structured_data_types": ["BreadcrumbList","ItemList","Product","Other..."],
  "internal_links_modules": ["popular_brands","related_searches","promos","none"],
  "notes": "one-sentence key observation"
}}

Rules:
- DO NOT invent. If absent, use null or "unknown" or empty lists.
- The JSON must be the last JSON object in your message (no markdown fences around it).
"""

def extract_last_json_block(text: str) -> Dict[str, Any] | None:
    last_open = text.rfind("{")
    if last_open == -1:
        return None
    last_close = text.rfind("}")
    if last_close == -1 or last_close < last_open:
        return None
    candidate = text[last_open:last_close+1]
    try:
        return json.loads(candidate)
    except Exception:
        candidate = candidate.strip("`").strip()
        try:
            return json.loads(candidate)
        except Exception:
            return None

def analyze_url(client: genai.Client, url: str) -> Dict[str, Any]:
    prompt = ANALYSIS_PROMPT_TEMPLATE.format(url=url)
    resp = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=GenerateContentConfig(tools=TOOLS),
    )

    text_out = resp.text or ""
    usage = getattr(resp, "usage_metadata", None)
    meta = getattr(resp.candidates[0], "url_context_metadata", None)

    safe_url = re.sub(r'\W+', '_', url)[:80]
    md_path = os.path.join(OUT_DIR, f"analysis_{safe_url}.md")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(text_out)

    j = extract_last_json_block(text_out) or {}
    return {
        "url": url,
        "markdown_path": md_path,
        "json_summary": j,
        "usage": usage,
        "url_context_metadata": str(meta),
    }

def to_csv(rows: List[Dict[str, Any]], path: str):
    import csv
    all_keys = set()
    for r in rows:
        for k in (r.get("json_summary") or {}).keys():
            all_keys.add(k)
    header = ["url", "markdown_path"] + sorted(all_keys)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            js = r.get("json_summary") or {}
            w.writerow([r["url"], r["markdown_path"]] + [js.get(k) for k in sorted(all_keys)])

def main():
    client = genai.Client()
    results = []
    for i, url in enumerate(URLS, 1):
        print(f"[{i}/{len(URLS)}] Analyzing: {url}")
        try:
            res = analyze_url(client, url)
            results.append(res)
            print("  -> markdown:", res["markdown_path"])
        except Exception as e:
            print("  !! error:", e)
        time.sleep(1)

    csv_path = os.path.join(OUT_DIR, "category_comparison.csv")
    to_csv(results, csv_path)
    print("\nDone.")
    print("CSV:", csv_path)
    print("Individual markdown reports are in:", OUT_DIR)

if __name__ == "__main__":
    main()
