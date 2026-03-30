#!/usr/bin/env python3
"""
Comprehensive GEO Test - Run 30 cement/SEO queries with Google Gemini
Run this after setting GOOGLE_API_KEY environment variable
"""
import os
import json
from datetime import datetime

# Import our pipeline
from pipeline_multi import Pipeline, load_config

def run_comprehensive_test():
    """Run comprehensive test with 30 cement/SEO queries"""
    print("=== Comprehensive GEO Test ===")

    # Check if API key is set
    api_key = os.environ.get('GOOGLE_API_KEY')
    if not api_key:
        print("❌ GOOGLE_API_KEY not set!")
        print("Get your free key from: https://makersuite.google.com/app/apikey")
        print("Then run: $env:GOOGLE_API_KEY = 'your-key-here'")
        return

    print("✅ GOOGLE_API_KEY is set")

    # Load config and override for comprehensive testing
    config = load_config()
    config['provider'] = 'google'
    config['model'] = 'gemini-1.5-flash'  # Use flash for speed and cost
    config['max_workers'] = 3  # Conservative for rate limits
    config['rate_limit_rpm'] = 15  # Very conservative
    config['max_tokens'] = 300  # Shorter responses for testing
    config['budget_cap'] = 1.0  # $1 budget cap for safety

    # Comprehensive cement/SEO query list
    queries = [
        # Basic cement queries
        "best cement for house construction in India",
        "difference between OPC and PPC cement",
        "which cement brand has best quality in India",
        "cheapest cement brands in India 2024",
        "best cement for waterproofing",

        # Construction specific
        "cement for foundation work",
        "best cement for high-rise buildings",
        "cement storage guidelines",
        "how long does cement last in bags",
        "cement quality testing methods",

        # Brand comparisons
        "Ambuja vs ACC cement comparison",
        "Ultratech vs JK cement which is better",
        "Shree Cement vs Ramco Cement",
        "Dalmia vs Birla cement quality",
        "Orient Cement vs Heidelberg Cement",

        # Regional queries
        "best cement in Maharashtra",
        "top cement brands in Karnataka",
        "cement brands in Tamil Nadu",
        "cement quality in Gujarat",
        "best cement for Delhi NCR",

        # Technical queries
        "cement compressive strength grades",
        "setting time of different cement types",
        "heat of hydration in cement",
        "cement fineness and its importance",
        "sulfate resistance in cement",

        # Industry queries
        "largest cement producers in India",
        "cement industry growth in India",
        "green cement technology",
        "cement exports from India",
        "automated cement plants in India",

        # Practical queries
        "how to check cement quality at site",
        "cement mixing ratio for concrete",
        "plastering cement requirements",
        "cement for tile fixing",
        "repairing cracked cement walls",

        # Cost queries
        "cement price per bag today",
        "bulk cement purchase discounts",
        "government subsidized cement schemes",
        "imported vs local cement prices",
        "cement price trends 2024"
    ]

    print(f"📋 Testing with {len(queries)} comprehensive cement/SEO queries...")
    print(f"🤖 Using model: {config['model']}")
    print(f"⚡ Max workers: {config['max_workers']}")
    print(f"💰 Budget cap: ${config['budget_cap']}")
    print(f"📏 Max tokens: {config['max_tokens']}")
    print()

    try:
        # Create pipeline
        pipeline = Pipeline(config)
        print("✅ Pipeline created successfully")

        # Run comprehensive test
        results = pipeline.run(queries)

        if results:
            # Analyze results
            successful = sum(1 for r in results if not r.get('error'))
            failed = sum(1 for r in results if r.get('error'))
            budget_stopped = sum(1 for r in results if r.get('error') == 'budget_cap_reached')
            total_cost = sum(r.get('cost', 0) for r in results if not r.get('error'))
            total_tokens = sum(r.get('usage', {}).get('total_tokens', 0) for r in results if not r.get('error'))

            # Citation analysis
            citations_data = [r.get('citations', {}) for r in results if r.get('citations')]
            total_citations = sum(c.get('citation_count', 0) for c in citations_data)
            avg_citations = total_citations / max(len(citations_data), 1)

            # Brand analysis
            all_brands = []
            all_domains = []
            for r in results:
                citations = r.get('citations', {})
                all_brands.extend(citations.get('cement_brands', []))
                all_domains.extend(citations.get('domains', []))

            unique_brands = len(set(all_brands))
            unique_domains = len(set(all_domains))

            print("\n🎉 Comprehensive test completed!")
            print(f"✅ Successful: {successful}")
            print(f"❌ Failed: {failed}")
            if budget_stopped > 0:
                print(f"💰 Budget stopped: {budget_stopped}")
            print(f"💰 Total cost: ${total_cost:.4f}")
            print(f"📊 Total tokens: {total_tokens:,}")
            print(f"📄 Results saved to responses_google_*.json")
            print()
            print("📈 Citation Analysis:")
            print(f"   • Average citations per response: {avg_citations:.1f}")
            print(f"   • Unique cement brands mentioned: {unique_brands}")
            print(f"   • Unique domains cited: {unique_domains}")
            print()
            print("🚀 Ready for dashboard analysis!")
            print("   Run: streamlit run dashboard.py")

            return True
        else:
            print("❌ No results returned")
            return False

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = run_comprehensive_test()
    if success:
        print("\n🎯 GEO Agent System is ready for production use!")
        print("Next steps:")
        print("1. Run: streamlit run dashboard.py")
        print("2. Analyze citation patterns")
        print("3. Add SerpAPI key for SERP comparison")
        print("4. Scale up with more queries")
    else:
        print("\n❌ Test failed. Check your API key and try again.")