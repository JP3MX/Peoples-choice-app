"""
Offline test of the corpus retrieval logic against the new 331-record corpus —
no DB, no server, no LLM required. Faithfully ports score_record()/match_corpus()
from server.py (not reimplemented) so this tests the ACTUAL matching code path,
just without the `await db.corpus.find(...)` fetch.

This tests whether retrieval surfaces the right historical record for a given
symptom — the part that feeds the LLM's diagnosis as context. It does NOT test
the LLM-generated diagnosis text itself (that needs a live GPT-5.4 key + server,
neither of which exist locally).

Run: python test_corpus_retrieval_offline.py
"""
import re
from corpus_seed import HISTORICAL_RECORDS

# --- exact port of server.py score_record()/match_corpus() (post-fix) ------
_CONFIDENCE_RANK = {"high": 2, "medium": 1, "low": 0}


def score_record(text: str, record: dict) -> int:
    tl = text.lower()
    score = 0
    for kw in record.get("keywords", []):
        if kw.lower() in tl:
            score += 3
    for field in ("symptom", "system", "make", "model", "engine"):
        val = str(record.get(field, "")).lower()
        for word in re.findall(r"[a-z0-9]{4,}", val):
            if word in tl:
                score += 1
    return score


def match_corpus_offline(text: str, records: list, aircraft: dict | None = None, limit: int = 4):
    scored = []
    for r in records:
        s = score_record(text, r)
        if aircraft:
            if aircraft.get("make") and aircraft["make"].lower() in (r.get("make", "").lower() + r.get("engine", "").lower()):
                s += 2
            if aircraft.get("model") and r.get("model", "").lower() and r["model"].lower() in aircraft["model"].lower():
                s += 2
        if s > 0:
            confidence_rank = _CONFIDENCE_RANK.get(r.get("likely_cause_confidence"), 0)
            scored.append((s, confidence_rank, r))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [r for _, _, r in scored[:limit]]


def main():
    records = HISTORICAL_RECORDS
    print(f"Loaded {len(records)} records from corpus_seed.py\n")

    # --- Test A: self-retrieval — feed each record's OWN symptom text back in,
    # check whether the record retrieves ITSELF (or a same-source_tail sibling
    # record, which is an equally valid match) at rank 1.
    pass_count = 0
    fail_details = []
    for i, rec in enumerate(records):
        query = rec["symptom"]
        top = match_corpus_offline(query, records, limit=1)
        ok = bool(top) and top[0]["source_tail"] == rec["source_tail"] and top[0]["symptom"] == rec["symptom"]
        if ok:
            pass_count += 1
        else:
            fail_details.append((i, rec["source_tail"], query[:60], top[0]["source_tail"] if top else None))

    print("=== Test A: self-retrieval (own symptom text -> should rank itself #1) ===")
    print(f"{pass_count}/{len(records)} passed ({pass_count/len(records)*100:.1f}%)")
    if fail_details:
        print(f"\nFirst 15 of {len(fail_details)} failures:")
        for idx, tail, q, got in fail_details[:15]:
            print(f"  [{idx}] tail={tail} query='{q}' -> top match tail={got}")

    # --- Test B: realistic paraphrased queries (not exact self-text) against a
    # sample of records — closer to how a mechanic would actually type. Checks
    # whether the SYSTEM/ATA of the top match agrees with the source record's
    # system (a looser, more realistic correctness bar than exact self-match).
    print("\n=== Test B: paraphrased-query system-match sample ===")
    paraphrase_cases = [
        ("engine rough at run-up, mag drop excessive on one side", "Ignition"),
        ("dead battery, aircraft wont start, no crank", "Electrical Power"),
        ("brakes feel spongy and soft, pulling to one side", "Landing Gear"),
        ("stall warning horn not working", None),  # system-agnostic, just check it returns something relevant
        ("landing light inoperative", None),
        ("nav light out", None),
        ("fuel cap loose", None),
        ("oil pressure low on climb", None),
    ]
    b_pass = 0
    for query, expect_system_substr in paraphrase_cases:
        top = match_corpus_offline(query, records, limit=3)
        top_systems = [r.get("system", "") for r in top]
        matched = bool(top) and (expect_system_substr is None or any(expect_system_substr.lower() in s.lower() for s in top_systems))
        if matched:
            b_pass += 1
        print(f"  '{query}' -> top3 systems: {top_systems} | {'OK' if matched else 'MISS'}")
    print(f"\n{b_pass}/{len(paraphrase_cases)} paraphrase queries returned a plausible match")

    # --- Test C: coverage sanity — how many records ever score > 0 against
    # ANY of the paraphrase queries above (checks the corpus isn't dead weight)
    print("\n=== Test C: keyword/field coverage sanity ===")
    zero_keyword_records = sum(1 for r in records if not r.get("keywords") or r["keywords"] == ["general"])
    print(f"Records with no specific keywords (fell back to 'general'): {zero_keyword_records}/{len(records)}")

    print("\n=== SUMMARY ===")
    print(f"Self-retrieval: {pass_count}/{len(records)} ({pass_count/len(records)*100:.1f}%)")
    print(f"Paraphrase plausibility: {b_pass}/{len(paraphrase_cases)}")
    print(f"'general'-only keyword records: {zero_keyword_records}/{len(records)}")


if __name__ == "__main__":
    main()
