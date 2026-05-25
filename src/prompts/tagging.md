You are tagging an AI-related article for a personal knowledge base.

Given the title, source, and full text below, return a JSON object with exactly these fields:

- `summary`: 1-2 sentences, plain text, capturing the substantive point. NOT a paraphrase of the title.
- `why_it_matters`: 1 sentence. Who should care and why? If nobody should, write "Marginal — skip unless tracking <specific topic>."
- `topics`: array. Use tags from this fixed set: ["evals", "agent-building", "prompt-engineering", "model-launch", "RL", "multimodal", "infra", "safety", "business", "claims"]. Include 1-4 tags. If a strong tag would fit that isn't on the list, also include it; it'll be flagged for taxonomy review.
- `vega_relevance`: one of "general", "claims", "agent-building", "high". Use "claims" for anything insurance/claims/TPA-relevant, "agent-building" for tooling/frameworks/eval/MCP, "high" for both, "general" otherwise.

Be terse. No preamble, no markdown, JSON only.

ARTICLE:
Title: {title}
Source: {source_name}
Author: {author}

{raw_text}
