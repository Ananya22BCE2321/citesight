import json
import openai
from datetime import datetime
import os
import time
import logging
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

# ============================================
# CONFIGURATION & SETUP
# ============================================

# Set up logging
logging.basicConfig(
    filename="pipeline.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Parse command-line arguments
parser = argparse.ArgumentParser(description="GEO Agent System - Query Monitoring Pipeline")
parser.add_argument("--model", default="meta/llama-3.1-8b-instruct",
                   help="NVIDIA model to use (default: meta/llama-3.1-8b-instruct)")
parser.add_argument("--max-workers", type=int, default=5,
                   help="Maximum number of concurrent workers (default: 5)")
args = parser.parse_args()

# Get API key from environment
API_KEY = os.environ.get("NVIDIA_API_KEY")
if not API_KEY:
    raise ValueError("NVIDIA_API_KEY environment variable not set. Please set it to a valid NVIDIA API key.")

# Initialize client
client = openai.OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=API_KEY
)

logging.info("Pipeline started")
print("=" * 60)
print("GEO AGENT SYSTEM - FULL PIPELINE")
print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"Model: {args.model}")
print(f"Max Workers: {args.max_workers}")
print("=" * 60)

# ============================================
# QUERIES - Replace with full 100 when ready
# ============================================

queries = [
    "best cement for house construction",
    "OPC vs PPC cement difference",
    "which cement is best for foundation"
]

# ============================================
# UTILITY FUNCTIONS
# ============================================

def call_with_retry(client, model, query, retries=3):
    """Call the API with retry logic and exponential backoff."""
    for attempt in range(retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": query}],
                max_tokens=500,
                temperature=0.7
            )
            return response
        except Exception as e:
            logging.warning(f"Attempt {attempt+1} failed for query '{query}': {e}")
            print(f"  ⚠️ Attempt {attempt+1} failed: {e}")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)  # exponential backoff
    return None

def process_query(query, client, model):
    """Process a single query and return the result."""
    content = call_with_retry(client, model, query)
    if content and content.choices:
        response_content = content.choices[0].message.content
        if response_content and response_content.strip():
            usage = content.usage
            return {
                "query": query,
                "engine": "nvidia",
                "response": response_content,
                "timestamp": datetime.now().isoformat(),
                "tokens": {
                    "prompt": usage.prompt_tokens if usage else None,
                    "completion": usage.completion_tokens if usage else None
                }
            }
        else:
            logging.warning(f"Empty response for query: {query}")
            print(f"  ⚠️ Empty response for: {query}")
    else:
        logging.error(f"Failed to get response for query: {query}")
        print(f"  ❌ Failed: {query}")
    return None

def validate_queries(queries):
    """Validate and clean the queries list."""
    valid_queries = []
    for q in queries:
        if isinstance(q, str) and q.strip():
            valid_queries.append(q.strip())
        else:
            logging.warning(f"Invalid query skipped: {q}")
    return valid_queries

# ============================================
# AGENT 2 - QUERY MONITORING
# ============================================

def run_query_monitoring():
    """Main function to run query monitoring."""
    print("\n[AGENT 2] Query Monitoring...")

    # Validate queries
    validated_queries = validate_queries(queries)
    if not validated_queries:
        logging.error("No valid queries to process")
        print("  ❌ No valid queries found")
        return []

    responses = []

    # Process queries in parallel
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = {executor.submit(process_query, q, client, args.model): q for q in validated_queries}
        for future in as_completed(futures):
            result = future.result()
            if result:
                responses.append(result)
                print(f"  ✅ Completed: {result['query'][:50]}...")

    # Save results with timestamped filename
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"responses_{timestamp}.json"
    with open(filename, "w") as f:
        json.dump(responses, f, indent=2)

    logging.info(f"Pipeline completed: {len(responses)}/{len(validated_queries)} queries successful")
    print(f"\n  ✅ {len(responses)}/{len(validated_queries)} queries monitored")
    print(f"  📄 Results saved to: {filename}")

    return responses

# ============================================
# MAIN EXECUTION
# ============================================

if __name__ == "__main__":
    try:
        run_query_monitoring()
    except Exception as e:
        logging.error(f"Pipeline failed: {e}")
        print(f"❌ Pipeline failed: {e}")
        raise