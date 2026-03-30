#!/usr/bin/env python3
"""
Agent 3: Citation Extraction
Extracts citations and references from LLM responses
"""
import re
from urllib.parse import urlparse
from typing import Dict, List, Set

class CitationExtractor:
    """Extract citations and references from text"""

    def __init__(self):
        # Common citation patterns
        self.url_pattern = re.compile(r'https?://[^\s\)\]\}\>\"\'\,]+')
        self.domain_pattern = re.compile(r'(?:https?://)?(?:www\.)?([^/\s]+\.[^/\s]+)')

        # Brand/domain patterns for cement industry
        self.cement_brands = {
            'ambuja', 'acc', 'ultratech', 'jk', 'shree', 'ramco', 'dalmia',
            'birla', 'orient', 'heidelberg', 'lafarge', 'holcim'
        }

    def extract_citations(self, response_text: str) -> Dict:
        """
        Extract citations from LLM response text

        Returns:
        {
            "urls": ["https://example.com", ...],
            "domains": ["example.com", ...],
            "cement_brands": ["ambuja", "acc", ...],
            "citation_count": 5,
            "has_external_links": true
        }
        """
        if not response_text or not isinstance(response_text, str):
            return self._empty_result()

        # Extract URLs
        urls = self.url_pattern.findall(response_text)
        urls = [url.rstrip('.,;:!?') for url in urls]  # Clean trailing punctuation

        # Extract domains
        domains = []
        for url in urls:
            try:
                parsed = urlparse(url)
                if parsed.netloc:
                    domain = parsed.netloc.lower()
                    # Remove www. prefix
                    if domain.startswith('www.'):
                        domain = domain[4:]
                    domains.append(domain)
            except:
                continue

        # Extract mentioned cement brands
        text_lower = response_text.lower()
        mentioned_brands = []
        for brand in self.cement_brands:
            if brand in text_lower:
                mentioned_brands.append(brand)

        # Check for external references (websites mentioned without full URLs)
        external_refs = self._extract_external_references(response_text)

        return {
            "urls": list(set(urls)),
            "domains": list(set(domains)),
            "cement_brands": list(set(mentioned_brands)),
            "external_references": external_refs,
            "citation_count": len(set(urls)),
            "has_external_links": len(urls) > 0,
            "has_brand_mentions": len(mentioned_brands) > 0
        }

    def _extract_external_references(self, text: str) -> List[str]:
        """Extract website references that aren't full URLs"""
        # Look for patterns like "according to example.com" or "source: example.com"
        ref_patterns = [
            r'(?:according to|source|from|via|at)\s+([^\s]+\.[^\s]+)',
            r'([^\s]+\.com|[^\s]+\.org|[^\s]+\.gov|[^\s]+\.edu)',
        ]

        references = []
        for pattern in ref_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            references.extend(matches)

        # Filter out already captured URLs and clean
        references = [ref.rstrip('.,;:!?') for ref in references
                     if not ref.startswith(('http://', 'https://'))]

        return list(set(references))

    def _empty_result(self) -> Dict:
        """Return empty citation result"""
        return {
            "urls": [],
            "domains": [],
            "cement_brands": [],
            "external_references": [],
            "citation_count": 0,
            "has_external_links": False,
            "has_brand_mentions": False
        }

    def analyze_citation_quality(self, citations: Dict) -> Dict:
        """Analyze the quality and diversity of citations"""
        if not citations:
            return {"quality_score": 0, "diversity_score": 0}

        urls = citations.get("urls", [])
        domains = citations.get("domains", [])
        brands = citations.get("cement_brands", [])

        # Quality score based on number and type of citations
        quality_score = min(10, len(urls) * 2 + len(brands))

        # Diversity score based on unique domains
        diversity_score = min(10, len(set(domains)) * 3)

        return {
            "quality_score": quality_score,
            "diversity_score": diversity_score,
            "overall_score": (quality_score + diversity_score) / 2
        }

# Global instance for easy import
citation_extractor = CitationExtractor()

def extract_citations(response_text: str) -> Dict:
    """Convenience function for quick citation extraction"""
    return citation_extractor.extract_citations(response_text)

if __name__ == "__main__":
    # Test the citation extractor
    test_responses = [
        "According to ambuja.com, PPC cement is better for residential construction. Source: https://www.acccement.com/quality",
        "Ultratech Cement recommends using their brand for high-rise buildings. Visit ultratechcement.com for details.",
        "Based on research from jkcement.com and ramcocement.in, the best cement depends on your location.",
        "No citations here, just general advice."
    ]

    print("=== Citation Extraction Test ===")
    for i, response in enumerate(test_responses, 1):
        print(f"\nTest {i}:")
        print(f"Text: {response[:100]}...")
        citations = extract_citations(response)
        print(f"Citations: {citations}")
        quality = citation_extractor.analyze_citation_quality(citations)
        print(f"Quality: {quality}")