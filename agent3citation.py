"""
Agent 3: Citation Extraction Engine (Refined)
=============================================
Improvements over original:
- Broader brand list with aliases and partial matching
- Detects implicit brand mentions (not just exact-case)
- Filters noisy/generic domains (google.com, youtube.com, etc.)
- Adds quality_score based on domain authority signals
- Extracts "reference phrases" (e.g. "according to X", "as per X")
- Deduplicates domains and brands cleanly
"""

import re
from urllib.parse import urlparse
from dataclasses import dataclass, field, asdict
from typing import List, Set

# ──────────────────────────────────────────────
# BRAND KNOWLEDGE BASE
# ──────────────────────────────────────────────

# Each entry: canonical name -> list of match patterns (case-insensitive)
CEMENT_BRANDS: dict[str, list[str]] = {
    "UltraTech":  ["ultratech", "ultra tech"],
    "ACC":        [r"\bacc\b", "acc cement"],
    "Ambuja":     ["ambuja"],
    "JK Cement":  ["jk cement", r"\bjk\b cement"],
    "Dalmia":     ["dalmia"],
    "Shree":      ["shree cement", "shree"],
    "India Cements": ["india cements", "the india cement"],
    "Orient":     ["orient cement", "orient"],
    "Ramco":      ["ramco"],
    "Birla":      ["birla cement", "birla shakti", "birla gold"],
    "Prism":      ["prism cement", "prism johnson"],
    "Sanghi":     ["sanghi"],
    "Chettinad":  ["chettinad"],
    "Heidelberg": ["heidelberg", "mycem"],
    "Penna":      ["penna cement"],
    "Nuvoco":     ["nuvoco", "lafarge"],
    "Wonder":     ["wonder cement"],
    "Maha Cement":["maha cement", "maha"],
}

# Domains that are too generic to be meaningful citations
NOISE_DOMAINS: Set[str] = {
    "google.com", "youtube.com", "facebook.com", "twitter.com",
    "instagram.com", "linkedin.com", "wikipedia.org", "amazon.com",
    "flipkart.com", "reddit.com", "quora.com", "pinterest.com",
    "whatsapp.com", "t.co", "bit.ly", "goo.gl", "tinyurl.com",
}

# Domains that signal high authority in this domain
AUTHORITY_DOMAINS: Set[str] = {
    "ultratechcement.com", "acclimited.com", "ambujacement.com",
    "jkcement.com", "dalmiacement.com", "shreecement.com",
    "indiacements.com", "orientcement.com", "ramcocements.com",
    "bis.gov.in", "nit.ac.in", "iitb.ac.in", "constructionworld.in",
    "nbmcw.com", "theconstructionindex.com",
}

# Patterns that signal an explicit citation/reference in text
REFERENCE_PHRASES = [
    r"according to ([A-Za-z0-9\-\.]+)",
    r"as (?:mentioned|stated|noted|per|cited) (?:on|in|by) ([A-Za-z0-9\-\.]+)",
    r"source[:\s]+([A-Za-z0-9\-\.]+)",
    r"via ([A-Za-z0-9\-\.]+\.(?:com|org|in|net|gov))",
    r"from ([A-Za-z0-9\-\.]+\.(?:com|org|in|net|gov))",
    r"visit ([A-Za-z0-9\-\.]+\.(?:com|org|in|net|gov))",
    r"check ([A-Za-z0-9\-\.]+\.(?:com|org|in|net|gov))",
]

# URL regex — handles bare domains, https://, http://
URL_PATTERN = re.compile(
    r'https?://(?:www\.)?([a-zA-Z0-9\-]+(?:\.[a-zA-Z]{2,})+)'
    r'|(?<!\w)(?:www\.)?([a-zA-Z0-9\-]+\.(?:com|org|in|net|gov|edu|co\.in))(?!\w)',
    re.IGNORECASE
)


@dataclass
class CitationResult:
    urls: List[str] = field(default_factory=list)
    domains: List[str] = field(default_factory=list)
    cement_brands: List[str] = field(default_factory=list)
    reference_phrases: List[str] = field(default_factory=list)
    citation_count: int = 0
    has_external_links: bool = False
    has_brand_mentions: bool = False
    quality_score: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


class CitationExtractor:
    """Extract and score citations from AI-generated text."""

    def extract_citations(self, text: str) -> dict:
        if not text or not isinstance(text, str):
            return CitationResult().to_dict()

        result = CitationResult()

        # 1. Extract URLs and domains
        raw_urls, raw_domains = self._extract_urls(text)
        result.urls = raw_urls
        result.domains = [d for d in raw_domains if d not in NOISE_DOMAINS]

        # 2. Extract reference phrases (e.g. "according to X")
        result.reference_phrases = self._extract_reference_phrases(text)

        # 3. Detect cement brands (case-insensitive, deduplicated)
        result.cement_brands = self._detect_brands(text)

        # 4. Derived counts
        result.citation_count = len(result.urls) + len(result.reference_phrases)
        result.has_external_links = len(result.domains) > 0
        result.has_brand_mentions = len(result.cement_brands) > 0

        # 5. Quality score (0.0 – 1.0)
        result.quality_score = self._compute_quality_score(result)

        return result.to_dict()

    # ── Private helpers ──────────────────────────────────────

    def _extract_urls(self, text: str) -> tuple[list, list]:
        """Return (full_urls, cleaned_domains) — deduped, noise-filtered."""
        urls, domains = [], []
        seen_domains: Set[str] = set()

        for match in URL_PATTERN.finditer(text):
            # Group 1 = from http(s)://, group 2 = bare domain
            domain_raw = match.group(1) or match.group(2) or ""
            domain = domain_raw.lower().strip(".")

            if not domain or domain in seen_domains:
                continue
            seen_domains.add(domain)

            if "http" in match.group(0):
                urls.append(f"https://{domain}")
            domains.append(domain)

        return urls, domains

    def _extract_reference_phrases(self, text: str) -> list[str]:
        """Find explicit reference phrases like 'according to X'."""
        found = []
        for pattern in REFERENCE_PHRASES:
            for m in re.finditer(pattern, text, re.IGNORECASE):
                phrase = m.group(0).strip()
                if phrase and phrase not in found:
                    found.append(phrase)
        return found

    def _detect_brands(self, text: str) -> list[str]:
        """Detect cement brand mentions using the brand knowledge base."""
        found = []
        text_lower = text.lower()

        for canonical, patterns in CEMENT_BRANDS.items():
            for pattern in patterns:
                if re.search(pattern, text_lower):
                    if canonical not in found:
                        found.append(canonical)
                    break  # matched this brand, move on

        return found

    def _compute_quality_score(self, result: CitationResult) -> float:
        """
        Score from 0.0 to 1.0 based on:
        - Has authority domains (+0.4)
        - Has brand mentions (+0.2)
        - Has reference phrases (+0.2)
        - Citation count > 1 (+0.1)
        - Has URLs (+0.1)
        """
        score = 0.0

        # Authority domain bonus
        authority_hits = sum(1 for d in result.domains if d in AUTHORITY_DOMAINS)
        if authority_hits > 0:
            score += min(0.4, authority_hits * 0.2)

        if result.has_brand_mentions:
            score += 0.2

        if result.reference_phrases:
            score += min(0.2, len(result.reference_phrases) * 0.1)

        if result.citation_count > 1:
            score += 0.1

        if result.has_external_links:
            score += 0.1

        return round(min(score, 1.0), 3)


# Singleton for import
citation_extractor = CitationExtractor()