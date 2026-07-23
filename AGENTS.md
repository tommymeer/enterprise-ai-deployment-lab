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
