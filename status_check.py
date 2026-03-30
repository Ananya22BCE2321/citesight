#!/usr/bin/env python3
"""
GEO Agent System Status Check
Shows what's ready and what needs to be configured.
"""

print('=== GEO Agent System Status Check ===')
print()

# Check API keys
import os
keys = ['GOOGLE_API_KEY', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'NVIDIA_API_KEY']
available = []
for key in keys:
    if os.environ.get(key):
        available.append(key.replace('_API_KEY', ''))

print('API Keys Available:', ', '.join(available) if available else 'None')
print()

# Check if Ollama is available
try:
    import ollama
    print('Ollama: ✅ Available (local models, no API key needed)')
except ImportError:
    print('Ollama: ❌ Not installed (pip install ollama)')

print()

# Check citation extraction
try:
    from agents.agent3_citation_extraction import citation_extractor
    print('Agent 3 (Citation Extraction): ✅ Ready')
except ImportError:
    print('Agent 3 (Citation Extraction): ❌ Not available')

print()

# Check SERP agent
try:
    from agents.agent4_serp_intelligence import serp_agent
    serp_key = os.environ.get('SERPAPI_API_KEY')
    if serp_key:
        print('Agent 4 (SERP Intelligence): ✅ Ready with API key')
    else:
        print('Agent 4 (SERP Intelligence): ⚠️ Ready (needs SERPAPI_API_KEY)')
except ImportError:
    print('Agent 4 (SERP Intelligence): ❌ Not available')

print()
print('=== Next Steps ===')
if not available:
    print('1. Get Google Gemini API key (free): https://makersuite.google.com/app/apikey')
    print('2. Set: $env:GOOGLE_API_KEY = "your-key"')
    print('3. Run: python test_comprehensive.py')
else:
    print('1. Run comprehensive test: python test_comprehensive.py')
    print('2. View dashboard: streamlit run dashboard.py')
    print('3. Analyze citation patterns in the results')