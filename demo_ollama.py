#!/usr/bin/env python3
"""
Quick Demo with Ollama - No API Keys Required!
Shows the GEO system working with local AI models.
"""

import os
import json
from datetime import datetime
from pipeline_multi import Pipeline, load_config

def demo_with_ollama():
    """Demo the GEO system using Ollama (free, no API keys)"""
    print("🚀 GEO System Demo with Ollama")
    print("=" * 35)

    # Check if Ollama is available
    try:
        import ollama
        # Test if service is running
        ollama.chat(model='llama3.2:1b', messages=[{'role': 'user', 'content': 'test'}])
        print("✅ Ollama is running!")
    except Exception as e:
        print("❌ Ollama not available:", str(e))
        print("\nTo fix:")
        print("1. Download Ollama: https://ollama.ai/download")
        print("2. Install and run it")
        print("3. Run: ollama pull llama3.2:1b")
        print("4. Run this script again")
        return

    # Load config and set to Ollama
    config = load_config()
    config['provider'] = 'ollama'
    config['model'] = 'llama3.2:1b'
    config['max_workers'] = 1  # Sequential for demo
    config['rate_limit_rpm'] = 60  # Ollama is fast

    # Sample queries (smaller set for demo)
    demo_queries = [
        "What is Portland cement?",
        "Best cement for home construction in India",
        "Difference between OPC and PPC cement",
        "How to choose cement for foundation work"
    ]

    print(f"📋 Testing with {len(demo_queries)} queries using Ollama...")
    print(f"🤖 Model: {config['model']}")
    print()

    # Create pipeline
    pipeline = Pipeline(config)

    # Run queries
    results = []
    successful = 0
    failed = 0

    for i, query in enumerate(demo_queries, 1):
        print(f"🔄 Query {i}/{len(demo_queries)}: {query[:50]}...")
        try:
            result = pipeline.process_query(query)
            if result and not result.get('error'):
                successful += 1
                results.append(result)
                print(f"  ✅ Success - Citations: {len(result.get('citations', {}).get('cement_brands', []))} brands")
            else:
                failed += 1
                print(f"  ❌ Failed: {result.get('error', 'Unknown error')}")
        except Exception as e:
            failed += 1
            print(f"  ❌ Error: {str(e)[:50]}")

    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    responses_file = f"responses_ollama_{timestamp}.json"
    summary_file = f"summary_ollama_{timestamp}.json"

    with open(responses_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)

    # Create summary
    total_cost = sum(r.get('cost', 0) for r in results)
    total_tokens = sum(r.get('tokens', 0) for r in results)

    # Extract citation data
    all_brands = []
    all_domains = []
    for result in results:
        citations = result.get('citations', {})
        all_brands.extend(citations.get('cement_brands', []))
        all_domains.extend(citations.get('domains', []))

    summary = {
        "timestamp": timestamp,
        "provider": "ollama",
        "model": config['model'],
        "total_queries": len(demo_queries),
        "successful": successful,
        "failed": failed,
        "total_cost": total_cost,
        "total_tokens": total_tokens,
        "citation_analysis": {
            "unique_brands_found": len(set(all_brands)),
            "unique_domains_found": len(set(all_domains)),
            "all_brands": list(set(all_brands)),
            "all_domains": list(set(all_domains))
        }
    }

    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2, default=str)

    print(f"🎉 Demo completed!")  
    print(f"✅ Successful: {successful}")
    print(f"❌ Failed: {failed}")
    print(f"💰 Total cost: FREE (Ollama)")
    print(f"📊 Total tokens: {total_tokens:,}")
    print(f"🏷️ Brands found: {len(set(all_brands))}")
    print(f"🌐 Domains found: {len(set(all_domains))}")
    print()
    print("📁 Files saved:")
    print(f"  - {responses_file}")
    print(f"  - {summary_file}")
    print()
    print("🎯 Next: Try with real API keys for better results!")
    print("Run: python setup_openai.py")

if __name__ == '__main__':
    demo_with_ollama()