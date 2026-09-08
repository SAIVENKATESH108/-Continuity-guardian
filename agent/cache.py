"""
agent/cache.py

In-memory memoization cache for the Continuity Guardian pipeline.

Why this exists:
    The pipeline calls external APIs (Gemini for extraction, web search for
    real-world fact-checking) that cost money and add latency.  If the same
    episode synopsis or claim text is submitted twice — e.g. because a re-run
    is triggered before any data has changed — there is no reason to hit the
    API again.  SimpleCache stores results keyed by a SHA-256 hash of the input
    string so that identical inputs always get an instant, free answer from
    memory.  Entries older than a configurable TTL are treated as expired and
    transparently re-fetched, ensuring the cache never silently serves stale
    data indefinitely.

Design principles:
    - Zero external dependencies (hashlib, time, and typing only).
    - Zero persistence — the cache lives for the lifetime of the process.
      If persistence across restarts is needed, graduate to repository.py.
    - Thread-safety is intentionally out of scope for v1; if the API server
      is run with multiple workers the cache is per-process (fine for now).
"""

from __future__ import annotations

import hashlib
import time
from typing import Any

# Default TTL: 24 hours expressed in seconds.
_DEFAULT_TTL_SECONDS: int = 24 * 60 * 60


class SimpleCache:
    """
    In-memory key/value store that automatically expires entries after a
    configurable time-to-live (TTL).

    Cache keys are SHA-256 hashes of the raw input string, which means:
      - Callers never have to worry about key naming conventions.
      - Two callers passing the exact same input string always hit the same
        cache slot, regardless of where in the codebase they are.
      - Keys are fixed length and safe to use as dict keys regardless of how
        large or unusual the input string is.

    Typical usage
    -------------
    ::

        cache = SimpleCache(ttl_seconds=3600)

        result = cache.get(episode_synopsis)
        if result is None:
            result = call_expensive_api(episode_synopsis)
            cache.set(episode_synopsis, result)

        # `result` is now either freshly fetched or retrieved from cache.
    """

    def __init__(self, ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> None:
        """
        Create a new SimpleCache.

        Args:
            ttl_seconds: How long a cached result is considered valid, in
                seconds.  After this window the entry is treated as a miss and
                the caller is expected to re-compute the value.  Defaults to
                86 400 seconds (24 hours).
        """
        if ttl_seconds <= 0:
            raise ValueError(
                f"ttl_seconds must be a positive integer, got {ttl_seconds!r}."
            )

        self._ttl: int = ttl_seconds

        # Internal store: { sha256_hex_digest: (result, stored_at_epoch_float) }
        self._store: dict[str, tuple[Any, float]] = {}

    # ------------------------------------------------------------------
    # Private helper
    # ------------------------------------------------------------------

    @staticmethod
    def _hash(key_input: str) -> str:
        """
        Return the SHA-256 hex digest of *key_input*.

        Using a cryptographic hash (rather than Python's built-in ``hash()``)
        gives us:
          - Deterministic output across interpreter restarts and platforms.
          - Fixed-length keys (64 hex characters) regardless of input size.
          - Negligible collision probability even across millions of entries.
        """
        return hashlib.sha256(key_input.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, key_input: str) -> Any | None:
        """
        Look up a cached result for the given input string.

        Hashes *key_input*, checks whether an entry exists **and** is still
        within the TTL window.  Expired entries are evicted lazily on access
        (the stale record is deleted and ``None`` is returned) so the store
        never accumulates dead weight.

        Args:
            key_input: The original, unhashed input string (e.g. an episode
                synopsis, a claim sentence, or a search query).

        Returns:
            The previously cached result if it exists and has not expired,
            otherwise ``None``.
        """
        digest = self._hash(key_input)
        entry = self._store.get(digest)

        if entry is None:
            return None  # cache miss — never stored

        result, stored_at = entry
        age = time.time() - stored_at

        if age > self._ttl:
            # Lazy eviction: remove the stale entry so memory isn't wasted.
            del self._store[digest]
            return None  # cache miss — entry has expired

        return result  # cache hit

    def set(self, key_input: str, result: Any) -> None:
        """
        Store a result in the cache, associated with the given input string.

        The current wall-clock time is recorded alongside the result so that
        ``get()`` can determine whether the entry has expired on the next read.

        If an entry for the same *key_input* already exists it is silently
        overwritten — this handles the case where a caller wants to refresh
        a result that was computed with newer data.

        Args:
            key_input: The original, unhashed input string.
            result:    The value to cache.  Can be any Python object; the
                       cache makes no assumptions about its type or size.
        """
        digest = self._hash(key_input)
        self._store[digest] = (result, time.time())

    def clear(self) -> None:
        """
        Remove all entries from the cache.

        Useful in tests (to guarantee a cold cache) or when the underlying
        data has changed wholesale and all cached results are known to be stale.
        """
        self._store.clear()

    # ------------------------------------------------------------------
    # Introspection helpers (read-only, useful for logging / monitoring)
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        """Return the number of entries currently in the cache (including expired ones)."""
        return len(self._store)

    def __repr__(self) -> str:
        return (
            f"SimpleCache(ttl_seconds={self._ttl}, entries={len(self._store)})"
        )
