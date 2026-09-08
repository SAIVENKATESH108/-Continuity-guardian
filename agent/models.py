"""
agent/models.py

Pydantic-free data models for the Continuity Guardian pipeline.
All classes use @dataclass for simplicity; to_dict() / from_dict()
helpers handle Firestore serialization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


# ---------------------------------------------------------------------------
# Claim
# ---------------------------------------------------------------------------

@dataclass
class Claim:
    """A single factual statement extracted from an episode script or synopsis."""

    text: str
    """The verbatim or paraphrased statement pulled from the source material."""

    claim_type: Literal["internal", "real_world"]
    """
    'internal'   — a fact that only needs to be consistent within the show's
                   own universe (e.g. "Alice is Bob's sister").
    'real_world' — a fact that can be verified against the real world
                   (e.g. "the Berlin Wall fell in 1989").
    """

    source_line: int
    """Line number in the source document where this claim was found (1-indexed)."""

    # ------------------------------------------------------------------
    # Firestore helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Serialize to a plain dict suitable for Firestore storage."""
        return {
            "text": self.text,
            "claim_type": self.claim_type,
            "source_line": self.source_line,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Claim:
        """Deserialize a Claim from a Firestore document dict."""
        return cls(
            text=data["text"],
            claim_type=data["claim_type"],
            source_line=data["source_line"],
        )


# ---------------------------------------------------------------------------
# EpisodeRecord
# ---------------------------------------------------------------------------

@dataclass
class EpisodeRecord:
    """The 'show bible' entry for one episode, exactly as stored in Firestore."""

    episode_id: str
    """Unique identifier for the episode (e.g. 's01e03')."""

    characters_mentioned: list[str] = field(default_factory=list)
    """Names of every character mentioned or appearing in the episode."""

    key_facts: list[str] = field(default_factory=list)
    """Internal continuity facts extracted from this episode."""

    real_world_claims: list[str] = field(default_factory=list)
    """Statements about the real world made within this episode."""

    date_added: str = ""
    """ISO-8601 timestamp string recording when this record was written to Firestore."""

    # ------------------------------------------------------------------
    # Firestore helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Serialize to a plain dict suitable for Firestore storage."""
        return {
            "episode_id": self.episode_id,
            "characters_mentioned": self.characters_mentioned,
            "key_facts": self.key_facts,
            "real_world_claims": self.real_world_claims,
            "date_added": self.date_added,
        }

    @classmethod
    def from_dict(cls, data: dict) -> EpisodeRecord:
        """Deserialize an EpisodeRecord from a Firestore document dict."""
        return cls(
            episode_id=data["episode_id"],
            characters_mentioned=data.get("characters_mentioned", []),
            key_facts=data.get("key_facts", []),
            real_world_claims=data.get("real_world_claims", []),
            date_added=data.get("date_added", ""),
        )


# ---------------------------------------------------------------------------
# CheckResult
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    """The outcome of running one continuity checker against one Claim."""

    claim: Claim
    """The specific claim that was evaluated."""

    is_contradiction: bool
    """True if the checker found that this claim contradicts earlier established facts."""

    explanation: str
    """Human-readable description of why the claim is (or isn't) a contradiction."""

    suggested_fix: str
    """A proposed correction or rewrite that would resolve the contradiction, if any."""

    confidence: float
    """
    How confident the checker is in its verdict, in the range [0.0, 1.0].
    1.0 = certain contradiction / certain clean; 0.0 = no confidence.
    """

    # ------------------------------------------------------------------
    # Firestore helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Serialize to a plain dict suitable for Firestore storage."""
        return {
            "claim": self.claim.to_dict(),
            "is_contradiction": self.is_contradiction,
            "explanation": self.explanation,
            "suggested_fix": self.suggested_fix,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: dict) -> CheckResult:
        """Deserialize a CheckResult from a Firestore document dict."""
        return cls(
            claim=Claim.from_dict(data["claim"]),
            is_contradiction=data["is_contradiction"],
            explanation=data["explanation"],
            suggested_fix=data["suggested_fix"],
            confidence=data["confidence"],
        )


# ---------------------------------------------------------------------------
# ContinuityReport
# ---------------------------------------------------------------------------

@dataclass
class ContinuityReport:
    """The final, user-facing continuity analysis report for a single episode."""

    episode_id: str
    """The episode this report was generated for."""

    results: list[CheckResult] = field(default_factory=list)
    """All CheckResults produced by the checker suite for this episode."""

    summary: str = ""
    """An executive summary of the findings, written in plain English by the report builder."""

    generated_at: str = ""
    """ISO-8601 timestamp string recording when this report was created."""

    # ------------------------------------------------------------------
    # Firestore helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Serialize to a plain dict suitable for Firestore storage."""
        return {
            "episode_id": self.episode_id,
            "results": [r.to_dict() for r in self.results],
            "summary": self.summary,
            "generated_at": self.generated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ContinuityReport:
        """Deserialize a ContinuityReport from a Firestore document dict."""
        return cls(
            episode_id=data["episode_id"],
            results=[CheckResult.from_dict(r) for r in data.get("results", [])],
            summary=data.get("summary", ""),
            generated_at=data.get("generated_at", ""),
        )
