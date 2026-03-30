#!/usr/bin/env python3
"""
Agent 5: Pattern Analysis Engine
Analyzes citation patterns across all GEO pipeline runs
"""
import os
import json
import glob
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from collections import defaultdict, Counter
from pathlib import Path

class PatternAnalysisAgent:
    """
    Pattern Analysis Agent for GEO System

    Analyzes citation patterns across all pipeline runs to identify:
    - Brand frequency and popularity
    - Domain authority patterns
    - Provider performance differences
    - Query category effectiveness
    - Citation quality trends
    - GEO optimization opportunities
    """

    def __init__(self):
        """Initialize the pattern analysis agent"""
        self.output_dir = Path("outputs")
        self.output_dir.mkdir(exist_ok=True)

    def load_all_pipeline_results(self) -> List[Dict]:
        """
        Load all responses_*.json files from outputs directory

        Returns:
            List of pipeline result records
        """
        pattern = self.output_dir / "responses_*.json"
        result_files = list(self.output_dir.glob("responses_*.json"))

        if not result_files:
            print("⚠️  No pipeline result files found in outputs/ directory")
            return []

        all_results = []
        for file_path in result_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        # Add source file info to each record
                        for record in data:
                            record['_source_file'] = str(file_path.name)
                        all_results.extend(data)
                    else:
                        print(f"⚠️  Unexpected format in {file_path.name}, expected list")
            except Exception as e:
                print(f"❌ Failed to load {file_path.name}: {e}")

        print(f"📂 Loaded {len(all_results)} records from {len(result_files)} files")
        return all_results

    def analyze_brand_frequency(self, all_results: List[Dict]) -> Dict[str, int]:
        """
        Analyze which cement brands appear most frequently across all runs

        Args:
            all_results: All pipeline result records

        Returns:
            Dict mapping brand names to frequency counts
        """
        brand_counter = Counter()

        for record in all_results:
            citations = record.get("citations", {})
            brands = citations.get("cement_brands", [])
            for brand in brands:
                brand_counter[brand] += 1

        return dict(brand_counter.most_common())

    def analyze_domain_frequency(self, all_results: List[Dict]) -> Dict[str, int]:
        """
        Analyze which domains are cited most frequently

        Args:
            all_results: All pipeline result records

        Returns:
            Dict mapping domain names to frequency counts
        """
        domain_counter = Counter()

        for record in all_results:
            citations = record.get("citations", {})
            domains = citations.get("domains", [])
            urls = citations.get("urls", [])

            # Count domains
            for domain in domains:
                domain_counter[domain] += 1

            # Also count domains from URLs
            for url in urls:
                try:
                    from urllib.parse import urlparse
                    parsed = urlparse(url)
                    domain = parsed.netloc.lower()
                    if domain.startswith('www.'):
                        domain = domain[4:]
                    if domain:
                        domain_counter[domain] += 1
                except:
                    continue

        return dict(domain_counter.most_common())

    def analyze_provider_comparison(self, all_results: List[Dict]) -> Dict:
        """
        Compare citation performance across different AI providers

        Args:
            all_results: All pipeline result records

        Returns:
            Dict with provider comparison metrics
        """
        provider_stats = defaultdict(lambda: {
            "total_queries": 0,
            "successful_queries": 0,
            "total_citations": 0,
            "total_quality_score": 0.0,
            "brand_counts": Counter(),
            "avg_citations": 0.0,
            "avg_quality": 0.0
        })

        for record in all_results:
            provider = record.get("engine") or record.get("provider", "unknown")
            citations = record.get("citations", {})
            brands = citations.get("cement_brands", [])
            citation_count = citations.get("citation_count", 0)
            quality_score = citations.get("quality_score", 0.0)

            stats = provider_stats[provider]
            stats["total_queries"] += 1

            if not record.get("error"):
                stats["successful_queries"] += 1
                stats["total_citations"] += citation_count
                stats["total_quality_score"] += quality_score

                for brand in brands:
                    stats["brand_counts"][brand] += 1

        # Calculate averages
        for provider, stats in provider_stats.items():
            if stats["successful_queries"] > 0:
                stats["avg_citations"] = round(stats["total_citations"] / stats["successful_queries"], 2)
                stats["avg_quality"] = round(stats["total_quality_score"] / stats["successful_queries"], 3)
            stats["brand_counts"] = dict(stats["brand_counts"].most_common(5))  # Top 5 brands

        return dict(provider_stats)

    def analyze_category_performance(self, all_results: List[Dict]) -> Dict:
        """
        Analyze which query categories generate the most citations

        Args:
            all_results: All pipeline result records

        Returns:
            Dict with category performance metrics
        """
        # Load queries.json to map queries to categories
        queries_file = Path("queries.json")
        query_to_category = {}

        if queries_file.exists():
            try:
                with open(queries_file, 'r', encoding='utf-8') as f:
                    queries_data = json.load(f)
                    categories = queries_data.get("categories", {})

                    for category, queries in categories.items():
                        for query in queries:
                            query_to_category[query] = category
            except Exception as e:
                print(f"⚠️  Could not load queries.json: {e}")

        category_stats = defaultdict(lambda: {
            "total_queries": 0,
            "successful_queries": 0,
            "total_citations": 0,
            "total_quality_score": 0.0,
            "avg_citations": 0.0,
            "avg_quality": 0.0
        })

        for record in all_results:
            query = record.get("query", "")
            category = query_to_category.get(query, "unknown")

            citations = record.get("citations", {})
            citation_count = citations.get("citation_count", 0)
            quality_score = citations.get("quality_score", 0.0)

            stats = category_stats[category]
            stats["total_queries"] += 1

            if not record.get("error"):
                stats["successful_queries"] += 1
                stats["total_citations"] += citation_count
                stats["total_quality_score"] += quality_score

        # Calculate averages
        for category, stats in category_stats.items():
            if stats["successful_queries"] > 0:
                stats["avg_citations"] = round(stats["total_citations"] / stats["successful_queries"], 2)
                stats["avg_quality"] = round(stats["total_quality_score"] / stats["successful_queries"], 3)

        return dict(category_stats)

    def analyze_citation_trend(self, all_results: List[Dict]) -> List[Dict]:
        """
        Analyze citation quality trends across runs ordered by timestamp

        Args:
            all_results: All pipeline result records

        Returns:
            List of trend data points sorted by timestamp
        """
        # Group by source file (run)
        runs_data = defaultdict(list)

        for record in all_results:
            source_file = record.get("_source_file", "unknown")
            if not record.get("error"):
                citations = record.get("citations", {})
                quality_score = citations.get("quality_score", 0.0)
                citation_count = citations.get("citation_count", 0)
                runs_data[source_file].append({
                    "quality_score": quality_score,
                    "citation_count": citation_count
                })

        # Calculate averages per run and sort by timestamp
        trend_data = []
        for source_file, records in runs_data.items():
            if records:
                avg_quality = sum(r["quality_score"] for r in records) / len(records)
                avg_citations = sum(r["citation_count"] for r in records) / len(records)

                # Extract timestamp from filename (responses_PROVIDER_TIMESTAMP.json)
                timestamp_str = source_file.replace("responses_", "").replace(".json", "")
                try:
                    # Handle different timestamp formats
                    if "_" in timestamp_str:
                        parts = timestamp_str.split("_")
                        if len(parts) >= 2:
                            timestamp_str = parts[-1]  # Last part should be timestamp
                    timestamp = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                except:
                    timestamp = datetime.now()  # Fallback

                trend_data.append({
                    "timestamp": timestamp.isoformat(),
                    "source_file": source_file,
                    "avg_quality_score": round(avg_quality, 3),
                    "avg_citations": round(avg_citations, 2),
                    "query_count": len(records)
                })

        # Sort by timestamp
        trend_data.sort(key=lambda x: x["timestamp"])
        return trend_data

    def analyze_geo_gaps(self, all_results: List[Dict]) -> Dict:
        """
        Identify queries with zero citations across ALL providers (GEO opportunities)

        Args:
            all_results: All pipeline result records

        Returns:
            Dict with zero citation queries and low citation queries
        """
        # Group by query
        query_stats = defaultdict(lambda: {
            "providers_tested": set(),
            "citation_counts": [],
            "zero_providers": 0,
            "total_providers": 0
        })

        for record in all_results:
            query = record.get("query", "")
            provider = record.get("engine") or record.get("provider", "unknown")
            citations = record.get("citations", {})
            citation_count = citations.get("citation_count", 0)

            stats = query_stats[query]
            stats["providers_tested"].add(provider)
            stats["citation_counts"].append(citation_count)
            stats["total_providers"] += 1

            if citation_count == 0:
                stats["zero_providers"] += 1

        # Identify GEO opportunities
        zero_citation_queries = []
        low_citation_queries = []

        for query, stats in query_stats.items():
            providers_tested = len(stats["providers_tested"])
            zero_count = stats["zero_providers"]
            avg_citations = sum(stats["citation_counts"]) / len(stats["citation_counts"]) if stats["citation_counts"] else 0

            # Zero citations across ALL providers
            if zero_count == providers_tested and providers_tested > 0:
                zero_citation_queries.append({
                    "query": query,
                    "providers_tested": providers_tested,
                    "avg_citations": round(avg_citations, 2)
                })
            # Low citations (less than 1 average)
            elif avg_citations < 1.0 and providers_tested > 0:
                low_citation_queries.append({
                    "query": query,
                    "providers_tested": providers_tested,
                    "avg_citations": round(avg_citations, 2)
                })

        return {
            "zero_citation_queries": zero_citation_queries,
            "low_citation_queries": low_citation_queries
        }

    def run_analysis(self) -> Dict:
        """
        Run complete pattern analysis across all pipeline results

        Returns:
            Complete pattern analysis report
        """
        print("🔍 Starting Pattern Analysis Engine...")
        print("=" * 50)

        # Load all data
        all_results = self.load_all_pipeline_results()

        if not all_results:
            return {
                "error": "No pipeline results found",
                "generated_at": datetime.now().isoformat(),
                "runs_analysed": 0,
                "total_queries": 0
            }

        # Run all analyses
        print("📊 Analyzing citation patterns...")

        brand_freq = self.analyze_brand_frequency(all_results)
        domain_freq = self.analyze_domain_frequency(all_results)
        provider_comp = self.analyze_provider_comparison(all_results)
        category_perf = self.analyze_category_performance(all_results)
        citation_trend = self.analyze_citation_trend(all_results)
        geo_gaps = self.analyze_geo_gaps(all_results)

        # Compile report
        report = {
            "generated_at": datetime.now().isoformat(),
            "runs_analysed": len(set(r.get("_source_file", "unknown") for r in all_results)),
            "total_queries": len(all_results),
            "brand_frequency": brand_freq,
            "domain_frequency": domain_freq,
            "provider_comparison": provider_comp,
            "category_performance": category_perf,
            "citation_trend": citation_trend,
            "geo_gap_analysis": geo_gaps
        }

        # Save report
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = self.output_dir / f"pattern_report_{timestamp}.json"

        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        print(f"💾 Report saved to: {report_file}")

        # Print summary
        self._print_summary(report)

        return report

    def get_geo_opportunities(self) -> List[str]:
        """
        Get queries with zero citations across all providers (GEO opportunities)

        Returns:
            List of query strings that are GEO opportunities
        """
        report = self.run_analysis()
        geo_gaps = report.get("geo_gap_analysis", {})
        zero_queries = geo_gaps.get("zero_citation_queries", [])

        return [item["query"] for item in zero_queries]

    def _print_summary(self, report: Dict):
        """Print human-readable summary of the analysis"""
        print("\n" + "=" * 60)
        print("📈 PATTERN ANALYSIS SUMMARY")
        print("=" * 60)

        print(f"📊 Runs Analyzed: {report['runs_analysed']}")
        print(f"🔍 Total Queries: {report['total_queries']}")

        # Top 5 brands
        brands = report.get("brand_frequency", {})
        if brands:
            print(f"\n🏆 Top 5 Cement Brands:")
            for i, (brand, count) in enumerate(list(brands.items())[:5], 1):
                print(f"  {i}. {brand}: {count} mentions")

        # Top 5 domains
        domains = report.get("domain_frequency", {})
        if domains:
            print(f"\n🌐 Top 5 Cited Domains:")
            for i, (domain, count) in enumerate(list(domains.items())[:5], 1):
                print(f"  {i}. {domain}: {count} citations")

        # Best performing provider
        providers = report.get("provider_comparison", {})
        if providers:
            best_provider = max(providers.items(),
                              key=lambda x: x[1].get("avg_quality", 0),
                              default=None)
            if best_provider:
                provider_name, stats = best_provider
                print(f"\n🥇 Best Performing Provider: {provider_name.upper()}")
                print(f"   • Avg Citations: {stats.get('avg_citations', 0):.1f}")
                print(f"   • Avg Quality: {stats.get('avg_quality', 0):.2f}")
                print(f"   • Success Rate: {stats.get('successful_queries', 0)}/{stats.get('total_queries', 0)}")

        # GEO opportunities
        geo_gaps = report.get("geo_gap_analysis", {})
        zero_queries = geo_gaps.get("zero_citation_queries", [])
        if zero_queries:
            print(f"\n🎯 GEO Opportunities: {len(zero_queries)} queries with ZERO citations")
            print("   These queries need citation optimization!")

        print("\n💡 Use this data to optimize your GEO strategy!")
        print("=" * 60)


# Global instance for easy import
pattern_agent = PatternAnalysisAgent()

def run_analysis() -> Dict:
    """Convenience function to run pattern analysis"""
    return pattern_agent.run_analysis()

def get_geo_opportunities() -> List[str]:
    """Convenience function to get GEO opportunities"""
    return pattern_agent.get_geo_opportunities()


if __name__ == "__main__":
    print("=== Agent 5: Pattern Analysis Engine ===")

    # Run full analysis
    report = run_analysis()

    if "error" in report:
        print(f"❌ Analysis failed: {report['error']}")
    else:
        print("✅ Pattern analysis completed!")

        # Show GEO opportunities for Agent 6
        opportunities = get_geo_opportunities()
        if opportunities:
            print(f"\n🚀 Found {len(opportunities)} GEO opportunities for Agent 6:")
            for i, query in enumerate(opportunities[:5], 1):  # Show first 5
                print(f"  {i}. {query}")
            if len(opportunities) > 5:
                print(f"  ... and {len(opportunities) - 5} more")
        else:
            print("\n✅ No GEO opportunities found - all queries have citations!")