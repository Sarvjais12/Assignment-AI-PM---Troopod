import gradio as gr
import google.generativeai as genai
import requests
import os
import json
import time

def scrape_url(url):
    """
    Uses Jina Reader to safely extract text from any URL, 
    bypassing most WAF/Cloudflare bot-blockers.
    """
    try:
        jina_url = f"https://r.jina.ai/{url}"
        headers = {"Accept": "application/json"}
        response = requests.get(jina_url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            return data.get("data", {}).get("content", "Could not extract text.")
        else:
            return f"Error: Status code {response.status_code}"
    except Exception as e:
        return f"Error scraping URL: {str(e)}"

def personalize_landing_page(ad_image, landing_page_url, progress=gr.Progress()):
    if not ad_image or not landing_page_url:
        return "⚠️ Please upload an ad image and enter a URL.", "", ""

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return "⚠️ GEMINI_API_KEY secret is missing in Hugging Face.", "", ""
    
    genai.configure(api_key=api_key)

    try:
        # STEP 1: Scrape the Live URL
        progress(0.2, desc="Scraping live URL via Jina Reader...")
        website_content = scrape_url(landing_page_url)
        
        if "Error" in website_content:
            return f"❌ Failed to scrape URL. {website_content}", "", ""

        # OPTIMIZATION 1: Aggressive Truncation 
        # Cut down to 1200 chars to ensure lightning-fast API response and avoid 504s
        website_content = website_content[:1200] 

        # OPTIMIZATION 2: Image Compression
        progress(0.4, desc="Optimizing Image Payload...")
        from PIL import Image
        img = Image.open(ad_image)
        # Shrink the image to max 800x800. Gemini vision still reads it perfectly, 
        # but it takes 1/10th the bandwidth and processing power.
        img.thumbnail((800, 800)) 

        # STEP 2: Configure Gemini 2.5 Flash
        progress(0.5, desc="Analyzing & Formulating CRO Strategy...")
        model = genai.GenerativeModel(
            model_name='gemini-2.5-flash',
            generation_config=genai.GenerationConfig(
                temperature=0.2, 
                response_mime_type="application/json", 
            )
        )

        system_prompt = """
        You are an elite Conversion Rate Optimization (CRO) Product Manager. 
        You are given an Ad Creative image and the Markdown text of a current landing page.
        
        Your task: Enhance the existing page copy to match the ad's specific offer, tone, and audience.
        DO NOT invent a completely new page. You must use the existing structure but rewrite the Hero Headline, Subheadline, and primary Call to Action (CTA) to create a perfect "Scent Trail" from the ad.
        
        Output strictly in this JSON format:
        {
            "ad_analysis": "Briefly describe the core offer and target audience of the ad.",
            "original_copy": {
                "headline": "Extract what looks like the main H1 from the website text",
                "cta": "Extract the primary CTA button text"
            },
            "personalized_page": {
                "new_headline": "Your CRO optimized headline",
                "new_subheadline": "Your CRO optimized subheadline",
                "new_cta": "Your optimized CTA"
            },
            "pm_reasoning": [
                "Change 1: Why you made it",
                "Change 2: Why you made it"
            ]
        }
        """
        
        user_prompt = f"Here is the text scraped from the landing page: \n\n{website_content}"
        
        # OPTIMIZATION 3: Paced Retry Loop (Respecting the 5 RPM Limit)
        max_retries = 2
        response = None
        
        for attempt in range(max_retries):
            try:
                progress(0.7, desc=f"Generating Content (Attempt {attempt + 1})...")
                response = model.generate_content([system_prompt, user_prompt, img])
                break 
            except Exception as api_error:
                if attempt == max_retries - 1:
                    raise api_error 
                print(f"API Timeout/Rate Limit. Retrying... {str(api_error)}")
                # Sleep for 15 seconds to let the 5-requests-per-minute quota cool down
                time.sleep(15) 
        
        # Parse the JSON
        result = json.loads(response.text)
        
        progress(1.0, desc="Done!")
        
        # FORMAT THE OUTPUTS FOR THE UI
        strategy = f"### 🎯 Ad Analysis\n{result.get('ad_analysis')}\n\n### 💡 PM Reasoning\n"
        for reason in result.get('pm_reasoning', []):
            strategy += f"- {reason}\n"
            
        before = f"**Headline:** {result.get('original_copy', {}).get('headline')}\n\n**CTA:** {result.get('original_copy', {}).get('cta')}"
        
        after = f"**Headline:** {result.get('personalized_page', {}).get('new_headline')}\n\n**Subheadline:** {result.get('personalized_page', {}).get('new_subheadline')}\n\n**CTA:** {result.get('personalized_page', {}).get('new_cta')}"
        
        return strategy, before, after

    except Exception as e:
        return f"❌ System Error: {str(e)}", "", ""

# --- Gradio UI Layout ---
with gr.Blocks(theme=gr.themes.Soft(), title="AI CRO Personalizer") as demo:
    gr.Markdown("# 🚀 AI Landing Page Personalizer")
    gr.Markdown("Upload an ad creative and paste your landing page URL to generate a CRO-optimized experience.")
    
    with gr.Row():
        with gr.Column():
            ad_input = gr.Image(type="filepath", label="1. Upload Ad Creative")
            url_input = gr.Textbox(label="2. Enter Landing Page URL", placeholder="https://www.example.com")
            submit_btn = gr.Button("Generate Personalized Page", variant="primary")
            
    gr.Markdown("---")
    
    with gr.Row():
        strategy_output = gr.Markdown(label="Strategy & Reasoning")
        
    gr.Markdown("### 📊 Page Content Comparison")
    with gr.Row():
        with gr.Column():
            gr.Markdown("#### Original 'Above the Fold' Copy")
            before_output = gr.Markdown()
        with gr.Column():
            gr.Markdown("#### ✨ Personalized Copy")
            after_output = gr.Markdown()

    submit_btn.click(
        fn=personalize_landing_page,
        inputs=[ad_input, url_input],
        outputs=[strategy_output, before_output, after_output]
    )

if __name__ == "__main__":
    demo.launch()