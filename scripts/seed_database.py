"""
scripts/seed_database.py

Reads seed episode records from data/seed_episodes.json and persists them into
Firestore using ShowBibleRepository.save_episode().

Safe to run multiple times: overwrites/merges on existing episode_id documents
without creating duplicates.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Add project root to sys.path so agent module can be imported regardless of CWD
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.models import EpisodeRecord
from agent.repository import ShowBibleRepository


def seed_show_bible() -> None:
    seed_file_path = PROJECT_ROOT / "data" / "seed_episodes.json"
    if not seed_file_path.exists():
        print(f"[ERROR] Seed file not found at: {seed_file_path}")
        sys.exit(1)

    print(f"Loading seed data from {seed_file_path}...")
    with open(seed_file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        print("[ERROR] Seed file must contain a JSON array of episode records.")
        sys.exit(1)

    print("Connecting to Firestore Show Bible...")
    try:
        repo = ShowBibleRepository()
    except Exception as exc:
        print(f"[ERROR] Failed to initialize ShowBibleRepository: {exc}")
        sys.exit(1)

    print(f"Seeding {len(data)} episode(s) into collection 'episodes'...\n")
    success_count = 0

    for item in data:
        record = EpisodeRecord.from_dict(item)
        saved = repo.save_episode(record)
        if saved:
            success_count += 1
            print(f"  [OK] Saved episode: {record.episode_id}")
            print(f"       Characters: {', '.join(record.characters_mentioned)}")
            print(f"       Key facts: {len(record.key_facts)} | Real-world facts: {len(record.real_world_claims)}")
        else:
            print(f"  [FAIL] Failed to save episode: {record.episode_id}")

    print(f"\n[DONE] Seed completed: {success_count}/{len(data)} episodes saved successfully.")


if __name__ == "__main__":
    seed_show_bible()
