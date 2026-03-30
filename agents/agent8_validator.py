#!/usr/bin/env python3
"""
Agent 8: Validation and Scoring Agent
Tests whether generated GEO content actually improves citation scores
"""
import os
import json
import glob
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from pathlib import Path
from collections import defaultdict

# Ensure UTF-8 output on Windows consoles (avoid charmap errors for unicode symbols)
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

class ValidationScoringAgent:
    """
    Validation and Scoring Agent for GEO System

    Tests whether Agent 6 & 7's generated content actually improves citation scores
    by running enriched prompts through the pipeline and comparing results.
    """

    def __init__(self):
        """Initialize the validation agent"""
        self.output_dir = Path("outputs")
        self.output_dir.mkdir(exist_ok=True)

        # Try to import required agents
        self.citation_agent = None
        self.content_provider = None
        self._init_dependencies()

    def _init_dependencies(self):
        """Initialize required dependencies"""
        try:
            from agents.agent3_citation_extraction import citation_extractor
            self.citation_agent = citation_extractor
        except ImportError:
            print("⚠️  Citation extraction not available (Agent 3 missing)")

        # Try to initialize content provider for validation
        try:
            nvidia_key = os.environ.get("NVIDIA_API_KEY")
            if nvidia_key:
                from pipeline_multi import create_provider
                self.content_provider = create_provider("nvidia", {"api_key": nvidia_key})
                print("✅ Using NVIDIA for validation testing")
            else:
                print("⚠️  NVIDIA_API_KEY not set - validation will be limited")
        except Exception as e:
            print(f"⚠️  Content provider not available: {e}")

    def load_latest_structured_content(self) -> Optional[Dict]:
        """
        Load the latest structured content from Agent 7

        Returns:
            Latest structured content dict or None if not found
        """
        pattern = self.output_dir / "structured_content_*.json"
        content_files = list(self.output_dir.glob("structured_content_*.json"))

        if not content_files:
            print("❌ No structured content files found in outputs/ directory")
            return None

        # Get the latest content file by timestamp
        latest_content = max(content_files, key=lambda f: f.stat().st_mtime)

        try:
            with open(latest_content, 'r', encoding='utf-8') as f:
                content = json.load(f)
            print(f"📂 Loaded structured content: {latest_content.name}")
            return content
        except Exception as e:
            print(f"❌ Failed to load structured content: {e}")
            return None

    def get_baseline_citations(self, query: str) -> Dict:
        """
        Get baseline citation data for a query from original pipeline results

        Args:
            query: The query to find baseline data for

        Returns:
            Dict with baseline citation information
        """
        # Load all pipeline results to find baseline
        pattern = self.output_dir / "responses_*.json"
        result_files = list(self.output_dir.glob("responses_*.json"))

        baseline_data = {
            "citation_count": 0,
            "quality_score": 0.0,
            "brands": [],
            "domains": [],
            "found_in_runs": 0
        }

        for file_path in result_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        for record in data:
                            if record.get("query") == query and not record.get("error"):
                                citations = record.get("citations", {})
                                baseline_data["citation_count"] += citations.get("citation_count", 0)
                                baseline_data["quality_score"] += citations.get("quality_score", 0.0)
                                baseline_data["brands"].extend(citations.get("cement_brands", []))
                                baseline_data["domains"].extend(citations.get("domains", []))
                                baseline_data["found_in_runs"] += 1
            except Exception:
                continue

        # Calculate averages
        if baseline_data["found_in_runs"] > 0:
            baseline_data["citation_count"] /= baseline_data["found_in_runs"]
            baseline_data["quality_score"] /= baseline_data["found_in_runs"]

        # Remove duplicates
        baseline_data["brands"] = list(set(baseline_data["brands"]))
        baseline_data["domains"] = list(set(baseline_data["domains"]))

        return baseline_data

    def run_enriched_query(self, query: str, generated_content: str) -> Optional[Dict]:
        """
        Run an enriched query with generated content as context

        Args:
            query: The original query
            generated_content: Generated GEO content to use as context

        Returns:
            Dict with response and citations, or None if failed
        """
        if not self.content_provider:
            return None

        # Create enriched prompt
        enriched_prompt = f"""Given this information:

{generated_content}

Now answer this question: {query}"""

        try:
            print(f"🔄 Testing enriched query: {query[:50]}...")

            # Run through content provider
            result = self.content_provider.generate(enriched_prompt, max_tokens=600, temperature=0.7)

            if not result or not result.get("content"):
                print("❌ Empty response from validation provider")
                return None

            response = result["content"].strip()

            # Extract citations using Agent 3
            citations = {}
            if self.citation_agent:
                citations = self.citation_agent.extract_citations(response)

            return {
                "response": response,
                "citations": citations,
                "usage": result.get("usage", {}),
                "cost": result.get("cost", 0.0)
            }

        except Exception as e:
            print(f"❌ Failed to run enriched query: {e}")
            return None

    def validate_content_piece(self, query: str, generated_content: str, baseline_citations: Dict) -> Dict:
        """
        Validate one content piece by testing citation improvement

        Args:
            query: The original query
            generated_content: Generated GEO content
            baseline_citations: Baseline citation data

        Returns:
            Validation report dict
        """
        print(f"🧪 Validating content for: {query[:60]}...")

        # Get baseline scores
        baseline_score = baseline_citations.get("quality_score", 0.0)
        baseline_brands = baseline_citations.get("brands", [])

        # Run enriched query
        enriched_result = self.run_enriched_query(query, generated_content)

        if not enriched_result:
            return {
                "query": query,
                "validation_error": "Failed to run enriched query",
                "baseline_citation_score": baseline_score,
                "new_citation_score": 0.0,
                "improvement": 0.0,
                "baseline_brands_cited": baseline_brands,
                "new_brands_cited": [],
                "verdict": "error"
            }

        # Extract new citation data
        new_citations = enriched_result.get("citations", {})
        new_score = new_citations.get("quality_score", 0.0)
        new_brands = new_citations.get("cement_brands", [])

        # Calculate improvement
        improvement = new_score - baseline_score

        # Determine verdict
        if improvement > 0.1:
            verdict = "improved"
        elif improvement < -0.1:
            verdict = "degraded"
        else:
            verdict = "no_change"

        return {
            "query": query,
            "baseline_citation_score": round(baseline_score, 3),
            "new_citation_score": round(new_score, 3),
            "improvement": round(improvement, 3),
            "baseline_brands_cited": baseline_brands,
            "new_brands_cited": new_brands,
            "verdict": verdict,
            "enriched_response": enriched_result.get("response", ""),
            "validation_timestamp": datetime.now().isoformat()
        }

    def run_validation(self) -> Dict:
        """
        Run validation on all structured content pieces

        Returns:
            Dict with validation results and summary
        """
        print("🧪 Starting Validation and Scoring Agent...")
        print("=" * 50)

        # Load structured content
        structured_data = self.load_latest_structured_content()
        if not structured_data:
            return {"error": "No structured content available"}

        structured_content = structured_data.get("structured_content", [])
        valid_content = [item for item in structured_content
                        if "error" not in item.get("structuring_report", {})]

        if not valid_content:
            return {"error": "No valid structured content found"}

        print(f"🧪 Validating {len(valid_content)} content pieces...")
        print()

        # Validate each content piece
        validation_results = []
        successful_validations = 0

        for i, item in enumerate(valid_content, 1):
            query = item.get("query", "")
            generated_content = item.get("generated_content", "")

            if not query or not generated_content:
                print(f"⚠️  Skipping item {i}: Missing query or content")
                continue

            # Get baseline citations
            baseline_citations = self.get_baseline_citations(query)

            # Run validation
            validation_result = self.validate_content_piece(
                query, generated_content, baseline_citations
            )

            validation_results.append(validation_result)

            if "validation_error" not in validation_result:
                successful_validations += 1

            # Print immediate result
            self._print_validation_result(validation_result)

        # Compile results
        results = {
            "validation_timestamp": datetime.now().isoformat(),
            "source_file": structured_data.get("structured_at", "unknown"),
            "total_pieces": len(valid_content),
            "successful_validations": successful_validations,
            "validation_results": validation_results
        }

        # Save results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = self.output_dir / f"validation_report_{timestamp}.json"

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        print(f"\n💾 Validation report saved to: {output_file}")

        # Generate and print summary
        summary = self.generate_summary_report(results)
        self._print_summary_report(summary)

        return results

    def generate_summary_report(self, validation_results: Dict) -> Dict:
        """
        Generate a summary report of validation results

        Args:
            validation_results: Full validation results dict

        Returns:
            Summary statistics dict
        """
        results = validation_results.get("validation_results", [])
        valid_results = [r for r in results if "validation_error" not in r]

        if not valid_results:
            return {"error": "No valid validation results"}

        # Calculate statistics
        improved = sum(1 for r in valid_results if r["verdict"] == "improved")
        no_change = sum(1 for r in valid_results if r["verdict"] == "no_change")
        degraded = sum(1 for r in valid_results if r["verdict"] == "degraded")

        improvements = [r["improvement"] for r in valid_results]
        avg_improvement = sum(improvements) / len(improvements) if improvements else 0.0

        # Find best performing content
        best_result = max(valid_results, key=lambda x: x["improvement"], default=None)

        # Verdict distribution
        verdict_counts = {
            "improved": improved,
            "no_change": no_change,
            "degraded": degraded
        }

        return {
            "total_validated": len(valid_results),
            "verdict_distribution": verdict_counts,
            "average_improvement": round(avg_improvement, 3),
            "best_improvement": best_result["improvement"] if best_result else 0.0,
            "best_query": best_result["query"] if best_result else "",
            "success_rate": round(improved / len(valid_results), 2) if valid_results else 0.0
        }

    def _print_validation_result(self, result: Dict):
        """Print a single validation result"""
        if "validation_error" in result:
            print(f"❌ {result['query'][:50]}... - {result['validation_error']}")
            return

        verdict_icons = {
            "improved": "📈",
            "no_change": "➡️",
            "degraded": "📉"
        }

        icon = verdict_icons.get(result["verdict"], "❓")
        improvement = result["improvement"]

        print(f"{icon} {result['query'][:50]}...")
        print(f"   Before: {result['baseline_citation_score']:.2f} | After: {result['new_citation_score']:.2f}")
        print(f"   Improvement: {improvement:+.3f} | Verdict: {result['verdict'].replace('_', ' ')}")
        print()

    def _print_summary_report(self, summary: Dict):
        """Print the summary report"""
        print("\n" + "=" * 60)
        print("📊 VALIDATION SUMMARY REPORT")
        print("=" * 60)

        if "error" in summary:
            print(f"❌ {summary['error']}")
            return

        print(f"📋 Total Queries Validated: {summary['total_validated']}")
        print(f"📈 Average Improvement: {summary['average_improvement']:+.3f}")
        print(f"🏆 Best Improvement: {summary['best_improvement']:+.3f}")
        print(f"✅ Success Rate: {summary['success_rate']:.1%}")

        verdicts = summary.get("verdict_distribution", {})
        print(f"\n📊 Verdict Distribution:")
        print(f"   📈 Improved: {verdicts.get('improved', 0)}")
        print(f"   ➡️ No Change: {verdicts.get('no_change', 0)}")
        print(f"   📉 Degraded: {verdicts.get('degraded', 0)}")

        if summary.get("best_query"):
            print(f"\n🏆 Best Performing Query:")
            print(f"   {summary['best_query']}")
            print(f"   Improvement: {summary['best_improvement']:+.3f}")

        print("\n🎯 GEO Content Validation Complete!")
        print("   This closes the loop - measuring actual citation improvement.")
        print("=" * 60)


# Global instance for easy import
validation_agent = ValidationScoringAgent()

def run_validation() -> Dict:
    """Convenience function to run validation"""
    return validation_agent.run_validation()

def generate_summary_report(validation_results: Dict) -> Dict:
    """Convenience function to generate summary report"""
    return validation_agent.generate_summary_report(validation_results)


if __name__ == "__main__":
    print("=== Agent 8: Validation and Scoring Agent ===")

    # Run full validation
    print("🧪 Running complete validation of GEO content effectiveness...")
    results = run_validation()

    if "error" in results:
        print(f"❌ Validation failed: {results['error']}")
    else:
        print("✅ Validation completed!")
        print(f"📊 Validated {results['successful_validations']} content pieces")