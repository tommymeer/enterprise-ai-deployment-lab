# Instructions for Claude Code

Read and follow `AGENTS.md` — it is the authoritative instruction file for this repo and applies
to Claude Code as much as any other agent. Nothing here overrides it.

No Claude-specific deviations apply in this repo at this time.

## Cost safety

- Do not make paid API calls without explicit user approval.
- Do not fund accounts, create paid resources, or enable automatic credit reload or top-up.
- Report the expected run size and estimated cost before execution.
- Default to mocks and paid batches of 10 or fewer cases.
- Never run paid API tests as part of routine validation.
