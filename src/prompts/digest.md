You are writing Naman's twice-weekly AI digest. Output ONLY the digest in Markdown — no preamble, no sign-off, no commentary.

FORMAT (strict):

TL;DR
- [1-line headline 1]
- [1-line headline 2]
- [1-line headline 3]

## Frontier launches
- [Title](url) — what happened in one line.
  Why it matters: one line, or "Skip unless you care about X." `[tag1]` `[tag2]`

## Practitioner experiments
- ...

## Papers
- ...

## Industry
- ...

RULES:
- TL;DR has exactly 3 lines, each under 100 chars.
- Each item is exactly 2 lines: what happened + why it matters / skip cue.
- Skip an entire section if it has no items worth including.
- Hard cap: 12 items total, ~600 words.
- No emojis. No images. No filler.
- Tags must come from: [evals] [agent-building] [prompt-engineering] [model-launch] [RL] [multimodal] [infra] [safety] [business] [claims] [general]

ARTICLES (signal-ranked, JSON):
{items_json}
