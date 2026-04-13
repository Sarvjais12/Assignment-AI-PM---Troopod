# AI Landing Page Personalizer — Troopod AI PM Assignment

> **Live Demo → [huggingface.co/spaces/Sarvjais12/troopod_AI-PM](https://huggingface.co/spaces/Sarvjais12/troopod_AI-PM)**

Upload an ad creative and a landing page URL. Get a CRO-optimized, personalized version of that page — with PM reasoning and a Scent Trail Score.

---

## What it does

| Input | Output |
|---|---|
| Ad creative image (upload) | Personalized hero headline |
| Landing page URL | Personalized subheadline + CTA |
| | PM reasoning for each change |
| | Scent Trail Score (1–10) |
| | Live HTML page preview |

The tool does **not** generate a new page from scratch. It reads the existing page's hero section and rewrites only the above-the-fold copy to create a message match ("scent trail") between the ad and the landing page — a core CRO principle.

---

## System flow

```
User uploads ad image + landing page URL
        │
        ▼
1. SCRAPE   Jina Reader fetches the page (bypasses Cloudflare/WAF)
        │
        ▼
2. EXTRACT  BeautifulSoup pulls only hero elements:
            H1/H2/H3 · button/link text · meta description · first paragraph
        │
        ▼
3. ENCODE   PIL resizes ad image to 800×800, converts to JPEG, base64-encodes
        │
        ▼
4. LLM CALL Groq API (Llama 4 Scout vision model)
            Single message: image + extracted hero text
            System prompt: CRO PM persona, strict JSON output
        │
        ▼
5. VALIDATE JSON schema check — 6 required keys, correct types, no empty strings
            If invalid → auto-retry once with specific error list
        │
        ▼
6. RENDER   Tab 1: Strategy & PM reasoning
            Tab 2: Copy comparison (before vs after)
            Tab 3: Live HTML preview (sandboxed iframe)
```

---

## Key design decisions

### Why Jina Reader, not requests.get()?
Direct HTTP requests are blocked by Cloudflare/WAF on most landing pages. Jina Reader runs a headless browser on their end and returns structured content. Results are cached per URL to avoid redundant scrapes.

### Why BeautifulSoup extraction, not raw text truncation?
Raw truncation at N characters randomly cuts off CTAs and key headings. BeautifulSoup surgically extracts only the signal: headings, buttons, meta description. This keeps token usage low while preserving the elements that matter most for CRO.

### Why Groq + Llama 4 Scout?
- **Free tier**: 14,400 requests/day vs Gemini's 5 RPM — usable for real development
- **Speed**: Sub-2s responses on Groq's LPU hardware
- **Vision**: Llama 4 Scout natively reads image + text in one call
- **JSON reliability**: Strong instruction-following at temperature=0.2

### Why a sandboxed iframe for the preview?
`gr.HTML()` renders inside Gradio's DOM, which means the parent page's dark-theme CSS bleeds into the preview and makes it unreadable. Encoding the HTML as a `data:text/html;base64,...` iframe creates a fully isolated document that the parent CSS cannot penetrate.

---

## How edge cases are handled

| Assignment requirement | How this system handles it |
|---|---|
| **Hallucinations** | JSON schema validation checks all 6 keys for correct type and non-empty values. Auto-retries once with a specific error list. |
| **Inconsistent outputs** | Temperature=0.2 keeps the model deterministic. Session-level cache returns the same result for the same ad + URL pair. |
| **Broken UI** | Preview runs inside a sandboxed iframe — isolated from Gradio's CSS. Input validation catches empty fields and bad URLs before any API call. |
| **Random changes** | Structured JSON output format is enforced by the system prompt and validated by code. The LLM cannot return free-form text. |

---

## Assumptions made

1. **Ad creative is an image file** (not a URL to a video ad). The brief mentioned "link/upload" — I assumed image upload for the prototype since video requires a separate transcription step.
2. **"Personalized page" means the hero section**, not the full page. Rewriting the entire page copy from a single ad would be over-engineering for a CRO use case — above-the-fold is where conversion happens.
3. **Scent Trail Score is a proxy metric**. In production this would be validated against actual A/B test conversion data. For the prototype, the LLM scores its own output against a rubric.

---

## Files

| File | Purpose |
|---|---|
| `app.py` | Full application — scraping, LLM call, validation, UI |
| `requirements.txt` | Python dependencies |
| `README.md` | This file |
| `SYSTEM_DOC.md` | Detailed technical doc (mirrors the Google Doc submission) |

---

## Setup (run locally)

```bash
git clone https://github.com/Sarvjais12/troopod_AI-PM
cd troopod_AI-PM
pip install -r requirements.txt

# Set your Groq API key
export GROQ_API_KEY=your_key_here   # get free key at console.groq.com

python app.py
```

---

## Stack

- **Frontend**: Gradio 4.x
- **Scraping**: Jina Reader API + BeautifulSoup4
- **Vision LLM**: Groq API — `meta-llama/llama-4-scout-17b-16e-instruct`
- **Image processing**: Pillow
- **Hosting**: Hugging Face Spaces
