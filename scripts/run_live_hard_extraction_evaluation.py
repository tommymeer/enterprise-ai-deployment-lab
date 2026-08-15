"""Manually authorized, bounded live evaluation of the six hard extraction cases."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import fields
from typing import TextIO

from support_agent import (
    AnthropicConfig,
    AnthropicModelClient,
    AnthropicProviderError,
    ModelClient,
    ModelRequest,
    ModelResponse,
    extract_customer_message,
)
from support_agent.extraction import CustomerMessageExtraction
from support_agent.extraction_evaluation import (
    ExtractionEvalCase,
    compare_extractions,
    get_hard_extraction_eval_cases,
)


MODEL = "claude-sonnet-5"
MAX_TOKENS = 512
TIMEOUT_SECONDS = 30
RETRIES = 0
MAX_ATTEMPTED_CALLS = 6
AUTHORIZED_ESTIMATED_SPEND_LIMIT_USD = 0.09
MAX_INPUT_TOKENS_PER_CALL = 2_000
INPUT_USD_PER_MILLION_TOKENS = 3.00
OUTPUT_USD_PER_MILLION_TOKENS = 15.00


def estimated_cost_usd(input_tokens: int, output_tokens: int) -> float:
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


def _display(value: object) -> object:
    return value.value if hasattr(value, "value") else value


def _extraction_record(extraction: CustomerMessageExtraction | None) -> object:
    if extraction is None:
        return None
    return {
        field.name: (
            list(value) if isinstance(value, tuple) else _display(value)
        )
        for field in fields(CustomerMessageExtraction)
        for value in (getattr(extraction, field.name),)
    }


def _write_record(stream: TextIO, record: dict[str, object]) -> None:
    print(json.dumps(record, separators=(",", ":"), sort_keys=True), file=stream)


def _cases() -> tuple[ExtractionEvalCase, ...]:
    cases = get_hard_extraction_eval_cases()
    if (
        len(cases) != MAX_ATTEMPTED_CALLS
        or len({case.case_id for case in cases}) != MAX_ATTEMPTED_CALLS
    ):
        raise RuntimeError("live hard extraction evaluation requires six unique cases")
    return cases


def spend_guard_allows_call(
    cumulative_cost_usd: float, uncompleted_calls: int
) -> bool:
    conservative_total = (
        cumulative_cost_usd + uncompleted_calls * MAXIMUM_COST_PER_CALL_USD
    )
    return conservative_total <= AUTHORIZED_ESTIMATED_SPEND_LIMIT_USD


class _ObservingClient:
    def __init__(self, delegate: ModelClient) -> None:
        self._delegate = delegate
        self.response: ModelResponse | None = None

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.response = self._delegate.complete(request)
        return self.response


def print_plan(stream: TextIO) -> None:
    cases = _cases()
    _write_record(
        stream,
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
    )


def run_live_evaluation(client: ModelClient, stream: TextIO = sys.stdout) -> int:
    cases = _cases()
    attempted = valid = semantic_matches = total_input = total_output = 0
    total_latency_ms = total_cost = 0.0
    provider_failures = validation_failures = 0
    field_matches: Counter[str] = Counter()
    field_names = tuple(field.name for field in fields(CustomerMessageExtraction))

    for index, case in enumerate(cases):
        remaining_calls = len(cases) - index
        if not spend_guard_allows_call(total_cost, remaining_calls):
            _write_record(stream, {"error": "spend_guard_blocked_call", "case_id": case.case_id})
            break

        observing = _ObservingClient(client)
        attempted += 1
        try:
            result = extract_customer_message(case.customer_message, observing)
        except AnthropicProviderError as error:
            provider_failures += 1
            _write_record(
                stream,
                {
                    "case_id": case.case_id,
                    "provider_failure": True,
                    "status_code": error.status_code,
                    "error_type": error.error_type,
                    "retryable": error.retryable,
                    "request_id_present": error.request_id is not None,
                },
            )
            continue

        response = observing.response
        if response is None:  # pragma: no cover - ModelClient contract invariant
            raise RuntimeError("model client returned no observable response")
        call_cost = estimated_cost_usd(
            response.input_token_count, response.output_token_count
        )
        total_input += response.input_token_count
        total_output += response.output_token_count
        total_latency_ms += response.latency_ms
        total_cost += call_cost

        comparisons = (
            compare_extractions(case.expected, result.extraction)
            if result.extraction is not None
            else ()
        )
        if result.extraction is not None:
            valid += 1
        else:
            validation_failures += 1
        for comparison in comparisons:
            if comparison.matched:
                field_matches[comparison.field_name] += 1
        semantic_match = bool(comparisons) and all(item.matched for item in comparisons)
        semantic_matches += int(semantic_match)
        mismatches = [
            {
                "field": item.field_name,
                "expected": _display(item.expected),
                "actual": _display(item.actual),
            }
            for item in comparisons
            if not item.matched
        ]
        _write_record(
            stream,
            {
                "case_id": case.case_id,
                "validation_status": result.status.value,
                "validation_reason": result.validation_reason,
                "semantic_result": "PASS" if semantic_match else "FAIL",
                "mismatched_fields": mismatches,
                "actual_extraction": _extraction_record(result.extraction),
                "raw_model_output": response.response_text,
                "input_tokens": response.input_token_count,
                "output_tokens": response.output_token_count,
                "latency_ms": round(response.latency_ms, 3),
                "finish_reason": response.finish_reason,
                "estimated_cost_usd": round(call_cost, 8),
            },
        )

    _write_record(
        stream,
        {
            "summary": True,
            "attempted_calls": attempted,
            "valid_outputs": valid,
            "total_cases": len(cases),
            "semantic_exact_matches": semantic_matches,
            "per_field_accuracy": {
                name: {
                    "matches": field_matches[name],
                    "total": len(cases),
                    "accuracy": field_matches[name] / len(cases),
                }
                for name in field_names
            },
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_latency_ms": round(total_latency_ms, 3),
            "total_estimated_cost_usd": round(total_cost, 8),
            "authorized_estimated_spend_limit_usd": AUTHORIZED_ESTIMATED_SPEND_LIMIT_USD,
            "estimated_spend_limit_respected": (
                total_cost <= AUTHORIZED_ESTIMATED_SPEND_LIMIT_USD
            ),
            "provider_failures": provider_failures,
            "validation_failures": validation_failures,
        },
    )
    return 0 if attempted == len(cases) else 1


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
        help="authorize exactly six bounded live Anthropic calls",
    )
    args = parser.parse_args(argv)
    if not args.confirm_live_call:
        print_plan(stream)
        return 0
    factory = client_factory or (
        lambda: AnthropicModelClient(
            AnthropicConfig(
                MODEL, MAX_TOKENS, TIMEOUT_SECONDS, disable_thinking=True
            )
        )
    )
    return run_live_evaluation(factory(), stream)


if __name__ == "__main__":
    raise SystemExit(main())
