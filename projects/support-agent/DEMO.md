# Support Agent Demo — Quick Start

## Short commands

After configuring the local shell aliases, start the demo from any Terminal directory.

Offline:

    support-demo

Live-enabled:

    support-demo-live

Both commands start the local server and open:

    http://127.0.0.1:8000

Stop the server with `Ctrl+C`.

## Offline demo

The offline demo uses scripted extraction and makes no paid model call.

Equivalent repository command:

    ./scripts/support-agent-demo

## Live-enabled demo

The live-enabled demo loads `ANTHROPIC_API_KEY` from the repository's untracked `.env`.

Equivalent repository command:

    ./scripts/support-agent-demo-live

Starting the live-enabled server does not itself make a provider call. A provider call occurs only when a case is run in live mode.

## Local aliases

The aliases on the development machine point to the version-controlled launcher scripts:

    alias support-demo="$HOME/AI-Projects/enterprise-ai-deployment-lab/scripts/support-agent-demo"
    alias support-demo-live="$HOME/AI-Projects/enterprise-ai-deployment-lab/scripts/support-agent-demo-live"

The scripts themselves are portable and locate the repository relative to their own location.
