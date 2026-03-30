"""
dashboard.py — GEO Agent Dashboard (Refined)
=============================================
Improvements:
- Reads from outputs/ folder by default (no root clutter)
- File picker: choose any past run, not just the "best" one
- Real charts: bar charts for domains/brands, pie for success rate
- Citation quality score visualized
- Cleaner section layout with explanatory context
- Response viewer shows full text without truncation bugs
- Summary cards with delta indicators
"""

import streamlit as st
import json
import glob
import os
import subprocess
import sys
from datetime import datetime
from collections import defaultdict, Counter
from pathlib import Path
import pandas as pd
import requests
from bs4 import BeautifulSoup
import time
import re

# ── Page config ─────────────────────────────────────────────
st.set_page_config(
    page_title="GEO Dashboard",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Styling ──────────────────────────────────────────────────
st.markdown("""
<style>
    .metric-card {
        background: #f8f9fa;
        border-radius: 8px;
        padding: 1rem;
        border-left: 4px solid #4CAF50;
    }
    .section-header {
        font-size: 1.1rem;
        font-weight: 600;
        color: #333;
        margin-bottom: 0.5rem;
    }
    .brand-pill {
        display: inline-block;
        background: #e3f2fd;
        border-radius: 12px;
        padding: 2px 10px;
        margin: 2px;
        font-size: 0.85rem;
    }
    div[data-testid="stMetric"] {
        background: #fafafa;
        border: 1px solid #eee;
        border-radius: 8px;
        padding: 0.75rem 1rem;
        color: #333 !important;
    }
    div[data-testid="stMetric"] label {
        color: #333 !important;
    }
    div[data-testid="stMetric"] div {
        color: #333 !important;
    }
</style>
""", unsafe_allow_html=True)

# ── Output directory ─────────────────────────────────────────
OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

# ============================================================
# DATA LOADING
# ============================================================

def find_result_files() -> list[Path]:
    """Find all responses_*.json files in outputs/ and root."""
    files = list(OUTPUT_DIR.glob("responses_*.json")) + list(Path(".").glob("responses_*.json"))
    # Deduplicate and sort newest first
    seen, unique = set(), []
    for f in sorted(files, key=lambda x: x.stat().st_mtime, reverse=True):
        if f.name not in seen:
            seen.add(f.name)
            unique.append(f)
    return unique

def load_file(path: Path) -> list[dict] | None:
    try:
        with open(path) as f:
            data = json.load(f)

        if isinstance(data, list):
            return data

        # Downstream flexibility: accept {"responses": [...]} shape too.
        if isinstance(data, dict) and "responses" in data and isinstance(data["responses"], list):
            return data["responses"]

        st.warning(f"Unexpected file shape in {path.name}; expected list or dict with 'responses'.")
        return None

    except Exception as e:
        st.error(f"Failed to load {path.name}: {e}")
    return None

def load_summary_for(response_file: Path) -> dict | None:
    """Try to load the matching summary_*.json for a responses file."""
    # e.g. responses_google_20260315_162253.json -> summary_google_20260315_162253.json
    name = response_file.name.replace("responses_", "summary_")
    for candidate in [response_file.parent / name, Path(name)]:
        if candidate.exists():
            try:
                with open(candidate) as f:
                    return json.load(f)
            except Exception:
                pass
    return None

def get_tokens(r: dict) -> int:
    """Handles both {tokens: N} and {usage: {total_tokens: N}} shapes."""
    return (r.get("tokens") or
            r.get("usage", {}).get("total_tokens") or
            r.get("usage", {}).get("input_tokens", 0) + r.get("usage", {}).get("output_tokens", 0))

def get_quality(c: dict) -> float:
    """Derive a 0–1 quality score from whatever citation fields exist."""
    if "quality_score" in c:
        return float(c["quality_score"])
    score = 0.0
    if c.get("has_brand_mentions") or c.get("cement_brands"):
        score += 0.4
    if c.get("has_external_links") or c.get("urls"):
        score += 0.3
    if c.get("citation_count", 0) > 1:
        score += 0.2
    if c.get("external_references"):
        score += 0.1
    return min(score, 1.0)

def compute_metrics(data: list[dict]) -> dict:
    total = len(data)
    ok    = sum(1 for r in data if not r.get("error"))
    cost  = sum(r.get("cost", 0) for r in data)
    tokens = sum(get_tokens(r) for r in data)

    with_cites = sum(1 for r in data if r.get("citations", {}).get("citation_count", 0) > 0)
    avg_cites  = sum(r.get("citations", {}).get("citation_count", 0) for r in data) / max(total, 1)
    avg_quality = sum(get_quality(r.get("citations", {})) for r in data) / max(total, 1)

    all_domains, all_brands = [], []
    for r in data:
        c = r.get("citations", {})
        all_domains.extend(c.get("domains", []))
        all_brands.extend(c.get("cement_brands", []))

    # SERP and GEO metrics
    with_serp = sum(1 for r in data if r.get("serp"))
    with_geo = sum(1 for r in data if r.get("geo_analysis"))
    avg_geo_score = sum(r.get("geo_analysis", {}).get("overlap_analysis", {}).get("geo_score", 0) 
                       for r in data if r.get("geo_analysis")) / max(with_geo, 1)
    avg_serp_coverage = sum(r.get("geo_analysis", {}).get("overlap_analysis", {}).get("serp_coverage", 0) 
                           for r in data if r.get("geo_analysis")) / max(with_geo, 1)

    return {
        "total": total, "ok": ok, "failed": total - ok,
        "success_pct": ok / max(total, 1) * 100,
        "cost": cost, "tokens": tokens,
        "with_cites": with_cites,
        "avg_cites": avg_cites,
        "avg_quality": avg_quality,
        "unique_domains": len(set(all_domains)),
        "domain_counts": Counter(all_domains),
        "brand_counts":  Counter(all_brands),
        "with_serp": with_serp,
        "with_geo": with_geo,
        "avg_geo_score": avg_geo_score,
        "avg_serp_coverage": avg_serp_coverage,
    }

# ============================================================
# PIPELINE RUNNER
# ============================================================

def run_pipeline(api_key: str, provider: str, model: str, num_queries: int,
                 categories: list[str] | None = None):
    os.environ[f"{provider.upper()}_API_KEY"] = api_key
    cmd = [
        sys.executable, "pipeline_multi.py",
        "--provider", provider, "--model", model,
        "--num-queries", str(num_queries),
        "--max-workers", "3",
        "--max-tokens", "500",
    ]
    if categories:
        cmd += ["--categories"] + categories

    result = subprocess.run(cmd, capture_output=True, text=True, cwd=os.getcwd())
    ok = result.returncode == 0
    msg = "Analysis complete!" if ok else f"Pipeline error:\n{result.stderr[:500]}"
    return ok, msg, result.stdout

def run_content_structuring():
    """Run GEO content structuring using Agent 7"""
    try:
        from agents.agent7_content_structurer import content_structurer
        results = content_structurer.run_structuring()
        return True, "Content structuring completed!", results
    except ImportError:
        return False, "Content structuring not available (Agent 7 missing)", None
    except Exception as e:
        return False, f"Content structuring failed: {e}", None

def run_validation_scoring():
    """Run validation and scoring using Agent 8"""
    try:
        from agents.agent8_validator import validation_agent
        results = validation_agent.run_validation()
        return True, "Validation and scoring completed!", results
    except ImportError:
        return False, "Validation and scoring not available (Agent 8 missing)", None
    except Exception as e:
        return False, f"Validation failed: {e}", None

def run_provider_comparison(provider_keys: dict, num_queries: int, categories: list[str] = None):
    """Run the same queries across multiple providers and return comparison data."""
    results = {}
    total_start_time = time.time()

    for provider, api_key in provider_keys.items():
        start_time = time.time()
        st.info(f"Running {provider}...")

        # Set environment variable for this provider
        os.environ[f"{provider.upper()}_API_KEY"] = api_key

        # Use default model for each provider
        model = {
            "openai": "gpt-4o-mini",
            "anthropic": "claude-3-haiku-20240307",
            "google": "gemini-1.5-flash",
            "nvidia": "meta/llama-3.1-8b-instruct",
            "ollama": "llama3"
        }.get(provider, "default")

        cmd = [
            sys.executable, "pipeline_multi.py",
            "--provider", provider,
            "--model", model,
            "--num-queries", str(num_queries),
            "--max-workers", "2",  # Reduce workers for comparison
            "--max-tokens", "500",
        ]
        if categories:
            cmd += ["--categories"] + categories

        result = subprocess.run(cmd, capture_output=True, text=True, cwd=os.getcwd())
        elapsed = time.time() - start_time

        if result.returncode == 0:
            # Try to find the generated results file
            output_files = list(OUTPUT_DIR.glob(f"responses_{provider}_*.json"))
            if output_files:
                latest_file = max(output_files, key=lambda x: x.stat().st_mtime)
                data = load_file(latest_file)
                if data:
                    metrics = compute_metrics(data)
                    results[provider] = {
                        "success": True,
                        "metrics": metrics,
                        "time": elapsed,
                        "file": latest_file
                    }
                else:
                    results[provider] = {"success": False, "error": "Could not load results"}
            else:
                results[provider] = {"success": False, "error": "No output file found"}
        else:
            results[provider] = {
                "success": False,
                "error": result.stderr[:200],
                "time": elapsed
            }

    total_time = time.time() - total_start_time
    return results, total_time

def analyze_website(url: str):
    """Scrape and analyze a website for citation patterns."""
    try:
        # Basic web scraping with rate limiting
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')

        # Extract text content
        text_content = soup.get_text()

        # Use citation extraction logic (similar to agent3)
        citations = extract_citations_from_text(text_content, url)

        # Calculate quality score
        quality_score = get_quality(citations)

        return {
            "success": True,
            "url": url,
            "title": soup.title.string if soup.title else "No title",
            "citations": citations,
            "quality_score": quality_score,
            "word_count": len(text_content.split()),
            "status_code": response.status_code
        }

    except Exception as e:
        return {
            "success": False,
            "url": url,
            "error": str(e)
        }

def extract_citations_from_text(text: str, source_url: str):
    """Extract citations from text content (similar to agent3_citation_extraction.py logic)."""
    # URL extraction
    url_pattern = r'https?://(?:[-\w.])+(?:[:\d]+)?(?:/(?:[\w/_.])*(?:\?(?:[\w&=%.])*)?(?:#(?:\w*))?)?'
    urls = re.findall(url_pattern, text)

    # Domain extraction
    domains = []
    for url in urls:
        try:
            domain = re.search(r'https?://([^/]+)', url).group(1)
            # Clean domain
            domain = domain.replace('www.', '')
            domains.append(domain)
        except:
            continue

    # Cement brand detection (from agent3 logic)
    cement_brands = [
        'ultratech', 'acc', 'ambuja', 'jk', 'dalmia', 'shree', 'orient',
        'india cements', 'ramco', 'birla', 'heidelbergcement', 'cemex'
    ]

    brands_found = []
    text_lower = text.lower()
    for brand in cement_brands:
        if brand.lower() in text_lower:
            brands_found.append(brand.title())

    # Reference phrases (simplified)
    reference_phrases = []
    ref_patterns = [
        r'according to\s+[^.]*',
        r'as per\s+[^.]*',
        r'source:\s*[^.]*',
        r'reference:\s*[^.]*'
    ]

    for pattern in ref_patterns:
        matches = re.findall(pattern, text_lower)
        reference_phrases.extend(matches[:3])  # Limit to 3 per pattern

    return {
        "citation_count": len(urls) + len(reference_phrases),
        "urls": urls[:10],  # Limit URLs
        "domains": list(set(domains))[:10],  # Unique domains, limited
        "cement_brands": brands_found,
        "reference_phrases": reference_phrases[:5],  # Limit phrases
        "has_brand_mentions": len(brands_found) > 0,
        "has_external_links": len(urls) > 0,
        "external_references": len(reference_phrases) > 0
    }

# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:
    st.title("🎯 GEO Dashboard")
    st.caption("Generative Engine Optimization — AI Citation Analysis")
    st.divider()

    # ── Run new analysis ──────────────────────────────────
    st.subheader("▶ Run Analysis")

    provider = st.selectbox("Provider", ["google", "openai", "anthropic", "nvidia", "ollama"])

    MODEL_OPTIONS = {
        "openai":    ["gpt-4o-mini", "gpt-3.5-turbo", "gpt-4o"],
        "anthropic": ["claude-3-haiku-20240307", "claude-3-sonnet-20240229", "claude-3-5-sonnet-20241022"],
        "google":    ["gemini-1.5-flash", "gemini-2.0-flash", "gemini-2.1"],
        "nvidia":    ["meta/llama-3.1-8b-instruct", "meta/llama-3.1-70b-instruct"],
        "ollama":    ["llama2", "mistral", "llama3"],
    }
    model = st.selectbox("Model", MODEL_OPTIONS.get(provider, ["default"]))

    api_key = st.text_input(
        f"{provider.upper()} API Key",
        type="password",
        placeholder="Paste your key here",
        help="Key is used only for this run and not stored"
    )

    # Query category filter
    CATEGORIES = ["product_selection", "brand_comparison", "technical", "seo_and_geo"]
    selected_cats = st.multiselect(
        "Query categories",
        CATEGORIES,
        default=CATEGORIES,
        help="Filter which query groups to run (from queries.json)"
    )
    num_queries = st.slider("Max queries", 3, 50, 10)

    col1, col2 = st.columns(2)
    run_btn  = col1.button("🚀 Run", type="primary", disabled=not api_key.strip(), width='stretch')
    demo_btn = col2.button("🎭 Demo", width='stretch', help="Run with mock AI data")

    st.divider()

    # ── Compare Providers ──────────────────────────────────
    st.subheader("⚖️ Compare Providers")

    # Provider selection for comparison
    available_providers = ["google", "openai", "anthropic", "nvidia", "ollama"]
    selected_providers = st.multiselect(
        "Select providers to compare",
        available_providers,
        default=[],
        max_selections=3,
        help="Choose up to 3 providers to compare side-by-side"
    )

    # API keys for selected providers
    provider_keys = {}
    if selected_providers:
        st.caption("Enter API keys for selected providers:")
        for provider in selected_providers:
            key = st.text_input(
                f"{provider.upper()} API Key",
                type="password",
                key=f"compare_{provider}",
                help=f"API key for {provider}"
            )
            if key.strip():
                provider_keys[provider] = key

    compare_queries = st.slider("Queries per provider", 3, 20, 5, key="compare_queries")
    compare_btn = st.button(
        "🔍 Compare Providers",
        type="secondary",
        disabled=len(provider_keys) < 2,
        width='stretch',
        help="Run same queries across selected providers and compare results"
    )

    st.divider()

    # ── Website Analysis ───────────────────────────────────
    st.subheader("🌐 Website Analysis")

    website_url = st.text_input(
        "Website URL to analyze",
        placeholder="https://example.com",
        help="Enter a website URL to analyze its citation patterns"
    )

    analyze_website_btn = st.button(
        "📊 Analyze Website",
        disabled=not website_url.strip(),
        width='stretch',
        help="Scrape and analyze citation patterns on the website"
    )

    st.divider()

    # ── File picker ───────────────────────────────────────
    st.subheader("📂 Load Results")
    
    # Only show file picker if not viewing active website/comparison results
    if 'website_results' not in st.session_state and 'comparison_results' not in st.session_state:
        result_files = find_result_files()

        if result_files:
            file_labels = {f.name: f for f in result_files}
            chosen_label = st.selectbox(
                "Select a results file",
                list(file_labels.keys()),
                help="Newest runs appear first"
            )
            chosen_file = file_labels[chosen_label]
        else:
            chosen_file = None
            st.info("No results yet — run an analysis above.")
    else:
        chosen_file = None
        if 'website_results' in st.session_state:
            st.info("📊 Viewing website analysis results")
        elif 'comparison_results' in st.session_state:
            st.info("⚖️ Viewing provider comparison results")

    st.divider()

    # ── Pattern Analysis (Agent 5) ─────────────────────────
    st.subheader("📊 Pattern Analysis")
    st.caption("Analyze citation patterns across all runs")
    if st.button("📊 Run Pattern Analysis", width='stretch', key="pattern_btn"):
        st.session_state['mode'] = 'pattern'
        st.rerun()

    st.divider()

    # ── Content Generator (Agent 6) ────────────────────────
    st.subheader("📝 Content Generator")
    st.caption("Generate GEO-optimized content for zero-citation queries")
    
    nvidia_key_gen = st.text_input("NVIDIA API Key", type="password", key="nvidia_key_gen", placeholder="For content generation")
    openai_key_gen = st.text_input("OpenAI API Key", type="password", key="openai_key_gen", placeholder="Alternative provider")
    max_gen_queries = st.slider("Max queries to generate", 1, 10, 3, key="max_gen_queries")
    
    if st.button("📝 Generate Content", type="secondary", width='stretch', key="generate_btn"):
        if nvidia_key_gen.strip():
            os.environ["NVIDIA_API_KEY"] = nvidia_key_gen
        if openai_key_gen.strip():
            os.environ["OPENAI_API_KEY"] = openai_key_gen
        st.session_state['mode'] = 'content'
        st.rerun()

    st.divider()

    # ── Content Structurer (Agent 7) ───────────────────────
    st.subheader("🔧 Content Structurer")
    st.caption("Validate and structure generated content quality")
    if st.button("🔧 Run Structuring", type="secondary", width='stretch', key="structuring_btn"):
        st.session_state['mode'] = 'structuring'
        st.rerun()

    st.divider()

    # ── Validation & Scoring (Agent 8) ────────────────────
    st.subheader("🧪 Validation & Scoring")
    st.caption("Test whether content improves citation scores")
    if st.button("🧪 Run Validation", type="secondary", width='stretch', key="validation_btn"):
        st.session_state['mode'] = 'validation'
        st.rerun()

    st.divider()
    st.caption(f"Output folder: `{OUTPUT_DIR}/`")

# ── Handle run / demo button clicks ─────────────────────────
status_placeholder = st.empty()

if run_btn and api_key.strip():
    with st.spinner(f"Running pipeline ({provider} / {model})…"):
        ok, msg, out = run_pipeline(api_key, provider, model, num_queries, selected_cats or None)
    if ok:
        st.success(msg)
        st.rerun()
    else:
        st.error(msg)
        if out:
            with st.expander("Pipeline output"):
                st.code(out)

if demo_btn:
    with st.spinner("Running mock demo…"):
        ok, msg, out = run_mock()
    if ok:
        st.success(msg)
        st.rerun()
    else:
        st.error(msg)

if compare_btn and len(provider_keys) >= 2:
    with st.spinner(f"Comparing {len(provider_keys)} providers…"):
        comparison_results, total_time = run_provider_comparison(provider_keys, compare_queries, selected_cats)
        st.session_state['comparison_results'] = comparison_results
        st.session_state['comparison_time'] = total_time
        st.success(f"Comparison complete! ({total_time:.1f}s)")
        st.rerun()

if analyze_website_btn and website_url.strip():
    with st.spinner(f"Analyzing website: {website_url}…"):
        website_results = analyze_website(website_url.strip())
        st.session_state['website_results'] = website_results
        # Clear any previously selected file to ensure website results display
        if 'chosen_file_label' in st.session_state:
            del st.session_state['chosen_file_label']
        if website_results["success"]:
            st.success("Website analysis complete!")
        else:
            st.error(f"Analysis failed: {website_results.get('error', 'Unknown error')}")
        st.rerun()

# Handle pattern analysis mode
if 'mode' in st.session_state and st.session_state['mode'] == 'pattern':
    with st.spinner("Running pattern analysis…"):
        ok, msg, report = run_pattern_analysis()
    if ok:
        st.session_state['pattern_results'] = report
        st.success(msg)
        st.rerun()
    else:
        st.error(msg)
    # Clear mode after handling
    if 'mode' in st.session_state:
        del st.session_state['mode']

# Handle content generation mode
if 'mode' in st.session_state and st.session_state['mode'] == 'content':
    st.markdown("### 📝 GEO Content Generation")
    st.caption("Generate citation-optimized content for zero-citation queries")

    # API key inputs
    col1, col2 = st.columns(2)
    with col1:
        nvidia_key = st.text_input("NVIDIA API Key", type="password", key="nvidia_key")
    with col2:
        openai_key = st.text_input("OpenAI API Key", type="password", key="openai_key")

    max_queries = st.slider("Max queries to process", 1, 10, 5, key="max_content_queries")

    if st.button("🚀 Generate GEO Content", type="primary"):
        if not nvidia_key and not openai_key:
            st.error("Please provide at least one API key (NVIDIA or OpenAI)")
        else:
            # Set environment variables
            if nvidia_key:
                os.environ["NVIDIA_API_KEY"] = nvidia_key
            if openai_key:
                os.environ["OPENAI_API_KEY"] = openai_key

            with st.spinner(f"Generating content for up to {max_queries} queries…"):
                ok, msg, results = run_content_generation(max_queries=max_queries)
            if ok:
                st.session_state['content_results'] = results
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

    # Clear mode after handling
    if 'mode' in st.session_state:
        del st.session_state['mode']

# Handle content structuring mode
if 'mode' in st.session_state and st.session_state['mode'] == 'structuring':
    st.markdown("### 🔧 GEO Content Structuring")
    st.caption("Analyze and validate content quality with GEO structuring rules")

    if st.button("🔧 Run Content Structuring", type="primary"):
        with st.spinner("Analyzing and structuring content…"):
            ok, msg, results = run_content_structuring()
        if ok:
            st.session_state['structuring_results'] = results
            st.success(msg)
            st.rerun()
        else:
            st.error(msg)

    # Clear mode after handling
    if 'mode' in st.session_state:
        del st.session_state['mode']

# Handle validation and scoring mode
if 'mode' in st.session_state and st.session_state['mode'] == 'validation':
    st.markdown("### 🧪 Validation and Scoring")
    st.caption("Test whether generated GEO content actually improves citation scores")

    if st.button("🧪 Run Validation", type="primary"):
        with st.spinner("Validating content effectiveness…"):
            ok, msg, results = run_validation_scoring()
        if ok:
            st.session_state['validation_results'] = results
            st.success(msg)
            st.rerun()
        else:
            st.error(msg)

    # Clear mode after handling
    if 'mode' in st.session_state:
        del st.session_state['mode']

# ============================================================
# MAIN CONTENT
# ============================================================

# Determine current mode based on session state
current_mode = None
if 'comparison_results' in st.session_state:
    current_mode = 'comparison'
elif 'website_results' in st.session_state:
    current_mode = 'website'
elif 'pattern_results' in st.session_state:
    current_mode = 'pattern'
elif 'content_results' in st.session_state:
    current_mode = 'content'
elif 'structuring_results' in st.session_state:
    current_mode = 'structuring'
elif 'validation_results' in st.session_state:
    current_mode = 'validation'
elif chosen_file is not None:
    current_mode = 'single_analysis'

# ── Mode Selector (when no specific results are active) ──────
if current_mode is None:
    st.title("🎯 GEO Agent Dashboard")
    st.markdown("Choose your analysis type:")

    # first row: core analytics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown("### 🚀 Single Provider Analysis")
        st.caption("Analyze results from one AI provider")
        if st.button("View Single Analysis", width='stretch'):
            st.session_state['mode'] = 'single'
            st.rerun()

    with col2:
        st.markdown("### ⚖️ Compare Providers")
        st.caption("Compare multiple AI providers side-by-side")
        if st.button("Start Comparison", width='stretch'):
            st.session_state['mode'] = 'comparison'
            st.rerun()

    with col3:
        st.markdown("### 🌐 Website Analysis")
        st.caption("Analyze citation patterns on websites")
        if st.button("Analyze Website", width='stretch'):
            st.session_state['mode'] = 'website'
            st.rerun()

    with col4:
        st.markdown("### 📊 Pattern Analysis")
        st.caption("Analyze citation patterns across all runs")
        if st.button("Run Pattern Analysis", width='stretch'):
            st.session_state['mode'] = 'pattern'
            st.rerun()

    st.markdown("---")

    # second row: content pipeline and validation
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown("### 📝 Content Generator")
        st.caption("Generate GEO-optimized content")
        if st.button("Generate Content", width='stretch'):
            st.session_state['mode'] = 'content'
            st.rerun()

    with col2:
        st.markdown("### 🔧 Content Structurer")
        st.caption("Structure and validate content quality")
        if st.button("Structure Content", width='stretch'):
            st.session_state['mode'] = 'structuring'
            st.rerun()

    with col3:
        st.markdown("### 🧪 Validation & Scoring")
        st.caption("Test content effectiveness on citations")
        if st.button("Validate Content", width='stretch'):
            st.session_state['mode'] = 'validation'
            st.rerun()

    with col4:
        st.empty()

    st.stop()

# ── Display Comparison Results ──────────────────────────────
if current_mode == 'comparison' and 'comparison_results' in st.session_state:
    comparison_results = st.session_state['comparison_results']
    comparison_time = st.session_state.get('comparison_time', 0)

    st.title("⚖️ Provider Comparison Results")
    st.caption(f"Comparison completed in {comparison_time:.1f} seconds across {len(comparison_results)} providers")

    # Create comparison dataframe
    comparison_data = []
    for provider, result in comparison_results.items():
        provider_time = result.get("time", 0.0)
        if result["success"]:
            m = result["metrics"]
            comparison_data.append({
                "Provider": provider.upper(),
                "Success Rate": m["success_pct"],
                "Avg Citations": m["avg_cites"],
                "Avg Quality": m["avg_quality"],
                "Unique Domains": m["unique_domains"],
                "Total Cost": m["cost"],
                "Total Tokens": m["tokens"],
                "Time (s)": provider_time
            })
        else:
            comparison_data.append({
                "Provider": provider.upper(),
                "Success Rate": 0,
                "Avg Citations": 0,
                "Avg Quality": 0,
                "Unique Domains": 0,
                "Total Cost": 0,
                "Total Tokens": 0,
                "Time (s)": provider_time,
                "Error": result.get("error", "Failed")
            })

    df_comp = pd.DataFrame(comparison_data)

    # Ranking based on quality score
    successful_providers = df_comp[df_comp["Success Rate"] > 0]
    if not successful_providers.empty:
        ranking = successful_providers.sort_values("Avg Quality", ascending=False)
        st.markdown("### 🏆 Provider Rankings")
        st.caption("Ranked by citation quality score (higher is better)")

        cols = st.columns(len(ranking))
        for i, (_, row) in enumerate(ranking.iterrows()):
            with cols[i]:
                st.metric(
                    f"#{i+1} {row['Provider']}",
                    f"{row['Avg Quality']:.2f}",
                    f"{row['Success Rate']:.0f}% success"
                )

    # Comparison table
    st.markdown("### 📋 Detailed Comparison")
    st.dataframe(
        df_comp,
        width='stretch',
        hide_index=True,
        column_config={
            "Avg Quality": st.column_config.ProgressColumn("Quality Score", min_value=0, max_value=1),
            "Success Rate": st.column_config.NumberColumn(format="%.1f%%"),
            "Total Cost": st.column_config.NumberColumn(format="$%.4f"),
            "Time (s)": st.column_config.NumberColumn(format="%.1f s")
        }
    )

    # Clear comparison results
    if st.button("← Back to Main Menu"):
        del st.session_state['comparison_results']
        if 'comparison_time' in st.session_state:
            del st.session_state['comparison_time']
        st.rerun()

    # Export comparison results
    if st.button("📊 Export Comparison Report"):
        csv_data = df_comp.to_csv(index=False)
        st.download_button(
            label="Download CSV",
            data=csv_data,
            file_name=f"geo_comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )

    st.stop()  # Don't show other content when in comparison mode

# ── Display Website Analysis Results ────────────────────────
if current_mode == 'website' and 'website_results' in st.session_state:
    website_results = st.session_state['website_results']

    st.title("🌐 Website Analysis Results")
    st.caption(f"Analysis of: {website_results['url']}")

    if website_results["success"]:
        cit = website_results["citations"]

        # Website metrics
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Word Count", f"{website_results['word_count']:,}")
        col2.metric("Citation Count", cit["citation_count"])
        col3.metric("Quality Score", f"{website_results['quality_score']:.2f}")
        col4.metric("Unique Domains", len(cit["domains"]))

        # Citation details
        st.markdown("### 🔗 Citation Analysis")

        c1, c2 = st.columns(2)

        with c1:
            st.markdown("**Domains Referenced:**")
            if cit["domains"]:
                for domain in cit["domains"][:10]:
                    st.code(domain)
            else:
                st.info("No external domains found")

        with c2:
            st.markdown("**Cement Brands Mentioned:**")
            if cit["cement_brands"]:
                brands_html = " ".join(
                    f'<span class="brand-pill">{b}</span>' for b in cit["cement_brands"]
                )
                st.markdown(brands_html, unsafe_allow_html=True)
            else:
                st.info("No cement brands detected")

        # Reference phrases
        if cit["reference_phrases"]:
            st.markdown("**Reference Phrases:**")
            for phrase in cit["reference_phrases"]:
                st.markdown(f"- _{phrase.strip()}_")

        # Raw data
        with st.expander("Raw Citation Data"):
            st.json(cit)

    else:
        st.error(f"Analysis failed: {website_results.get('error', 'Unknown error')}")

    # Clear website results
    if st.button("← Back to Main Menu"):
        del st.session_state['website_results']
        st.rerun()

    # Export website analysis (only if successful)
    if website_results["success"] and st.button("📊 Export Website Report"):
        report_data = {
            "url": website_results["url"],
            "analysis_date": datetime.now().isoformat(),
            "metrics": {
                "word_count": website_results["word_count"],
                "citation_count": website_results["citations"]["citation_count"],
                "quality_score": website_results["quality_score"],
                "unique_domains": len(website_results["citations"]["domains"])
            },
            "citations": website_results["citations"]
        }
        json_data = json.dumps(report_data, indent=2)
        st.download_button(
            label="Download JSON Report",
            data=json_data,
            file_name=f"website_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json"
        )

    st.stop()  # Don't show other content when in website mode

# ── Display Pattern Analysis Results ───────────────────────
if current_mode == 'pattern' and 'pattern_results' in st.session_state:
    pattern_report = st.session_state['pattern_results']

    st.title("📊 Pattern Analysis Results")
    st.caption(f"Analysis generated at {pattern_report.get('generated_at', 'unknown')}")

    # Back button
    if st.button("← Back to Main Menu"):
        del st.session_state['pattern_results']
        st.rerun()

    # Overview metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Runs Analyzed", pattern_report.get("runs_analysed", 0))
    with col2:
        st.metric("Total Queries", pattern_report.get("total_queries", 0))
    with col3:
        st.metric("Unique Brands", len(pattern_report.get("brand_frequency", {})))
    with col4:
        st.metric("GEO Opportunities", len(pattern_report.get("geo_gap_analysis", {}).get("zero_citation_queries", [])))

    st.markdown("---")

    # Brand frequency
    st.markdown("### 🏆 Top Cement Brands")
    brands = pattern_report.get("brand_frequency", {})
    if brands:
        # Top 10 brands chart
        top_brands = dict(list(brands.items())[:10])
        st.bar_chart(top_brands)
    else:
        st.info("No brand data available")

    # Domain frequency
    st.markdown("### 🌐 Top Cited Domains")
    domains = pattern_report.get("domain_frequency", {})
    if domains:
        top_domains = dict(list(domains.items())[:10])
        st.bar_chart(top_domains)
    else:
        st.info("No domain data available")

    # Provider comparison
    st.markdown("### ⚖️ Provider Performance")
    providers = pattern_report.get("provider_comparison", {})
    if providers:
        provider_data = []
        for provider, stats in providers.items():
            provider_data.append({
                "Provider": provider.upper(),
                "Success Rate": f"{stats.get('successful_queries', 0)}/{stats.get('total_queries', 0)}",
                "Avg Citations": stats.get("avg_citations", 0),
                "Avg Quality": stats.get("avg_quality", 0),
                "Top Brands": ", ".join(list(stats.get("brand_counts", {}).keys())[:3])
            })
        st.dataframe(pd.DataFrame(provider_data), width='stretch', hide_index=True)
    else:
        st.info("No provider comparison data available")

    # Category performance
    st.markdown("### 📂 Query Category Performance")
    categories = pattern_report.get("category_performance", {})
    if categories:
        category_data = []
        for category, stats in categories.items():
            category_data.append({
                "Category": category.replace("_", " ").title(),
                "Queries": stats.get("total_queries", 0),
                "Success Rate": f"{stats.get('successful_queries', 0)}/{stats.get('total_queries', 0)}",
                "Avg Citations": stats.get("avg_citations", 0),
                "Avg Quality": stats.get("avg_quality", 0)
            })
        st.dataframe(pd.DataFrame(category_data), width='stretch', hide_index=True)
    else:
        st.info("No category performance data available")

    # Citation trends
    st.markdown("### 📈 Citation Quality Trends")
    trends = pattern_report.get("citation_trend", [])
    if trends:
        trend_df = pd.DataFrame(trends)
        if not trend_df.empty:
            # Convert timestamp to datetime for better display
            trend_df['timestamp'] = pd.to_datetime(trend_df['timestamp'])
            trend_df = trend_df.sort_values('timestamp')

            # Quality score over time
            st.line_chart(trend_df.set_index('timestamp')['avg_quality_score'])
    else:
        st.info("No trend data available")

    # GEO gap analysis
    st.markdown("### 🎯 GEO Opportunities")
    geo_gaps = pattern_report.get("geo_gap_analysis", {})
    zero_queries = geo_gaps.get("zero_citation_queries", [])
    low_queries = geo_gaps.get("low_citation_queries", [])

    if zero_queries:
        st.success(f"Found {len(zero_queries)} queries with ZERO citations across all providers")
        st.markdown("**Queries needing citation optimization:**")
        for i, query_data in enumerate(zero_queries[:10], 1):  # Show first 10
            st.markdown(f"{i}. {query_data['query']}")
        if len(zero_queries) > 10:
            st.caption(f"... and {len(zero_queries) - 10} more")
    else:
        st.info("No GEO opportunities found - all queries have citations!")

    if low_queries:
        st.warning(f"Found {len(low_queries)} queries with low citation counts (< 1 average)")

    # Export pattern analysis
    if st.button("📊 Export Pattern Report"):
        json_data = json.dumps(pattern_report, indent=2)
        st.download_button(
            label="Download JSON",
            data=json_data,
            file_name=f"pattern_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json"
        )

    st.stop()  # Don't show other content when in pattern mode

# ── Display Content Generation Results ─────────────────────
if current_mode == 'content' and 'content_results' in st.session_state:
    content_results = st.session_state['content_results']

    st.title("📝 GEO Content Generation Results")
    st.caption(f"Generated at {content_results.get('generated_at', 'unknown')}")

    # Back button
    if st.button("← Back to Main Menu"):
        del st.session_state['content_results']
        st.rerun()

    # Overview metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Queries Processed", content_results.get("total_queries_processed", 0))
    with col2:
        st.metric("Successful", content_results.get("successful_generations", 0))
    with col3:
        st.metric("Failed", content_results.get("failed_generations", 0))
    with col4:
        generated_content = content_results.get("generated_content", [])
        successful_content = [item for item in generated_content if "error" not in item]
        total_words = sum(item.get("word_count", 0) for item in successful_content)
        st.metric("Total Words", total_words)

    st.markdown("---")

    # Display generated content
    st.markdown("### 📄 Generated Articles")

    for i, item in enumerate(generated_content, 1):
        if "error" in item:
            st.error(f"❌ Query {i}: {item['query'][:60]}... - {item['error']}")
            continue

        with st.expander(f"📝 Article {i}: {item['query'][:60]}...", expanded=(i==1)):
            st.markdown(f"**Query:** {item['query']}")
            st.markdown(f"**Word Count:** {item.get('word_count', 0)}")
            st.markdown(f"**Provider:** {item.get('provider_used', 'unknown')}")

            # Brands and domains
            col1, col2 = st.columns(2)
            with col1:
                brands = item.get('target_brands', [])
                if brands:
                    st.markdown("**🏷️ Brands Mentioned:**")
                    st.write(", ".join(brands))
                else:
                    st.info("No brands detected")

            with col2:
                domains = item.get('domains_referenced', [])
                if domains:
                    st.markdown("**🌐 Domains Referenced:**")
                    st.write(", ".join(domains))
                else:
                    st.info("No domains referenced")

            st.markdown("---")
            st.markdown("**📝 Generated Content:**")
            st.markdown(item['generated_content'])

    # Export content
    if st.button("📊 Export Generated Content"):
        json_data = json.dumps(content_results, indent=2)
        st.download_button(
            label="Download JSON",
            data=json_data,
            file_name=f"geo_content_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json"
        )

    st.stop()  # Don't show other content when in content mode

# ── Display Content Structuring Results ────────────────────
if current_mode == 'structuring' and 'structuring_results' in st.session_state:
    structuring_results = st.session_state['structuring_results']

    st.title("🔧 GEO Content Structuring Results")
    st.caption(f"Analysis completed at {structuring_results.get('structured_at', 'unknown')}")

    # Back button
    if st.button("← Back to Main Menu"):
        del st.session_state['structuring_results']
        st.rerun()

    # Overview metrics
    structured_content = structuring_results.get("structured_content", [])
    valid_items = [item for item in structured_content if "error" not in item.get("structuring_report", {})]

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Items", len(structured_content))
    with col2:
        st.metric("Valid Content", len(valid_items))
    with col3:
        passed_all = sum(1 for item in valid_items
                        if item.get("structuring_report", {}).get("passed_checks", 0) ==
                        item.get("structuring_report", {}).get("total_checks", 0))
        st.metric("Passed All Checks", passed_all)
    with col4:
        if valid_items:
            geo_scores = [item.get("structuring_report", {}).get("geo_score", 0.0) for item in valid_items]
            avg_score = sum(geo_scores) / len(geo_scores)
            st.metric("Avg GEO Score", f"{avg_score:.2f}")
        else:
            st.metric("Avg GEO Score", "0.00")

    st.markdown("---")

    # Display structured content
    st.markdown("### 📄 Structured Content Analysis")

    for i, item in enumerate(structured_content, 1):
        if "error" in item.get("structuring_report", {}):
            st.error(f"❌ Item {i}: {item.get('query', 'unknown')[:60]}... - Content generation failed")
            continue

        report = item.get("structuring_report", {})
        geo_score = report.get("geo_score", 0.0)
        passed_checks = report.get("passed_checks", 0)
        total_checks = report.get("total_checks", 0)

        # Color coding based on GEO score
        if geo_score >= 0.8:
            status_icon = "✅"
            status_color = "green"
        elif geo_score >= 0.6:
            status_icon = "⚠️"
            status_color = "orange"
        else:
            status_icon = "❌"
            status_color = "red"

        with st.expander(f"{status_icon} Item {i}: {item.get('query', 'unknown')[:60]}... (GEO: {geo_score:.2f})", expanded=(i==1)):
            st.markdown(f"**Query:** {item['query']}")
            st.markdown(f"**GEO Score:** {geo_score:.2f}/1.0")
            st.markdown(f"**Checks Passed:** {passed_checks}/{total_checks}")

            # Show check results
            checks = report.get("checks", [])
            if checks:
                st.markdown("**Quality Checks:**")
                for check in checks:
                    check_icon = "✅" if check.get("passed", False) else "❌"
                    st.markdown(f"- {check_icon} **{check['check'].replace('_', ' ').title()}**: {check.get('suggestion', 'OK')}")
                    if not check.get("passed", False) and check.get("suggestion"):
                        st.caption(f"💡 {check['suggestion']}")

            # Show content preview
            content = item.get("generated_content", "")
            if content:
                st.markdown("**Content Preview:**")
                preview = content[:300] + "..." if len(content) > 300 else content
                st.text_area("Content", preview, height=100, disabled=True)

            # Show metadata
            col1, col2 = st.columns(2)
            with col1:
                brands = item.get("target_brands", [])
                if brands:
                    st.markdown("**🏷️ Brands:**")
                    st.write(", ".join(brands))
            with col2:
                domains = item.get("domains_referenced", [])
                if domains:
                    st.markdown("**🌐 Domains:**")
                    st.write(", ".join(domains))

    # Summary insights
    if valid_items:
        st.markdown("---")
        st.markdown("### 📊 Structuring Insights")

        # Most common issues
        all_issues = []
        for item in valid_items:
            report = item.get("structuring_report", {})
            needs_improvement = report.get("needs_improvement", [])
            all_issues.extend([check["check"] for check in needs_improvement])

        if all_issues:
            from collections import Counter
            issue_counts = Counter(all_issues)
            st.markdown("**Most Common Issues:**")
            for issue, count in issue_counts.most_common(3):
                st.markdown(f"- **{issue.replace('_', ' ').title()}**: {count} items need improvement")

        # GEO score distribution
        geo_scores = [item.get("structuring_report", {}).get("geo_score", 0.0) for item in valid_items]
        score_ranges = {
            "Excellent (0.8-1.0)": len([s for s in geo_scores if s >= 0.8]),
            "Good (0.6-0.8)": len([s for s in geo_scores if 0.6 <= s < 0.8]),
            "Needs Work (0-0.6)": len([s for s in geo_scores if s < 0.6])
        }

        st.markdown("**GEO Score Distribution:**")
        for range_name, count in score_ranges.items():
            if count > 0:
                st.markdown(f"- {range_name}: {count} items")

    # Export structuring results
    if st.button("📊 Export Structuring Report"):
        json_data = json.dumps(structuring_results, indent=2)
        st.download_button(
            label="Download JSON",
            data=json_data,
            file_name=f"structured_content_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json"
        )

    st.stop()  # Don't show other content when in structuring mode

# ── Display Validation and Scoring Results ──────────────────
if current_mode == 'validation' and 'validation_results' in st.session_state:
    validation_results = st.session_state['validation_results']

    st.title("🧪 Validation and Scoring Results")
    st.caption("Testing whether GEO content actually improves citation scores")

    if "error" in validation_results:
        st.error(f"❌ Validation failed: {validation_results['error']}")
        st.stop()

    # Summary metrics
    summary = validation_agent.generate_summary_report(validation_results)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Queries Validated", summary.get("total_validated", 0))
    with col2:
        st.metric("Average Improvement", f"{summary.get('average_improvement', 0.0):+.3f}")
    with col3:
        st.metric("Success Rate", f"{summary.get('success_rate', 0.0):.1%}")
    with col4:
        st.metric("Best Improvement", f"{summary.get('best_improvement', 0.0):+.3f}")

    # Verdict distribution
    st.subheader("📊 Validation Results")
    verdicts = summary.get("verdict_distribution", {})

    verdict_data = pd.DataFrame({
        "Verdict": ["Improved", "No Change", "Degraded"],
        "Count": [verdicts.get("improved", 0), verdicts.get("no_change", 0), verdicts.get("degraded", 0)]
    })

    st.bar_chart(verdict_data.set_index("Verdict"))

    # Detailed results table
    st.subheader("📋 Detailed Validation Results")

    results_data = validation_results.get("validation_results", [])
    valid_results = [r for r in results_data if "validation_error" not in r]

    if valid_results:
        table_data = []
        for result in valid_results:
            table_data.append({
                "Query": result["query"][:50] + "..." if len(result["query"]) > 50 else result["query"],
                "Baseline Score": f"{result['baseline_citation_score']:.2f}",
                "New Score": f"{result['new_citation_score']:.2f}",
                "Improvement": f"{result['improvement']:+.3f}",
                "Verdict": result["verdict"].replace("_", " ").title()
            })

        st.dataframe(pd.DataFrame(table_data), use_container_width=True)

        # Best performing query
        if summary.get("best_query"):
            st.subheader("🏆 Best Performing Query")
            st.markdown(f"**Query:** {summary['best_query']}")
            st.markdown(f"**Improvement:** {summary['best_improvement']:+.3f}")

            # Show the enriched response for the best query
            best_result = max(valid_results, key=lambda x: x["improvement"])
            if best_result.get("enriched_response"):
                with st.expander("View Enriched Response"):
                    st.markdown(best_result["enriched_response"])

    # Export validation results
    if st.button("📊 Export Validation Report"):
        json_data = json.dumps(validation_results, indent=2)
        st.download_button(
            label="Download JSON",
            data=json_data,
            file_name=f"validation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json"
        )

    st.stop()  # Don't show other content when in validation mode

# ── Single File Analysis ────────────────────────────────────
if current_mode == 'single_analysis' and chosen_file is not None:
    data = load_file(chosen_file)
    if data is None or len(data) == 0:
        st.warning(
            "The selected file is empty or could not be read. "
            "If this run had all failures, rerun pipeline with a valid API key or check the corresponding failures_*.json file."
        )
        st.stop()

    summary_data = load_summary_for(chosen_file)
    metrics = compute_metrics(data)

    # ── Show failed query details if present ─────────────────────
    failed_records = [r for r in data if r.get("error")]
    if failed_records:
        st.warning(f"{len(failed_records)} query(ies) failed. See details below.")
        # build a compact table
        st.table([
            {
                "query": r.get("query", ""),
                "error": r.get("error", ""),
                "details": r.get("error_details", ""),
            }
            for r in failed_records
        ])

    # ── Page title + file info ───────────────────────────────────
    provider_name = (data[0].get("engine") or data[0].get("provider") or "unknown").upper()
    run_time = datetime.fromtimestamp(chosen_file.stat().st_mtime).strftime("%d %b %Y, %H:%M")

    st.title(f"🎯 GEO Analysis — {provider_name}")
    st.caption(f"File: `{chosen_file.name}`  ·  Run at: {run_time}  ·  {metrics['total']} queries")

    # Back button for single analysis
    if st.button("← Back to Main Menu"):
        # Clear file selection
        chosen_file = None
        st.rerun()

    # Export single analysis
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("📊 Export Report"):
            report_data = {
                "provider": provider_name,
                "run_time": run_time,
                "metrics": metrics,
                "data": data
            }
            json_data = json.dumps(report_data, indent=2)
            st.download_button(
                label="Download JSON",
                data=json_data,
                file_name=f"geo_analysis_{provider_name.lower()}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json"
            )

# ============================================================
# SECTION 1 — TOP METRICS
# ============================================================

st.markdown("---")
st.markdown("### 📊 Run Summary")
st.caption("High-level stats for this pipeline run.")

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Queries", metrics["total"])
c2.metric("Success Rate", f"{metrics['success_pct']:.0f}%",
          delta=f"{metrics['ok']} ok / {metrics['failed']} failed",
          delta_color="normal" if metrics['failed'] == 0 else "inverse")
c3.metric("Total Cost", f"${metrics['cost']:.4f}")
c4.metric("Total Tokens", f"{metrics['tokens']:,}")
c5.metric("Avg Quality Score", f"{metrics['avg_quality']:.2f}",
          help="Citation quality 0–1 based on authority domains, brands, reference phrases")

# ============================================================
# SECTION 2 — CITATION OVERVIEW
# ============================================================

st.markdown("---")
st.markdown("### 🔗 Citation Overview")
st.caption(
    "A **citation** is any URL, domain, or reference phrase found in the AI's response. "
    "Higher citation rates mean the AI is actively referencing sources — a key GEO signal."
)

ca, cb, cc, cd = st.columns(4)
ca.metric("Responses with Citations", f"{metrics['with_cites']} / {metrics['total']}")
cb.metric("Avg Citations per Response", f"{metrics['avg_cites']:.1f}")
cc.metric("Unique Domains Cited",       metrics["unique_domains"])
cd.metric("Cement Brands Detected",     len(metrics["brand_counts"]))

# Charts row
if metrics["domain_counts"] or metrics["brand_counts"]:
    ch1, ch2 = st.columns(2)

    with ch1:
        st.markdown("**Top Cited Domains**")
        if metrics["domain_counts"]:
            top_domains = dict(sorted(metrics["domain_counts"].items(),
                                      key=lambda x: x[1], reverse=True)[:10])
            df_d = pd.DataFrame({"Domain": list(top_domains.keys()),
                                  "Mentions": list(top_domains.values())})
            st.bar_chart(df_d.set_index("Domain"), height=260)
        else:
            st.info("No domain citations found in this run.")

    with ch2:
        st.markdown("**Brand Mentions**")
        if metrics["brand_counts"]:
            top_brands = dict(sorted(metrics["brand_counts"].items(),
                                     key=lambda x: x[1], reverse=True)[:10])
            df_b = pd.DataFrame({"Brand": list(top_brands.keys()),
                                  "Mentions": list(top_brands.values())})
            st.bar_chart(df_b.set_index("Brand"), height=260)
        else:
            st.info("No cement brand mentions found in this run.")

# ============================================================
# SECTION 2.1 — SERP & GEO ANALYSIS
# ============================================================

st.markdown("---")
st.markdown("### 🔍 SERP & GEO Analysis")
st.caption(
    "**SERP** = Search Engine Results Pages (what Google shows for the query). "
    "**GEO Score** = How well AI citations match actual search rankings (0–1). "
    "Higher GEO scores indicate the AI cites sources that actually rank on Google."
)

if metrics["with_serp"] > 0:
    ga, gb, gc, gd = st.columns(4)
    ga.metric("Queries with SERP Data", f"{metrics['with_serp']} / {metrics['total']}")
    gb.metric("Queries with GEO Analysis", f"{metrics['with_geo']} / {metrics['total']}")
    gc.metric("Avg GEO Score", f"{metrics['avg_geo_score']:.2f}",
              help="0–1 scale: how well citations match SERP rankings")
    gd.metric("Avg SERP Coverage", f"{metrics['avg_serp_coverage']:.1f}%",
              help="What % of ranking domains are cited by AI")

    # GEO Score distribution
    if metrics["with_geo"] > 0:
        st.markdown("**GEO Score Distribution**")
        geo_scores = [r.get("geo_analysis", {}).get("overlap_analysis", {}).get("geo_score", 0) 
                     for r in data if r.get("geo_analysis")]
        
        if geo_scores:
            geo_bins = {"0.0": 0, "0.1–0.3": 0, "0.4–0.6": 0, "0.7–0.9": 0, "1.0": 0}
            for score in geo_scores:
                if score == 0:
                    geo_bins["0.0"] += 1
                elif score <= 0.3:
                    geo_bins["0.1–0.3"] += 1
                elif score <= 0.6:
                    geo_bins["0.4–0.6"] += 1
                elif score < 1.0:
                    geo_bins["0.7–0.9"] += 1
                else:
                    geo_bins["1.0"] += 1
            
            df_geo = pd.DataFrame({"GEO Score Band": list(geo_bins.keys()), "Count": list(geo_bins.values())})
            st.bar_chart(df_geo.set_index("GEO Score Band"), height=200)
else:
    st.info("No SERP/GEO data found. Run pipeline with SERP API key to enable this analysis.")

st.markdown("---")
st.markdown("### 💰 Cost Optimization Insights")
st.caption("Smart recommendations to improve citation quality while managing costs.")

# Calculate cost efficiency metrics
cost_per_quality = metrics["cost"] / max(metrics["avg_quality"], 0.01)
cost_per_citation = metrics["cost"] / max(metrics["with_cites"], 1)

col_opt1, col_opt2, col_opt3 = st.columns(3)

with col_opt1:
    st.metric(
        "Cost per Quality Point",
        f"${cost_per_quality:.4f}",
        help="Dollars spent per 0.1 quality score improvement"
    )

with col_opt2:
    st.metric(
        "Cost per Citation",
        f"${cost_per_citation:.4f}",
        help="Average cost for responses with citations"
    )

with col_opt3:
    efficiency_score = min(1.0, metrics["avg_quality"] / max(metrics["cost"], 0.01) * 100)
    st.metric(
        "Quality Efficiency",
        f"{efficiency_score:.1f}%",
        help="Quality score relative to cost (higher is better)"
    )

# Recommendations
st.markdown("**💡 Recommendations:**")
recs = []

if metrics["success_pct"] < 80:
    recs.append("• Consider using a more reliable provider or model for better success rates")

if cost_per_quality > 0.01:
    recs.append("• Try cheaper models with similar quality (e.g., GPT-4o-mini vs GPT-4o)")

if metrics["avg_quality"] < 0.5:
    recs.append("• Focus on queries that tend to generate more citations")

if len(recs) == 0:
    recs.append("• Your current setup is well-optimized! 🎉")

for rec in recs:
    st.markdown(rec)

# ============================================================
# SECTION 3 — QUERY RESULTS TABLE
# ============================================================

st.markdown("---")
st.markdown("### 📋 All Query Results")
st.caption("Each row is one query sent to the AI. Click a column header to sort.")

rows = []
for i, r in enumerate(data):
    c = r.get("citations", {})
    geo = r.get("geo_analysis", {}).get("overlap_analysis", {})
    rows.append({
        "#":         i + 1,
        "Query":     r.get("query", ""),
        "Status":    "✅" if not r.get("error") else "❌",
        "Citations": c.get("citation_count", 0),
        "Domains":   len(c.get("domains", [])),
        "Brands":    len(c.get("cement_brands", [])),
        "Quality":   get_quality(c),
        "GEO Score": geo.get("geo_score", 0),
        "SERP Overlap": geo.get("overlap_count", 0),
        "Tokens":    r.get("usage", {}).get("total_tokens", 0),
        "Cost ($)":  round(r.get("cost", 0), 5),
    })

df = pd.DataFrame(rows)
st.dataframe(
    df,
    width='stretch',
    hide_index=True,
    column_config={
        "Quality": st.column_config.ProgressColumn(
            "Quality Score", min_value=0, max_value=1, format="%.2f"
        ),
        "GEO Score": st.column_config.ProgressColumn(
            "GEO Score", min_value=0, max_value=1, format="%.2f",
            help="How well citations match SERP rankings"
        ),
        "Cost ($)": st.column_config.NumberColumn(format="$%.5f"),
        "Query": st.column_config.TextColumn(width="large"),
    }
)

# ============================================================
# SECTION 4 — QUERY DEEP DIVE
# ============================================================

st.markdown("---")
st.markdown("### 🔍 Query Deep Dive")
st.caption("Inspect the full AI response and all extracted citation data for any query.")

query_labels = [f"{i+1}. {r.get('query','')[:70]}" for i, r in enumerate(data)]
selected_label = st.selectbox("Select a query", query_labels)
idx = query_labels.index(selected_label)
r = data[idx]
cit = r.get("citations", {})

col_left, col_right = st.columns([3, 2])

with col_left:
    st.markdown(f"**Query:** {r.get('query','')}")
    st.markdown("**AI Response:**")
    response_text = r.get("response") or "_No response recorded_"
    st.text_area("AI Response", value=response_text, height=280, disabled=True, label_visibility="collapsed")

    if r.get("error"):
        st.error(f"Error: {r['error']}")

with col_right:
    st.markdown("**Run Metadata**")
    meta_cols = st.columns(2)
    meta_cols[0].metric("Engine",  r.get("engine") or r.get("provider", "—"))
    meta_cols[0].metric("Tokens",  get_tokens(r))
    meta_cols[1].metric("Model",   (r.get("model") or "—")[-20:])
    meta_cols[1].metric("Cost",    f"${r.get('cost', 0):.5f}")

    # SERP/GEO Analysis
    if r.get("geo_analysis"):
        geo = r.get("geo_analysis", {})
        overlap = geo.get("overlap_analysis", {})
        
        st.markdown("**GEO Analysis**")
        geo_cols = st.columns(2)
        geo_cols[0].metric("GEO Score", f"{overlap.get('geo_score', 0):.2f}")
        geo_cols[0].metric("Domain Overlap", overlap.get("overlap_count", 0))
        geo_cols[1].metric("SERP Coverage", f"{overlap.get('serp_coverage', 0):.1%}")
        geo_cols[1].metric("Citation Coverage", f"{overlap.get('citation_coverage', 0):.1%}")

    st.markdown("**Citations Extracted**")
    if cit:
        st.metric("Citation Count",  cit.get("citation_count", 0))
        st.metric("Quality Score",   f"{get_quality(cit):.2f} / 1.00")

        if cit.get("domains"):
            st.markdown("*Domains:*")
            st.code(", ".join(cit["domains"]))

        if cit.get("cement_brands"):
            st.markdown("*Brands detected:*")
            brands_html = " ".join(
                f'<span class="brand-pill">{b}</span>' for b in cit["cement_brands"]
            )
            st.markdown(brands_html, unsafe_allow_html=True)

        if cit.get("reference_phrases"):
            st.markdown("*Reference phrases:*")
            for phrase in cit["reference_phrases"]:
                st.markdown(f"- _{phrase}_")

        with st.expander("Raw citation JSON"):
            st.json(cit)
    else:
        st.info("No citation data for this response.")

    # SERP and GEO details
    if r.get("serp"):
        with st.expander("SERP Results"):
            serp = r.get("serp", {})
            st.markdown(f"**Query:** {serp.get('query', '')}")
            st.markdown(f"**Total Results:** {serp.get('total_results', 0):,}")
            st.markdown(f"**Organic Domains:** {', '.join(serp.get('organic_domains', [])[:10])}")
            
            if serp.get("results"):
                st.markdown("**Top Results:**")
                for result in serp["results"][:5]:
                    st.markdown(f"- **{result['title']}** ({result['domain']})")

    if r.get("geo_analysis"):
        with st.expander("GEO Analysis Details"):
            geo = r.get("geo_analysis", {})
            overlap = geo.get("overlap_analysis", {})
            
            st.markdown("**Overlap Analysis:**")
            st.json(overlap)
            
            opportunities = geo.get("opportunities", {})
            if opportunities:
                st.markdown("**Opportunities:**")
                if opportunities.get("uncited_rankers"):
                    st.markdown(f"- **Uncitted rankers:** {', '.join(opportunities['uncited_rankers'][:5])}")
                if opportunities.get("cited_not_ranking"):
                    st.markdown(f"- **Cited but not ranking:** {', '.join(opportunities['cited_not_ranking'][:5])}")
            
            recommendations = geo.get("recommendations", [])
            if recommendations:
                st.markdown("**Recommendations:**")
                for rec in recommendations:
                    st.markdown(f"- {rec}")

# ============================================================
# SECTION 5 — QUALITY DISTRIBUTION
# ============================================================

st.markdown("---")
st.markdown("### 📈 Citation Quality Distribution")
st.caption(
    "Quality score (0–1) measures how authoritative a response's citations are. "
    "Scores above 0.5 indicate brand mentions + authority domains. "
    "0 means no meaningful citations were found."
)

quality_data = [get_quality(r.get("citations", {})) for r in data]
if any(q > 0 for q in quality_data):
    bins = {"0.0": 0, "0.1–0.3": 0, "0.4–0.6": 0, "0.7–0.9": 0, "1.0": 0}
    for q in quality_data:
        if q == 0:
            bins["0.0"] += 1
        elif q <= 0.3:
            bins["0.1–0.3"] += 1
        elif q <= 0.6:
            bins["0.4–0.6"] += 1
        elif q < 1.0:
            bins["0.7–0.9"] += 1
        else:
            bins["1.0"] += 1
    df_q = pd.DataFrame({"Quality Band": list(bins.keys()), "Count": list(bins.values())})
    st.bar_chart(df_q.set_index("Quality Band"), height=220)
else:
    st.info("All responses have a quality score of 0 — no authoritative citations detected.")

# ============================================================
# SECTION 6 — HISTORICAL TRENDS
# ============================================================

st.markdown("---")
st.markdown("### 📊 Historical Trends")
st.caption("Compare this run against your recent analysis history.")

# Get all result files for trend analysis
all_files = find_result_files()
if len(all_files) > 1:
    # Load metrics from recent files (last 10)
    trend_data = []
    for file_path in all_files[:10]:  # Most recent 10
        file_data = load_file(file_path)
        if file_data:
            file_metrics = compute_metrics(file_data)
            provider = (file_data[0].get("engine") or file_data[0].get("provider") or "unknown").upper()
            run_date = datetime.fromtimestamp(file_path.stat().st_mtime).strftime("%m/%d")

            trend_data.append({
                "Date": run_date,
                "Provider": provider,
                "Quality": file_metrics["avg_quality"],
                "Citations": file_metrics["avg_cites"],
                "Cost": file_metrics["cost"],
                "Success": file_metrics["success_pct"]
            })

    if trend_data:
        df_trend = pd.DataFrame(trend_data)

        # Quality trend chart
        st.markdown("**Quality Score Trends**")
        quality_trend = df_trend.pivot_table(
            index="Date", columns="Provider", values="Quality", aggfunc="mean"
        ).fillna(0)
        st.line_chart(quality_trend, height=200)

        # Recent runs summary
        st.markdown("**Recent Runs Summary**")
        recent_df = df_trend.head(5)[["Date", "Provider", "Quality", "Cost", "Success"]]
        st.dataframe(
            recent_df,
            width='stretch',
            hide_index=True,
            column_config={
                "Quality": st.column_config.NumberColumn(format="%.2f"),
                "Cost": st.column_config.NumberColumn(format="$%.4f"),
                "Success": st.column_config.NumberColumn(format="%.1f%%")
            }
        )
    else:
        st.info("Need more runs to show trends. Complete a few more analyses!")
else:
    st.info("Complete more analyses to see historical trends and performance patterns.")

# ── Footer ──────────────────────────────────────────────────
st.markdown("---")
st.caption(
    "GEO Agent System · Results saved to `outputs/` · "
    "Re-run with different providers to compare citation patterns across models."
)