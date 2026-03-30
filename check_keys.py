#!/usr/bin/env python3
"""
API Key Status Checker
"""
import os

def check_api_keys():
    print("=== API Key Status Check ===")
    keys = ['OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'GOOGLE_API_KEY', 'NVIDIA_API_KEY']
    for key in keys:
        value = os.environ.get(key, '')
        status = 'SET' if value else 'NOT SET'
        print(f'{key}: {status}')
    print()
    print('Ollama: Available (no API key needed)')
    print()
    print('To get Google Gemini API key:')
    print('1. Go to: https://makersuite.google.com/app/apikey')
    print('2. Sign in with Google account')
    print('3. Create new API key')
    print('4. Copy the key and set it in PowerShell:')
    print('   $env:GOOGLE_API_KEY = "your-key-here"')
    print()
    print('To get NVIDIA API key:')
    print('1. Go to: https://build.nvidia.com/')
    print('2. Sign up for free tier')
    print('3. Get API key from dashboard')
    print('4. Set it: $env:NVIDIA_API_KEY = "your-key-here"')

if __name__ == "__main__":
    check_api_keys()