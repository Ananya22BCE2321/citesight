"""
pipeline_multi.py — Multi-Provider GEO Agent Pipeline (Refined)
================================================================
Key improvements:
- All output files go into outputs/ folder (no more root clutter)
- Queries loaded from queries.json (never hardcoded)
- Cleaner config loading with explicit priority chain
- Pricing config validated on startup
- Rate limiter shared per provider type
"""

import json
import os
import time
import logging
import argparse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from abc import ABC, abstractmethod
import threading
from pathlib import Path
import sys

# Ensure UTF-8 output on Windows consoles (avoid charmap errors for unicode symbols)
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def safe_print(*args, **kwargs):
    msg = " ".join(str(a) for a in args)
    try:
        print(msg, **kwargs)
    except UnicodeEncodeError:
        print(msg.encode("utf-8", errors="replace").decode("ascii", errors="replace"), **kwargs)

# ============================================
# DEPENDENCY CHECKS
# ============================================

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

try:
    from google import genai
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

try:
    from agents.agent3_citation_extraction import citation_extractor
    CITATION_AVAILABLE = True
except ImportError:
    CITATION_AVAILABLE = False
    print("Warning: Citation extraction not available (agents/agent3_citation_extraction.py missing)")

try:
    from agents.agent4_serp_intelligence import serp_agent
    SERP_AVAILABLE = True
except ImportError:
    SERP_AVAILABLE = False
    print("Warning: SERP intelligence not available (agents/agent4_serp_intelligence.py missing)")

try:
    from agents.agent5_pattern_analysis import pattern_agent
    PATTERN_AVAILABLE = True
except ImportError:
    PATTERN_AVAILABLE = False
    print("Warning: Pattern analysis not available (agents/agent5_pattern_analysis.py missing)")

try:
    from agents.agent6_content_generator import content_generator
    CONTENT_GEN_AVAILABLE = True
except ImportError:
    CONTENT_GEN_AVAILABLE = False
    print("Warning: Content generation not available (agents/agent6_content_generator.py missing)")

try:
    from agents.agent7_content_structurer import content_structurer
    CONTENT_STRUCT_AVAILABLE = True
except ImportError:
    CONTENT_STRUCT_AVAILABLE = False
    print("Warning: Content structuring not available (agents/agent7_content_structurer.py missing)")

try:
    from agents.agent8_validator import validation_agent
    VALIDATION_AVAILABLE = True
except ImportError:
    VALIDATION_AVAILABLE = False
    print("Warning: Validation and scoring not available (agents/agent8_validator.py missing)")

# ============================================
# OUTPUT DIRECTORY
# ============================================

OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

# ============================================
# LOGGING
# ============================================

logger = logging.getLogger("pipeline")
logger.setLevel(logging.DEBUG)

_log_file = OUTPUT_DIR / "pipeline.log"
file_handler = logging.FileHandler(_log_file)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.WARNING)
console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

logger.addHandler(file_handler)
logger.addHandler(console_handler)

# ============================================
# CONFIGURATION
# ============================================

DEFAULT_CONFIG = {
    "provider": "google",
    "model": "gemini-1.5-flash",
    "max_workers": 5,
    "max_tokens": 500,
    "temperature": 0.7,
    "retries": 3,
    "rate_limit_rpm": 60,
    "cost_tracking": True,
    "budget_cap": None,
    "local_model_host": "http://localhost:11434",
    "queries_file": "queries.json",
    "query_categories": None,  # None = all categories
}

def validate_pricing_config(config: dict) -> None:
    if "pricing" not in config:
        logger.warning("No pricing config found — using hardcoded defaults")
        return
    for provider, models in config["pricing"].items():
        if not isinstance(models, dict):
            logger.error(f"Invalid pricing format for provider '{provider}'")
            continue
        for model, costs in models.items():
            if not isinstance(costs, dict) or "input" not in costs or "output" not in costs:
                logger.warning(f"Incomplete pricing for {provider}/{model}")
            elif not all(isinstance(v, (int, float)) and v >= 0 for v in costs.values()):
                logger.warning(f"Invalid pricing values for {provider}/{model}")

def load_config() -> dict:
    """
    Priority chain: hardcoded defaults < pipeline_config.json < env vars.
    CLI args applied separately in main().
    """
    config = DEFAULT_CONFIG.copy()

    config_file = "pipeline_config.json"
    if os.path.exists(config_file):
        try:
            with open(config_file) as f:
                config.update(json.load(f))
            logger.info(f"Loaded config from {config_file}")
        except Exception as e:
            logger.warning(f"Failed to load {config_file}: {e}")

    validate_pricing_config(config)

    env_mappings = {
        "PIPELINE_PROVIDER":       ("provider",          str),
        "PIPELINE_MODEL":          ("model",             str),
        "PIPELINE_MAX_WORKERS":    ("max_workers",       int),
        "PIPELINE_MAX_TOKENS":     ("max_tokens",        int),
        "PIPELINE_TEMPERATURE":    ("temperature",       float),
        "PIPELINE_RETRIES":        ("retries",           int),
        "PIPELINE_RATE_LIMIT_RPM": ("rate_limit_rpm",    int),
        "PIPELINE_COST_TRACKING":  ("cost_tracking",     bool),
        "PIPELINE_BUDGET_CAP":     ("budget_cap",        float),
        "PIPELINE_LOCAL_HOST":     ("local_model_host",  str),
        "PIPELINE_QUERIES_FILE":   ("queries_file",      str),
    }
    for env_var, (key, cast) in env_mappings.items():
        value = os.environ.get(env_var)
        if value is not None:
            try:
                if cast == bool:
                    config[key] = value.lower() in ("true", "1", "yes")
                elif cast == float and value.lower() in ("none", ""):
                    config[key] = None
                else:
                    config[key] = cast(value)
            except ValueError:
                logger.warning(f"Could not parse {env_var}='{value}' as {cast.__name__}, ignoring")

    return config

# ============================================
# QUERY LOADER
# ============================================

def load_queries(queries_file: str, categories: list | None = None, limit: int | None = None) -> list[str]:
    """
    Load queries from queries.json.
    Optionally filter to specific categories, and/or limit total count.
    Falls back to a small default set if the file is missing.
    """
    FALLBACK = [
        "best cement for house construction in India",
        "OPC vs PPC cement which is better",
        "which cement brand is best for foundations",
        "best cement for high-rise buildings",
        "cement storage guidelines",
    ]

    if not os.path.exists(queries_file):
        logger.warning(f"Queries file '{queries_file}' not found — using fallback queries")
        print(f"⚠️  '{queries_file}' not found, using built-in fallback queries")
        queries = FALLBACK
    else:
        try:
            with open(queries_file) as f:
                data = json.load(f)
            all_categories = data.get("categories", {})

            if categories:
                # Only load requested categories
                selected = {k: v for k, v in all_categories.items() if k in categories}
                missing = set(categories) - set(selected)
                if missing:
                    logger.warning(f"Categories not found in queries file: {missing}")
            else:
                selected = all_categories

            queries = []
            for cat_queries in selected.values():
                queries.extend(cat_queries)

            if not queries:
                logger.warning("No queries found in selected categories — using fallback")
                queries = FALLBACK

        except Exception as e:
            logger.warning(f"Failed to load queries from '{queries_file}': {e} — using fallback")
            queries = FALLBACK

    # Deduplicate while preserving order
    seen = set()
    deduped = []
    for q in queries:
        if isinstance(q, str) and q.strip() and q.strip() not in seen:
            seen.add(q.strip())
            deduped.append(q.strip())

    if limit and limit > 0:
        deduped = deduped[:limit]

    return deduped

# ============================================
# RATE LIMITER
# ============================================

_rate_limiters: dict = {}
_rate_limiters_lock = threading.Lock()

class RateLimiter:
    """Token bucket — acquire() returns seconds to sleep (0 if no wait needed)."""

    def __init__(self, rpm: int):
        self.rpm = rpm
        self.tokens = float(rpm)
        self.last_refill = time.time()
        self.lock = threading.Lock()

    def acquire(self) -> float:
        with self.lock:
            now = time.time()
            elapsed = now - self.last_refill
            self.tokens = min(self.rpm, self.tokens + elapsed * (self.rpm / 60.0))
            self.last_refill = now
            if self.tokens >= 1:
                self.tokens -= 1
                return 0.0
            return (1.0 - self.tokens) / (self.rpm / 60.0)

def get_shared_rate_limiter(provider_name: str, rpm: int) -> RateLimiter:
    key = f"{provider_name}_{rpm}"
    with _rate_limiters_lock:
        if key not in _rate_limiters:
            _rate_limiters[key] = RateLimiter(rpm)
        return _rate_limiters[key]

# ============================================
# BASE PROVIDER
# ============================================

class BaseProvider(ABC):
    def __init__(self, api_key=None, model=None, **kwargs):
        self.api_key = api_key
        self.model = model
        self.config = kwargs.get("config", {})
        self.cost_tracking = kwargs.get("cost_tracking", True)
        self.budget_cap = kwargs.get("budget_cap", None)
        provider_name = kwargs.get("provider_name", self.__class__.__name__)
        rpm = kwargs.get("rate_limit_rpm", 60)
        self.rate_limiter = get_shared_rate_limiter(provider_name, rpm)
        self._cost_lock = threading.Lock()
        self.total_cost = 0.0
        self.total_tokens = 0

    @abstractmethod
    def generate(self, query: str, **kwargs) -> dict:
        """Returns dict: {content, usage: {prompt_tokens, completion_tokens, total_tokens}, cost}"""
        pass

    def estimate_cost(self, usage) -> float:
        return 0.0

    def check_and_reserve_budget(self, estimated_cost: float = 0.0) -> bool:
        if not self.budget_cap:
            return True
        with self._cost_lock:
            if (self.total_cost + estimated_cost) >= self.budget_cap:
                return False
            self.total_cost += estimated_cost
            return True

    def record_cost(self, actual_cost: float, reserved_cost: float, tokens: int):
        with self._cost_lock:
            self.total_cost += (actual_cost - reserved_cost)
            self.total_tokens += tokens

    def record_cost_simple(self, cost: float, tokens: int):
        with self._cost_lock:
            self.total_cost += cost
            self.total_tokens += tokens

# ============================================
# PROVIDER IMPLEMENTATIONS
# ============================================

class OpenAIProvider(BaseProvider):
    def __init__(self, api_key=None, model="gpt-4o", **kwargs):
        super().__init__(api_key, model, **kwargs)
        if not OPENAI_AVAILABLE:
            raise ImportError("openai package not installed")
        self.client = openai.OpenAI(api_key=api_key)

    def generate(self, query: str, **kwargs) -> dict:
        wait = self.rate_limiter.acquire()
        if wait > 0:
            time.sleep(wait)
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": query}],
            max_tokens=kwargs.get("max_tokens", 500),
            temperature=kwargs.get("temperature", 0.7)
        )
        content = response.choices[0].message.content
        usage = response.usage
        cost = self.estimate_cost(usage) if self.cost_tracking else 0.0
        tokens = usage.prompt_tokens + usage.completion_tokens
        self.record_cost_simple(cost, tokens)
        return {"content": content,
                "usage": {"prompt_tokens": usage.prompt_tokens,
                          "completion_tokens": usage.completion_tokens,
                          "total_tokens": tokens},
                "cost": cost}

    def estimate_cost(self, usage) -> float:
        pricing = self.config.get("pricing", {}).get("openai", {})
        c = pricing.get(self.model, {"input": 0.005, "output": 0.015})
        return usage.prompt_tokens / 1000 * c["input"] + usage.completion_tokens / 1000 * c["output"]


class AnthropicProvider(BaseProvider):
    def __init__(self, api_key=None, model="claude-3-5-sonnet-20241022", **kwargs):
        super().__init__(api_key, model, **kwargs)
        if not ANTHROPIC_AVAILABLE:
            raise ImportError("anthropic package not installed")
        self.client = anthropic.Anthropic(api_key=api_key)

    def generate(self, query: str, **kwargs) -> dict:
        wait = self.rate_limiter.acquire()
        if wait > 0:
            time.sleep(wait)
        response = self.client.messages.create(
            model=self.model,
            max_tokens=kwargs.get("max_tokens", 500),
            temperature=kwargs.get("temperature", 0.7),
            messages=[{"role": "user", "content": query}]
        )
        content = response.content[0].text
        usage = response.usage
        cost = self.estimate_cost(usage) if self.cost_tracking else 0.0
        tokens = usage.input_tokens + usage.output_tokens
        self.record_cost_simple(cost, tokens)
        return {"content": content,
                "usage": {"prompt_tokens": usage.input_tokens,
                          "completion_tokens": usage.output_tokens,
                          "total_tokens": tokens},
                "cost": cost}

    def estimate_cost(self, usage) -> float:
        pricing = self.config.get("pricing", {}).get("anthropic", {})
        m = self.model.lower()
        key = "opus" if "opus" in m else "haiku" if "haiku" in m else "sonnet"
        defaults = {"opus": {"input": 0.015, "output": 0.075},
                    "sonnet": {"input": 0.003, "output": 0.015},
                    "haiku": {"input": 0.00025, "output": 0.00125}}
        c = pricing.get(key, defaults[key])
        return usage.input_tokens / 1000 * c["input"] + usage.output_tokens / 1000 * c["output"]


class GoogleProvider(BaseProvider):
    def __init__(self, api_key=None, model="gemini-2.0-flash", **kwargs):
        # GEMINI model mapping for known supported/endpoints
        unsupported_map = {
            "gemini-1.5-pro": "gemini-1.5-flash",
            "gemini-1.5-ultra": "gemini-1.5-flash",
            "gemini-2.0-pro": "gemini-2.0-flash"
        }
        if model in unsupported_map:
            logger.warning(f"Model '{model}' is not supported for this API version; switching to '{unsupported_map[model]}'")
            model = unsupported_map[model]

        super().__init__(api_key, model, **kwargs)
        if not GOOGLE_AVAILABLE:
            raise ImportError("google-genai package not installed")
        self.client = genai.Client(api_key=api_key)

    def _google_generate_content(self, query: str, **kwargs):
        """Try the Google GenAI APIs in order to tolerate SDK/backwards compatibility changes."""
        # Newer SDK flavor (Google Gemini generative API)
        if hasattr(self.client, "models") and hasattr(self.client.models, "generate_content"):
            return self.client.models.generate_content(model=self.model, contents=query)

        # GenAI v1 response API
        if hasattr(self.client, "responses") and hasattr(self.client.responses, "generate"):
            return self.client.responses.generate(model=self.model, input=query)

        # Legacy/older API method
        if hasattr(self.client, "generate"):
            return self.client.generate(model=self.model, prompt=query)

        raise RuntimeError("No supported Google GenAI generation method available")

    def generate(self, query: str, **kwargs) -> dict:
        wait = self.rate_limiter.acquire()
        if wait > 0:
            time.sleep(wait)

        response = None
        content = None
        usage_dict = None

        # Attempt main Google generation paths with strong fallback.
        try:
            response = self._google_generate_content(query, **kwargs)
        except Exception as e:
            logger.warning(f"Google model generation failed for '{self.model}': {e}")
            raise

        # Normalize response payloads across SDK versions
        if hasattr(response, "text"):
            content = response.text
            meta = getattr(response, "usage_metadata", None)
            if meta:
                prompt_tokens = getattr(meta, "prompt_token_count", 0)
                completion_tokens = getattr(meta, "candidates_token_count", 0)
                total_tokens = getattr(meta, "total_token_count", prompt_tokens + completion_tokens)
                usage_dict = {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens}
            else:
                # fallback if usage metadata is absent
                usage_dict = {"prompt_tokens": 0, "completion_tokens": 0}
                total_tokens = 0

        elif isinstance(response, dict):
            # `responses.generate` returns dict-like
            if "output" in response:
                output = response["output"]
                if isinstance(output, list) and output:
                    content = output[0].get("content", "") if isinstance(output[0], dict) else str(output[0])
                else:
                    content = response.get("content", "") or ""
            else:
                content = response.get("content", "") or ""

            usage = response.get("usage") or {}
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", usage.get("output_tokens", 0))
            total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)
            usage_dict = {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens}

        else:
            # Last-resort if response object is raw string etc.
            content = str(response)
            usage_dict = {"prompt_tokens": 0, "completion_tokens": 0}
            total_tokens = 0

        if not content or not content.strip():
            raise ValueError("Empty response from Google GenAI")

        cost = self.estimate_cost(usage_dict) if self.cost_tracking else 0.0
        self.record_cost_simple(cost, total_tokens)

        return {
            "content": content,
            "usage": {"prompt_tokens": usage_dict.get("prompt_tokens", 0),
                      "completion_tokens": usage_dict.get("completion_tokens", 0),
                      "total_tokens": total_tokens},
            "cost": cost
        }

    def estimate_cost(self, usage: dict) -> float:
        pricing = self.config.get("pricing", {}).get("google", {})
        c = pricing.get(self.model, {"input": 0.00125, "output": 0.005})
        return usage["prompt_tokens"] / 1000 * c["input"] + usage["completion_tokens"] / 1000 * c["output"]


class NvidiaProvider(BaseProvider):
    def __init__(self, api_key=None, model="meta/llama-3.1-8b-instruct", **kwargs):
        super().__init__(api_key, model, **kwargs)
        if not OPENAI_AVAILABLE:
            raise ImportError("openai package not installed")
        self.client = openai.OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=api_key)

    def generate(self, query: str, **kwargs) -> dict:
        wait = self.rate_limiter.acquire()
        if wait > 0:
            time.sleep(wait)
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": query}],
            max_tokens=kwargs.get("max_tokens", 500),
            temperature=kwargs.get("temperature", 0.7)
        )
        content = response.choices[0].message.content
        usage = response.usage
        cost = self.estimate_cost(usage) if self.cost_tracking else 0.0
        tokens = usage.prompt_tokens + usage.completion_tokens
        self.record_cost_simple(cost, tokens)
        return {"content": content,
                "usage": {"prompt_tokens": usage.prompt_tokens,
                          "completion_tokens": usage.completion_tokens,
                          "total_tokens": tokens},
                "cost": cost}

    def estimate_cost(self, usage) -> float:
        pricing = self.config.get("pricing", {}).get("nvidia", {})
        c = pricing.get(self.model, {"input": 0.0005, "output": 0.0005})
        return usage.prompt_tokens / 1000 * c["input"] + usage.completion_tokens / 1000 * c["output"]


class OllamaProvider(BaseProvider):
    def __init__(self, api_key=None, model="llama2", **kwargs):
        super().__init__(api_key, model, **kwargs)
        if not OLLAMA_AVAILABLE:
            raise ImportError("ollama package not installed")
        self.client = ollama.Client(host=kwargs.get("local_model_host", "http://localhost:11434"))

    def generate(self, query: str, **kwargs) -> dict:
        wait = self.rate_limiter.acquire()
        if wait > 0:
            time.sleep(wait)
        response = self.client.chat(
            model=self.model,
            messages=[{"role": "user", "content": query}],
            options={"num_predict": kwargs.get("max_tokens", 500),
                     "temperature": kwargs.get("temperature", 0.7)}
        )
        content = response["message"]["content"]
        prompt_tokens = int(response.get("prompt_eval_count") or len(query.split()) * 1.3)
        completion_tokens = int(response.get("eval_count") or len(content.split()) * 1.3)
        total_tokens = prompt_tokens + completion_tokens
        self.record_cost_simple(0.0, total_tokens)
        return {"content": content,
                "usage": {"prompt_tokens": prompt_tokens,
                          "completion_tokens": completion_tokens,
                          "total_tokens": total_tokens},
                "cost": 0.0}

# ============================================
# PROVIDER FACTORY
# ============================================

PROVIDER_API_KEY_ENV = {
    "openai":    "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google":    "GOOGLE_API_KEY",
    "nvidia":    "NVIDIA_API_KEY",
    "ollama":    None,
    "serp":      "SERPAPI_API_KEY",
}

PROVIDER_CLASSES = {
    "openai":    OpenAIProvider,
    "anthropic": AnthropicProvider,
    "google":    GoogleProvider,
    "nvidia":    NvidiaProvider,
    "ollama":    OllamaProvider,
}

def create_provider(provider_name: str, config: dict) -> BaseProvider:
    if provider_name not in PROVIDER_CLASSES:
        raise ValueError(f"Unsupported provider '{provider_name}'. Supported: {list(PROVIDER_CLASSES)}")

    api_key = None
    env_var = PROVIDER_API_KEY_ENV.get(provider_name)
    if env_var:
        api_key = os.environ.get(env_var)
        if not api_key:
            raise ValueError(f"API key not found. Set the '{env_var}' environment variable.")

    try:
        return PROVIDER_CLASSES[provider_name](
            api_key=api_key,
            model=config["model"],
            config=config,
            provider_name=provider_name,
            rate_limit_rpm=config["rate_limit_rpm"],
            cost_tracking=config["cost_tracking"],
            budget_cap=config.get("budget_cap"),
            local_model_host=config.get("local_model_host"),
        )
    except ImportError as e:
        err_msg = str(e)
        if "google-genai" in err_msg:
            raise ImportError(
                "google-genai package not installed. Run 'pip install google-genai' and retry."
            ) from e
        raise

# ============================================
# PIPELINE
# ============================================

class Pipeline:
    def __init__(self, config: dict):
        self.config = config
        self.provider = create_provider(config["provider"], config)

    def process_query(self, query: str) -> dict:
        if not self.provider.check_and_reserve_budget(estimated_cost=0.0):
            msg = f"Budget cap ${self.config['budget_cap']:.2f} reached — skipping"
            logger.warning(f"{msg}: {query[:60]}")
            return self._error_record(query, "budget_cap_reached", msg)

        last_error = None
        for attempt in range(self.config["retries"]):
            try:
                result = self.provider.generate(
                    query,
                    max_tokens=self.config["max_tokens"],
                    temperature=self.config["temperature"]
                )
                if result and result.get("content") and result["content"].strip():
                    record = {
                        "query": query,
                        "engine": self.config["provider"],
                        "model": self.config["model"],
                        "response": result["content"],
                        "timestamp": datetime.now().isoformat(),
                        "usage": result["usage"],
                        "cost": result["cost"],
                    }
                    if CITATION_AVAILABLE:
                        record["citations"] = citation_extractor.extract_citations(result["content"])
                    
                    # Add SERP analysis if available
                    if SERP_AVAILABLE and record.get("citations"):
                        try:
                            serp_results = serp_agent.search(query, num_results=10)
                            if "error" not in serp_results:
                                record["serp"] = serp_results
                                record["geo_analysis"] = serp_agent.analyze_geo_opportunity(
                                    serp_results, record["citations"]
                                )
                        except Exception as e:
                            logger.warning(f"SERP analysis failed for query '{query[:60]}': {e}")
                    
                    return record
                else:
                    last_error = "empty_response"
                    logger.warning(f"Empty response (attempt {attempt+1}): {query[:60]}")

            except Exception as e:
                last_error = str(e)
                logger.warning(f"Attempt {attempt+1} failed for '{query[:60]}': {e}")
                print(f"  ⚠️  Attempt {attempt+1} failed: {query[:40]}...")
                if attempt < self.config["retries"] - 1:
                    time.sleep(2 ** attempt)

        logger.error(f"All {self.config['retries']} attempts failed: {query[:60]}")
        return self._error_record(
            query,
            f"failed_after_{self.config['retries']}_attempts",
            last_error
        )

    def _error_record(self, query: str, error: str, error_details: str | None = None) -> dict:
        record = {
            "query": query,
            "engine": self.config["provider"],
            "model": self.config["model"],
            "response": None,
            "timestamp": datetime.now().isoformat(),
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "cost": 0.0,
            "error": error,
        }
        if error_details:
            record["error_details"] = error_details
        return record

    def run(self, queries: list) -> dict:
        logger.info(f"Pipeline started — {self.config['provider']} / {self.config['model']}")

        safe_print("=" * 60)
        safe_print("  GEO AGENT PIPELINE")
        safe_print(f"  Started:  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        safe_print(f"  Provider: {self.config['provider']}  |  Model: {self.config['model']}")
        safe_print(f"  Workers:  {self.config['max_workers']}", end="")
        if self.config.get("budget_cap"):
            safe_print(f"  |  Budget: ${self.config['budget_cap']:.2f}", end="")
        safe_print(f"\n  Outputs:  {OUTPUT_DIR}/")
        safe_print("=" * 60)

        validated = [q.strip() for q in queries if isinstance(q, str) and q.strip()]
        if not validated:
            logger.error("No valid queries to process")
            print("❌  No valid queries found")
            return {"successful": 0, "failed": 0, "budget_stopped": 0, "responses": []}

        print(f"\n  Processing {len(validated)} queries...\n")

        all_results = []
        with ThreadPoolExecutor(max_workers=self.config["max_workers"]) as executor:
            futures = {executor.submit(self.process_query, q): q for q in validated}
            for future in as_completed(futures):
                result = future.result()
                if result:
                    all_results.append(result)
                    error = result.get("error")
                    if error == "budget_cap_reached":
                        safe_print(f"  [BUDGET] Budget cap — skipped: {result['query'][:50]}")
                    elif error:
                        safe_print(f"  [FAIL] Failed:                 {result['query'][:50]}")
                    else:
                        safe_print(f"  [OK]   Done:                   {result['query'][:50]} (${result['cost']:.5f})")

        successes      = [r for r in all_results if not r.get("error")]
        failures       = [r for r in all_results if r.get("error") and r["error"] != "budget_cap_reached"]
        budget_stopped = [r for r in all_results if r.get("error") == "budget_cap_reached"]

        timestamp    = datetime.now().strftime("%Y%m%d_%H%M%S")
        provider_tag = self.config["provider"]

        response_file = OUTPUT_DIR / f"responses_{provider_tag}_{timestamp}.json"
        # Write all results (success + failures) so dashboard can display full run status
        with open(response_file, "w") as f:
            json.dump(all_results, f, indent=2)

        failure_file = None
        if failures or budget_stopped:
            failure_file = OUTPUT_DIR / f"failures_{provider_tag}_{timestamp}.json"
            with open(failure_file, "w") as f:
                json.dump(failures + budget_stopped, f, indent=2)

        summary = {
            "timestamp": timestamp,
            "provider":  self.config["provider"],
            "model":     self.config["model"],
            "total_queries":   len(validated),
            "successful":      len(successes),
            "failed":          len(failures),
            "budget_stopped":  len(budget_stopped),
            "total_cost_usd":  round(self.provider.total_cost, 6),
            "total_tokens":    self.provider.total_tokens,
            "output_file":     str(response_file),
            "failure_file":    str(failure_file) if failure_file else None,
        }
        summary_file = OUTPUT_DIR / f"summary_{provider_tag}_{timestamp}.json"
        with open(summary_file, "w") as f:
            json.dump(summary, f, indent=2)

        logger.info(
            f"Done — {len(successes)}/{len(validated)} ok, {len(failures)} failed, "
            f"cost: ${self.provider.total_cost:.5f}, tokens: {self.provider.total_tokens}"
        )

        print(f"\n{'=' * 60}")
        print(f"  ✅  Successful:     {len(successes)}/{len(validated)}")
        if failures:
            print(f"  ❌  Failed:         {len(failures)}")
        if budget_stopped:
            print(f"  💰  Budget stopped: {len(budget_stopped)}")
        print(f"  📊  Total tokens:   {self.provider.total_tokens:,}")
        print(f"  💵  Total cost:     ${self.provider.total_cost:.5f}")
        print(f"  📁  Output folder:  {OUTPUT_DIR}/")
        print(f"  📄  Responses:      {response_file.name}")
        if failure_file:
            print(f"  📄  Failures:       {failure_file.name}")
        print(f"  📄  Summary:        {summary_file.name}")
        print("=" * 60)

        return summary

# ============================================
# ENTRY POINT
# ============================================

def main():
    config = load_config()

    parser = argparse.ArgumentParser(description="Multi-Provider GEO Agent Pipeline")
    parser.add_argument("--provider",        choices=list(PROVIDER_API_KEY_ENV.keys()))
    parser.add_argument("--model",           help="Model name")
    parser.add_argument("--max-workers",     type=int)
    parser.add_argument("--max-tokens",      type=int)
    parser.add_argument("--temperature",     type=float)
    parser.add_argument("--retries",         type=int)
    parser.add_argument("--rate-limit-rpm",  type=int)
    parser.add_argument("--budget-cap",      type=float)
    parser.add_argument("--num-queries",     type=int, help="Limit total queries to run")
    parser.add_argument("--categories",      nargs="+", help="Query categories to load from queries.json")
    parser.add_argument("--queries-file",    default="queries.json", help="Path to queries JSON file")
    parser.add_argument("--no-cost-tracking", action="store_true")
    args = parser.parse_args()

    for key, value in vars(args).items():
        if value is not None:
            if key == "no_cost_tracking":
                config["cost_tracking"] = False
            else:
                config[key.replace("-", "_")] = value

    try:
        pipeline = Pipeline(config)
    except Exception as e:
        logger.error(f"Failed to initialise pipeline: {e}")
        print(f"❌  Failed to initialise pipeline: {e}")
        return

    queries = load_queries(
        queries_file=config.get("queries_file", "queries.json"),
        categories=config.get("categories"),
        limit=config.get("num_queries"),
    )

    pipeline.run(queries)

    # Run pattern analysis if available
    if PATTERN_AVAILABLE:
        print("\n🔍 Running Pattern Analysis Engine...")
        try:
            pattern_report = pattern_agent.run_analysis()
            print("✅ Pattern analysis completed!")
            print(f"📊 Analyzed {pattern_report.get('runs_analysed', 0)} runs with {pattern_report.get('total_queries', 0)} total queries")

            # Show GEO opportunities for next agent
            geo_opportunities = pattern_agent.get_geo_opportunities()
            if geo_opportunities:
                print(f"🎯 Found {len(geo_opportunities)} GEO opportunities for Agent 6")
            else:
                print("✅ No GEO opportunities found")

        except Exception as e:
            logger.error(f"Pattern analysis failed: {e}")
            print(f"⚠️  Pattern analysis failed: {e}")

    # Run content generation if available and API keys present
    if CONTENT_GEN_AVAILABLE and content_generator.content_provider:
        print("\n📝 Running GEO Content Generator...")
        try:
            content_results = content_generator.run_content_generation(max_queries=3)  # Generate for top 3
            if "error" not in content_results:
                print("✅ Content generation completed!")
                print(f"📝 Generated {content_results.get('successful_generations', 0)} articles")
            else:
                print(f"⚠️  Content generation skipped: {content_results['error']}")
        except Exception as e:
            logger.error(f"Content generation failed: {e}")
            print(f"⚠️  Content generation failed: {e}")
    elif CONTENT_GEN_AVAILABLE:
        print("ℹ️  Content generation available but no API keys configured (set NVIDIA_API_KEY or OPENAI_API_KEY)")
    else:
        print("ℹ️  Content generation not available (Agent 6 missing)")

    # Run content structuring if available
    if CONTENT_STRUCT_AVAILABLE:
        print("\n🔧 Running Content Structuring Agent...")
        try:
            structuring_results = content_structurer.run_structuring()
            if "error" not in structuring_results:
                print("✅ Content structuring completed!")
                print(f"🔧 Structured {structuring_results.get('total_items', 0)} content items")
            else:
                print(f"⚠️  Content structuring skipped: {structuring_results['error']}")
        except Exception as e:
            logger.error(f"Content structuring failed: {e}")
            print(f"⚠️  Content structuring failed: {e}")
    else:
        print("ℹ️  Content structuring not available (Agent 7 missing)")

    # Run validation and scoring if available
    if VALIDATION_AVAILABLE:
        print("\n🧪 Running Validation and Scoring Agent...")
        try:
            validation_results = validation_agent.run_validation()
            if "error" not in validation_results:
                print("✅ Validation and scoring completed!")
                print(f"🧪 Validated {validation_results.get('successful_validations', 0)} content pieces")
            else:
                print(f"⚠️  Validation skipped: {validation_results['error']}")
        except Exception as e:
            logger.error(f"Validation failed: {e}")
            print(f"⚠️  Validation failed: {e}")
    else:
        print("ℹ️  Validation and scoring not available (Agent 8 missing)")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"Pipeline crashed: {e}")
        print(f"❌  Pipeline crashed: {e}")
        raise