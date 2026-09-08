"""
agent/extractor.py

FactExtractor uses the Gemini API to pull structured Claim objects out of
raw episode script text.  It is the first stage of the pipeline: everything
downstream works on the list[Claim] this module produces.

Caching note: identical script text is never sent to Gemini twice.  The
SimpleCache from agent/cache.py is used as a transparent memoization layer,
keyed on the raw script text.  This keeps API costs low during repeated
development runs and test cycles.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import google.generativeai as genai
from dotenv import load_dotenv

from agent.cache import SimpleCache
from agent.models import Claim

# ---------------------------------------------------------------------------
# Module-level setup
# ---------------------------------------------------------------------------

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_SYSTEM_INSTRUCTION = """
You are a script continuity analyst. Your job is to read a TV or film script
excerpt and extract every factual claim it contains.

Classify each claim into one of two categories:

  "internal"    — A fact that exists only within this show's fictional universe.
                  Examples: character relationships, invented locations, plot events,
                  made-up technology, fictional organisations.
                  (e.g. "Maya's brother is alive", "the story is set in Portland")

  "real_world"  — A statement that references the actual world and could be
                  independently verified against real sources: history, science,
                  geography, current events, real people, real dates.
                  (e.g. "penicillin was discovered in 1928",
                         "Mount Everest is the tallest mountain")

OUTPUT FORMAT — respond with VALID JSON only.
Return a JSON array where every element has exactly these three fields:
  {
    "text":        "<the claim, verbatim or lightly paraphrased>",
    "claim_type":  "internal" | "real_world",
    "source_line": <1-based integer line number where this claim appears>
  }

Rules:
  - Output ONLY the JSON array. No markdown fences, no explanation, no preamble.
  - If you find no claims, output an empty array: []
  - Do not invent claims that are not in the text.
  - Each claim should be a single, atomic fact (one idea per entry).
""".strip()

_RETRY_SUFFIX = """

IMPORTANT REMINDER: your previous response could not be parsed as JSON.
Output the JSON array and NOTHING else — no ```json fences, no explanation,
no prose. Start your response with [ and end with ].
""".strip()


# ---------------------------------------------------------------------------
# FactExtractor
# ---------------------------------------------------------------------------

class FactExtractor:
    """
    Extracts structured Claim objects from raw script text using Gemini.

    Instantiate once per process and reuse — the Gemini client and the
    SimpleCache are shared across calls.

    Args:
        model_name:  Gemini model identifier to use.
        ttl_seconds: How long extracted results are cached (default 24 h).
    """

    def __init__(
        self,
        model_name: str = "gemini-3.5-flash",
        ttl_seconds: int = 24 * 60 * 60,
    ) -> None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "GEMINI_API_KEY is not set. "
                "Copy .env.example to .env and add your key."
            )

        genai.configure(api_key=api_key)

        self._model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=_SYSTEM_INSTRUCTION,
        )
        self._cache = SimpleCache(ttl_seconds=ttl_seconds)

        logger.info("FactExtractor initialised (model=%s).", model_name)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(self, script_text: str) -> list[Claim]:
        """
        Extract all factual claims from *script_text* and return them as
        a list of Claim objects.

        On the first call with a given script, the text is sent to Gemini.
        On subsequent calls with the same text, the cached result is returned
        immediately — no API call is made.

        If Gemini returns malformed JSON on the first attempt, one retry is
        made with a stricter prompt reminding the model to output JSON only.
        If the retry also fails, an empty list is returned and the error is
        logged so the pipeline can continue with whatever other episodes it has.

        Args:
            script_text: The raw episode script or synopsis to analyse.

        Returns:
            A (possibly empty) list of Claim objects.
        """
        if not script_text or not script_text.strip():
            logger.warning("extract() called with empty script text — returning [].")
            return []

        # ---- Cache check ----
        cached = self._cache.get(script_text)
        if cached is not None:
            logger.debug("Cache hit — returning %d cached claim(s).", len(cached))
            return cached

        # ---- First attempt ----
        raw_response = self._call_gemini(script_text)
        claims = self._parse_claims(raw_response)

        if claims is None:
            # ---- Retry with stricter instruction ----
            logger.warning(
                "Gemini returned non-JSON on first attempt — retrying with "
                "stricter prompt."
            )
            retry_prompt = script_text + "\n\n" + _RETRY_SUFFIX
            raw_response = self._call_gemini(retry_prompt)
            claims = self._parse_claims(raw_response)

        if claims is None:
            logger.error(
                "Gemini returned non-JSON on both attempts. "
                "Returning empty claim list so the pipeline can continue."
            )
            return []

        # ---- Store in cache and return ----
        self._cache.set(script_text, claims)
        logger.debug("Extracted and cached %d claim(s).", len(claims))
        return claims

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _call_gemini(self, prompt: str) -> str:
        """
        Send *prompt* to the Gemini model and return the raw text response.

        Any API-level exception is caught here so the caller can decide
        how to handle it (retry, log, return empty list, etc.).

        Returns:
            The model's response text, or an empty string on error.
        """
        try:
            response = self._model.generate_content(prompt)
            return response.text or ""
        except Exception as exc:  # noqa: BLE001
            logger.error("Gemini API call failed: %s", exc)
            return ""

    def _parse_claims(self, raw: str) -> list[Claim] | None:
        """
        Attempt to parse *raw* as a JSON array and convert each element
        into a Claim dataclass.

        Returns:
            A list of Claim objects on success, or None if *raw* is not
            valid JSON or does not match the expected schema.
        """
        if not raw.strip():
            return None

        # Strip accidental markdown fences that some model versions add.
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            # Remove opening fence (```json or ```)
            cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.strip()

        try:
            data: Any = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.debug("JSON parse failed: %s — raw snippet: %.200s", exc, raw)
            return None

        if not isinstance(data, list):
            logger.debug(
                "Expected a JSON array but got %s.", type(data).__name__
            )
            return None

        claims: list[Claim] = []
        for i, item in enumerate(data):
            try:
                claim = Claim(
                    text=str(item["text"]),
                    claim_type=item["claim_type"],   # Literal validated below
                    source_line=int(item["source_line"]),
                )
                if claim.claim_type not in ("internal", "real_world"):
                    logger.warning(
                        "Skipping claim %d — unknown claim_type %r.",
                        i,
                        claim.claim_type,
                    )
                    continue
                claims.append(claim)
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning(
                    "Skipping malformed claim at index %d: %s — item: %r",
                    i,
                    exc,
                    item,
                )

        return claims


# ---------------------------------------------------------------------------
# Standalone test — run: python -m agent.extractor
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import pprint

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(levelname)-8s %(name)s — %(message)s",
    )

    SAMPLE_SCRIPT = """\
Line 1: INT. DETECTIVE AGENCY — DAY
Line 2: MAYA sits across from her client, visibly shaken.
Line 3: MAYA: My brother Daniel is still alive — I'm certain of it.
Line 4: CLIENT: But the police said the accident happened near the Golden Gate Bridge.
Line 5: MAYA: Bridges can be faked. Besides, Daniel knew that penicillin was
Line 6:        first discovered by Alexander Fleming in 1928. He'd never let
Line 7:        a little thing like a bridge stop him.
Line 8: CLIENT: So you think he's hiding somewhere in the city?
Line 9: MAYA: He mentioned once that he loved Seattle. Not Portland. Seattle.
Line 10: MAYA: The real question is why Apex Corp wants us to think he's dead.
"""

    extractor = FactExtractor()

    print("\n── First call (should hit Gemini) ──")
    claims = extractor.extract(SAMPLE_SCRIPT)
    pprint.pprint([c.to_dict() for c in claims])

    print(f"\n── Second call (should be a cache hit — cache size: {len(extractor._cache)}) ──")
    claims_again = extractor.extract(SAMPLE_SCRIPT)
    assert claims_again is claims or [c.to_dict() for c in claims_again] == [c.to_dict() for c in claims], \
        "Cache returned different results!"
    print(f"Returned {len(claims_again)} claim(s) — cache working correctly.")
