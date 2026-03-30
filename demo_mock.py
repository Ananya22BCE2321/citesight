#!/usr/bin/env python3
"""
Mock Demo - Shows GEO System Working with Sample Data
No API keys or external services required!
"""

import json
import random
from datetime import datetime

def create_mock_responses():
    """Create realistic mock responses for demonstration"""

    mock_queries = [
        "What is the best cement for house construction in India?",
        "Difference between OPC and PPC cement types",
        "Which cement brand has the best quality for foundations?",
        "How to choose cement for high-rise building construction",
        "Cheapest cement brands available in India 2024",
        "Best waterproof cement for basement construction",
        "Cement storage guidelines and shelf life",
        "How long does cement last in open bags",
        "Comparison of UltraTech vs ACC cement",
        "Best cement for RCC construction work"
    ]

    cement_brands = ["UltraTech", "ACC", "Ambuja", "JK Cement", "Shree Cement", "Ramco", "Dalmia", "Birla", "Orient", "Lafarge"]
    domains = ["ultratechcement.com", "acclimited.com", "ambujacement.com", "jkcement.com", "shreecement.com"]

    responses = []

    for i, query in enumerate(mock_queries):
        # Simulate realistic AI response
        base_responses = [
            f"For house construction in India, {random.choice(cement_brands)} Cement is highly recommended due to its superior strength and durability. According to industry experts at {random.choice(domains)}, it provides excellent workability.",
            f"The key difference between OPC and PPC cement lies in their composition. OPC sets quickly while PPC offers better workability. As mentioned on {random.choice(domains)}, PPC is ideal for most construction applications.",
            f"When choosing cement for foundations, consider {random.choice(cement_brands)} which has proven track record. The {random.choice(domains)} website provides detailed specifications for foundation work.",
            f"For high-rise buildings, {random.choice(cement_brands)} Cement meets all IS standards. According to {random.choice(domains)}, it offers consistent quality and strength.",
            f"Among affordable options, {random.choice(cement_brands)} provides good value. Check {random.choice(domains)} for current pricing and availability.",
            f"For waterproof applications, consider {random.choice(cement_brands)} which has excellent resistance to moisture. The {random.choice(domains)} technical data sheet provides more details.",
            f"Proper cement storage is crucial. According to {random.choice(domains)}, cement should be stored in dry conditions and used within 3 months of manufacture.",
            f"Cement in open bags typically lasts 3-6 months if stored properly. {random.choice(domains)} recommends checking for lumps before use.",
            f"Both UltraTech and ACC offer premium quality. {random.choice(domains)} compares their performance characteristics in detail.",
            f"For RCC construction, {random.choice(cement_brands)} is preferred by engineers. Visit {random.choice(domains)} for technical specifications."
        ]

        response_text = base_responses[i % len(base_responses)]

        # Extract mock citations
        brands_mentioned = [brand for brand in cement_brands if brand.lower() in response_text.lower()]
        urls_found = [f"https://{domain}" for domain in domains if domain in response_text]

        response = {
            "query": query,
            "provider": "mock_ai",
            "response": response_text,
            "citations": {
                "urls": urls_found,
                "domains": [domain for domain in domains if domain in response_text],
                "cement_brands": brands_mentioned,
                "external_references": [domain for domain in domains if domain in response_text],
                "citation_count": len(urls_found),
                "has_external_links": len(urls_found) > 0,
                "has_brand_mentions": len(brands_mentioned) > 0
            },
            "cost": round(random.uniform(0.001, 0.005), 4),
            "tokens": random.randint(150, 300),
            "timestamp": datetime.now().isoformat()
        }

        responses.append(response)

    return responses

def run_mock_demo():
    """Run the complete mock demonstration"""
    print("GEO System Mock Demo")
    print("=" * 25)
    print("Shows the system working with realistic sample data")
    print("(No API keys or internet required!)\n")

    # Generate mock data
    print("Generating mock AI responses...")
    responses = create_mock_responses()

    # Save responses
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    responses_file = f"responses_mock_{timestamp}.json"
    summary_file = f"summary_mock_{timestamp}.json"

    with open(responses_file, 'w') as f:
        json.dump(responses, f, indent=2)

    # Create summary
    total_cost = sum(r['cost'] for r in responses)
    total_tokens = sum(r['tokens'] for r in responses)

    all_brands = []
    all_domains = []
    for response in responses:
        citations = response['citations']
        all_brands.extend(citations['cement_brands'])
        all_domains.extend(citations['domains'])

    summary = {
        "timestamp": timestamp,
        "provider": "mock_ai",
        "model": "simulated",
        "total_queries": len(responses),
        "successful": len(responses),
        "failed": 0,
        "total_cost": total_cost,
        "total_tokens": total_tokens,
        "citation_analysis": {
            "unique_brands_found": len(set(all_brands)),
            "unique_domains_found": len(set(all_domains)),
            "all_brands": sorted(list(set(all_brands))),
            "all_domains": sorted(list(set(all_domains))),
            "avg_citations_per_query": round(sum(len(r['citations']['cement_brands']) for r in responses) / len(responses), 1)
        }
    }

    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)

    # Display results
    print("\nMock demo completed!")
    print(f"Processed: {len(responses)} queries")
    print(f"Unique cement brands found: {summary['citation_analysis']['unique_brands_found']}")
    print(f"Unique domains found: {summary['citation_analysis']['unique_domains_found']}")
    print(f"Total simulated cost: ${total_cost:.4f}")
    print(f"Average citations per query: {summary['citation_analysis']['avg_citations_per_query']}")
    print()
    print("Files created:")
    print(f"  - {responses_file} (detailed responses)")
    print(f"  - {summary_file} (analysis summary)")
    print()
    print("Next steps:")
    print("1. View dashboard: streamlit run dashboard.py")
    print("2. Get real API key: python setup_openai.py")
    print("3. Run real queries: python run.py --test")

if __name__ == '__main__':
    run_mock_demo()