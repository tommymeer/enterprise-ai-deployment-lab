# Instructions for coding agents

This is a learning lab, not a production codebase. Before doing substantive work, read
`docs/lab-operating-standard.md`.

This file is the authoritative, agent-agnostic instruction set for this repo. Tool-specific files
(e.g. `CLAUDE.md`) point back here rather than duplicating these rules.

## Ground rules

- Preserve and follow the project sequence: **Reality → Build → Break → Repair → Abstract**. Do
  not jump ahead to implementation before reality discovery and design for a project exist.
- Avoid premature frameworks, abstractions, or dependencies. Prefer the smallest thing that
  answers the current question. Do not add libraries or infrastructure "for later."
- Explain important decisions where you make them (code comments only for non-obvious *why*;
  substantial design or scope decisions belong in the relevant project's decision log).
- Never commit or push unless explicitly instructed for that specific action.
- Prefer small, testable increments over large speculative changes.

## Secrets and sensitive data

Never place real credentials, API keys, tokens, customer records, PII, or other sensitive data
in any of the following:

- source code
- documentation
- fixtures
- prompts
- traces
- logs
- screenshots
- evaluation datasets

Use `.env` (untracked) and `.env.example` (tracked template, no real values) for credentials. This
project uses synthetic, placeholder data by default; see each project's `docs/01-business-context.md`
and `docs/03-system-boundaries.md` for the data-safety questions to answer before using anything
real.

## API cost controls

- Keep incremental API spend for the support-agent project under the $30 target. Stop and ask
  before expected cumulative spend would exceed $30. The absolute project ceiling is $50; never
  exceed it without an explicit change to these governing instructions.
- Claude Code currently uses the user's subscription. The Anthropic API has approximately $10 in
  prepaid credit, with auto-reload disabled.
- A dedicated OpenAI project exists for this lab, but its API balance is $0. Do not create or fund
  an API key until an integration requires it.
- Never fund an account, enable automatic credit reload or top-up, or create paid infrastructure
  without explicit user approval.
- Every paid call requires explicit user approval. Default paid development runs to no more than
  10 cases, and obtain explicit approval before any run of more than 50 paid cases.
- Before any paid run, report the provider and model, purpose, number of cases or expected calls,
  estimated input and output tokens, estimated cost, maximum possible cost, and whether outputs
  will be cached or saved.
- Record the provider, model, input tokens, output tokens, latency, and estimated cost for every
  paid call. Save model outputs so identical cases are not paid for repeatedly.
- Do not use unbounded paid loops, uncontrolled concurrency, unlimited automatic retries, or
  other execution patterns without a firm cost bound.
- Normal unit tests must never make paid API calls. Paid model tests must use a separate,
  explicit command and must be excluded from routine unit-test commands and validation.
- Use mocks or deterministic fixtures by default during ordinary development.
