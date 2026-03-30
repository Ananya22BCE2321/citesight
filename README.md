# Multi-Provider GEO Agent System

A flexible AI pipeline that supports multiple providers for Generative Engine Optimization (GEO) content generation.

## Supported Providers

- **OpenAI**: GPT-4, GPT-3.5-turbo
- **Anthropic**: Claude-3 models
- **Google**: Gemini models
- **NVIDIA**: Llama models via API Catalog
- **Ollama**: Local models (Llama, Mistral, etc.)

## Installation

Install required packages based on providers you want to use:

```bash
# Core dependencies
pip install openai

# For Anthropic
pip install anthropic

# For Google
pip install google-genai

# For Ollama (local models)
pip install ollama
```

## Configuration

Configuration hierarchy (highest priority first):
1. Command-line arguments
2. Environment variables
3. `pipeline_config.json` file
4. Hardcoded defaults

### Environment Variables

Set API keys securely:

```bash
# For NVIDIA (default)
export NVIDIA_API_KEY="your-nvidia-api-key"

# For OpenAI
export OPENAI_API_KEY="your-openai-api-key"

# For Anthropic
export ANTHROPIC_API_KEY="your-anthropic-api-key"

# For Google
export GOOGLE_API_KEY="your-google-api-key"

# Optional: Pipeline settings
export PIPELINE_PROVIDER="nvidia"
export PIPELINE_MODEL="meta/llama-3.1-8b-instruct"
export PIPELINE_MAX_WORKERS="10"
export PIPELINE_RATE_LIMIT_RPM="30"
```

### Config File

Create `pipeline_config.json`:

```json
{
  "provider": "nvidia",
  "model": "meta/llama-3.1-8b-instruct",
  "max_workers": 5,
  "max_tokens": 500,
  "temperature": 0.7,
  "retries": 3,
  "rate_limit_rpm": 60,
  "cost_tracking": true,
  "local_model_host": "http://localhost:11434"
}
```

## Usage

### Basic Usage

```bash
# Use defaults (NVIDIA)
python pipeline_multi.py

# Specify provider and model
python pipeline_multi.py --provider openai --model gpt-4

# Use Anthropic
python pipeline_multi.py --provider anthropic --model claude-3-sonnet-20240229

# Use local Ollama model
python pipeline_multi.py --provider ollama --model llama2

# Custom settings
python pipeline_multi.py --provider google --model gemini-1.5-pro --max-workers 10 --temperature 0.5
```

### Advanced Options

```bash
# Disable cost tracking
python pipeline_multi.py --no-cost-tracking

# Custom rate limiting
python pipeline_multi.py --rate-limit-rpm 30

# More retries
python pipeline_multi.py --retries 5
```

## Features

- **Multi-Provider Support**: Switch between AI providers seamlessly
- **Parallel Processing**: Concurrent query processing with configurable workers
- **Rate Limiting**: Built-in rate limiting per provider
- **Cost Tracking**: Automatic cost estimation and token counting
- **Error Handling**: Retry logic with exponential backoff
- **Logging**: Comprehensive logging to `pipeline.log`
- **Flexible Configuration**: Multiple configuration methods
- **Local Models**: Support for Ollama local models

## Output

Results are saved as timestamped JSON files: `responses_{provider}_{timestamp}.json`

Each response includes:
- Query
- Provider and model used
- Generated content
- Token usage and cost
- Timestamp

## Cost Estimation

Approximate costs per 1K tokens (may vary):
- OpenAI GPT-4: $0.03 prompt + $0.06 completion
- Anthropic Claude-3: $0.003 input + $0.015 output
- Google Gemini: ~$0.00025 per 1K characters
- NVIDIA: ~$0.0005 per 1K tokens
- Ollama: Free (local)

## Local Models with Ollama

1. Install Ollama: https://ollama.ai/
2. Pull models: `ollama pull llama2`
3. Run: `python pipeline_multi.py --provider ollama --model llama2`

## Troubleshooting

- **Missing API Key**: Set the appropriate environment variable
- **Import Errors**: Install required packages for your provider
- **Rate Limits**: Reduce `--rate-limit-rpm` or increase delays
- **Local Models**: Ensure Ollama is running on the correct host/port

## Extending

To add a new provider:
1. Create a class inheriting from `BaseProvider`
2. Implement the `generate()` method
3. Add to the `providers` dict in `create_provider()`
4. Add API key environment variable mapping
