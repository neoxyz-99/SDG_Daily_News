"""Trace a known URL or event in a saved report, without crawling again."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from .discovery_parse import canonical_url


def trace_report(report, url="", query=""):
    result = []
    for row in report.get("candidates", []) + report.get("source_events", []):
        if (url and canonical_url(row.get("url", "")) == canonical_url(url)) or (
                query and query.casefold() in json.dumps(row, ensure_ascii=False).casefold()):
            result.append(row)
    if result:
        return result
    host = urlsplit(url).netloc
    monitored = any(urlsplit(r["url"]).netloc == host for r in report.get("sources", [])) if host else False
    return [{"url": url, "query": query,
        "decision": "discovery_or_extraction_failure" if monitored else "source_not_monitored",
        "reason": "no_matching_record; bounded_discovery_does_not_prove_absence; historical_cause_unknown"}]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--url", default="")
    group.add_argument("--query", default="")
    args = parser.parse_args()
    print(json.dumps(trace_report(json.loads(Path(args.report).read_text()), args.url, args.query), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
