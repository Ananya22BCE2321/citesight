#!/usr/bin/env python3
"""
Quick Setup for OpenAI API Key
Helps you get the GEO system running with OpenAI.
"""

import os
import sys

def main():
    print("🚀 GEO System - OpenAI Setup")
    print("=" * 35)

    # Check if OpenAI key is already set
    if os.environ.get('OPENAI_API_KEY'):
        print("✅ OPENAI_API_KEY is already set!")
        test_openai()
        return

    print("To get an OpenAI API key:")
    print("1. Go to: https://platform.openai.com/api-keys")
    print("2. Sign up or log in")
    print("3. Click 'Create new secret key'")
    print("4. Copy the key (starts with 'sk-')")
    print()

    key = input("Paste your OpenAI API key: ").strip()

    if not key:
        print("❌ No key provided. Exiting.")
        return

    if not key.startswith('sk-'):
        print("❌ Invalid OpenAI key format (should start with 'sk-')")
        return

    # Set the environment variable
    os.environ['OPENAI_API_KEY'] = key
    print("✅ OPENAI_API_KEY set!")

    # Test it
    test_openai()

def test_openai():
    """Test the OpenAI API key"""
    print("\n🧪 Testing OpenAI API...")

    try:
        import openai
        client = openai.OpenAI(api_key=os.environ['OPENAI_API_KEY'])

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "Hello, what is cement?"}],
            max_tokens=50
        )

        print("✅ OpenAI API working!")
        print(f"Response: {response.choices[0].message.content[:100]}...")

        print("\n🎯 Ready to run GEO system!")
        print("Run: python run.py --test")

    except Exception as e:
        print(f"❌ OpenAI test failed: {str(e)[:100]}")
        print("Check your API key and billing status.")

if __name__ == '__main__':
    main()