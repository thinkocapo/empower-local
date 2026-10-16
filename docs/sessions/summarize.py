"""Summarize a Spotlight envelope stream capture.

Capture (while Spotlight is running on :8969):
    curl -sN -H 'Accept: text/event-stream' http://localhost:8969/stream > capture.txt

Summarize:
    python3 docs/sessions/summarize.py capture.txt
"""

import json
import sys
from collections import Counter


def envelopes(path):
    with open(path) as f:
        for line in f:
            if line.startswith("data: "):
                header, items = json.loads(line[6:])
                yield header, items


def tags_on(payload):
    tags = payload.get("tags") or {}
    return sorted(tags) if isinstance(tags, dict) else sorted(t[0] for t in tags)


def main(path):
    counts = Counter()
    sessions, transactions, spans = [], [], []

    for header, items in envelopes(path):
        source = header.get("__spotlight_inferred_source", "?")
        if source not in ("browser", "server"):
            continue  # other apps posting to the same Spotlight sidecar
        for item_header, payload in items:
            kind = item_header.get("type")
            counts[(source, kind)] += 1
            if not isinstance(payload, dict):
                continue
            if kind == "session":
                sessions.append(payload)
            elif kind == "transaction" and source == "browser":
                transactions.append(payload)
            elif kind == "span":
                spans.extend(payload.get("items", [payload]))

    print("## Envelope items (source, type) -> count")
    for (source, kind), n in sorted(counts.items()):
        print(f"- {source:7} {kind:12} {n}")

    print("\n## Browser sessions (in send order)")
    for s in sessions:
        print(
            f"- sid={s.get('sid', '')[:8]} init={s.get('init')} status={s.get('status')} "
            f"errors={s.get('errors')} did={s.get('did')} release={s.get('attrs', {}).get('release')}"
        )
    print(f"distinct session ids: {len({s.get('sid') for s in sessions})}")

    print("\n## Browser transactions (static lifecycle)")
    for t in transactions:
        op = t.get("contexts", {}).get("trace", {}).get("op") or ""
        print(
            f"- {op:12} {t.get('transaction')!r:28} spans={len(t.get('spans', []))} "
            f"trace={t.get('contexts', {}).get('trace', {}).get('trace_id', '')[:8]} tags={tags_on(t)}"
        )

    print("\n## Streamed spans (stream lifecycle)")
    segments = [s for s in spans if s.get("is_segment")]
    print(f"total streamed spans: {len(spans)}, segment spans: {len(segments)}")
    for s in segments:
        attrs = s.get("attributes", {})
        print(
            f"- {attrs.get('sentry.op', {}).get('value', ''):12} {s.get('name')!r:28} "
            f"trace={s.get('trace_id', '')[:8]} attrs={sorted(k for k in attrs if not k.startswith('sentry.'))}"
        )


if __name__ == "__main__":
    main(sys.argv[1])
