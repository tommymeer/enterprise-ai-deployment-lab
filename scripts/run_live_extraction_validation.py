"""Manually authorized, bounded live validation of customer-message extraction.

This runner deliberately owns only its local pricing assumptions and spend guard. Provider
transport and API-key lookup remain the responsibility of ``AnthropicModelClient``.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TextIO

from support_agent import (
    AnthropicConfig,
    AnthropicModelClient,
    AnthropicProviderError,
    ExtractionResult,
    ModelClient,
    ModelRequest,
    ModelResponse,
    extract_customer_message,
)


MODEL = "claude-sonnet-5"
MAX_TOKENS = 256
TIMEOUT_SECONDS = 30
RETRIES = 0
MAX_ATTEMPTED_CALLS = 3
MAXIMUM_AUTHORIZED_SPEND_USD = 0.10
MAX_INPUT_TOKENS_PER_CALL = 2_000
INPUT_USD_PER_MILLION_TOKENS = 2.00
OUTPUT_USD_PER_MILLION_TOKENS = 10.00


@dataclass(frozen=True, slots=True)
class LiveCase:
    case_id: str
    customer_message: str


CASES = (
    LiveCase(
        "complete_delivered_not_received",
        "This is a synthetic test. Order SYNTH-ORDER-41001 shows delivered, but I did not receive the package.",
    ),
    LiveCase(
        "missing_order_identifier",
        "This is a synthetic test. The tracking page says delivered, but the package is not here.",
    ),
    LiveCase(
        "ambiguous_unknown_issue",
        "This is a synthetic test about order SYNTH-ORDER-41003. Something seems unusual; please review my message.",
    ),
)


def estimated_cost_usd(input_tokens: int, output_tokens: int) -> float:
    """Estimate cost using this runner's explicit local Anthropic pricing assumptions."""
    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("token counts must be non-negative")
    return (
        input_tokens * INPUT_USD_PER_MILLION_TOKENS
        + output_tokens * OUTPUT_USD_PER_MILLION_TOKENS
    ) / 1_000_000


MAXIMUM_COST_PER_CALL_USD = estimated_cost_usd(
    MAX_INPUT_TOKENS_PER_CALL, MAX_TOKENS
)
PRE_RUN_MAXIMUM_COST_USD = MAXIMUM_COST_PER_CALL_USD * MAX_ATTEMPTED_CALLS


def _validate_plan() -> None:
    if not len(CASES) == MAX_ATTEMPTED_CALLS == 3:
        raise RuntimeError(
            "live validation plan must contain exactly three attempted calls"
        )


def spend_guard_allows_call(
    cumulative_actual_cost_usd: float,
    uncompleted_calls: int,
    *,
    ceiling_usd: float = MAXIMUM_AUTHORIZED_SPEND_USD,
) -> bool:
    """Include the pending call in the conservative allowance for all unfinished calls."""
    if cumulative_actual_cost_usd < 0 or uncompleted_calls < 0 or ceiling_usd < 0:
        raise ValueError("spend guard inputs must be non-negative")
    conservative_total = (
        cumulative_actual_cost_usd + uncompleted_calls * MAXIMUM_COST_PER_CALL_USD
    )
    return conservative_total <= ceiling_usd


class _ObservingClient:
    """Retain neutral response metadata without changing the extraction execution path."""

    def __init__(self, delegate: ModelClient) -> None:
        self._delegate = delegate
        self.response: ModelResponse | None = None

    def complete(self, request: ModelRequest) -> ModelResponse:
        response = self._delegate.complete(request)
        self.response = response
        return response


def _write_record(stream: TextIO, record: dict[str, object]) -> None:
    print(json.dumps(record, separators=(",", ":"), sort_keys=True), file=stream)


def _case_record(
    case: LiveCase, result: ExtractionResult, response: ModelResponse, call_cost: float
) -> dict[str, object]:
    extraction = result.extraction
    return {
        "case_id": case.case_id,
        "extraction_status": result.status.value,
        "issue_type": extraction.issue_type.value if extraction is not None else None,
        "order_identifier_extracted": bool(
            extraction is not None and extraction.order_identifier is not None
        ),
        "missing_required_fields": list(extraction.missing_required_fields)
        if extraction is not None
        else [],
        "validation_reason": result.validation_reason,
        "provider_model": response.model,
        "input_tokens": response.input_token_count,
        "output_tokens": response.output_token_count,
        "latency_ms": round(response.latency_ms, 3),
        "estimated_call_cost_usd": round(call_cost, 8),
        "request_id_present": response.request_id is not None,
    }


def print_plan(stream: TextIO) -> None:
    _write_record(
        stream,
        {
            "mode": "plan_only",
            "model": MODEL,
            "call_count": MAX_ATTEMPTED_CALLS,
            "max_tokens_per_call": MAX_TOKENS,
            "retry_count": RETRIES,
            "maximum_authorized_spend_usd": MAXIMUM_AUTHORIZED_SPEND_USD,
            "maximum_input_tokens_per_call": MAX_INPUT_TOKENS_PER_CALL,
            "pre_run_maximum_cost_usd": round(PRE_RUN_MAXIMUM_COST_USD, 8),
            "case_ids": [case.case_id for case in CASES],
        },
    )


def run_live_validation(client: ModelClient, stream: TextIO = sys.stdout) -> int:
    _validate_plan()
    attempted = completed = total_input = total_output = 0
    total_cost = 0.0
    statuses: Counter[str] = Counter()

    for index, case in enumerate(CASES):
        remaining_calls = len(CASES) - index
        if not spend_guard_allows_call(total_cost, remaining_calls):
            _write_record(
                stream,
                {
                    "error": "spend_guard_blocked_call",
                    "attempted_calls": attempted,
                    "completed_calls": completed,
                },
            )
            return 1

        observing_client = _ObservingClient(client)
        attempted += 1
        try:
            result = extract_customer_message(case.customer_message, observing_client)
        except AnthropicProviderError as error:
            _write_record(
                stream,
                {
                    "provider_error": True,
                    "status": error.status_code,
                    "error_type": error.error_type,
                    "retryable": error.retryable,
                    "request_id_present": error.request_id is not None,
                },
            )
            return 1

        response = observing_client.response
        if response is None:  # pragma: no cover - invariant of nonempty fixed cases
            raise RuntimeError("model client returned no observable response")
        completed += 1
        total_input += response.input_token_count
        total_output += response.output_token_count
        call_cost = estimated_cost_usd(
            response.input_token_count, response.output_token_count
        )
        total_cost += call_cost
        statuses[result.status.value] += 1
        _write_record(stream, _case_record(case, result, response, call_cost))

    _write_record(
        stream,
        {
            "attempted_calls": attempted,
            "completed_calls": completed,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_estimated_cost_usd": round(total_cost, 8),
            "count_by_extraction_status": dict(sorted(statuses.items())),
        },
    )
    return 0


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
        help="authorize exactly three bounded live Anthropic calls",
    )
    args = parser.parse_args(argv)
    _validate_plan()
    if not args.confirm_live_call:
        print_plan(stream)
        return 0

    factory = client_factory or (
        lambda: AnthropicModelClient(
            AnthropicConfig(MODEL, MAX_TOKENS, TIMEOUT_SECONDS)
        )
    )
    return run_live_validation(factory(), stream)


if __name__ == "__main__":
    raise SystemExit(main())
