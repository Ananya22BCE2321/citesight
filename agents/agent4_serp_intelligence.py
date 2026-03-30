#!/usr/bin/env python3
"""
Agent 4: SERP Intelligence
Analyze Google Search Engine Results Pages for GEO insights
"""
import os
import requests
import json
import time
from typing import Dict, List, Optional
from datetime import datetime

class SERPAgent:
    """
    SERP Intelligence Agent for GEO Analysis

    Uses SerpAPI to get Google search results and analyze them for:
    - Top ranking domains for target keywords
    - Citation overlap with LLM responses
    - GEO scoring opportunities
    """

    def __init__(self, api_key: Optional[str] = None, demo_mode: bool = False):
        """
        Initialize SERP Agent

        Args:
            api_key: SerpAPI key (if None, will look for SERPAPI_API_KEY env var)
            demo_mode: If True, returns mock data for testing without API calls
        """
        self.api_key = api_key or os.environ.get('SERPAPI_API_KEY')
        self.demo_mode = demo_mode
        self.base_url = "https://serpapi.com/search"
        self.session = requests.Session()

        if not self.api_key and not demo_mode:
            print("Warning: No SerpAPI key provided. Set SERPAPI_API_KEY environment variable.")
            print("Get your free API key at: https://serpapi.com/")
            print("Or use demo_mode=True for testing with mock data.")

    def _get_mock_serp_data(self, query: str, num_results: int) -> Dict:
        """Return mock SERP data for demo/testing purposes"""
        # Mock cement industry SERP results
        mock_domains = [
            "ultratechcement.com", "ambujacement.com", "acclimited.com", 
            "jkcement.com", "shreecement.com", "dalmiacement.com",
            "indiacements.com", "ramcocements.com", "birla.com",
            "pennacement.com"
        ]
        
        results = []
        for i in range(min(num_results, len(mock_domains))):
            results.append({
                "position": i + 1,
                "title": f"Best Cement Brands in India - {mock_domains[i].replace('.com', '').title()}",
                "link": f"https://www.{mock_domains[i]}",
                "domain": mock_domains[i],
                "snippet": f"Learn about {mock_domains[i].replace('.com', '').title()} cement products and construction solutions in India.",
                "displayed_link": f"https://www.{mock_domains[i]}/cement"
            })
        
        return {
            "query": query,
            "timestamp": datetime.now().isoformat(),
            "total_results": 1250000,  # Mock total results
            "results": results,
            "organic_domains": mock_domains[:num_results],
            "location": "India",
            "note": "This is mock data for demo purposes. Set SERPAPI_API_KEY for real data."
        }

    def search(self, query: str, num_results: int = 10, location: str = "India") -> Dict:
        """
        Search Google and return structured results

        Args:
            query: Search query
            num_results: Number of results to fetch (max 100)
            location: Geographic location for search

        Returns:
            {
                "query": "search query",
                "timestamp": "ISO timestamp",
                "total_results": 123456,
                "results": [
                    {
                        "position": 1,
                        "title": "Page Title",
                        "link": "https://example.com",
                        "domain": "example.com",
                        "snippet": "Page description...",
                        "displayed_link": "https://example.com/path"
                    },
                    ...
                ],
                "organic_domains": ["example.com", "competitor.com", ...]
            }
        """
        # Use mock data in demo mode
        if self.demo_mode:
            return self._get_mock_serp_data(query, num_results)
        
        if not self.api_key:
            return {
                "error": "No SerpAPI key configured. Set SERPAPI_API_KEY environment variable or use demo_mode=True",
                "query": query,
                "results": []
            }

        params = {
            "q": query,
            "api_key": self.api_key,
            "num": min(num_results, 100),  # SerpAPI max is 100
            "location": location,
            "hl": "en",  # Language
            "gl": "in"   # Country
        }

        # Retry with exponential backoff for rate limits
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self.session.get(self.base_url, params=params, timeout=30)
                
                # Handle rate limiting
                if response.status_code == 429:
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                        print(f"    Rate limited, waiting {wait_time}s before retry...")
                        time.sleep(wait_time)
                        continue
                    else:
                        return {
                            "error": "Rate limit exceeded. Free SerpAPI accounts have limited requests. Consider upgrading or waiting.",
                            "query": query,
                            "results": []
                        }
                
                response.raise_for_status()
                data = response.json()

                # Parse organic results
                organic_results = data.get("organic_results", [])
                results = []

                for result in organic_results[:num_results]:
                    parsed_result = {
                        "position": result.get("position"),
                        "title": result.get("title", ""),
                        "link": result.get("link", ""),
                        "domain": self._extract_domain(result.get("link", "")),
                        "snippet": result.get("snippet", ""),
                        "displayed_link": result.get("displayed_link", "")
                    }
                    results.append(parsed_result)

                # Extract unique domains
                organic_domains = list(set(r["domain"] for r in results if r["domain"]))

                return {
                    "query": query,
                    "timestamp": datetime.now().isoformat(),
                    "total_results": data.get("search_information", {}).get("total_results", 0),
                    "results": results,
                    "organic_domains": organic_domains,
                    "location": location
                }

            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    print(f"    Request failed, retrying in {wait_time}s: {str(e)}")
                    time.sleep(wait_time)
                    continue
                else:
                    return {
                        "error": f"API request failed after {max_retries} attempts: {str(e)}",
                        "query": query,
                        "results": []
                    }
            except json.JSONDecodeError as e:
                return {
                    "error": f"Invalid API response: {str(e)}",
                    "query": query,
                    "results": []
                }

    def check_citation_overlap(self, serp_domains: List[str], llm_citations: Dict) -> Dict:
        """
        Check overlap between SERP domains and LLM citations

        This is the core GEO insight: does the LLM cite the same sources
        that actually rank on Google for the target keywords?

        Args:
            serp_domains: List of domains from SERP results
            llm_citations: Citation dict from CitationExtractor

        Returns:
            {
                "overlap_count": 3,
                "overlap_domains": ["example.com", "competitor.com"],
                "geo_score": 0.6,  # overlap_count / min(serp_domains, llm_domains)
                "serp_coverage": 0.3,  # overlap_count / len(serp_domains)
                "citation_coverage": 0.5  # overlap_count / len(llm_domains)
            }
        """
        llm_domains = llm_citations.get("domains", [])
        llm_urls = llm_citations.get("urls", [])

        # Convert URLs to domains for comparison
        url_domains = []
        for url in llm_urls:
            domain = self._extract_domain(url)
            if domain:
                url_domains.append(domain)

        # Combine all LLM domains
        all_llm_domains = list(set(llm_domains + url_domains))

        # Find overlap
        overlap_domains = []
        for serp_domain in serp_domains:
            if serp_domain in all_llm_domains:
                overlap_domains.append(serp_domain)

        # Calculate scores
        overlap_count = len(overlap_domains)
        total_serp = len(serp_domains)
        total_llm = len(all_llm_domains)

        geo_score = overlap_count / max(total_serp, total_llm) if max(total_serp, total_llm) > 0 else 0
        serp_coverage = overlap_count / total_serp if total_serp > 0 else 0
        citation_coverage = overlap_count / total_llm if total_llm > 0 else 0

        return {
            "overlap_count": overlap_count,
            "overlap_domains": overlap_domains,
            "geo_score": round(geo_score, 3),
            "serp_coverage": round(serp_coverage, 3),
            "citation_coverage": round(citation_coverage, 3),
            "serp_domains_count": total_serp,
            "llm_domains_count": total_llm
        }

    def analyze_geo_opportunity(self, serp_results: Dict, llm_citations: Dict) -> Dict:
        """
        Comprehensive GEO analysis for a query

        Args:
            serp_results: Results from search() method
            llm_citations: Citations from CitationExtractor

        Returns:
            Complete GEO analysis including overlap scores and opportunities
        """
        overlap = self.check_citation_overlap(
            serp_results.get("organic_domains", []),
            llm_citations
        )

        # Identify domains that rank but aren't cited by LLM
        serp_domains = set(serp_results.get("organic_domains", []))
        llm_domains = set(llm_citations.get("domains", []))
        uncited_rankers = serp_domains - llm_domains

        # Identify domains cited by LLM but don't rank
        cited_not_ranking = llm_domains - serp_domains

        return {
            "query": serp_results.get("query"),
            "overlap_analysis": overlap,
            "opportunities": {
                "uncited_rankers": list(uncited_rankers),  # Domains that rank but LLM doesn't cite
                "cited_not_ranking": list(cited_not_ranking),  # Domains LLM cites but don't rank
                "citation_gap": len(uncited_rankers),  # How many ranking domains are missed
                "false_positives": len(cited_not_ranking)  # Citations to non-ranking domains
            },
            "recommendations": self._generate_recommendations(overlap, uncited_rankers, cited_not_ranking)
        }

    def _extract_domain(self, url: str) -> Optional[str]:
        """Extract domain from URL"""
        if not url:
            return None

        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc.lower()

            # Remove www. prefix
            if domain.startswith('www.'):
                domain = domain[4:]

            return domain
        except:
            return None

    def _generate_recommendations(self, overlap: Dict, uncited_rankers: set, cited_not_ranking: set) -> List[str]:
        """Generate GEO optimization recommendations"""
        recommendations = []

        geo_score = overlap["geo_score"]

        if geo_score < 0.3:
            recommendations.append("Low GEO alignment - LLM citations don't match SERP rankings")
        elif geo_score > 0.7:
            recommendations.append("Strong GEO alignment - Citations match search rankings well")

        if uncited_rankers:
            recommendations.append(f"Consider citing these ranking domains: {', '.join(list(uncited_rankers)[:3])}")

        if cited_not_ranking:
            recommendations.append(f"LLM cites non-ranking domains: {', '.join(list(cited_not_ranking)[:3])}")

        if overlap["serp_coverage"] < 0.5:
            recommendations.append("Many ranking domains not cited - potential GEO opportunity")

        return recommendations

    def run_serp_analysis(self, queries: List[str], output_dir: str = "outputs") -> Dict:
        """
        Run comprehensive SERP analysis for a list of queries.
        
        Args:
            queries: List of search queries to analyze
            output_dir: Directory containing pipeline output files
            
        Returns:
            Analysis report with SERP data and GEO comparisons
        """
        import glob
        from pathlib import Path
        
        print(f"🔍 Starting SERP analysis for {len(queries)} queries...")
        
        # Find the latest pipeline output file
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        response_files = list(output_path.glob("responses_*.json"))
        if not response_files:
            return {
                "error": f"No pipeline output files found in {output_dir}",
                "queries_analyzed": 0,
                "results": []
            }
        
        # Load the most recent pipeline results
        latest_file = max(response_files, key=lambda x: x.stat().st_mtime)
        print(f"📂 Loading pipeline results from: {latest_file.name}")
        
        try:
            with open(latest_file, 'r') as f:
                pipeline_data = json.load(f)
        except Exception as e:
            return {
                "error": f"Failed to load pipeline results: {str(e)}",
                "queries_analyzed": 0,
                "results": []
            }
        
        # Create query -> citations mapping from pipeline data
        query_citations = {}
        for record in pipeline_data:
            if record.get("citations"):
                query_citations[record["query"]] = record["citations"]
        
        print(f"📊 Found {len(query_citations)} queries with citation data")
        
        # Run SERP analysis for each query
        results = []
        successful = 0
        
        for i, query in enumerate(queries, 1):
            print(f"  [{i}/{len(queries)}] Analyzing: {query[:50]}...")
            
            # Get SERP results
            serp_result = self.search(query, num_results=10)
            
            if "error" in serp_result:
                print(f"    ❌ SERP failed: {serp_result['error']}")
                results.append({
                    "query": query,
                    "error": serp_result["error"],
                    "serp_domains": [],
                    "llm_domains": [],
                    "geo_score": 0.0,
                    "uncited_rankers": [],
                    "cited_not_ranking": [],
                    "recommendations": ["SERP analysis failed - check API key"]
                })
                continue
            
            serp_domains = serp_result.get("organic_domains", [])
            llm_citations = query_citations.get(query, {"domains": [], "urls": []})
            
            # Get LLM domains (combine domains and URLs)
            llm_domains = llm_citations.get("domains", [])
            url_domains = []
            for url in llm_citations.get("urls", []):
                domain = self._extract_domain(url)
                if domain:
                    url_domains.append(domain)
            all_llm_domains = list(set(llm_domains + url_domains))
            
            # Calculate GEO score
            overlap_domains = [d for d in serp_domains if d in all_llm_domains]
            geo_score = len(overlap_domains) / max(len(serp_domains), len(all_llm_domains)) if max(len(serp_domains), len(all_llm_domains)) > 0 else 0
            
            # Find opportunities
            serp_set = set(serp_domains)
            llm_set = set(all_llm_domains)
            uncited_rankers = list(serp_set - llm_set)
            cited_not_ranking = list(llm_set - serp_set)
            
            # Generate recommendations
            recommendations = []
            if geo_score < 0.3:
                recommendations.append("Low GEO alignment - citations don't match SERP rankings")
            elif geo_score > 0.7:
                recommendations.append("Strong GEO alignment - citations match search rankings well")
            
            if uncited_rankers:
                recommendations.append(f"Consider citing ranking domains: {', '.join(uncited_rankers[:3])}")
            
            if cited_not_ranking:
                recommendations.append(f"LLM cites non-ranking domains: {', '.join(cited_not_ranking[:3])}")
            
            if not recommendations:
                recommendations.append("GEO alignment is moderate - monitor for changes")
            
            result = {
                "query": query,
                "serp_domains": serp_domains,
                "llm_domains": all_llm_domains,
                "geo_score": round(geo_score, 3),
                "uncited_rankers": uncited_rankers,
                "cited_not_ranking": cited_not_ranking,
                "recommendations": recommendations
            }
            
            results.append(result)
            successful += 1
            print(f"    ✅ GEO Score: {result['geo_score']:.2f} ({len(overlap_domains)}/{len(serp_domains)} overlap)")
            
            # Add delay between queries to avoid rate limits
            if i < len(queries):
                time.sleep(1)  # 1 second delay between queries
        
        # Save report
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = output_path / f"serp_report_{timestamp}.json"
        
        report = {
            "timestamp": datetime.now().isoformat(),
            "queries_analyzed": len(queries),
            "successful_analyses": successful,
            "pipeline_source": str(latest_file),
            "results": results
        }
        
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"💾 Report saved to: {report_file}")
        print(f"📈 Analysis complete: {successful}/{len(queries)} queries analyzed")
        
        return report

# Global instances for easy import
serp_agent = SERPAgent()  # Real API mode
demo_serp_agent = SERPAgent(demo_mode=True)  # Demo mode for testing

def search_google(query: str, num_results: int = 10) -> Dict:
    """Convenience function for quick Google search"""
    return serp_agent.search(query, num_results)

def run_serp_analysis(queries: List[str], output_dir: str = "outputs") -> Dict:
    """Convenience function to run SERP analysis"""
    return serp_agent.run_serp_analysis(queries, output_dir)

if __name__ == "__main__":
    # Test the SERP agent with 3 cement queries
    print("=== SERP Intelligence Agent Test ===")
    print("Testing with 3 cement industry queries...\n")
    
    test_queries = [
        "best cement for house construction in India",
        "UltraTech vs ACC cement comparison",
        "which cement brand is most trusted in India"
    ]
    
    # Test with real API first
    print("🔍 Testing with Real API...")
    real_report = run_serp_analysis(test_queries)
    
    if "error" in real_report and "No pipeline output" in real_report["error"]:
        print("❌ No pipeline data found - run pipeline first")
    elif any("error" in result for result in real_report.get("results", [])):
        print("⚠️  Real API failed (rate limited), switching to demo mode...")
        
        # Test with demo mode
        print("\n🎭 Testing with Demo Mode...")
        demo_report = demo_serp_agent.run_serp_analysis(test_queries)
        
        if "error" not in demo_report:
            print("✅ Demo mode successful!")
            print(f"📊 Results saved to demo report")
            print(f"📈 Analyzed {demo_report['successful_analyses']}/{demo_report['queries_analyzed']} queries")
            
            # Show summary
            print("\n📋 Demo Results Summary:")
            for result in demo_report.get("results", []):
                if "error" not in result:
                    print(f"  • {result['query'][:40]}... → GEO Score: {result['geo_score']:.2f}")
                    if result['uncited_rankers']:
                        print(f"    Uncited rankers: {', '.join(result['uncited_rankers'][:2])}")
        else:
            print(f"❌ Demo mode failed: {demo_report.get('error')}")
    else:
        print("✅ Real API successful!")
        print(f"📊 Results saved to: {real_report.get('pipeline_source', 'outputs/')}")
        print(f"📈 Analyzed {real_report['successful_analyses']}/{real_report['queries_analyzed']} queries")
        
        # Show summary
        print("\n📋 Real API Results Summary:")
        for result in real_report.get("results", []):
            if "error" not in result:
                print(f"  • {result['query'][:40]}... → GEO Score: {result['geo_score']:.2f}")
                if result['uncited_rankers']:
                    print(f"    Uncited rankers: {', '.join(result['uncited_rankers'][:2])}")
            else:
                print(f"  • {result['query'][:40]}... → ❌ {result['error']}")
    
    print("\n💡 To use real data:")
    print("   1. Set SERPAPI_API_KEY environment variable")
    print("   2. Get API key at: https://serpapi.com/")
    print("   3. Free accounts have rate limits - consider paid plans for production use")