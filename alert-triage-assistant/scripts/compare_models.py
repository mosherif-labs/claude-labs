"""W1D2 Mission 4: 4 model configs x 10 alerts -> notes/d02-runs.csv + a summary.

    uv run scripts/compare_models.py

Needs ANTHROPIC_API_KEY (workspace-scoped key). ~40 calls, roughly $0.30-$1.50.
Haiku 4.5 has no effort parameter, so output_config is left off for it.
"""

import csv
import json
import os
import statistics
import time
from pathlib import Path

import anthropic

# Reuse the repo's shared key file (gitignored) unless the var is already set.
_ENV = Path(__file__).resolve().parents[2] / ".env"
if _ENV.exists():
    for line in _ENV.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

client = anthropic.Anthropic()
SYSTEM = "Triage this synthetic AML alert. Reply: risk (low|medium|high), typology, one-sentence rationale."
PRICE = {  # USD per MTok (input, output), from the Models overview
    "claude-haiku-4-5-20251001": (1, 5),
    "claude-sonnet-5-5": (2, 10),
    "claude-opus-5-5": (4, 20),
}
RUNS = [
    ("claude-haiku-4-5-20251001", None),
    ("claude-sonnet-5-5", "low"),
    ("claude-sonnet-5-5", "high"),
    ("claude-opus-5-5", None),  # default effort = medium
]
alerts = json.loads(Path("data/alerts.json").read_text(encoding="utf-8"))[:10]
rows = []

with open("notes/d02-runs.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(
        [
            "model",
            "effort",
            "alert",
            "rule",
            "est_in",
            "in",
            "out",
            "thinking",
            "stop",
            "secs",
            "usd",
            "answer",
            "quality",
        ]
    )
    for model, effort in RUNS:
        for a in alerts:
            msgs = [{"role": "user", "content": json.dumps(a)}]
            est = client.messages.count_tokens(
                model=model, system=SYSTEM, messages=msgs
            ).input_tokens
            extra = {"output_config": {"effort": effort}} if effort else {}
            t0 = time.perf_counter()
            m = client.messages.create(
                model=model, max_tokens=1024, system=SYSTEM, messages=msgs, **extra
            )
            secs = time.perf_counter() - t0
            pin, pout = PRICE[model]
            usd = (m.usage.input_tokens * pin + m.usage.output_tokens * pout) / 1e6
            details = getattr(m.usage, "output_tokens_details", None)
            thinking = getattr(details, "thinking_tokens", None) or 0
            text = next((b.text for b in m.content if b.type == "text"), "")
            row = [
                model,
                effort or "default",
                a["id"],
                a["rule"],
                est,
                m.usage.input_tokens,
                m.usage.output_tokens,
                thinking,
                m.stop_reason,
                round(secs, 2),
                round(usd, 5),
                text,
                "",  # M5: grade 1-5 by hand
            ]
            w.writerow(row)
            f.flush()  # keep the rows already paid for if a later call fails
            rows.append(row)
            print(f"{model} {effort or 'default'} {a['id']} {secs:.1f}s ${usd:.4f}")

print("\nmodel · effort · p50 secs · mean out · mean thinking · $ per 100 alerts")
for model, effort in RUNS:
    r = [x for x in rows if x[0] == model and x[1] == (effort or "default")]
    print(
        f"{model} · {effort or 'default'} · {statistics.median(x[9] for x in r):.2f}"
        f" · {statistics.mean(x[6] for x in r):.0f}"
        f" · {statistics.mean(x[7] for x in r):.0f}"
        f" · ${sum(x[10] for x in r) / len(r) * 100:.2f}"
    )
