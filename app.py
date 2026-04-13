import gradio as gr
import requests
import os
import json
import time
import base64
import html as html_lib
from bs4 import BeautifulSoup
from PIL import Image
import io

# ─────────────────────────────────────────────
#  CACHE  (saves API calls during repeated tests)
# ─────────────────────────────────────────────
_scrape_cache = {}   # url → raw html
_result_cache = {}   # (url, img_hash) → full result dict


# ─────────────────────────────────────────────
#  SCRAPING  (Jina Reader → BeautifulSoup hero extract)
# ─────────────────────────────────────────────
def scrape_url(url: str) -> tuple[str, str]:
    if url in _scrape_cache:
        raw_html = _scrape_cache[url]
    else:
        try:
            jina_url = f"https://r.jina.ai/{url}"
            resp = requests.get(
                jina_url,
                headers={"Accept": "application/json", "X-Return-Format": "html"},
                timeout=20,
            )
            if resp.status_code != 200:
                return f"[SCRAPE ERROR] Status {resp.status_code}", ""
            data = resp.json()
            raw_html = data.get("data", {}).get("content", "")
            if not raw_html:
                resp2 = requests.get(jina_url, headers={"Accept": "application/json"}, timeout=20)
                raw_html = resp2.json().get("data", {}).get("content", "")
            _scrape_cache[url] = raw_html
        except Exception as e:
            return f"[SCRAPE ERROR] {str(e)}", ""

    if not raw_html or len(raw_html) < 100:
        return "[SCRAPE ERROR] Page returned too little content.", ""

    try:
        soup = BeautifulSoup(raw_html, "html.parser")
        hero_parts = []
        for tag in ["h1", "h2", "h3"]:
            for el in soup.find_all(tag)[:3]:
                text = el.get_text(strip=True)
                if text:
                    hero_parts.append(f"[{tag.upper()}] {text}")
        for el in soup.find_all(["button", "a"], limit=10):
            text = el.get_text(strip=True)
            if text and 2 < len(text) < 60:
                hero_parts.append(f"[CTA] {text}")
        meta = soup.find("meta", attrs={"name": "description"})
        if meta and meta.get("content"):
            hero_parts.append(f"[META] {meta['content']}")
        p = soup.find("p")
        if p:
            hero_parts.append(f"[P] {p.get_text(strip=True)[:200]}")
        extracted = "\n".join(hero_parts) if hero_parts else raw_html[:1500]
    except Exception:
        extracted = raw_html[:1500]

    return extracted, raw_html


# ─────────────────────────────────────────────
#  IMAGE UTILITIES
# ─────────────────────────────────────────────
def image_to_base64(image_path: str) -> tuple[str, str]:
    img = Image.open(image_path).convert("RGB")
    img.thumbnail((800, 800))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return b64, "image/jpeg"


def quick_hash(image_path: str) -> str:
    s = os.stat(image_path)
    return f"{s.st_size}_{s.st_mtime}"


# ─────────────────────────────────────────────
#  GROQ API CALL  (with retry)
# ─────────────────────────────────────────────
def call_groq(messages: list, model="meta-llama/llama-4-scout-17b-16e-instruct",
              max_tokens=1200, temperature=0.2, retries=3) -> str:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not set in Hugging Face Secrets.")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}

    for attempt in range(retries):
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers, json=payload, timeout=30,
            )
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            elif resp.status_code == 429:
                time.sleep(int(resp.headers.get("Retry-After", 10)))
            elif resp.status_code in (500, 503):
                time.sleep(5)
            else:
                raise RuntimeError(f"Groq API error {resp.status_code}: {resp.text[:300]}")
        except requests.exceptions.Timeout:
            if attempt == retries - 1:
                raise RuntimeError("Groq API timed out after 3 attempts.")
            time.sleep(5)
    raise RuntimeError("Groq API failed after all retries.")


# ─────────────────────────────────────────────
#  JSON VALIDATION  (hallucination guard)
# ─────────────────────────────────────────────
REQUIRED_KEYS = {
    "ad_analysis": str, "original_copy": dict, "personalized_page": dict,
    "pm_reasoning": list, "scent_score": int, "scent_reason": str,
}
REQUIRED_PAGE_KEYS = ["new_headline", "new_subheadline", "new_cta"]
REQUIRED_ORIG_KEYS = ["headline", "cta"]


def validate_result(data: dict) -> list[str]:
    errors = []
    for key, typ in REQUIRED_KEYS.items():
        if key not in data:
            errors.append(f"Missing key: {key}")
        elif not isinstance(data[key], typ):
            errors.append(f"Wrong type for {key}: expected {typ.__name__}")
        elif isinstance(data[key], str) and not data[key].strip():
            errors.append(f"Empty string: {key}")
    for k in REQUIRED_PAGE_KEYS:
        if not data.get("personalized_page", {}).get(k, "").strip():
            errors.append(f"personalized_page.{k} is missing or empty")
    for k in REQUIRED_ORIG_KEYS:
        if not data.get("original_copy", {}).get(k, "").strip():
            errors.append(f"original_copy.{k} is missing or empty")
    if isinstance(data.get("scent_score"), int) and not (1 <= data["scent_score"] <= 10):
        errors.append("scent_score must be between 1 and 10")
    return errors


def safe_parse_json(raw_text: str) -> dict:
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.rsplit("```", 1)[0]
    return json.loads(text.strip())


# ─────────────────────────────────────────────
#  HTML PREVIEW BUILDER
#
#  THE FIX: We encode the entire preview as a base64
#  data URI and serve it inside a sandboxed <iframe>.
#  This completely isolates it from Gradio's dark-theme
#  CSS, which was bleeding in and making everything
#  unreadable when using gr.HTML() directly.
# ─────────────────────────────────────────────
def build_preview(result: dict, original_url: str) -> str:
    page  = result.get("personalized_page", {})
    orig  = result.get("original_copy", {})
    score = result.get("scent_score", "?")

    score_color = (
        "#22c55e" if isinstance(score, int) and score >= 7 else
        "#f59e0b" if isinstance(score, int) and score >= 5 else
        "#ef4444"
    )

    # Escape every string — prevents broken HTML from AI output
    headline       = html_lib.escape(page.get("new_headline", ""))
    subheadline    = html_lib.escape(page.get("new_subheadline", ""))
    cta            = html_lib.escape(page.get("new_cta", ""))
    old_h          = html_lib.escape(orig.get("headline", "N/A"))
    old_cta        = html_lib.escape(orig.get("cta", "N/A"))
    safe_url       = html_lib.escape(original_url)
    reasoning_html = "".join(
        f'<div class="reason-item">{html_lib.escape(str(r))}</div>'
        for r in result.get("pm_reasoning", [])
    )

    inner_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #f8fafc !important;
    color: #1e293b !important;
  }}
  .topbar {{
    background: #1e293b; color: #f8fafc !important;
    padding: 10px 24px;
    display: flex; align-items: center; justify-content: space-between;
    font-size: 13px;
  }}
  .topbar a {{ color: #94a3b8; text-decoration: none; font-size: 12px; }}
  .score-pill {{
    background: {score_color}22; color: {score_color} !important;
    border: 1px solid {score_color}66;
    border-radius: 99px; padding: 3px 14px;
    font-size: 13px; font-weight: 700;
  }}
  .hero {{
    background: linear-gradient(135deg, #1e40af 0%, #3b82f6 100%);
    padding: 80px 24px; text-align: center;
  }}
  .hero h1 {{
    font-size: clamp(26px, 4vw, 48px); font-weight: 700;
    margin-bottom: 18px; line-height: 1.2;
    color: #ffffff !important;
  }}
  .hero p {{
    font-size: clamp(15px, 2vw, 20px);
    color: rgba(255,255,255,0.92) !important;
    max-width: 600px; margin: 0 auto 36px; line-height: 1.6;
  }}
  .cta-btn {{
    display: inline-block; background: #ffffff; color: #1e40af !important;
    font-size: 17px; font-weight: 700; padding: 16px 40px;
    border-radius: 8px; cursor: pointer; border: none;
    box-shadow: 0 4px 24px rgba(0,0,0,0.2);
  }}
  .section {{
    max-width: 860px; margin: 40px auto 0; padding: 0 20px 40px;
  }}
  .section h2 {{
    font-size: 18px; font-weight: 600; margin-bottom: 20px;
    color: #475569 !important;
  }}
  .comp-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
  .comp-card {{
    background: #ffffff !important; border-radius: 12px;
    padding: 20px; border: 1px solid #e2e8f0;
  }}
  .comp-card.new {{ border-color: #3b82f6; border-width: 2px; }}
  .comp-label {{
    font-size: 11px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.07em; margin-bottom: 12px;
  }}
  .comp-label.orig {{ color: #94a3b8; }}
  .comp-label.new  {{ color: #3b82f6; }}
  .comp-card p {{
    font-size: 14px; color: #475569 !important;
    margin-bottom: 8px; line-height: 1.5;
  }}
  .comp-card strong {{ color: #1e293b !important; }}
  .reason-item {{
    background: #ffffff !important;
    border-left: 4px solid #3b82f6;
    border-radius: 0 8px 8px 0;
    padding: 14px 18px; margin-bottom: 10px;
    font-size: 14px; color: #475569 !important; line-height: 1.6;
    border-top: 1px solid #e2e8f0;
    border-right: 1px solid #e2e8f0;
    border-bottom: 1px solid #e2e8f0;
  }}
  @media (max-width: 600px) {{ .comp-grid {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>

<div class="topbar">
  <span>AI CRO Preview &mdash; <a href="{safe_url}" target="_blank">{safe_url}</a></span>
  <span class="score-pill">Scent Trail Score: {score}/10</span>
</div>

<div class="hero">
  <h1>{headline}</h1>
  <p>{subheadline}</p>
  <button class="cta-btn">{cta}</button>
</div>

<div class="section">
  <h2>Before vs After</h2>
  <div class="comp-grid">
    <div class="comp-card">
      <div class="comp-label orig">Original copy</div>
      <p><strong>Headline:</strong> {old_h}</p>
      <p><strong>CTA:</strong> {old_cta}</p>
    </div>
    <div class="comp-card new">
      <div class="comp-label new">Personalized copy</div>
      <p><strong>Headline:</strong> {headline}</p>
      <p><strong>Subheadline:</strong> {subheadline}</p>
      <p><strong>CTA:</strong> {cta}</p>
    </div>
  </div>
</div>

<div class="section">
  <h2>PM Reasoning</h2>
  {reasoning_html}
</div>

</body>
</html>"""

    encoded = base64.b64encode(inner_html.encode("utf-8")).decode("utf-8")
    return (
        f'<iframe src="data:text/html;base64,{encoded}" '
        f'style="width:100%; height:720px; border:none; border-radius:8px; display:block;" '
        f'sandbox="allow-same-origin allow-popups"></iframe>'
    )


# ─────────────────────────────────────────────
#  SYSTEM PROMPT
# ─────────────────────────────────────────────
SYSTEM_PROMPT = """You are an elite Conversion Rate Optimization (CRO) Product Manager.

You are given:
1. An ad creative image
2. Extracted hero elements from the landing page the ad points to

Your task: Rewrite the landing page's hero section to create a perfect "scent trail" from the ad.
- Do NOT invent a completely new page.
- Keep the brand voice; only sharpen the message match.
- The new copy must directly mirror the ad's offer, pain point, and tone.

ALSO assign a "scent_score" from 1-10 measuring how well the new copy matches the ad.
- 9-10: Near-perfect mirror.
- 7-8: Strong match, minor gaps.
- 5-6: Decent but generic.
- 1-4: Weak or off-target.

Respond ONLY with valid JSON. No preamble, no backticks, no explanation outside the JSON.

{
  "ad_analysis": "One paragraph: core offer, target audience, emotional hook of the ad.",
  "original_copy": {
    "headline": "The main H1 extracted from the page",
    "cta": "The primary CTA button text"
  },
  "personalized_page": {
    "new_headline": "Your CRO-optimized headline (mirrors the ad core message)",
    "new_subheadline": "Your subheadline (addresses the ad pain point and expands the benefit)",
    "new_cta": "Your CTA (action-oriented, low-friction, consistent with ad)"
  },
  "pm_reasoning": [
    "Headline change: [what you changed and exactly why it improves message match]",
    "Subheadline change: [same format]",
    "CTA change: [same format]"
  ],
  "scent_score": 8,
  "scent_reason": "One sentence explaining the score."
}"""

RETRY_PROMPT_SUFFIX = """
IMPORTANT: Your previous response was missing required fields or had empty values.
Fill in EVERY field. Do not leave any field blank or null.
Return ONLY valid JSON with all required keys populated."""


# ─────────────────────────────────────────────
#  MAIN PIPELINE
# ─────────────────────────────────────────────
def personalize_landing_page(ad_image, landing_page_url, progress=gr.Progress()):
    if not ad_image:
        return "⚠️ Please upload an ad creative image.", "", "", ""
    if not landing_page_url or not landing_page_url.startswith("http"):
        return "⚠️ Please enter a valid URL starting with http:// or https://", "", "", ""

    progress(0.15, desc="Scraping landing page...")
    hero_text, raw_html = scrape_url(landing_page_url)

    if hero_text.startswith("[SCRAPE ERROR]"):
        return (
            f"**Scraping failed:** {hero_text}\n\n"
            "**Tip:** Some sites block bots. Try the root domain without subpaths.",
            "", "", ""
        )

    progress(0.30, desc="Preparing ad image...")
    img_b64, img_type = image_to_base64(ad_image)

    cache_key = (landing_page_url, quick_hash(ad_image))
    if cache_key in _result_cache:
        progress(1.0, desc="Loaded from cache!")
        return _format_outputs(_result_cache[cache_key], landing_page_url)

    user_content = [
        {"type": "image_url", "image_url": {"url": f"data:{img_type};base64,{img_b64}"}},
        {"type": "text", "text": (
            f"Extracted hero elements from {landing_page_url}:\n\n{hero_text}\n\n"
            "Analyze the ad image above and generate the personalized copy as instructed."
        )}
    ]
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": user_content},
    ]

    progress(0.55, desc="Generating personalized copy...")
    result = None
    raw_response = ""

    for attempt in range(2):
        try:
            raw_response = call_groq(messages, max_tokens=1200, temperature=0.2)
            result = safe_parse_json(raw_response)
            errors = validate_result(result)
            if not errors:
                break
            progress(0.70, desc="Fixing incomplete response...")
            messages.append({"role": "assistant", "content": raw_response})
            messages.append({"role": "user", "content": f"Issues: {'; '.join(errors)}." + RETRY_PROMPT_SUFFIX})
        except json.JSONDecodeError:
            if attempt == 1:
                return (f"❌ Malformed JSON twice.\n\n```\n{raw_response[:600]}\n```", "", "", "")
            messages.append({"role": "assistant", "content": raw_response})
            messages.append({"role": "user", "content": "Response was not valid JSON." + RETRY_PROMPT_SUFFIX})
        except Exception as e:
            return f"❌ API Error: {str(e)}", "", "", ""

    if result is None:
        return "❌ Could not generate a valid response after 2 attempts.", "", "", ""

    _result_cache[cache_key] = result
    progress(1.0, desc="Done!")
    return _format_outputs(result, landing_page_url)


def _format_outputs(result: dict, url: str):
    score = result.get("scent_score", "?")
    emoji = "🟢" if isinstance(score, int) and score >= 7 else "🟡" if isinstance(score, int) and score >= 5 else "🔴"

    strategy = (
        f"### 🎯 Ad Analysis\n{result.get('ad_analysis', '')}\n\n"
        f"### {emoji} Scent Trail Score: **{score}/10**\n{result.get('scent_reason', '')}\n\n"
        f"### 💡 PM Reasoning\n" + "\n".join(f"- {r}" for r in result.get("pm_reasoning", []))
    )
    orig   = result.get("original_copy", {})
    before = f"**Headline:** {orig.get('headline', 'N/A')}\n\n**CTA:** {orig.get('cta', 'N/A')}"
    page   = result.get("personalized_page", {})
    after  = (
        f"**Headline:** {page.get('new_headline', '')}\n\n"
        f"**Subheadline:** {page.get('new_subheadline', '')}\n\n"
        f"**CTA:** {page.get('new_cta', '')}"
    )
    return strategy, before, after, build_preview(result, url)


# ─────────────────────────────────────────────
#  GRADIO UI
# ─────────────────────────────────────────────
with gr.Blocks(
    theme=gr.themes.Soft(),
    title="AI CRO Landing Page Personalizer",
    css="footer { display: none !important; }"
) as demo:

    gr.Markdown("""# 🚀 AI Landing Page Personalizer
Upload an ad creative and a landing page URL to generate a CRO-optimized, personalized page preview.
> **Powered by Groq + Llama 4 Scout** — fast, free, vision-capable.
""")

    with gr.Row():
        with gr.Column(scale=1):
            ad_input    = gr.Image(type="filepath", label="1. Upload Ad Creative", height=260)
            url_input   = gr.Textbox(label="2. Enter Landing Page URL", placeholder="https://www.example.com")
            submit_btn  = gr.Button("✨ Generate Personalized Page", variant="primary", size="lg")
            gr.Markdown("_**Tip:** If scraping fails, try the root domain without subpaths._")

    gr.Markdown("---")

    with gr.Tabs():
        with gr.Tab("📊 Strategy & Reasoning"):
            strategy_output = gr.Markdown()
        with gr.Tab("📝 Copy Comparison"):
            with gr.Row():
                with gr.Column():
                    gr.Markdown("#### Original 'Above the Fold'")
                    before_output = gr.Markdown()
                with gr.Column():
                    gr.Markdown("#### ✨ Personalized Copy")
                    after_output = gr.Markdown()
        with gr.Tab("🖥️ Live Page Preview"):
            gr.Markdown("_Sandboxed preview — isolated from the app's dark theme._")
            html_preview_output = gr.HTML()

    submit_btn.click(
        fn=personalize_landing_page,
        inputs=[ad_input, url_input],
        outputs=[strategy_output, before_output, after_output, html_preview_output],
    )

    gr.Markdown("""---
### How it works
1. **Scrape** — Jina Reader extracts the page, BeautifulSoup isolates hero elements (H1/H2/CTAs/meta)
2. **Analyze** — Llama 4 Scout (vision) reads your ad image and hero text together
3. **Generate** — Produces new headline, subheadline, and CTA with PM reasoning
4. **Validate** — Schema check catches hallucinations; auto-retries once if needed
5. **Score** — Scent Trail Score (1–10) measures ad ↔ page message match
6. **Preview** — Sandboxed iframe; fully isolated from Gradio's dark theme
""")

if __name__ == "__main__":
    demo.launch()