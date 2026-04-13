import gradio as gr
import google.generativeai as genai
import os
import json
from typing import Dict, Tuple

# Global state for tracking progress in the UI
agent_status = {}

def get_gemini_model(system_prompt: str):
    """
    Helper function to initialize the Gemini model with specific PM constraints.
    """
    return genai.GenerativeModel(
        model_name='gemini-2.5-flash', # <--- Changed to the current active model!
        system_instruction=system_prompt,
        generation_config=genai.GenerationConfig(
            temperature=0.3, 
            response_mime_type="application/json", 
        )
    )

def run_agent(agent_id: str, agent_name: str, system_prompt: str, user_prompt: str) -> Dict:
    """
    Core function to run a single specialized agent and return structured data.
    """
    # Check for API key before attempting the call
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is missing. Please add it to your Space secrets.")

    genai.configure(api_key=api_key)

    try:
        agent_status[agent_id] = "running"
        
        # Initialize the specific agent persona
        model = get_gemini_model(system_prompt)
        
        # Run the generation
        response = model.generate_content(user_prompt)
        
        # Because we enforced JSON mime-type, we can parse it safely and directly
        result_json = json.loads(response.text)
        
        agent_status[agent_id] = "complete"
        return result_json
        
    except Exception as e:
        agent_status[agent_id] = "error"
        raise Exception(f"{agent_name} failed: {str(e)}")


def agent_1_analyze_ad(ad_description: str) -> Dict:
    """Agent 1: Extracts messaging, tone, and visual elements from the ad."""
    
    system_prompt = "You are an expert ad creative analyst. Your job is to identify the core messaging, emotional tone, and target audience from ad descriptions."
    
    user_prompt = f"""Analyze this ad creative and extract the following using this exact JSON schema:
{{
  "primary_value_prop": "main promise or benefit",
  "emotional_tone": "urgent/aspirational/educational/etc",
  "target_audience": "who this is for",
  "headline": "main headline or hook",
  "cta_text": "call to action text",
  "key_messages": ["key point 1", "key point 2"]
}}

Ad Description:
{ad_description}"""

    return run_agent("agent1", "Ad Creative Analyzer", system_prompt, user_prompt)


def agent_2_analyze_page(landing_page_description: str) -> Dict:
    """Agent 2: Maps current page structure and identifies personalization zones."""
    
    system_prompt = "You are an expert landing page analyst. Map page structure and identify areas where copy can be personalized to match incoming traffic."
    
    user_prompt = f"""Analyze this landing page and extract the following using this exact JSON schema:
{{
  "current_headline": "main headline",
  "current_subheading": "supporting headline",
  "current_cta": "main call to action",
  "current_messaging_focus": "what the page emphasizes",
  "personalization_opportunities": [
    "hero_headline",
    "hero_subheading",
    "primary_cta"
  ]
}}

Landing Page Description:
{landing_page_description}"""

    return run_agent("agent2", "Landing Page Analyzer", system_prompt, user_prompt)


def agent_3_create_strategy(ad_analysis: Dict, page_analysis: Dict) -> Dict:
    """Agent 3: Designs the CRO-aligned personalization strategy."""
    
    system_prompt = "You are a CRO (Conversion Rate Optimization) expert. Design personalization strategies that improve conversion rates by matching landing pages to ad creatives."
    
    user_prompt = f"""Given this ad creative analysis:
{json.dumps(ad_analysis, indent=2)}

And this current landing page analysis:
{json.dumps(page_analysis, indent=2)}

Create a personalization strategy using CRO principles. Use this exact JSON schema:
{{
  "message_match": {{
    "new_page_headline": "...",
    "rationale": "why this improves conversion"
  }},
  "scent_trail": {{
    "page_emphasis": "...",
    "rationale": "..."
  }},
  "cta_optimization": {{
    "new_cta": "...",
    "rationale": "..."
  }},
  "modifications_summary": [
    "High-level change 1",
    "High-level change 2"
  ]
}}"""

    return run_agent("agent3", "Personalization Strategist", system_prompt, user_prompt)


def agent_4_generate_comparison(page_analysis: Dict, strategy: Dict) -> Dict:
    """Agent 4: Synthesizes the final before/after comparison."""
    
    system_prompt = "You are an expert at creating clear before/after product comparisons. Show the original vs personalized content side-by-side."
    
    user_prompt = f"""Given this landing page analysis:
{json.dumps(page_analysis, indent=2)}

And this personalization strategy:
{json.dumps(strategy, indent=2)}

Create a before/after comparison using this exact JSON schema:
{{
  "before": {{
    "headline": "original headline",
    "subheading": "original subheading",
    "cta": "original cta"
  }},
  "after": {{
    "headline": "personalized headline (matching ad)",
    "subheading": "personalized subheading",
    "cta": "personalized cta (using ad language)"
  }},
  "changes_explained": [
    "Change 1: Why it matters",
    "Change 2: Why it matters"
  ]
}}"""

    return run_agent("agent4", "Comparison Generator", system_prompt, user_prompt)

# --- UI Formatting Helpers ---

def format_before_after(comparison: Dict) -> Tuple[str, str]:
    """Formats the JSON comparison data into readable Markdown for the UI."""
    before = comparison.get("before", {})
    after = comparison.get("after", {})
    
    before_text = f"""### 📄 Original Landing Page

**Headline:** {before.get('headline', 'N/A')}

**Subheading:** {before.get('subheading', 'N/A')}

**Call to Action:** {before.get('cta', 'N/A')}
"""
    
    after_text = f"""### ✨ Personalized Landing Page

**Headline:** {after.get('headline', 'N/A')}

**Subheading:** {after.get('subheading', 'N/A')}

**Call to Action:** {after.get('cta', 'N/A')}
"""
    
    return before_text, after_text

def format_strategy(strategy: Dict) -> str:
    """Formats the CRO strategy JSON into a readable Markdown report."""
    output = "## 🎯 CRO Personalization Strategy\n\n"
    
    if "message_match" in strategy:
        mm = strategy["message_match"]
        output += f"**1. Message Match:** Changed headline to '{mm.get('new_page_headline', '')}'. *Why: {mm.get('rationale', '')}*\n\n"
        
    if "scent_trail" in strategy:
        st = strategy["scent_trail"]
        output += f"**2. Scent Trail:** {st.get('page_emphasis', '')}. *Why: {st.get('rationale', '')}*\n\n"
        
    if "cta_optimization" in strategy:
        cta = strategy["cta_optimization"]
        output += f"**3. CTA Optimization:** Updated to '{cta.get('new_cta', '')}'. *Why: {cta.get('rationale', '')}*\n\n"
        
    return output

# --- Main Orchestrator ---

def personalize_landing_page(ad_description: str, landing_page_description: str, progress=gr.Progress()):
    """Main pipeline that orchestrates the 4 agents sequentially."""
    
    if not ad_description.strip() or not landing_page_description.strip():
        return "⚠️ Please provide both descriptions.", "", "", ""

    try:
        global agent_status
        agent_status = {}
        
        progress(0.1, desc="Agent 1: Analyzing ad creative...")
        ad_analysis = agent_1_analyze_ad(ad_description)
        
        progress(0.3, desc="Agent 2: Analyzing landing page...")
        page_analysis = agent_2_analyze_page(landing_page_description)
        
        progress(0.6, desc="Agent 3: Creating CRO strategy...")
        strategy = agent_3_create_strategy(ad_analysis, page_analysis)
        
        progress(0.8, desc="Agent 4: Generating comparison...")
        comparison = agent_4_generate_comparison(page_analysis, strategy)
        
        progress(1.0, desc="Complete!")
        
        # Format for UI
        strategy_text = format_strategy(strategy)
        before_text, after_text = format_before_after(comparison)
        
        changes = comparison.get("changes_explained", [])
        changes_text = "## 💡 What Changed & Why\n\n" + "\n\n".join(f"**{i+1}.** {change}" for i, change in enumerate(changes))
        
        return strategy_text, before_text, after_text, changes_text
        
    except Exception as e:
        error_msg = f"❌ Error: {str(e)}\n\n(Tip: Did you set the GEMINI_API_KEY in your Hugging Face space secrets?)"
        return error_msg, "", "", ""

# --- Gradio UI Layout ---

with gr.Blocks(theme=gr.themes.Soft(), title="AI Landing Page Personalizer") as demo:
    gr.Markdown("""
    # 🚀 AI Landing Page Personalizer
    ### Multi-Agent CRO Optimization System
    
    This system uses **4 specialized AI agents** (powered by Gemini 1.5 Flash) to personalize landing pages based on ad creative:
    - **Agent 1:** Analyzes ad messaging and tone
    - **Agent 2:** Maps current landing page structure  
    - **Agent 3:** Creates CRO-aligned strategy
    - **Agent 4:** Generates before/after comparison
    """)
    
    with gr.Row():
        with gr.Column():
            gr.Markdown("### 📢 Ad Creative Context")
            ad_input = gr.Textbox(
                label="Describe the ad the user just clicked",
                placeholder="Example: Facebook ad for a fitness app. Headline: 'Transform Your Body in 30 Days'. CTA: 'Start Free Trial'. Visuals are energetic and orange.",
                lines=5
            )
            
            gr.Markdown("### 🌐 Landing Page Context")
            page_input = gr.Textbox(
                label="Describe your generic landing page",
                placeholder="Example: Headline: 'Welcome to FitApp'. Subheading: 'Your fitness journey starts here'. CTA: 'Sign Up Now'. Focuses on general wellness.",
                lines=5
            )
            
            submit_btn = gr.Button("🎯 Generate Personalized Page", variant="primary", size="lg")
    
    gr.Markdown("---")
    
    with gr.Row():
        strategy_output = gr.Markdown(label="Personalization Strategy")
    
    gr.Markdown("---")
    gr.Markdown("## 📊 Before & After Comparison")
    
    with gr.Row():
        with gr.Column():
            before_output = gr.Markdown(label="Original")
        with gr.Column():
            after_output = gr.Markdown(label="Personalized")
            
    with gr.Row():
        changes_output = gr.Markdown(label="Changes Explained")

    submit_btn.click(
        fn=personalize_landing_page,
        inputs=[ad_input, page_input],
        outputs=[strategy_output, before_output, after_output, changes_output]
    )

if __name__ == "__main__":
    demo.launch()