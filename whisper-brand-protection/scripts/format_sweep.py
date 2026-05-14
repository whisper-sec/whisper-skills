#!/usr/bin/env python3
"""Format a WhisperGraph brand-protection sweep into a prioritized report.

Takes the per-variant results collected from the WhisperGraph MCP tools
(`domain_variants`, `query`, `explain_indicator`) and produces a Markdown
report grouped by risk tier plus a flat CSV for ticketing / spreadsheets.

Input JSON schema - a JSON array of objects, one per variant. Only `variant`
is required; every other field is optional and missing values are handled.

    [
      {
        "variant": "paypa1.com",            # required: the lookalike domain
        "method": "OMISSION",               # domain_variants method
        "confidence": 0.7,                  # domain_variants confidence (0-1)
        "threatLevel": "HIGH",              # explain_indicator / query: NONE..CRITICAL
        "threatScore": 82.5,                # explain_indicator / query
        "feeds": ["OpenPhish", "PhishTank"],# threat feeds listing the variant
        "registrar": "registrar:namecheap", # WHOIS pivot
        "contactEmail": "email:a@b.com",    # WHOIS pivot
        "organization": "redacted",         # WHOIS pivot
        "brandOwned": false                 # true = defensive registration by the brand
      }
    ]

Usage:
    python format_sweep.py --brand paypal.com --input results.json --out report
    cat results.json | python format_sweep.py --brand paypal.com --out report

Writes <out>.md and <out>.csv. Use --stdout to also print the Markdown.
"""

import argparse
import csv
import json
import sys

# domain_variants methods with the highest base confidence (see the cookbook).
# A registered hit by one of these is treated as suspicious even with no feed.
HIGH_CONFIDENCE_METHODS = {"HOMOGLYPH", "BITSQUATTING", "KEYBOARD_REPLACEMENT"}

WEAPONIZED_LEVELS = {"HIGH", "CRITICAL"}
SUSPICIOUS_LEVELS = {"LOW", "MEDIUM"}

# Tier order controls section order in the report and sort priority.
TIERS = ["Weaponized", "Suspicious", "Monitor", "Brand-owned"]


def to_unicode(domain):
    """Decode punycode (xn--) labels back to their Unicode form for display."""
    out = []
    for label in str(domain).split("."):
        if label.startswith("xn--"):
            try:
                out.append(label.encode("ascii").decode("idna"))
            except Exception:
                out.append(label)
        else:
            out.append(label)
    return ".".join(out)


def classify(record):
    """Assign a risk tier to one variant record."""
    if record.get("brandOwned") is True:
        return "Brand-owned"

    feeds = record.get("feeds") or []
    level = (record.get("threatLevel") or "").upper()

    if feeds or level in WEAPONIZED_LEVELS:
        return "Weaponized"

    method = (record.get("method") or "").upper()
    if level in SUSPICIOUS_LEVELS or method in HIGH_CONFIDENCE_METHODS:
        return "Suspicious"

    return "Monitor"


def sort_key(record):
    """Within a tier, rank by threat score then confidence, both descending."""
    score = record.get("threatScore")
    score = float(score) if isinstance(score, (int, float)) else -1.0
    conf = record.get("confidence")
    conf = float(conf) if isinstance(conf, (int, float)) else -1.0
    return (-score, -conf)


def load_records(path):
    raw = sys.stdin.read() if path in (None, "-") else open(path, encoding="utf-8").read()
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError("input must be a JSON array of variant records")
    records = []
    for i, rec in enumerate(data):
        if not isinstance(rec, dict) or not rec.get("variant"):
            raise ValueError(f"record {i} is missing the required 'variant' field")
        rec = dict(rec)
        rec["_display"] = to_unicode(rec["variant"])
        rec["_tier"] = classify(rec)
        records.append(rec)
    return records


def fmt_cell(value):
    if value is None or value == "":
        return "-"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) if value else "-"
    return str(value)


def build_markdown(brand, records):
    by_tier = {tier: [] for tier in TIERS}
    for rec in records:
        by_tier[rec["_tier"]].append(rec)

    lines = [f"# Brand-Protection Sweep: {brand}", ""]
    total = len(records)
    counts = ", ".join(f"{t}: {len(by_tier[t])}" for t in TIERS)
    lines.append(f"**{total} registered lookalike(s)** - {counts}")
    lines.append("")
    lines.append(
        "Tiers: **Weaponized** = on a threat feed or HIGH/CRITICAL verdict (report for "
        "takedown). **Suspicious** = LOW/MEDIUM verdict or high-confidence method "
        "(escalate / monitor closely). **Monitor** = registered, no threat signal yet. "
        "**Brand-owned** = defensive registration by the brand."
    )
    lines.append("")

    for tier in TIERS:
        rows = sorted(by_tier[tier], key=sort_key)
        if not rows:
            continue
        lines.append(f"## {tier} ({len(rows)})")
        lines.append("")
        lines.append(
            "| Variant | Display | Method | Conf. | Level | Score | Feeds | Registrar | Registrant |"
        )
        lines.append(
            "|---------|---------|--------|-------|-------|-------|-------|-----------|------------|"
        )
        for r in rows:
            lines.append(
                "| {variant} | {display} | {method} | {conf} | {level} | {score} | "
                "{feeds} | {registrar} | {org} |".format(
                    variant=fmt_cell(r.get("variant")),
                    display=fmt_cell(r.get("_display")),
                    method=fmt_cell(r.get("method")),
                    conf=fmt_cell(r.get("confidence")),
                    level=fmt_cell(r.get("threatLevel")),
                    score=fmt_cell(r.get("threatScore")),
                    feeds=fmt_cell(r.get("feeds")),
                    registrar=fmt_cell(r.get("registrar")),
                    org=fmt_cell(r.get("organization") or r.get("contactEmail")),
                )
            )
        lines.append("")

    lines.append("## Recommended actions")
    lines.append("")
    lines.append(f"- **Weaponized ({len(by_tier['Weaponized'])})** - report for takedown now.")
    lines.append(
        f"- **Suspicious ({len(by_tier['Suspicious'])})** - escalate; monitor closely; "
        "pivot on shared registrant data."
    )
    lines.append(f"- **Monitor ({len(by_tier['Monitor'])})** - add to the watchlist.")
    lines.append(
        f"- **Brand-owned ({len(by_tier['Brand-owned'])})** - no action; confirmed "
        "defensive registrations."
    )
    lines.append("")
    return "\n".join(lines)


def write_csv(path, records):
    fields = [
        "tier", "variant", "display", "method", "confidence", "threatLevel",
        "threatScore", "feeds", "registrar", "contactEmail", "organization",
    ]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(fields)
        ordered = sorted(records, key=lambda r: (TIERS.index(r["_tier"]), *sort_key(r)))
        for r in ordered:
            feeds = r.get("feeds") or []
            writer.writerow([
                r["_tier"], r.get("variant", ""), r.get("_display", ""),
                r.get("method", ""), r.get("confidence", ""), r.get("threatLevel", ""),
                r.get("threatScore", ""), "; ".join(str(f) for f in feeds),
                r.get("registrar", ""), r.get("contactEmail", ""), r.get("organization", ""),
            ])


def main():
    parser = argparse.ArgumentParser(
        description="Format a WhisperGraph brand-protection sweep into a report.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--brand", required=True, help="brand apex domain, e.g. paypal.com")
    parser.add_argument(
        "--input", "-i", default="-",
        help="path to the variant JSON array (default: stdin)",
    )
    parser.add_argument(
        "--out", "-o", default="sweep-report",
        help="output file prefix; writes <prefix>.md and <prefix>.csv (default: sweep-report)",
    )
    parser.add_argument(
        "--stdout", action="store_true", help="also print the Markdown report to stdout",
    )
    args = parser.parse_args()

    try:
        records = load_records(args.input)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(f"could not read input: {exc}")

    if not records:
        parser.error("input contained no variant records")

    markdown = build_markdown(args.brand, records)
    md_path = f"{args.out}.md"
    csv_path = f"{args.out}.csv"
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(markdown)
    write_csv(csv_path, records)

    print(f"Wrote {md_path} and {csv_path} ({len(records)} variant(s)).", file=sys.stderr)
    if args.stdout:
        print(markdown)


if __name__ == "__main__":
    main()
