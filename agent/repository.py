"""
agent/repository.py

ShowBibleRepository is the single point of contact between this application
and Google Cloud Firestore.  No other file in this project should import
`google.cloud.firestore` directly — all database access must go through
this class.  This keeps the repository pattern clean: swap out the backing
store (e.g. replace Firestore with Postgres) by changing only this file.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from google.cloud import firestore
from google.oauth2 import service_account
from google.api_core.exceptions import GoogleAPICallError

from agent.models import EpisodeRecord

# ---------------------------------------------------------------------------
# Module-level setup
# ---------------------------------------------------------------------------

load_dotenv()  # pull .env values into os.environ before anything reads them

logger = logging.getLogger(__name__)

_EPISODES_COLLECTION = "episodes"


# ---------------------------------------------------------------------------
# Repository class
# ---------------------------------------------------------------------------

class ShowBibleRepository:
    """
    Wraps all Firestore operations for the Continuity Guardian project.

    Instantiate once and share the instance across the application —
    the underlying Firestore client maintains its own connection pool.
    """

    def __init__(self) -> None:
        """
        Build a Firestore client from environment variables.

        Supported env vars (set in .env or the host environment):
            FIREBASE_PROJECT_ID          — GCP project that owns the database.
            FIREBASE_CREDENTIALS_PATH    — Path to a service-account JSON key.
            FIREBASE_CREDENTIALS_JSON    — Raw JSON string of the service account (for Vercel / serverless).
        """
        project_id = os.getenv("FIREBASE_PROJECT_ID")
        credentials_path = os.getenv("FIREBASE_CREDENTIALS_PATH")
        credentials_json = os.getenv("FIREBASE_CREDENTIALS_JSON")

        self._db = None
        self._episodes = None

        try:
            if credentials_json:
                info = json.loads(credentials_json)
                creds = service_account.Credentials.from_service_account_info(info)
                resolved_project = project_id or info.get("project_id")
                self._db = firestore.Client(project=resolved_project, credentials=creds)
                self._episodes = self._db.collection(_EPISODES_COLLECTION)
                logger.info(
                    "ShowBibleRepository initialised via FIREBASE_CREDENTIALS_JSON (project=%s, collection=%s)",
                    resolved_project,
                    _EPISODES_COLLECTION,
                )
            elif credentials_path and os.path.exists(credentials_path):
                os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", credentials_path)
                self._db = firestore.Client(project=project_id)
                self._episodes = self._db.collection(_EPISODES_COLLECTION)
                logger.info(
                    "ShowBibleRepository initialised via file path (project=%s, collection=%s)",
                    project_id,
                    _EPISODES_COLLECTION,
                )
            elif project_id:
                self._db = firestore.Client(project=project_id)
                self._episodes = self._db.collection(_EPISODES_COLLECTION)
                logger.info(
                    "ShowBibleRepository initialised via default credentials (project=%s, collection=%s)",
                    project_id,
                    _EPISODES_COLLECTION,
                )
            else:
                logger.info("Firebase credentials not configured — ShowBibleRepository operating in local canon seed mode.")
        except Exception as exc:
            logger.warning("Could not connect to Firestore (%s) — operating in local canon seed mode.", exc)
            self._db = None
            self._episodes = None

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save_episode(self, episode: EpisodeRecord) -> bool:
        """
        Write an EpisodeRecord to Firestore, using episode_id as the document ID.

        Performs an upsert (merge=True), so calling this method on an already-
        existing episode will update changed fields without wiping unrelated ones.

        Args:
            episode: The EpisodeRecord to persist.

        Returns:
            True on success, False if Firestore was unreachable.
        """
        if not self._episodes:
            logger.warning(
                "Firestore client not available — cannot persist episode '%s'.",
                episode.episode_id,
            )
            return False

        try:
            doc_ref = self._episodes.document(episode.episode_id)
            doc_ref.set(episode.to_dict(), merge=True)
            logger.debug("Saved episode '%s' to Firestore.", episode.episode_id)
            return True
        except GoogleAPICallError as exc:
            logger.warning(
                "Could not save episode '%s' — Firestore returned an error: %s",
                episode.episode_id,
                exc,
            )
            return False
        except Exception as exc:  # noqa: BLE001  (broad catch intentional for resilience)
            logger.warning(
                "Unexpected error saving episode '%s': %s",
                episode.episode_id,
                exc,
            )
            return False

    # ------------------------------------------------------------------
    # Read — single document
    # ------------------------------------------------------------------

    def get_episode(self, episode_id: str) -> EpisodeRecord | None:
        """
        Fetch a single episode by its ID.

        Args:
            episode_id: The document ID (e.g. 's01e03').

        Returns:
            An EpisodeRecord if the document exists, None otherwise.
            Also returns None if Firestore is unreachable.
        """
        if not self._episodes:
            for ep in self._fallback_seed_records():
                if ep.episode_id == episode_id:
                    return ep
            return None

        try:
            doc = self._episodes.document(episode_id).get()
            if not doc.exists:
                logger.debug("Episode '%s' not found in Firestore.", episode_id)
                return None
            return EpisodeRecord.from_dict(doc.to_dict())
        except GoogleAPICallError as exc:
            logger.warning(
                "Could not fetch episode '%s' — Firestore returned an error: %s",
                episode_id,
                exc,
            )
            return None
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Unexpected error fetching episode '%s': %s",
                episode_id,
                exc,
            )
            return None

    # ------------------------------------------------------------------
    # Read — all documents
    # ------------------------------------------------------------------

    def _fallback_seed_records(self) -> list[EpisodeRecord]:
        """Load seed episodes from data/seed_episodes.json if Firestore is empty or uninitialized."""
        try:
            seed_file = Path(__file__).resolve().parent.parent / "data" / "seed_episodes.json"
            if seed_file.exists():
                with open(seed_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return [EpisodeRecord.from_dict(item) for item in data]
        except Exception as exc:
            logger.debug("Local seed fallback failed: %s", exc)
        return []

    def get_all_episodes(self) -> list[EpisodeRecord]:
        """
        Return every episode in the collection, ordered by date_added (ascending).
        Falls back to local seed_episodes.json if Firestore is uninitialized.
        """
        if self._episodes:
            try:
                docs = (
                    self._episodes
                    .order_by("date_added", direction=firestore.Query.ASCENDING)
                    .stream()
                )
                episodes = [EpisodeRecord.from_dict(doc.to_dict()) for doc in docs]
                if episodes:
                    logger.debug("Fetched %d episodes from Firestore.", len(episodes))
                    return episodes
            except Exception as exc:
                logger.warning("Could not fetch all episodes from Firestore (%s) — using local seed fallback.", exc)

        fallback = self._fallback_seed_records()
        logger.debug("Returning %d fallback seed episodes.", len(fallback))
        return fallback

    # ------------------------------------------------------------------
    # Read — filtered by character names
    # ------------------------------------------------------------------

    def find_related_facts(self, characters: list[str]) -> list[EpisodeRecord]:
        """
        Return episodes that mention at least one of the given character names.
        Uses Firestore's array-contains-any operator with automatic fallback to local seed data.
        """
        if not characters:
            return []

        if self._episodes:
            _FIRESTORE_ARRAY_CONTAINS_ANY_LIMIT = 30
            chars_to_query = characters[:_FIRESTORE_ARRAY_CONTAINS_ANY_LIMIT]

            try:
                docs = (
                    self._episodes
                    .where(
                        filter=firestore.FieldFilter(
                            "characters_mentioned",
                            "array_contains_any",
                            chars_to_query,
                        )
                    )
                    .stream()
                )
                results = [EpisodeRecord.from_dict(doc.to_dict()) for doc in docs]
                if results:
                    logger.debug("find_related_facts(%s) -> %d episode(s) matched in Firestore.", characters, len(results))
                    return results
            except Exception as exc:
                logger.warning("Firestore query error in find_related_facts (%s) — falling back to local seed canon.", exc)

        # Fallback: search local seed records
        matched = []
        chars_lower = {c.strip().lower() for c in characters}
        for ep in self._fallback_seed_records():
            ep_chars_lower = {c.strip().lower() for c in ep.characters_mentioned}
            if chars_lower.intersection(ep_chars_lower):
                matched.append(ep)
        logger.debug("find_related_facts(%s) -> %d fallback episode(s) matched.", characters, len(matched))
        return matched
