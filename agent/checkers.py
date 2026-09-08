"""
agent/checkers.py

Continuity-checking strategy classes.

Architecture note — why the strategy pattern?
---------------------------------------------
Both InternalChecker and RealWorldChecker expose the *identical* method
signature:

    check(claim: Claim, context: Any) -> CheckResult

This is intentional.  The pipeline (agent/pipeline.py) holds a list of
checker instances and calls checker.check(claim, context) in a loop — it
never needs to know *which* kind of checker it is talking to.  Adding a new
checking strategy in the future (e.g. a database lookup checker or a
human-review flagging checker) requires only:

  1. Subclassing BaseChecker.
  2. Registering the new instance in the pipeline's checker list.

No if/else chains, no isinstance() calls, no changes to the pipeline itself.

Imports from the rest of the project
-------------------------------------
  - agent.models   → Claim, EpisodeRecord, CheckResult
  - agent.cache    → SimpleCache (memoises Gemini and web-search calls)
  - google.generativeai → Gemini API
  - httpx          → HTTP client for the Parallel Search MCP endpoint
"""

from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any

import google.generativeai as genai
import httpx
from dotenv import load_dotenv

from agent.cache import SimpleCache
from agent.models import Claim, CheckResult, EpisodeRecord

# ---------------------------------------------------------------------------
# Module-level setup
# ---------------------------------------------------------------------------

load_dotenv()

logger = logging.getLogger(__name__)

_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

# Parallel AI MCP search endpoint
_PARALLEL_SEARCH_URL = "https://search-mcp.parallel.ai/mcp"

# TTLs
_INTERNAL_TTL = 24 * 60 * 60   # 24 hours — show-bible facts change rarely
_REAL_WORLD_TTL = 6 * 60 * 60  # 6 hours  — real-world facts can change faster

# ---------------------------------------------------------------------------
# Shared prompt templates
# ---------------------------------------------------------------------------

_CHECKER_SYSTEM_INSTRUCTION = """
You are a continuity and fact-checking assistant for a TV production company.
You will be given a claim extracted from a script and some supporting context.
Your job is to judge whether the claim is accurate or contradicts established facts.

OUTPUT FORMAT — respond with VALID JSON only.
Return a single JSON object with exactly these four fields:
{
  "is_contradiction": true | false,
  "explanation":      "<one concise paragraph explaining your verdict>",
  "suggested_fix":    "<a proposed rewrite that would remove the contradiction, or empty string if none>",
  "confidence":       <float between 0.0 and 1.0>
}

Rules:
  - Output ONLY the JSON object. No markdown fences, no preamble, no extra text.
  - Start your response with { and end with }.
  - If you are uncertain, set confidence below 0.5 and explain why.
  - suggested_fix may be an empty string "" if there is no contradiction.
""".strip()

_RETRY_REMINDER = (
    "\n\nIMPORTANT: Your previous response was not valid JSON. "
    "Output ONLY the JSON object. Start with { and end with }. "
    "No markdown fences, no explanation outside the JSON."
)


# ---------------------------------------------------------------------------
# Helpers shared by both checkers
# ---------------------------------------------------------------------------

def _configure_gemini() -> None:
    """Configure the Gemini library with the API key from the environment."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "GEMINI_API_KEY is not set. Copy .env.example → .env and fill it in."
        )
    genai.configure(api_key=api_key)


def _call_gemini(model: genai.GenerativeModel, prompt: str) -> str:
    """Send *prompt* to *model* and return the raw text response, with multi-model quota failover."""
    candidates = [
        getattr(model, "_model_name", None) or "gemini-flash-latest",
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
                system_instruction=_CHECKER_SYSTEM_INSTRUCTION,
            )
            response = m.generate_content(prompt)
            if response and response.text:
                return response.text
        except Exception as exc:
            logger.warning("Checker model '%s' call failed: %s — trying next candidate.", name, exc)
            continue
    return ""


def _parse_check_result(raw: str, claim: Claim) -> CheckResult | None:
    """
    Parse a raw Gemini response string into a CheckResult.

    Returns None if the string is not valid JSON or does not match the
    expected schema, so callers can trigger a retry.
    """
    cleaned = raw.strip()

    # Strip accidental markdown fences
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
    if cleaned.endswith("```"):
        cleaned = cleaned.rsplit("```", 1)[0]
    cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.debug("JSON parse failed: %s — raw: %.200s", exc, raw)
        return None

    if not isinstance(data, dict):
        logger.debug("Expected JSON object, got %s.", type(data).__name__)
        return None

    try:
        return CheckResult(
            claim=claim,
            is_contradiction=bool(data["is_contradiction"]),
            explanation=str(data["explanation"]),
            suggested_fix=str(data.get("suggested_fix", "")),
            confidence=float(data["confidence"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("Malformed CheckResult schema: %s — data: %r", exc, data)
        return None


def _gemini_with_retry(
    model: genai.GenerativeModel, prompt: str, claim: Claim
) -> CheckResult:
    """
    Call Gemini with *prompt*, parse the response into a CheckResult.
    On JSON failure, retry once with a stricter instruction appended.
    Falls back to a low-confidence, non-contradiction result if both attempts fail.
    """
    raw = _call_gemini(model, prompt)
    result = _parse_check_result(raw, claim)

    if result is None:
        logger.warning("Retrying Gemini call with stricter JSON instruction.")
        raw = _call_gemini(model, prompt + _RETRY_REMINDER)
        result = _parse_check_result(raw, claim)

    if result is None:
        logger.error(
            "Both Gemini attempts failed to produce valid JSON for claim: %r. "
            "Returning a default non-contradiction result.",
            claim.text,
        )
        result = CheckResult(
            claim=claim,
            is_contradiction=False,
            explanation=(
                "The checker could not produce a valid analysis response. "
                "Manual review is recommended."
            ),
            suggested_fix="",
            confidence=0.0,
        )

    return result


# ---------------------------------------------------------------------------
# Abstract base class
# ---------------------------------------------------------------------------

class BaseChecker(ABC):
    """
    Abstract base for all continuity checkers.

    Subclasses implement one method — check() — and nothing else is required.
    The uniform signature is the contract that lets the pipeline call every
    checker interchangeably without branching on checker type.
    """

    @abstractmethod
    def check(self, claim: Claim, context: Any) -> CheckResult:
        """
        Evaluate *claim* against *context* and return a CheckResult.

        Args:
            claim:   The Claim extracted from the script by FactExtractor.
            context: Checker-specific supporting data:
                       - InternalChecker expects list[EpisodeRecord]
                       - RealWorldChecker expects None (it fetches its own context)

        Returns:
            A CheckResult describing whether a contradiction was found.
        """


# ---------------------------------------------------------------------------
# InternalChecker
# ---------------------------------------------------------------------------

class InternalChecker(BaseChecker):
    """
    Checks an 'internal' claim against the show bible stored in Firestore.

    Workflow:
      1. Receive a Claim and a list of relevant EpisodeRecords (provided by
         ShowBibleRepository.find_related_facts — already narrowed to episodes
         mentioning the same characters as this claim).
      2. Build a prompt containing the claim and all prior key_facts from those
         episodes.
      3. Ask Gemini: does this new claim contradict any of these established facts?
      4. Parse the response into a CheckResult and return it.

    Cache key: sha256(claim.text + sorted episode_ids) — same claim against the
    same context always returns a cached result; any new episode in context busts
    the cache naturally.
    """

    # Both checkers share the same check() signature — see module docstring.

    def __init__(self) -> None:
        _configure_gemini()
        self._model = genai.GenerativeModel(
            model_name=_GEMINI_MODEL,
            system_instruction=_CHECKER_SYSTEM_INSTRUCTION,
        )
        self._cache = SimpleCache(ttl_seconds=_INTERNAL_TTL)
        logger.info("InternalChecker initialised.")

    def check(self, claim: Claim, context: Any) -> CheckResult:
        """
        Evaluate an internal claim against prior EpisodeRecords.

        Args:
            claim:   A Claim with claim_type == "internal".
            context: list[EpisodeRecord] — relevant prior episodes from the
                     show bible.  Pass an empty list if no prior episodes exist.

        Returns:
            A CheckResult with Gemini's contradiction verdict.
        """
        episodes: list[EpisodeRecord] = context if isinstance(context, list) else []

        # ---- Build cache key ----
        episode_ids_sorted = sorted(ep.episode_id for ep in episodes)
        cache_key = claim.text + "|" + ",".join(episode_ids_sorted)

        cached = self._cache.get(cache_key)
        if cached is not None:
            logger.debug("InternalChecker cache hit for claim: %.60s…", claim.text)
            return cached

        # ---- Build prompt ----
        prior_facts_block = self._format_prior_facts(episodes)

        prompt = (
            f"CLAIM TO CHECK:\n{claim.text}\n\n"
            f"PRIOR ESTABLISHED FACTS FROM THE SHOW BIBLE:\n{prior_facts_block}\n\n"
            "Does the claim above contradict any of the prior established facts? "
            "Respond in strict JSON as instructed."
        )

        # ---- Call Gemini (with retry) ----
        result = _gemini_with_retry(self._model, prompt, claim)

        # ---- Cache and return ----
        self._cache.set(cache_key, result)
        return result

    @staticmethod
    def _format_prior_facts(episodes: list[EpisodeRecord]) -> str:
        """Format prior key_facts from all context episodes into a readable block."""
        if not episodes:
            return "(No prior episodes found — this may be the first episode.)"

        lines: list[str] = []
        for ep in episodes:
            lines.append(f"[{ep.episode_id}]")
            if ep.key_facts:
                for fact in ep.key_facts:
                    lines.append(f"  • {fact}")
            else:
                lines.append("  (no key facts recorded for this episode)")
        return "\n".join(lines)

    def check_batch(
        self, claims: list[Claim], context: list[EpisodeRecord]
    ) -> list[CheckResult]:
        """
        Evaluate a batch of internal claims in a single unified Gemini call.
        Eliminates free-tier rate limit (429) bottlenecks and dramatically reduces latency.
        """
        if not claims:
            return []

        prior_facts_block = self._format_prior_facts(context)
        claims_block = "\n".join(
            f"Claim [{i}]: {c.text} (line {c.source_line})"
            for i, c in enumerate(claims)
        )

        prompt = (
            f"PRIOR ESTABLISHED SHOW BIBLE CANON:\n{prior_facts_block}\n\n"
            f"CLAIMS EXTRACTED FROM DRAFT TO VERIFY:\n{claims_block}\n\n"
            "TASK:\n"
            "For each claim above, check whether it contradicts any established facts in the show bible canon.\n"
            "Respond in strict JSON with a JSON array where each item corresponds to one claim:\n"
            "[\n"
            "  {\n"
            '    "claim_index": 0,\n'
            '    "is_contradiction": true or false,\n'
            '    "explanation": "Detailed analysis of why it contradicts canon or is consistent",\n'
            '    "suggested_fix": "Screenplay repair recommendation if contradiction, else empty string",\n'
            '    "confidence": 0.95\n'
            "  }\n"
            "]\n"
            "Rules:\n"
            "- Output valid JSON only (no markdown fences, no extra text).\n"
            f"- Check every claim index from 0 to {len(claims) - 1}."
        )

        raw = _call_gemini(self._model, prompt)
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.strip()

        results_map: dict[int, CheckResult] = {}
        try:
            data = json.loads(cleaned)
            if isinstance(data, list):
                for item in data:
                    idx = item.get("claim_index")
                    if idx is not None and 0 <= idx < len(claims):
                        claim = claims[idx]
                        results_map[idx] = CheckResult(
                            claim=claim,
                            is_contradiction=bool(item.get("is_contradiction", False)),
                            explanation=str(item.get("explanation", "Consistent with established canon.")),
                            suggested_fix=str(item.get("suggested_fix", "")),
                            confidence=float(item.get("confidence", 0.9)),
                        )
        except Exception as exc:
            logger.warning("Failed to parse batch JSON in InternalChecker: %s", exc)

        results: list[CheckResult] = []
        for i, c in enumerate(claims):
            if i in results_map:
                results.append(results_map[i])
            else:
                results.append(self.check(c, context))
        return results


# ---------------------------------------------------------------------------
# RealWorldChecker
# ---------------------------------------------------------------------------

class RealWorldChecker(BaseChecker):
    """
    Checks a 'real_world' claim against live web search results.

    Workflow:
      1. Receive a Claim.
      2. Query the Parallel Search MCP server with the claim text as the
         search objective, retrieving live web results.
      3. Pass those results to Gemini, asking it to judge whether the claim
         is accurate based on the evidence found.
      4. Parse the response into a CheckResult and return it.

    Cache TTL is intentionally shorter (6 hours) than InternalChecker (24 hours)
    because real-world facts — laws, records, current events — can change,
    and stale cached verdicts could cause false negatives.

    Cache key: sha256(claim.text) — the search results are live so we don't
    include them in the key; the TTL is the freshness guarantee.
    """

    # Both checkers share the same check() signature — see module docstring.

    def __init__(self, http_timeout: float = 15.0) -> None:
        """
        Args:
            http_timeout: Seconds to wait for the Parallel Search MCP endpoint
                          before giving up.  Defaults to 15 s.
        """
        _configure_gemini()
        self._model = genai.GenerativeModel(
            model_name=_GEMINI_MODEL,
            system_instruction=_CHECKER_SYSTEM_INSTRUCTION,
        )
        self._cache = SimpleCache(ttl_seconds=_REAL_WORLD_TTL)
        self._http_timeout = http_timeout
        self._parallel_api_key = os.getenv("PARALLEL_API_KEY", "")
        logger.info("RealWorldChecker initialised (TTL=%dh).", _REAL_WORLD_TTL // 3600)

    def check(self, claim: Claim, context: Any) -> CheckResult:
        """
        Evaluate a real_world claim using live web search.

        Args:
            claim:   A Claim with claim_type == "real_world".
            context: Ignored — this checker fetches its own context via search.
                     Kept in the signature to match BaseChecker's contract.

        Returns:
            A CheckResult with Gemini's accuracy verdict, citing web sources.
        """
        # ---- Cache check ----
        cached = self._cache.get(claim.text)
        if cached is not None:
            logger.debug("RealWorldChecker cache hit for claim: %.60s…", claim.text)
            return cached

        # ---- Fetch search results ----
        search_results = self._search(claim.text)

        # ---- Build prompt ----
        prompt = (
            f"CLAIM TO VERIFY:\n{claim.text}\n\n"
            f"LIVE WEB SEARCH RESULTS:\n{search_results}\n\n"
            "Based on the search results above, is the claim accurate? "
            "In the explanation field, note that verification was performed "
            "via live web search and cite any relevant source titles or URLs "
            "from the results. Respond in strict JSON as instructed."
        )

        # ---- Call Gemini (with retry) ----
        result = _gemini_with_retry(self._model, prompt, claim)

        # ---- Cache and return ----
        self._cache.set(claim.text, result)
        return result

    def _search(self, query: str) -> str:
        """
        Call the Parallel Search MCP server and return a formatted string of
        results suitable for inclusion in a Gemini prompt.

        The MCP protocol uses JSON-RPC 2.0 over HTTP POST.  We call the
        ``tools/call`` method with tool name ``search`` and the claim text
        as the natural-language objective.

        Returns a human-readable block of results, or an error notice string
        if the request fails (so the pipeline can still produce a low-confidence
        result rather than crashing).
        """
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "web_search_preview",
                "arguments": {
                    "objective": f"Verify whether the following claim is factually accurate: {query}",
                    "search_queries": [query[:100]],
                },
            },
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self._parallel_api_key:
            headers["Authorization"] = f"Bearer {self._parallel_api_key}"

        try:
            response = httpx.post(
                _PARALLEL_SEARCH_URL,
                json=payload,
                headers=headers,
                timeout=self._http_timeout,
            )
            response.raise_for_status()
            data = response.json()
            return self._format_search_results(data)

        except httpx.TimeoutException:
            logger.warning(
                "Parallel Search MCP request timed out after %.1f s for query: %.80s",
                self._http_timeout,
                query,
            )
            return "(Search timed out — no live results available for this claim.)"

        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Parallel Search MCP returned HTTP %d for query: %.80s",
                exc.response.status_code,
                query,
            )
            return f"(Search service returned HTTP {exc.response.status_code}.)"

        except Exception as exc:  # noqa: BLE001
            logger.warning("Unexpected error calling Parallel Search MCP: %s", exc)
            return "(Search unavailable — unexpected error.)"

    @staticmethod
    def _format_search_results(data: dict) -> str:
        """
        Extract the useful text from the MCP JSON-RPC response and format it
        as a readable block for inclusion in the Gemini prompt.
        """
        try:
            content = data.get("result", {}).get("content", [])
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and "text" in item:
                        text_val = item["text"]
                        try:
                            inner = json.loads(text_val)
                            results = inner.get("results", [])
                            lines = []
                            for r in results[:3]:
                                title = r.get("title", "")
                                url = r.get("url", "")
                                excerpts = " ".join(r.get("excerpts", []))
                                lines.append(f"Source: {title} ({url})\nExcerpt: {excerpts}")
                            if lines:
                                return "\n\n".join(lines)
                        except Exception:
                            return text_val
        except Exception:
            pass

        # Fallback: serialise whatever we got so Gemini can still try
        try:
            return json.dumps(data, indent=2)[:4000]  # cap at 4 000 chars
        except Exception:  # noqa: BLE001
            return "(Could not parse search results.)"

    def check_batch(self, claims: list[Claim]) -> list[CheckResult]:
        """
        Evaluate a batch of real-world claims in a single unified Gemini call.
        Eliminates free-tier rate limit (429) bottlenecks.
        """
        if not claims:
            return []

        search_sections: list[str] = []
        for i, c in enumerate(claims):
            s_res = self._search(c.text)
            search_sections.append(f"Claim [{i}]: '{c.text}'\nLive Web Grounding:\n{s_res}")

        search_block = "\n\n---\n\n".join(search_sections)

        prompt = (
            f"LIVE WEB GROUNDING CONTEXT:\n{search_block}\n\n"
            "TASK:\n"
            "For each claim above, check whether it is accurate or contradicts real-world facts.\n"
            "Respond in strict JSON with a JSON array:\n"
            "[\n"
            "  {\n"
            '    "claim_index": 0,\n'
            '    "is_contradiction": true or false,\n'
            '    "explanation": "State verification via live web search and cite external sources/facts",\n'
            '    "suggested_fix": "Factual correction if contradiction, else empty string",\n'
            '    "confidence": 0.95\n'
            "  }\n"
            "]\n"
            "Rules:\n"
            "- Output valid JSON only (no markdown fences, no extra text).\n"
            f"- Cover all claims from 0 to {len(claims) - 1}."
        )

        raw = _call_gemini(self._model, prompt)
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.strip()

        results_map: dict[int, CheckResult] = {}
        try:
            data = json.loads(cleaned)
            if isinstance(data, list):
                for item in data:
                    idx = item.get("claim_index")
                    if idx is not None and 0 <= idx < len(claims):
                        claim = claims[idx]
                        results_map[idx] = CheckResult(
                            claim=claim,
                            is_contradiction=bool(item.get("is_contradiction", False)),
                            explanation=str(item.get("explanation", "Verified against external sources.")),
                            suggested_fix=str(item.get("suggested_fix", "")),
                            confidence=float(item.get("confidence", 0.9)),
                        )
        except Exception as exc:
            logger.warning("Failed to parse batch JSON in RealWorldChecker: %s", exc)

        results: list[CheckResult] = []
        for i, c in enumerate(claims):
            if i in results_map:
                results.append(results_map[i])
            else:
                results.append(self.check(c, None))
        return results
