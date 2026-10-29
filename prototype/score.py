"""Deterministic eligibility, scoring and ranking. No AI calls happen here.

Reads the admin's criteria config and the AI extraction results, then:
  1. verifies evidence quotes against the source text (when available)
  2. scans the source text for manipulation attempts
  3. applies mandatory pass/fail gates
  4. scores eligible proposals with the admin's weights
  5. writes a ranking in the ranking.json format plus a detailed run record

Usage:
  python score.py --criteria criteria.json --extracted extracted_sample.json
  python score.py --criteria criteria.json --extracted output/extracted.json --sources samples
"""
import argparse
import hashlib
import json
import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

# Second safety net behind the AI's own embedded_instructions report.
INJECTION_PATTERNS = [
    r"\b(ai|automated|automatic)\s+(review|reviewer|scoring|system|evaluat\w*)",
    r"\b(ignore|disregard|override)\b.{0,40}\b(instruction|criteria|rule|prompt)s?\b",
    r"\brank\s+(this|it|us|our)\b.{0,30}\b(first|1st|top|highest)\b",
    r"\b(full|maximum|max|perfect)\s+(marks|score|points)\b",
    r"\bpre-?approved\b",
]

NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalise(text):
    return re.sub(r"\s+", " ", text).strip().lower()


def round1(x):
    return float(Decimal(str(round(x, 6))).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def validate_config(cfg):
    total = sum(c["weight"] for c in cfg["weighted"])
    if total != 100:
        raise SystemExit(f"Config error: weights add up to {total}, not 100.")
    field_ids = {f["id"] for f in cfg["extraction_fields"]}
    used = [g["field"] for g in cfg["mandatory"]]
    for c in cfg["weighted"]:
        used += [c["field"]] if "field" in c else []
        used += c.get("fields", []) + [p["field"] for p in c.get("parts", [])]
    unknown = set(used) - field_ids
    if unknown:
        raise SystemExit(f"Config error: criteria use undefined fields {sorted(unknown)}.")


def verify_evidence(fields, source_text):
    """A value only counts if its quote really appears in the document."""
    issues = []
    src = normalise(source_text)
    for fid, f in fields.items():
        if f["status"] in ("stated", "unclear") and f["evidence"] and normalise(f["evidence"]) not in src:
            f["status"], f["value"] = "unverified", None
            issues.append(f"Evidence quote for '{fid}' was not found in the document; value discarded.")
        elif f["status"] == "stated" and not f["evidence"]:
            f["status"], f["value"] = "unverified", None
            issues.append(f"No evidence quote for '{fid}'; value discarded.")
    return issues


def scan_for_injection(source_text):
    return [m.group(0) for p in INJECTION_PATTERNS for m in re.finditer(p, source_text, re.IGNORECASE)]


def period_start_year(period, as_of):
    """Turn 'since 2021' / 'in the past four years' into a start year, or None."""
    if not period:
        return None
    m = re.search(r"\b(?:since|from)\s+(\d{4})\b", period, re.IGNORECASE)
    if m:
        return int(m.group(1))
    m = re.search(r"\b(?:last|past)\s+(\w+)\s+years?\b", period, re.IGNORECASE)
    if m:
        n = NUMBER_WORDS.get(m.group(1).lower()) or (int(m.group(1)) if m.group(1).isdigit() else None)
        return as_of.year - n if n else None
    return None


def check_gate(gate, field):
    if field["status"] != "stated" or field["value"] is None:
        return "missing"
    v, target = field["value"], gate["value"]
    ok = {"eq": v == target, "gte": v >= target, "lte": v <= target}[gate["op"]]
    return "pass" if ok else "fail"


def ratio(method, field_id, part, value, pool):
    if method == "capped_ratio":
        return min(value, part["target"]) / part["target"]
    if method == "lowest_ratio":
        return min(pool[field_id]) / value
    if method == "highest_ratio":
        return value / max(pool[field_id])
    raise ValueError(f"Unknown scoring method {method}")


def score_criterion(crit, fields, pool):
    """Return (ratio 0-1, explanation)."""
    if crit["method"] == "checklist":
        hits = [f for f in crit["fields"] if fields[f]["status"] == "stated" and fields[f]["value"] is True]
        missing = [f for f in crit["fields"] if f not in hits]
        return len(hits) / len(crit["fields"]), f"{len(hits)}/{len(crit['fields'])} items" + (
            f" (missing: {', '.join(missing)})" if missing else "")
    if crit["method"] == "parts":
        total, notes = 0.0, []
        for part in crit["parts"]:
            f = fields[part["field"]]
            r = ratio(part["method"], part["field"], part, f["value"], pool) if f["value"] is not None else 0.0
            total += part["share"] * r
            notes.append(f"{part['field']}={f['value']}")
        return total, ", ".join(notes)
    value = fields[crit["field"]]["value"]
    return ratio(crit["method"], crit["field"], crit, value, pool), f"{crit['field']}={value}"


def weighted_inputs(crit):
    if "field" in crit:
        return [crit["field"]]
    return crit.get("fields", []) + [p["field"] for p in crit.get("parts", [])]


def evaluate(cfg, extracted, sources_dir, as_of):
    results = {}
    # Steps 1-3: validation, integrity and mandatory gates, per proposal.
    for pid, ext in sorted(extracted["proposals"].items()):
        fields = json.loads(json.dumps(ext["fields"]))  # work on a copy
        r = {"proposal": pid, "fields": fields, "issues": [], "flags": [], "warnings": [],
             "gates": {}, "status": None, "score": None, "breakdown": []}
        src_path = Path(sources_dir, f"{pid}.txt") if sources_dir else None
        if src_path and src_path.exists():
            text = src_path.read_text(encoding="utf-8")
            r["document_sha256"] = sha256(text)
            r["issues"] += verify_evidence(fields, text)
            hits = scan_for_injection(text)
            if hits:
                r["flags"].append(f"Pattern scan found possible instructions to reviewers: {hits}")
        if ext.get("embedded_instructions"):
            r["flags"].append("Document contains text addressed to the review system (possible manipulation).")

        for gate in cfg["mandatory"]:
            outcome = check_gate(gate, fields[gate["field"]])
            r["gates"][gate["id"]] = outcome
        failed = [g["label"] for g in cfg["mandatory"] if r["gates"][g["id"]] == "fail"]
        missing = [g["label"] for g in cfg["mandatory"] if r["gates"][g["id"]] == "missing"]
        for crit in cfg["weighted"]:
            if crit["if_missing"] == "flag" and crit["field"] not in [g["field"] for g in cfg["mandatory"]]:
                if fields[crit["field"]]["status"] != "stated":
                    missing.append(f"{crit['label']} input '{crit['field']}'")

        if failed:
            r["status"] = "ineligible"
            r["reason_parts"] = [f"Fails mandatory: {'; '.join(failed)}"]
        elif missing:
            r["status"] = "flagged"
            r["reason_parts"] = [f"Cannot confirm: {'; '.join(missing)}"]
        else:
            r["status"] = "flagged" if r["flags"] else "ranked"

        # Non-blocking warnings shown to the reviewer.
        for w in cfg.get("warnings", []):
            if fields[w["field"]]["status"] == w["when"]:
                r["warnings"].append(w["message"])
        for crit in cfg["weighted"]:
            win = crit.get("window")
            if win:
                start = period_start_year(fields[win["field"]]["value"], as_of)
                if start is None:
                    r["warnings"].append(f"Could not read the period for {crit['label']}; confirm the {win['years']}-year window.")
                elif start < as_of.year - win["years"]:
                    r["warnings"].append(f"{crit['label']}: count covers {start} onward; some work may fall outside the {win['years']}-year window ({as_of.year - win['years']} onward).")
        results[pid] = r

    # Step 4: score every proposal that passed the gates with complete data.
    scorable = [r for r in results.values() if r["status"] in ("ranked", "flagged") and not r.get("reason_parts")]
    pool = {}
    for crit in cfg["weighted"]:
        for fid in weighted_inputs(crit):
            pool[fid] = [r["fields"][fid]["value"] for r in scorable if r["fields"][fid]["value"] is not None]
    for r in scorable:
        total = 0.0
        for crit in cfg["weighted"]:
            share, how = score_criterion(crit, r["fields"], pool)
            points = crit["weight"] * share
            total += points
            r["breakdown"].append({"criterion": crit["id"], "weight": crit["weight"],
                                   "points": round(points, 2), "basis": how})
        r["score"] = round1(total)
    r_pool = {k: sorted(set(v)) for k, v in pool.items()}

    # Step 5: rank only clean proposals; deterministic tie-breakers.
    def sort_key(r):
        pts = {b["criterion"]: b["points"] for b in r["breakdown"]}
        return (-r["score"], *[-pts.get(t, 0) for t in cfg["tie_breakers"]], r["proposal"])
    ranked = sorted([r for r in results.values() if r["status"] == "ranked"], key=sort_key)
    for i, r in enumerate(ranked, start=1):
        r["rank"] = i
    return results, r_pool


def reason(r):
    if r["status"] != "ranked" or not r["breakdown"]:
        parts = list(r.get("reason_parts", [])) + r["flags"]
        if r["score"] is not None:
            parts.append(f"merit score {r['score']} held for human review")
        return " | ".join(parts)
    by_share = sorted(r["breakdown"], key=lambda b: b["points"] / b["weight"])
    weakest = by_share[0]
    strong = [b["criterion"] for b in r["breakdown"] if b["points"] == b["weight"]]
    text = "Passes all mandatory checks"
    if strong:
        text += f"; full marks on {', '.join(strong)}"
    if weakest["points"] < weakest["weight"]:
        text += f"; weakest on {weakest['criterion']} ({weakest['points']}/{weakest['weight']})"
    return text


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--criteria", required=True)
    ap.add_argument("--extracted", required=True)
    ap.add_argument("--sources", help="folder with <letter>.txt proposal text, enables quote checks")
    ap.add_argument("--as-of", default=date.today().isoformat(), help="evaluation date, YYYY-MM-DD")
    ap.add_argument("--out", default="output")
    args = ap.parse_args()

    cfg_text = Path(args.criteria).read_text(encoding="utf-8")
    cfg = json.loads(cfg_text)
    validate_config(cfg)
    extracted = load_json(args.extracted)
    if extracted.get("criteria_version") != cfg["version"]:
        print(f"WARNING: extraction used criteria v{extracted.get('criteria_version')}, config is v{cfg['version']}.")
    as_of = date.fromisoformat(args.as_of)

    results, pool = evaluate(cfg, extracted, args.sources, as_of)

    order = {"ranked": 0, "flagged": 1, "ineligible": 2}
    rows = sorted(results.values(), key=lambda r: (order[r["status"]], r.get("rank") or 99, -(r["score"] or 0), r["proposal"]))
    ranking = [{"proposal": r["proposal"], "rank": r.get("rank"), "status": r["status"],
                "score": r["score"], "reason": reason(r)} for r in rows]

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "ranking.json").write_text(json.dumps(ranking, indent=2), encoding="utf-8")
    run_record = {"as_of": args.as_of, "criteria_version": cfg["version"], "criteria_sha256": sha256(cfg_text),
                  "scoring_pool_values": pool, "proposals": results}
    (out / "run_record.json").write_text(json.dumps(run_record, indent=2, default=str), encoding="utf-8")

    print(f"{'Prop':<5}{'Status':<12}{'Rank':<6}{'Score':<7}Reason")
    for row in ranking:
        print(f"{row['proposal']:<5}{row['status']:<12}{str(row['rank'] or '-'):<6}{str(row['score'] or '-'):<7}{row['reason']}")
    for r in rows:
        for w in r["warnings"] + r["issues"]:
            print(f"  [{r['proposal']}] note: {w}")
    print(f"\nWrote {out / 'ranking.json'} and {out / 'run_record.json'}")


if __name__ == "__main__":
    main()
