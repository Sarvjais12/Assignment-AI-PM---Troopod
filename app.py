import gradio as gr
import anthropic
import os
import json
import re
from typing import Dict, List, Tuple

# Initialize Anthropic client
client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

# Global state for tracking progress
agent_status = {}

def run_agent(agent_id: str, agent_name: str, system_prompt: str, user_prompt: str) -> str:
    """
    Run a single agent and return structured output
    """
    try:
        agent_status[agent_id] = "running"
        
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            temperature=0.3,  # Low temperature for consistency
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt}
            ]
        )
        
        result = message.content[0].text
        agent_status[agent_id] = "complete"
        return result
        
    except Exception as e:
        agent_status[agent_id] = "error"
        raise Exception(f"{agent_name} failed: {str(e)}")


def agent_1_analyze_ad(ad_description: str) -> Dict:
    """
    Agent 1: Ad Creative Analyzer
    Extracts messaging, tone, and visual elements from ad description
    """
    system_prompt = """You are an expert ad creative analyst. Extract structured insights from advertising materials.
Your job is to identify the core messaging, emotional tone, target audience, and key elements."""

    user_prompt = f"""Analyze this ad creative and extract the following in JSON format:
{{
  "primary_value_prop": "main promise or benefit",
  "emotional_tone": "urgent/aspirational/educational/etc",
  "target_audience": "who this is for",
  "headline": "main headline or hook",
  "subheading": "supporting text if any",
  "cta_text": "call to action text",
  "key_messages": ["key point 1", "key point 2"],
  "visual_style": "description of visual approach"
}}

Ad Description:
{ad_description}

Focus on:
- What promise does this ad make?
- What emotional angle does it use?
- Who is it targeting?
- What's the core messaging hierarchy?

Respond ONLY with valid JSON, no markdown formatting, no explanation."""

    result = run_agent("agent1", "Ad Creative Analyzer", system_prompt, user_prompt)
    
    # Clean and parse JSON
    cleaned = result.replace("```json", "").replace("```", "").strip()
    return json.loads(cleaned)


def agent_2_analyze_page(landing_page_description: str) -> Dict:
    """
    Agent 2: Landing Page Analyzer
    Maps page structure and identifies personalization opportunities
    """
    system_prompt = """You are an expert landing page analyst. Map page structure and identify personalization opportunities.
Your job is to understand current messaging and find areas to improve."""

    user_prompt = f"""Analyze this landing page and extract the following in JSON format:
{{
  "current_headline": "main headline",
  "current_subheading": "supporting headline",
  "current_cta": "main call to action",
  "page_structure": {{
    "has_hero": true/false,
    "has_features": true/false,
    "has_social_proof": true/false,
    "has_pricing": true/false
  }},
  "current_messaging_focus": "what the page emphasizes",
  "personalization_opportunities": [
    "hero_headline",
    "hero_subheading",
    "primary_cta"
  ]
}}

Landing Page Description:
{landing_page_description}

Respond ONLY with valid JSON, no markdown formatting, no explanation."""

    result = run_agent("agent2", "Landing Page Analyzer", system_prompt, user_prompt)
    
    cleaned = result.replace("```json", "").replace("```", "").strip()
    return json.loads(cleaned)


def agent_3_create_strategy(ad_analysis: Dict, page_analysis: Dict) -> Dict:
    """
    Agent 3: Personalization Strategist
    Designs CRO-aligned personalization strategy
    """
    system_prompt = """You are a CRO (Conversion Rate Optimization) expert. Design personalization strategies that improve conversion rates.
Focus on proven principles: message match, scent trail, visual consistency, CTA optimization."""

    user_prompt = f"""Given this ad creative analysis:
{json.dumps(ad_analysis, indent=2)}

And this landing page analysis:
{json.dumps(page_analysis, indent=2)}

Create a personalization strategy using CRO principles. Return JSON:
{{
  "message_match": {{
    "ad_headline": "...",
    "new_page_headline": "...",
    "rationale": "why this improves conversion"
  }},
  "scent_trail": {{
    "ad_promise": "...",
    "page_emphasis": "...",
    "rationale": "..."
  }},
  "cta_optimization": {{
    "original_cta": "...",
    "new_cta": "...",
    "rationale": "..."
  }},
  "additional_changes": [
    "change 1",
    "change 2"
  ],
  "modifications_summary": [
    "High-level change 1",
    "High-level change 2",
    "High-level change 3"
  ]
}}

Focus on 3-5 strategic changes that follow CRO best practices:
1. Message Match: Ad headline should echo in page headline
2. Scent Trail: Ad promise should be reinforced above fold
3. CTA Optimization: Use ad's action language

Respond ONLY with valid JSON, no markdown formatting, no explanation."""

    result = run_agent("agent3", "Personalization Strategist", system_prompt, user_prompt)
    
    cleaned = result.replace("```json", "").replace("```", "").strip()
    return json.loads(cleaned)


def agent_4_generate_comparison(page_analysis: Dict, strategy: Dict) -> Dict:
    """
    Agent 4: Comparison Generator
    Creates before/after comparison
    """
    system_prompt = """You are an expert at creating clear before/after comparisons.
Your job is to show the original vs personalized content side-by-side."""

    user_prompt = f"""Given this landing page analysis:
{json.dumps(page_analysis, indent=2)}

And this personalization strategy:
{json.dumps(strategy, indent=2)}

Create a before/after comparison in JSON format:
{{
  "before": {{
    "headline": "original headline",
    "subheading": "original subheading",
    "cta": "original cta",
    "key_messages": ["original message 1", "original message 2"]
  }},
  "after": {{
    "headline": "personalized headline (matching ad)",
    "subheading": "personalized subheading",
    "cta": "personalized cta (using ad language)",
    "key_messages": ["personalized message 1", "personalized message 2"]
  }},
  "changes_explained": [
    "Change 1: Why it matters",
    "Change 2: Why it matters"
  ]
}}

Apply the strategy to show specific before/after changes.

Respond ONLY with valid JSON, no markdown formatting, no explanation."""

    result = run_agent("agent4", "Comparison Generator", system_prompt, user_prompt)
    
    cleaned = result.replace("```json", "").replace("```", "").strip()
    return json.loads(cleaned)


def format_before_after(comparison: Dict) -> Tuple[str, str]:
    """
    Format the before/after comparison for display
    """
    before = comparison.get("before", {})
    after = comparison.get("after", {})
    
    before_text = f"""### Original Landing Page

**Headline:** {before.get('headline', 'N/A')}

**Subheading:** {before.get('subheading', 'N/A')}

**Call to Action:** {before.get('cta', 'N/A')}

**Key Messages:**
{chr(10).join('• ' + msg for msg in before.get('key_messages', []))}
"""
    
    after_text = f"""### ✨ Personalized Landing Page

**Headline:** {after.get('headline', 'N/A')}

**Subheading:** {after.get('subheading', 'N/A')}

**Call to Action:** {after.get('cta', 'N/A')}

**Key Messages:**
{chr(10).join('• ' + msg for msg in after.get('key_messages', []))}
"""
    
    return before_text, after_text


def format_strategy(strategy: Dict) -> str:
    """
    Format the personalization strategy for display
    """
    output = "## 🎯 Personalization Strategy\n\n"
    
    # Message Match
    if "message_match" in strategy:
        mm = strategy["message_match"]
        output += f"""### 1. Message Match
**Ad Headline:** {mm.get('ad_headline', 'N/A')}
**New Page Headline:** {mm.get('new_page_headline', 'N/A')}
**Why:** {mm.get('rationale', 'N/A')}

"""
    
    # Scent Trail
    if "scent_trail" in strategy:
        st = strategy["scent_trail"]
        output += f"""### 2. Scent Trail
**Ad Promise:** {st.get('ad_promise', 'N/A')}
**Page Emphasis:** {st.get('page_emphasis', 'N/A')}
**Why:** {st.get('rationale', 'N/A')}

"""
    
    # CTA Optimization
    if "cta_optimization" in strategy:
        cta = strategy["cta_optimization"]
        output += f"""### 3. CTA Optimization
**Original:** {cta.get('original_cta', 'N/A')}
**Personalized:** {cta.get('new_cta', 'N/A')}
**Why:** {cta.get('rationale', 'N/A')}

"""
    
    # Summary
    if "modifications_summary" in strategy:
        output += "### Summary of Changes\n"
        for i, change in enumerate(strategy["modifications_summary"], 1):
            output += f"{i}. {change}\n"
    
    return output


def personalize_landing_page(ad_description: str, landing_page_description: str, progress=gr.Progress()):
    """
    Main function that orchestrates the 4-agent workflow
    """
    try:
        # Reset status
        global agent_status
        agent_status = {}
        
        # Agent 1: Analyze Ad
        progress(0.1, desc="Agent 1: Analyzing ad creative...")
        ad_analysis = agent_1_analyze_ad(ad_description)
        
        # Agent 2: Analyze Landing Page
        progress(0.3, desc="Agent 2: Analyzing landing page...")
        page_analysis = agent_2_analyze_page(landing_page_description)
        
        # Agent 3: Create Strategy
        progress(0.6, desc="Agent 3: Creating personalization strategy...")
        strategy = agent_3_create_strategy(ad_analysis, page_analysis)
        
        # Agent 4: Generate Comparison
        progress(0.8, desc="Agent 4: Generating before/after comparison...")
        comparison = agent_4_generate_comparison(page_analysis, strategy)
        
        progress(1.0, desc="Complete!")
        
        # Format outputs
        strategy_text = format_strategy(strategy)
        before_text, after_text = format_before_after(comparison)
        
        # Create changes explanation
        changes = comparison.get("changes_explained", [])
        changes_text = "## 💡 What Changed & Why\n\n" + "\n\n".join(f"**{i+1}.** {change}" for i, change in enumerate(changes))
        
        return strategy_text, before_text, after_text, changes_text
        
    except Exception as e:
        error_msg = f"❌ Error: {str(e)}\n\nPlease check your inputs and try again."
        return error_msg, "", "", ""


# Create Gradio Interface
with gr.Blocks(theme=gr.themes.Soft(), title="AI Landing Page Personalizer") as demo:
    gr.Markdown("""
    # 🚀 AI Landing Page Personalizer
    ### Multi-Agent CRO Optimization System
    
    This system uses **4 specialized AI agents** to personalize landing pages based on ad creative:
    - **Agent 1:** Analyzes ad messaging and tone
    - **Agent 2:** Maps landing page structure  
    - **Agent 3:** Creates CRO-aligned strategy
    - **Agent 4:** Generates before/after comparison
    
    **CRO Principles Applied:** Message Match • Scent Trail • Visual Consistency • CTA Optimization
    """)
    
    with gr.Row():
        with gr.Column():
            gr.Markdown("### 📢 Ad Creative")
            ad_input = gr.Textbox(
                label="Describe your ad creative",
                placeholder="""Example: 
Facebook ad for a fitness app
Headline: "Transform Your Body in 30 Days"
Subheading: "No gym required - 15 min workouts at home"
CTA: "Start Free Trial"
Visual: Energetic, bold colors (orange and blue)
Target: Busy professionals, 25-45 years old""",
                lines=8
            )
            
            gr.Markdown("### 🌐 Landing Page")
            page_input = gr.Textbox(
                label="Describe your current landing page",
                placeholder="""Example:
Headline: "Welcome to FitApp"
Subheading: "Your fitness journey starts here"
Has hero section, features list, testimonials, pricing
CTA: "Sign Up Now"
Focus: General fitness and wellness""",
                lines=8
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
    
    gr.Markdown("---")
    
    with gr.Row():
        changes_output = gr.Markdown(label="Changes Explained")
    
    # Examples
    gr.Markdown("---")
    gr.Markdown("### 💡 Try These Examples")
    
    gr.Examples(
        examples=[
            [
                """Facebook ad for SaaS project management tool
Headline: "Ship Projects 2x Faster"
Subheading: "AI-powered task management for growing teams"
CTA: "Start 14-Day Free Trial"
Visual: Clean, professional, blue and white
Target: Tech startup founders and project managers""",
                """Headline: "Modern Project Management Software"
Subheading: "Collaborate, plan, and deliver projects efficiently"
Hero section with product screenshot
Features: Task boards, time tracking, team collaboration
Testimonials from enterprise customers
CTA: "Request Demo"
Focus: Enterprise-grade project management"""
            ],
            [
                """Google ad for online course platform
Headline: "Learn Python in 30 Days - Guaranteed"
Subheading: "From zero to job-ready with 1-on-1 mentorship"
CTA: "Enroll Now - $49"
Visual: Educational, trustworthy, green accents
Target: Career switchers, 22-35 years old""",
                """Headline: "Online Learning Platform"
Subheading: "Thousands of courses to advance your career"
Hero with video preview
Features: Self-paced learning, certificates, community
Multiple course categories (design, business, tech)
CTA: "Browse Courses"
Focus: General skill development"""
            ]
        ],
        inputs=[ad_input, page_input],
    )
    
    # Connect the button
    submit_btn.click(
        fn=personalize_landing_page,
        inputs=[ad_input, page_input],
        outputs=[strategy_output, before_output, after_output, changes_output]
    )
    
    gr.Markdown("""
    ---
    ### 🧠 How It Works
    
    **Multi-Agent Architecture:**
    1. **Agent 1** extracts key messaging from your ad (value prop, tone, audience)
    2. **Agent 2** analyzes your landing page structure and opportunities
    3. **Agent 3** creates a CRO-aligned personalization strategy
    4. **Agent 4** generates before/after comparison showing improvements
    
    **CRO Principles:**
    - **Message Match:** Ad headline → Page headline (reduces bounce rate 20-30%)
    - **Scent Trail:** Ad promise → Page delivery (maintains user journey)
    - **Visual Consistency:** Ad colors → Page accents (builds trust)
    - **CTA Optimization:** Ad language → CTA text (improves conversions)
    
    ---
    Built for Troopod AI PM Assignment • Powered by Claude Sonnet 4
    """)

if __name__ == "__main__":
    demo.launch()
