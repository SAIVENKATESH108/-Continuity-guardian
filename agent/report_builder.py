"""
agent/report_builder.py

ReportBuilder is the final stage of the pipeline.  It receives the raw
list of CheckResult objects produced by all checkers, filters to contradictions
only, asks Gemini to write a plain-English summary a writer can act on, and
assembles the finished ContinuityReport ready for Firestore storage and
frontend display.

This file contains NO formatting, printing, or presentation logic — that
responsibility belongs entirely to the API and frontend layers.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import google.generativeai as genai
from dotenv import load_dotenv

from agent.models import CheckResult, ContinuityReport

# ---------------------------------------------------------------------------
# Module-level setup
# ---------------------------------------------------------------------------

load_dotenv()

logger = logging.getLogger(__name__)

_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

_NO_ISSUES_SUMMARY = (
    "No continuity or factual issues found — this script is clear to proceed."
)

_SUMMARY_SYSTEM_INSTRUCTION = """
You are a script editor's assistant helping a TV writing team understand a
continuity analysis report.  Your audience is writers and producers, not
engineers.  Write in warm, clear, professional language — no bullet points,
no jargon, no technical terms like "JSON" or "confidence score".

You will be given a list of continuity or factual issues found in an episode
script.  Write a short summary paragraph (2-4 sentences) that covers:
  - How many issues were found overall.
  - Whether they seem minor or serious.
  - A brief note on the most important issue (if any stands out).

Keep the tone constructive and helpful, not alarming.  Output ONLY the
summary paragraph — no heading, no preamble, no sign-off.
""".strip()


# ---------------------------------------------------------------------------
# ReportBuilder
# ---------------------------------------------------------------------------

class ReportBuilder:
    """
    Assembles a finished ContinuityReport from raw checker output.

    Responsibilities:
      1. Filter CheckResults to contradictions only.
      2. Sort them by confidence (highest first) so the most certain issues
         appear at the top of the report.
      3. Generate a plain-English summary via Gemini (or use a hardcoded
         "all clear" message if there are no issues, saving an API call).
      4. Return a ContinuityReport with episode_id, sorted results, summary,
         and an ISO-8601 timestamp.
    """

    def __init__(self) -> None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "GEMINI_API_KEY is not set. "
                "Copy .env.example to .env and fill in your key."
            )
        genai.configure(api_key=api_key)

        self._model = genai.GenerativeModel(
            model_name=_GEMINI_MODEL,
            system_instruction=_SUMMARY_SYSTEM_INSTRUCTION,
        )
        logger.info("ReportBuilder initialised (model=%s).", _GEMINI_MODEL)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(
        self,
        episode_id: str,
        results: list[CheckResult],
    ) -> ContinuityReport:
        """
        Build and return a ContinuityReport for *episode_id*.

        Args:
            episode_id: Identifier for the episode being reported on
                        (e.g. 's01e03').
            results:    The full list of CheckResult objects produced by all
                        checkers for this episode.  Non-contradiction results
                        are silently filtered out — they don't appear in the
                        report because there is nothing to flag.

        Returns:
            A ContinuityReport containing only the flagged contradictions,
            sorted by confidence, with a Gemini-written (or hardcoded) summary
            and a UTC timestamp.
        """
        # ---- Step 1: filter to contradictions only ----
        flagged = [r for r in results if r.is_contradiction]

        logger.info(
            "episode=%s — %d total result(s), %d flagged as contradiction(s).",
            episode_id,
            len(results),
            len(flagged),
        )

        # ---- Step 2: sort by confidence, highest first ----
        flagged.sort(key=lambda r: r.confidence, reverse=True)

        # ---- Step 3: generate summary ----
        if not flagged:
            summary = _NO_ISSUES_SUMMARY
            logger.debug(
                "No contradictions found for episode=%s — skipping Gemini call.",
                episode_id,
            )
        else:
            summary = self._generate_summary(episode_id, flagged)

        # ---- Step 4: assemble and return the report ----
        report = ContinuityReport(
            episode_id=episode_id,
            results=flagged,
            summary=summary,
            generated_at=_utc_now_iso(),
        )

        logger.info(
            "Report built for episode=%s — %d issue(s) surfaced.",
            episode_id,
            len(flagged),
        )
        return report

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _generate_summary(
        self,
        episode_id: str,
        flagged: list[CheckResult],
    ) -> str:
        """
        Ask Gemini to write a short, writer-friendly summary of the flagged issues.

        If the Gemini call fails for any reason, falls back to a simple
        hardcoded template so the report is never returned with an empty summary.

        Args:
            episode_id: Used to contextualise the prompt.
            flagged:    The sorted list of contradiction CheckResults.

        Returns:
            A 2-4 sentence plain-English summary paragraph.
        """
        prompt = self._build_summary_prompt(episode_id, flagged)

        candidates = [
            getattr(self, "_model_name", None) or "gemini-flash-latest",
            "gemini-flash-latest",
            "gemini-3.7-flash",
            "gemini-3.8-flash",
            "gemini-3.6-flash",
        ]
        seen = set()
        for name in candidates:
            if not name or name in seen:
                continue
            seen.add(name)
            try:
                m = genai.GenerativeModel(
                    model_name=name,
                    system_instruction=_SUMMARY_SYSTEM_INSTRUCTION,
                )
                response = m.generate_content(prompt)
                summary = (response.text or "").strip()
                if summary:
                    logger.debug("Gemini summary generated via %s (%d chars).", name, len(summary))
                    return summary
            except Exception as exc:
                logger.warning("ReportBuilder model '%s' failed: %s — trying next.", name, exc)
                continue

        # Graceful fallback: a factually correct (if bland) summary
        return self._fallback_summary(flagged)

    @staticmethod
    def _build_summary_prompt(episode_id: str, flagged: list[CheckResult]) -> str:
        """
        Format a Gemini prompt listing all flagged issues in readable form.

        Includes the claim text, checker verdict, explanation, and confidence
        so Gemini can gauge relative seriousness without needing to interpret
        raw floats in the output.
        """
        lines = [
            f"Episode: {episode_id}",
            f"Total issues found: {len(flagged)}",
            "",
            "Issues (listed from most to least confident):",
        ]

        for i, result in enumerate(flagged, start=1):
            confidence_pct = int(result.confidence * 100)
            lines.append(
                f"\n{i}. Claim: \"{result.claim.text}\"\n"
                f"   Type: {result.claim.claim_type}\n"
                f"   Explanation: {result.explanation}\n"
                f"   Confidence: {confidence_pct}%"
            )

        lines.append(
            "\nWrite a 2-4 sentence summary a script writer would find helpful."
        )
        return "\n".join(lines)

    @staticmethod
    def _fallback_summary(flagged: list[CheckResult]) -> str:
        """
        A simple template-based summary used when the Gemini call fails.

        This is intentionally plain — it's a last resort, not the primary path.
        """
        count = len(flagged)
        high_confidence = sum(1 for r in flagged if r.confidence >= 0.7)

        if high_confidence == count:
            severity_note = "all of which appear to be high-confidence issues."
        elif high_confidence == 0:
            severity_note = "though the checker's confidence in each is relatively low — manual review is advised."
        else:
            severity_note = (
                f"{high_confidence} of which appear high-confidence and "
                f"{count - high_confidence} of which may warrant manual review."
            )

        return (
            f"The analysis found {count} potential continuity or factual "
            f"issue{'s' if count != 1 else ''} in this episode, {severity_note} "
            "Please review the flagged items below and consider the suggested "
            "fixes before the script goes to production."
        )


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string with timezone suffix."""
    return datetime.now(tz=timezone.utc).isoformat()
