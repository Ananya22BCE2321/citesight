#!/usr/bin/env python3
"""
Quick Start Script for GEO Agent System
Run this to get started with the GEO system.
"""

import os
import sys

def main():
    print("🚀 GEO Agent System - Quick Start")
    print("=" * 40)

    # Check if Google API key is set
    api_key = os.environ.get('GOOGLE_API_KEY')
    if not api_key:
        print("❌ GOOGLE_API_KEY not found!")
        print()
        print("To get started:")
        print("1. Go to: https://makersuite.google.com/app/apikey")
        print("2. Create a free API key")
        print("3. Set it with: $env:GOOGLE_API_KEY = 'your-key-here'")
        print("4. Run this script again")
        return

    print("✅ GOOGLE_API_KEY found")

    # Quick quota check for Google
    if api_key:
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            # Try a minimal request to check quota
            response = client.models.generate_content(
                model='gemini-2.0-flash',
                contents='test'
            )
            print("✅ Google Gemini API working!")
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                print("⚠️  Google Gemini quota exceeded!")
                print("💡 Switching to OpenAI (more reliable)...")
                print("Run: python setup_openai.py")
                return
            else:
                print(f"❌ Google API error: {str(e)[:50]}...")
                print("💡 Try OpenAI instead: python setup_openai.py")
                return

    # Check if we want to run the comprehensive test
    if len(sys.argv) > 1 and sys.argv[1] == '--test':
        print("\n🧪 Running comprehensive test (30 queries)...")
        os.system('python test_comprehensive.py')
        return

    # Check if we want to run the dashboard
    if len(sys.argv) > 1 and sys.argv[1] == '--dashboard':
        print("\n📊 Starting dashboard...")
        os.system('streamlit run dashboard.py')
        return

    # Default: show menu
    print("\nChoose what to do:")
    print("1. Run comprehensive test (30 cement/SEO queries)")
    print("2. Start dashboard (visualize results)")
    print("3. Show system status")
    print()

    choice = input("Enter choice (1-3): ").strip()

    if choice == '1':
        print("\n🧪 Running comprehensive test...")
        os.system('python test_comprehensive.py')
    elif choice == '2':
        print("\n📊 Starting dashboard...")
        os.system('streamlit run dashboard.py')
    elif choice == '3':
        os.system('python status_check.py')
    else:
        print("Invalid choice. Run with --test or --dashboard for direct commands.")

if __name__ == '__main__':
    main()