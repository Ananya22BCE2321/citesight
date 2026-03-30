#!/usr/bin/env python3
"""
Test Gemini API with sample cement/SEO queries
Run this after setting GOOGLE_API_KEY environment variable
"""
import os
import json
from datetime import datetime

# Import our pipeline
from pipeline_multi import Pipeline, load_config

def test_gemini_api():
    """Test Gemini API with sample queries"""
    print("=== Testing Google Gemini API ===")

    # Check if API key is set
    api_key = os.environ.get('GOOGLE_API_KEY')
    if not api_key:
        print("❌ GOOGLE_API_KEY not set!")
        print("Please set it first: $env:GOOGLE_API_KEY = 'your-key-here'")
        return

    print("✅ GOOGLE_API_KEY is set")

    # Load config and override to use Google
    config = load_config()
    config['provider'] = 'google'
    config['model'] = 'gemini-2.0-flash'  # Use flash for faster, cheaper responses
    config['max_workers'] = 2  # Keep it low for testing
    config['rate_limit_rpm'] = 30  # Conservative rate limit

    # Sample cement/SEO queries
    test_queries = [
        "best cement for house construction in India",
        "difference between OPC and PPC cement",
        "which cement brand is best for foundation work",
        "cement quality testing methods",
        "how to choose cement for high-rise buildings"
    ]

    print(f"📋 Testing with {len(test_queries)} queries...")
    print(f"🤖 Using model: {config['model']}")
    print(f"⚡ Max workers: {config['max_workers']}")
    print()

    try:
        # Create pipeline
        pipeline = Pipeline(config)
        print("✅ Pipeline created successfully")

        # Run test
        results = pipeline.run(test_queries)

        if results:
            successful = sum(1 for r in results if not r.get('error'))
            failed = sum(1 for r in results if r.get('error'))
            total_cost = sum(r.get('cost', 0) for r in results)

            print("🎉 Test completed!")
            print(f"✅ Successful: {successful}")
            print(f"❌ Failed: {failed}")
            print(f"💰 Total cost: ${total_cost:.4f}")
            print(f"📄 Results saved to responses_google_*.json")

            return True
        else:
            print("❌ No results returned")
            return False

    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

if __name__ == "__main__":
    test_gemini_api()