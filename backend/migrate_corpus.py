"""
One-time corpus migration: replace whatever is currently in the `corpus`
collection with the 331 real owner-authored records from corpus_seed.py.

SAFE BY DEFAULT — dry-run unless you pass --confirm. Dry-run alone answers
"what's actually in the live DB right now" without changing anything.

Scope: touches ONLY the `corpus` collection. Never reads or writes users,
aircraft, manuals, logbook, sessions, or messages.

Usage:
    python migrate_corpus.py               # dry run: report current state only
    python migrate_corpus.py --confirm      # back up, then replace corpus records

Requires MONGO_URL and DB_NAME in the environment (same as server.py) — this
script does not read or print their values, and does not accept them as
command-line arguments, so they never end up in shell history.
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient

from corpus_seed import HISTORICAL_RECORDS


async def main(confirm: bool):
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        print("MONGO_URL and DB_NAME must be set in the environment. Aborting — no connection attempted.")
        sys.exit(1)

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    current_count = await db.corpus.count_documents({})
    print(f"Current corpus collection: {current_count} document(s).")
    print(f"New corpus_seed.py has: {len(HISTORICAL_RECORDS)} record(s).")

    if current_count == len(HISTORICAL_RECORDS):
        # Heuristic only — count matching isn't proof of identical content,
        # but it's a real signal this may already be migrated. Report and
        # let the operator decide rather than silently no-op-ing.
        print("Counts already match the new corpus. This may already be migrated — verify before re-running with --confirm.")

    if not confirm:
        print("\nDRY RUN — no changes made. Re-run with --confirm to actually replace the corpus collection.")
        client.close()
        return

    if current_count > 0:
        backup_path = f"corpus_backup_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
        existing = await db.corpus.find({}, {"_id": 0}).to_list(10000)
        with open(backup_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, default=str)
        print(f"Backed up {len(existing)} existing corpus document(s) to {backup_path} before touching anything.")

    delete_result = await db.corpus.delete_many({})
    print(f"Deleted {delete_result.deleted_count} old corpus document(s).")

    import uuid
    to_insert = [dict(r, id=str(uuid.uuid4())) for r in HISTORICAL_RECORDS]
    insert_result = await db.corpus.insert_many(to_insert)
    print(f"Inserted {len(insert_result.inserted_ids)} new corpus document(s).")

    final_count = await db.corpus.count_documents({})
    print(f"\nDone. Corpus collection now has {final_count} document(s) (expected {len(HISTORICAL_RECORDS)}).")
    if final_count != len(HISTORICAL_RECORDS):
        print("WARNING: final count does not match expected — investigate before trusting this data.")

    client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", action="store_true", help="Actually perform the migration (default: dry run, report only)")
    args = parser.parse_args()
    asyncio.run(main(args.confirm))
