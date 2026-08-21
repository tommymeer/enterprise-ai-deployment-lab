"""Manually authorized live evaluation of the 20 semantic extraction variants."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from typing import TextIO

from run_live_hard_extraction_evaluation import (
    MAX_INPUT_TOKENS_PER_CALL,
    MAX_TOKENS,
    MAXIMUM_COST_PER_CALL_USD,
    MODEL,
    RETRIES,
    TIMEOUT_SECONDS,
    run_bounded_live_evaluation,
)
from support_agent import AnthropicConfig, AnthropicModelClient, ModelClient
from support_agent.extraction_evaluation import get_semantic_robustness_eval_cases


MAX_ATTEMPTED_CALLS = 20
AUTHORIZED_ESTIMATED_SPEND_LIMIT_USD = 0.28
PRE_RUN_MAXIMUM_COST_USD = MAXIMUM_COST_PER_CALL_USD * MAX_ATTEMPTED_CALLS


def print_plan(stream: TextIO) -> None:
    cases = get_semantic_robustness_eval_cases()
    print(
        json.dumps(
            {
                "mode": "plan_only",
                "model": MODEL,
                "case_ids": [case.case_id for case in cases],
                "call_count": MAX_ATTEMPTED_CALLS,
                "max_tokens_per_call": MAX_TOKENS,
                "thinking": "disabled",
                "timeout_seconds": TIMEOUT_SECONDS,
                "retry_count": RETRIES,
                "maximum_input_tokens_per_call": MAX_INPUT_TOKENS_PER_CALL,
                "pre_run_maximum_cost_usd": PRE_RUN_MAXIMUM_COST_USD,
                "authorized_estimated_spend_limit_usd": AUTHORIZED_ESTIMATED_SPEND_LIMIT_USD,
                "result_retention": "stdout JSONL includes raw_model_output; save with tee",
            },
            separators=(",", ":"),
            sort_keys=True,
        ),
        file=stream,
    )


def run_live_evaluation(client: ModelClient, stream: TextIO = sys.stdout) -> int:
    cases = get_semantic_robustness_eval_cases()
    if len(cases) != MAX_ATTEMPTED_CALLS or len({case.case_id for case in cases}) != 20:
        raise RuntimeError("live semantic robustness evaluation requires 20 unique variants")
    return run_bounded_live_evaluation(
        client, cases, AUTHORIZED_ESTIMATED_SPEND_LIMIT_USD, stream
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    client_factory: Callable[[], ModelClient] | None = None,
    stream: TextIO = sys.stdout,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm-live-call",
        action="store_true",
        help="authorize exactly 20 bounded live Anthropic calls",
    )
    args = parser.parse_args(argv)
    if not args.confirm_live_call:
        print_plan(stream)
        return 0
    factory = client_factory or (
        lambda: AnthropicModelClient(
            AnthropicConfig(MODEL, MAX_TOKENS, TIMEOUT_SECONDS, disable_thinking=True)
        )
    )
    return run_live_evaluation(factory(), stream)


if __name__ == "__main__":
    raise SystemExit(main())
