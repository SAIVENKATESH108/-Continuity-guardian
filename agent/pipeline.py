"""
agent/pipeline.py

ContinuityPipeline orchestrates every stage of the Continuity Guardian
workflow in the correct order, using the Google Agent Development Kit (ADK)
to model the agentic reasoning loop and asyncio for concurrency.

Why concurrent checker execution matters (step d)
---------------------------------------------------
InternalChecker calls Gemini with show-bible context.
RealWorldChecker calls the Parallel Search MCP server, then Gemini again.

These two operations are completely independent of each other — neither
needs the other's result to start.  If run sequentially, total latency is
roughly:

    latency_total ≈ internal_check_time + real_world_check_time

For a script with 10 internal claims and 10 real-world claims, that could
easily be 20+ seconds.  With asyncio.gather(), both checker groups run in
parallel across a thread pool:

    latency_total ≈ max(internal_check_time, real_world_check_time)

This halves wall-clock time in the typical case where both checker groups
have similar workloads, and gives an even bigger win when one group is
much larger than the other.

Note: the checkers (InternalChecker, RealWorldChecker) are synchronous
because they use blocking I/O (google-generativeai, httpx).  We lift them
into asyncio using loop.run_in_executor(), which runs each call in the
default ThreadPoolExecutor so they don't block the event loop.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from functools import partial
from typing import Any

from dotenv import load_dotenv

from agent.cache import SimpleCache
from agent.checkers import InternalChecker, RealWorldChecker
from agent.extractor import FactExtractor
from agent.models import Claim, CheckResult, ContinuityReport, EpisodeRecord
from agent.report_builder import ReportBuilder
from agent.repository import ShowBibleRepository

# ---------------------------------------------------------------------------
# ADK import — optional structural enhancement
# ---------------------------------------------------------------------------
# google-adk provides an Agent base class and lifecycle hooks that make
# the pipeline observable via the ADK dashboard and composable with other
# ADK agents.  We import it defensively so the pipeline still works in
# environments where only the core dependencies are installed.

try:
    from google.adk.agents import Agent as _AdkAgent          # type: ignore[import]
    _ADK_AVAILABLE = True
except ImportError:
    _AdkAgent = object  # plain object as a no-op base class
    _ADK_AVAILABLE = False

# ---------------------------------------------------------------------------
# Module-level setup
# ---------------------------------------------------------------------------

load_dotenv()

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ContinuityPipeline
# ---------------------------------------------------------------------------

class ContinuityPipeline:
    """
    Top-level agent that runs the full Continuity Guardian workflow.

    Usage::

        pipeline = ContinuityPipeline()
        report = await pipeline.run(episode_id="s01e03", script_text="...")
    """

    name = "continuity_guardian"
    description = (
        "Analyses a TV or film episode script for continuity errors and "
        "real-world factual inaccuracies, cross-referenced against a "
        "persistent show bible stored in Firestore."
    )

    def __init__(self) -> None:
        if _ADK_AVAILABLE:
            try:
                self.adk_agent = _AdkAgent(
                    name=self.name,
                    model=os.getenv("GEMINI_MODEL", "gemini-3.6-flash"),
                    description=self.description,
                    instruction=(
                        "You are a Hollywood script continuity analyst identifying factual "
                        "and narrative inconsistencies across episodes."
                    ),
                )
                logger.info("ADK agent initialised — pipeline is ADK-native.")
            except Exception as exc:
                logger.warning("Could not initialize ADK Agent: %s", exc)
                self.adk_agent = None
        else:
            self.adk_agent = None
            logger.warning(
                "google-adk not found — running in standalone mode. "
                "Install google-adk for ADK dashboard integration."
            )

        # ---- Instantiate all pipeline components ----
        logger.info("Initialising pipeline components…")

        self.extractor = FactExtractor()
        logger.debug("  ✓ FactExtractor ready.")

        self.repository = ShowBibleRepository()
        logger.debug("  ✓ ShowBibleRepository ready.")

        self.internal_checker = InternalChecker()
        logger.debug("  ✓ InternalChecker ready.")

        self.real_world_checker = RealWorldChecker()
        logger.debug("  ✓ RealWorldChecker ready.")

        self.report_builder = ReportBuilder()
        logger.debug("  ✓ ReportBuilder ready.")

        # Shared SimpleCache: components also carry their own caches
        # (keyed differently); this top-level cache is reserved for
        # future pipeline-level memoisation (e.g. full-run deduplication).
        self.cache = SimpleCache(ttl_seconds=24 * 60 * 60)
        logger.debug("  ✓ Shared SimpleCache ready.")

        logger.info("ContinuityPipeline fully initialised.")

    # ------------------------------------------------------------------ #
    # Main entry point                                                     #
    # ------------------------------------------------------------------ #

    async def run(
        self,
        episode_id: str,
        script_text: str,
    ) -> ContinuityReport:
        """
        Run the full continuity analysis pipeline for one episode.

        Stages
        ------
        1. Extract claims from the script (FactExtractor → list[Claim]).
        2. Split claims by type: internal vs real_world.
        3. Fetch show-bible context from Firestore for the internal claims.
        4. Run InternalChecker and RealWorldChecker CONCURRENTLY (asyncio.gather).
        5. Build the final ContinuityReport (ReportBuilder).
        6. Persist this episode to Firestore so it enriches future checks.

        Args:
            episode_id:  A unique identifier for this episode (e.g. 's01e03').
            script_text: The raw episode script or synopsis text to analyse.

        Returns:
            A fully assembled ContinuityReport.

        Raises:
            This method is designed to be resilient: every stage catches its
            own exceptions and degrades gracefully.  An error in one stage
            will not prevent the pipeline from producing a (possibly partial)
            report.
        """
        logger.info("═══ Pipeline start — episode=%s ═══", episode_id)

        # ── Stage 1: Claim extraction ─────────────────────────────────────
        logger.info("[1/6] Extracting claims from script text…")
        claims = await self._run_sync(self.extractor.extract, script_text)
        logger.info(
            "[1/6] Extracted %d claim(s) from episode=%s.", len(claims), episode_id
        )

        if not claims:
            logger.warning(
                "No claims extracted from episode=%s — returning empty report.",
                episode_id,
            )
            return self._empty_report(episode_id)

        # ── Stage 2: Split by claim type ──────────────────────────────────
        logger.info("[2/6] Splitting claims by type…")
        internal_claims = [c for c in claims if c.claim_type == "internal"]
        real_world_claims = [c for c in claims if c.claim_type == "real_world"]
        logger.info(
            "[2/6] %d internal claim(s), %d real-world claim(s).",
            len(internal_claims),
            len(real_world_claims),
        )

        # ── Stage 3: Fetch show-bible context ─────────────────────────────
        logger.info("[3/6] Fetching show-bible context from Firestore…")
        character_names = _extract_character_names(internal_claims)
        logger.debug("[3/6] Looking up characters: %s", character_names)

        context_episodes: list[EpisodeRecord] = []
        if character_names:
            all_matched = await self._run_sync(
                self.repository.find_related_facts, character_names
            )
            # Only compare against prior canonical episodes — never validate against the unverified draft itself
            context_episodes = [ep for ep in all_matched if ep.episode_id.lower() != episode_id.lower()]
        logger.info(
            "[3/6] Found %d related episode(s) in show bible.",
            len(context_episodes),
        )

        # ── Stage 4: Run both checker groups CONCURRENTLY ─────────────────
        #
        # WHY asyncio.gather HERE:
        # InternalChecker and RealWorldChecker are independent — internal
        # checks query Gemini + Firestore context, real-world checks query
        # Parallel Search then Gemini.  Neither result is needed by the other.
        # Running them in parallel with asyncio.gather() means total wall-clock
        # time ≈ max(internal_time, real_world_time) rather than their sum.
        # For a script with many claims of each type this is a significant
        # speedup; for small scripts the overhead is negligible.
        #
        logger.info(
            "[4/6] Running checkers concurrently — "
            "%d internal + %d real-world claim(s)…",
            len(internal_claims),
            len(real_world_claims),
        )

        internal_task = self._run_all_internal(internal_claims, context_episodes)
        real_world_task = self._run_all_real_world(real_world_claims)

        internal_results, real_world_results = await asyncio.gather(
            internal_task,
            real_world_task,
            return_exceptions=False,
        )

        all_results: list[CheckResult] = internal_results + real_world_results
        logger.info(
            "[4/6] Checker stage complete — %d total result(s) (%d internal, %d real-world).",
            len(all_results),
            len(internal_results),
            len(real_world_results),
        )

        # ── Stage 5: Build report ─────────────────────────────────────────
        logger.info("[5/6] Building ContinuityReport…")
        report = await self._run_sync(
            self.report_builder.build, episode_id, all_results
        )
        logger.info(
            "[5/6] Report built — %d contradiction(s) surfaced, summary: %.80s…",
            len(report.results),
            report.summary,
        )

        # ── Stage 6: Persist episode to show bible (only if clean) ────────
        has_contradictions = any(r.is_contradiction for r in report.results)
        if not has_contradictions:
            logger.info("[6/6] Clean episode approved — persisting to Firestore show bible…")
            episode_record = _build_episode_record(episode_id, claims)
            saved = await self._run_sync(self.repository.save_episode, episode_record)
            if saved:
                logger.info(
                    "[6/6] Episode=%s saved to show bible (%d key fact(s), %d character(s)).",
                    episode_id,
                    len(episode_record.key_facts),
                    len(episode_record.characters_mentioned),
                )
            else:
                logger.warning(
                    "[6/6] Could not save episode=%s to Firestore.",
                    episode_id,
                )
        else:
            logger.info(
                "[6/6] Episode=%s contains %d unapproved contradiction(s) — skipping show-bible persistence.",
                episode_id,
                len(report.results),
            )

        logger.info("═══ Pipeline complete — episode=%s ═══", episode_id)
        return report

    # ------------------------------------------------------------------ #
    # Concurrent checker helpers                                          #
    # ------------------------------------------------------------------ #

    async def _run_all_internal(
        self,
        claims: list[Claim],
        context: list[EpisodeRecord],
    ) -> list[CheckResult]:
        """
        Run InternalChecker.check_batch() to evaluate all internal claims in a single
        unified API pass, preventing rate-limiting while providing deep canon context.
        """
        if not claims:
            return []

        results: list[CheckResult] = await self._run_sync(
            self.internal_checker.check_batch, claims, context
        )
        logger.debug(
            "_run_all_internal: %d claim(s) → %d result(s).",
            len(claims),
            len(results),
        )
        return results

    async def _run_all_real_world(
        self,
        claims: list[Claim],
    ) -> list[CheckResult]:
        """
        Run RealWorldChecker.check_batch() to evaluate all real-world claims in a single
        unified API pass with live web grounding.
        """
        if not claims:
            return []

        results: list[CheckResult] = await self._run_sync(
            self.real_world_checker.check_batch, claims
        )
        logger.debug(
            "_run_all_real_world: %d claim(s) → %d result(s).",
            len(claims),
            len(results),
        )
        return results

    # ------------------------------------------------------------------ #
    # Utility helpers                                                      #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def _run_sync(fn: Any, *args: Any) -> Any:
        """
        Run a blocking (synchronous) callable in the default ThreadPoolExecutor
        so it doesn't block the asyncio event loop.

        This is the bridge between asyncio.gather() and the synchronous
        checker / repository / extractor methods.

        Args:
            fn:    The synchronous callable to run off-thread.
            *args: Positional arguments forwarded to *fn*.

        Returns:
            Whatever *fn* returns.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(fn, *args))

    @staticmethod
    def _empty_report(episode_id: str) -> ContinuityReport:
        """Return a valid but empty ContinuityReport when no claims were found."""
        return ContinuityReport(
            episode_id=episode_id,
            results=[],
            summary=(
                "No claims could be extracted from the provided script text. "
                "Please check that the script is non-empty and try again."
            ),
            generated_at=datetime.now(tz=timezone.utc).isoformat(),
        )


# ---------------------------------------------------------------------------
# Module-level helpers (pure functions — no instance state needed)
# ---------------------------------------------------------------------------

def _extract_character_names(internal_claims: list[Claim]) -> list[str]:
    """
    Heuristically extract character name candidates from internal claims.

    Strategy: tokenise each claim into words, collect tokens that start with
    an uppercase letter and are longer than one character.  This is a simple
    approximation; a more robust approach would use an NER model or rely on
    the characters_mentioned list already extracted by Gemini in a prior step.

    Returns a deduplicated list of candidate names, capped at 30 to stay
    within Firestore's array-contains-any limit (enforced in repository.py).
    """
    candidates: set[str] = set()
    for claim in internal_claims:
        for token in claim.text.split():
            # Strip punctuation from the edges of each token
            word = token.strip(".,!?\"'()[]")
            if len(word) > 1 and word[0].isupper() and word.isalpha():
                candidates.add(word)

    result = sorted(candidates)[:30]  # deterministic ordering, respect Firestore limit
    return result


def _build_episode_record(
    episode_id: str,
    claims: list[Claim],
) -> EpisodeRecord:
    """
    Construct an EpisodeRecord from the claims extracted by FactExtractor.

    This record becomes part of the show bible and will be used as context
    for future episodes.  We derive:
      - characters_mentioned: uppercase-initial tokens from internal claims.
      - key_facts:            text of every internal claim.
      - real_world_claims:    text of every real_world claim.
    """
    internal = [c for c in claims if c.claim_type == "internal"]
    real_world = [c for c in claims if c.claim_type == "real_world"]

    characters = _extract_character_names(internal)
    key_facts = [c.text for c in internal]
    rw_texts = [c.text for c in real_world]

    return EpisodeRecord(
        episode_id=episode_id,
        characters_mentioned=characters,
        key_facts=key_facts,
        real_world_claims=rw_texts,
        date_added=datetime.now(tz=timezone.utc).isoformat(),
    )
