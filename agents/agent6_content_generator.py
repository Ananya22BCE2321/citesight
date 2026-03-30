#!/usr/bin/env python3
"""
Agent 6: GEO Content Generator
Generates GEO-optimized content for queries with zero citations
"""
import os
import json
import glob
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from pathlib import Path
import sys

# Ensure UTF-8 output on Windows consoles (avoid charmap errors for unicode symbols)
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

class GEOContentGenerator:
    """
    GEO Content Generator for GEO System

    Generates citation-optimized content for queries that received zero citations
    across all AI providers, using patterns identified by Agent 5.
    """

    def __init__(self):
        """Initialize the GEO content generator"""
        self.output_dir = Path("outputs")
        self.output_dir.mkdir(exist_ok=True)

        # Try to import providers
        self.providers = {}
        try:
            from agents.agent4_serp_intelligence import serp_agent
            self.providers['serp'] = serp_agent
        except ImportError:
            pass

        # Initialize provider for content generation
        self.content_provider = None
        self._init_content_provider()

    def _init_content_provider(self):
        """Initialize a content generation provider (NVIDIA or OpenAI)"""
        # Try NVIDIA first
        try:
            import openai
            # Check for NVIDIA API key
            nvidia_key = os.environ.get("NVIDIA_API_KEY")
            if nvidia_key:
                from pipeline_multi import create_provider
                self.content_provider = create_provider("nvidia", {"api_key": nvidia_key})
                print("✅ Using NVIDIA for content generation")
                return
        except Exception as e:
            print(f"⚠️  NVIDIA provider not available: {e}")

        # Try OpenAI
        try:
            import openai
            openai_key = os.environ.get("OPENAI_API_KEY")
            if openai_key:
                from pipeline_multi import create_provider
                self.content_provider = create_provider("openai", {"api_key": openai_key})
                print("✅ Using OpenAI for content generation")
                return
        except Exception as e:
            print(f"⚠️  OpenAI provider not available: {e}")

        print("❌ No content generation provider available (NVIDIA or OpenAI API key required)")

    def load_latest_pattern_report(self) -> Optional[Dict]:
        """
        Load the latest pattern report from Agent 5

        Returns:
            Latest pattern report dict or None if not found
        """
        pattern = self.output_dir / "pattern_report_*.json"
        report_files = list(self.output_dir.glob("pattern_report_*.json"))

        if not report_files:
            print("❌ No pattern reports found in outputs/ directory")
            return None

        # Get the latest report by timestamp
        latest_report = max(report_files, key=lambda f: f.stat().st_mtime)

        try:
            with open(latest_report, 'r', encoding='utf-8') as f:
                report = json.load(f)
            print(f"📂 Loaded pattern report: {latest_report.name}")
            return report
        except Exception as e:
            print(f"❌ Failed to load pattern report: {e}")
            return None

    def get_zero_citation_queries(self, pattern_report: Dict) -> List[str]:
        """
        Extract zero-citation queries from pattern report

        Args:
            pattern_report: Pattern analysis report from Agent 5

        Returns:
            List of queries with zero citations across all providers
        """
        geo_gaps = pattern_report.get("geo_gap_analysis", {})
        zero_queries = geo_gaps.get("zero_citation_queries", [])

        queries = [item["query"] for item in zero_queries]
        print(f"🎯 Found {len(queries)} zero-citation queries for content generation")
        return queries

    def generate_content_for_query(self, query: str) -> Optional[Dict]:
        """
        Generate GEO-optimized content for a single query

        Args:
            query: The query to generate content for

        Returns:
            Dict with generated content and metadata, or None if failed
        """
        if not self.content_provider:
            print("❌ No content provider available")
            return None

        system_prompt = f"""You are a GEO content specialist. Write a factual, authoritative answer to the following question 
about the Indian cement industry. Your answer should:
- Directly answer the question in the first sentence
- Mention at least 3 specific cement brand names naturally
- Reference at least 2 authoritative sources or websites
- Use clear headings and structured paragraphs
- Include specific facts, numbers, or IS standards where relevant
- Be between 200-400 words
Question: {query}"""

        try:
            print(f"🤖 Generating content for: {query[:60]}...")

            # Generate content using the provider
            result = self.content_provider.generate(system_prompt, max_tokens=800, temperature=0.7)

            if not result or not result.get("content"):
                print("❌ Empty response from content provider")
                return None

            content = result["content"].strip()

            # Extract metadata from generated content
            target_brands = self._extract_brands_from_content(content)
            domains_referenced = self._extract_domains_from_content(content)

            generated_item = {
                "query": query,
                "generated_content": content,
                "target_brands": target_brands,
                "domains_referenced": domains_referenced,
                "word_count": len(content.split()),
                "generated_at": datetime.now().isoformat(),
                "provider_used": getattr(self.content_provider, 'config', {}).get('provider', 'unknown')
            }

            print(f"✅ Generated {len(content.split())} words for query")
            return generated_item

        except Exception as e:
            print(f"❌ Failed to generate content for query: {e}")
            return None

    def _extract_brands_from_content(self, content: str) -> List[str]:
        """
        Extract cement brand names mentioned in the content

        Args:
            content: Generated content text

        Returns:
            List of cement brands found in the content
        """
        cement_brands = [
            'ultratech', 'acc', 'ambuja', 'jk', 'dalmia', 'shree', 'orient',
            'india cements', 'ramco', 'birla', 'heidelbergcement', 'cemex',
            'lafarge', 'holcim', 'prism', 'bangur', 'sanghi', 'kcp'
        ]

        found_brands = []
        content_lower = content.lower()

        for brand in cement_brands:
            if brand.lower() in content_lower:
                found_brands.append(brand.title())

        return found_brands

    def _extract_domains_from_content(self, content: str) -> List[str]:
        """
        Extract domain references from the content

        Args:
            content: Generated content text

        Returns:
            List of domains referenced in the content
        """
        import re

        # URL pattern
        url_pattern = r'https?://(?:[-\w.])+(?:[:\d]+)?(?:/(?:[\w/_.])*(?:\?(?:[\w&=%.])*)?(?:#(?:\w*))?)?'
        urls = re.findall(url_pattern, content)

        domains = []
        for url in urls:
            try:
                from urllib.parse import urlparse
                parsed = urlparse(url)
                domain = parsed.netloc.lower()
                if domain.startswith('www.'):
                    domain = domain[4:]
                if domain and domain not in domains:
                    domains.append(domain)
            except:
                continue

        return domains

    def run_content_generation(self, max_queries: Optional[int] = None) -> Dict:
        """
        Run content generation for all zero-citation queries

        Args:
            max_queries: Maximum number of queries to process (None for all)

        Returns:
            Dict with generation results and metadata
        """
        print("🚀 Starting GEO Content Generation...")
        print("=" * 50)

        # Load pattern report
        pattern_report = self.load_latest_pattern_report()
        if not pattern_report:
            return {"error": "No pattern report available"}

        # Get zero-citation queries
        zero_queries = self.get_zero_citation_queries(pattern_report)
        if not zero_queries:
            return {"error": "No zero-citation queries found"}

        # Limit queries if specified
        if max_queries:
            zero_queries = zero_queries[:max_queries]

        print(f"📝 Processing {len(zero_queries)} queries...")
        print()

        # Generate content for each query
        generated_content = []
        successful = 0
        failed = 0

        for i, query in enumerate(zero_queries, 1):
            print(f"[{i}/{len(zero_queries)}] Processing query...")
            result = self.generate_content_for_query(query)

            if result:
                generated_content.append(result)
                successful += 1
            else:
                failed += 1
                # Add failure record
                generated_content.append({
                    "query": query,
                    "error": "Content generation failed",
                    "generated_at": datetime.now().isoformat()
                })

        # Compile results
        results = {
            "generated_at": datetime.now().isoformat(),
            "pattern_report_used": pattern_report.get("generated_at", "unknown"),
            "total_queries_processed": len(zero_queries),
            "successful_generations": successful,
            "failed_generations": failed,
            "generated_content": generated_content
        }

        # Save results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = self.output_dir / f"generated_content_{timestamp}.json"

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        print(f"\n💾 Results saved to: {output_file}")
        print(f"✅ Successfully generated content for {successful}/{len(zero_queries)} queries")

        # Print summary
        self._print_generation_summary(results)

        return results

    def _print_generation_summary(self, results: Dict):
        """Print a summary of the content generation results"""
        print("\n" + "=" * 60)
        print("📝 CONTENT GENERATION SUMMARY")
        print("=" * 60)

        print(f"📊 Queries Processed: {results['total_queries_processed']}")
        print(f"✅ Successful: {results['successful_generations']}")
        print(f"❌ Failed: {results['failed_generations']}")

        generated_content = results.get("generated_content", [])
        successful_content = [item for item in generated_content if "error" not in item]

        if successful_content:
            total_words = sum(item.get("word_count", 0) for item in successful_content)
            avg_words = total_words / len(successful_content)

            all_brands = []
            all_domains = []
            for item in successful_content:
                all_brands.extend(item.get("target_brands", []))
                all_domains.extend(item.get("domains_referenced", []))

            unique_brands = len(set(all_brands))
            unique_domains = len(set(all_domains))

            print(f"📝 Total Words Generated: {total_words}")
            print(f"📏 Average Words per Article: {avg_words:.0f}")
            print(f"🏷️  Unique Brands Mentioned: {unique_brands}")
            print(f"🌐 Unique Domains Referenced: {unique_domains}")

        print("\n🎯 GEO Content Ready for Publication!")
        print("   These articles are optimized to maximize AI citation likelihood.")
        print("=" * 60)


# Global instance for easy import
content_generator = GEOContentGenerator()

def run_content_generation(max_queries: Optional[int] = None) -> Dict:
    """Convenience function to run content generation"""
    return content_generator.run_content_generation(max_queries)


if __name__ == "__main__":
    print("=== Agent 6: GEO Content Generator ===")

    # Run content generation for top 5 zero-citation queries
    print("🎯 Generating GEO-optimized content for top 5 zero-citation queries...")
    results = run_content_generation(max_queries=5)

    if "error" in results:
        print(f"❌ Content generation failed: {results['error']}")
    else:
        print("✅ Content generation completed!")
        print(f"📊 Processed {results['total_queries_processed']} queries")
        print(f"✅ Successfully generated {results['successful_generations']} articles")