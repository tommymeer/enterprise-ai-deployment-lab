import json, os, unittest
from pathlib import Path
from unittest.mock import patch
from support_agent.demo import (SYNTHETIC_CUSTOMER_CONFIRMED_ADDRESSES, demo_options,
    eval_evidence, run_demo)
from support_agent import AddressMatchResult, DeterministicAddressComparison, OrderReference, RetrievalStatus, MatchStatus, SyntheticSupportCaseInput
from datetime import UTC, datetime
from support_agent.modeling import ModelResponse

class FakeLiveClient:
    def __init__(self,response=None,error=None): self.response,self.error,self.calls=response,error,0
    def complete(self,request):
        self.calls+=1
        if self.error: raise self.error
        return self.response

class DemoViewTests(unittest.TestCase):
    def run_live_order(self, order_id, *, scenario_id="refund-success"):
        message=f"Order {order_id} says delivered but I never got it."
        payload=json.dumps({"original_message":message,"issue_type":"delivered_not_received","order_identifier":order_id,"tracking_identifier":None,"customer_claims_package_missing":True,"customer_claims_address_correct":None,"missing_required_fields":[],"needs_clarification":False,"clarification_reason":None})
        client=FakeLiveClient(ModelResponse("anthropic","test-claude",response_text=payload,synthetic=False))
        return run_demo(scenario_id,message,mode="live",live_enabled=True,live_client_factory=lambda:client)

    def test_customer_outcomes_derive_from_final_state(self):
        success,failure=run_demo("refund-success"),run_demo("refund-execution-failure")
        self.assertEqual((success["customer_outcome"]["title"],success["final_state"]["case_status"]),("Refund processed","closed"))
        self.assertEqual((failure["customer_outcome"]["title"],failure["final_state"]["case_status"]),("Escalated for human review","human_review"))

    def test_trace_names_tools_and_covers_success_path(self):
        trace=run_demo("refund-success")["execution_trace"]; components=[x["component"] for x in trace]
        self.assertEqual(components[:2],["customer_message_extractor","extraction_validator"])
        for name in ("customer_lookup","order_lookup","shipment_lookup","carrier_lookup","address_comparison","dnr_policy","resolution_selector","refund_authority","execution_adapter","case_state"): self.assertIn(name,components)
        self.assertNotIn("tool_called",components)
        tool=next(x for x in trace if x["component"]=="order_lookup")
        self.assertEqual(tool["technical_details"][0]["tool_name"],"synthetic_order_lookup"); self.assertIn("order_id",tool["input"])

    def test_failure_trace_passes_authority_then_routes_review(self):
        trace=run_demo("refund-execution-failure")["execution_trace"]; names=[x["component"] for x in trace]
        self.assertLess(names.index("refund_authority"),names.index("execution_adapter")); self.assertLess(names.index("execution_adapter"),names.index("human_review_router"))
        execution=next(x for x in trace if x["component"]=="execution_adapter")
        self.assertEqual(execution["status"],"Failed")
        self.assertTrue(execution["state_changed"])
        self.assertEqual(execution["state_before"]["execution_status"],"in_progress")
        self.assertEqual(execution["state_after"]["execution_status"],"failed")
        self.assertFalse(execution["state_after"]["closed"])

    def test_cards_without_grouped_state_transition_do_not_claim_one(self):
        row=next(x for x in run_demo("refund-success")["execution_trace"] if x["component"]=="order_lookup")
        self.assertFalse(row["state_changed"])
        self.assertIsNone(row["state_before"])
        self.assertIsNone(row["state_after"])

    def test_offline_mode_is_locked_and_labeled(self):
        options=demo_options()
        self.assertFalse(options["modes"][0]["message_editable"]); self.assertEqual(options["default_mode"],"scripted")
        self.assertEqual([x["title"] for x in options["scenarios"]],
            ["Normal execution","Inject refund execution failure"])
        self.assertEqual([x["order_id"] for x in options["synthetic_order_examples"]],
            ["12345","24680","31415","27182"])
        self.assertEqual(run_demo("refund-success")["mode"]["label"],"Scripted extraction")
        with self.assertRaisesRegex(ValueError,"locked scenario fixture"): run_demo("refund-success","different words")

    def test_live_enabled_options_default_to_editable_live_mode(self):
        options=demo_options(live_enabled=True)
        self.assertEqual(options["default_mode"],"live")
        self.assertTrue(next(x for x in options["modes"] if x["id"]=="live")["message_editable"])

    def test_live_requires_opt_in_and_key_before_client_creation(self):
        with self.assertRaisesRegex(ValueError,"disabled"): run_demo("refund-success","Order 12345 is missing",mode="live")
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaisesRegex(ValueError,"ANTHROPIC_API_KEY"): run_demo("refund-success","Order 12345 is missing",mode="live",live_enabled=True)

    def test_provider_failure_does_not_enter_workflow(self):
        client=FakeLiveClient(error=RuntimeError("provider unavailable"))
        with self.assertRaisesRegex(RuntimeError,"provider unavailable"): run_demo("refund-success","Order 12345 is missing",mode="live",live_enabled=True,live_client_factory=lambda:client)
        self.assertEqual(client.calls,1)

    def test_live_one_call_and_unsupported_order_not_faked(self):
        message="Order 99999 says delivered but is missing."
        payload=json.dumps({"original_message":message,"issue_type":"delivered_not_received","order_identifier":"99999","tracking_identifier":None,"customer_claims_package_missing":True,"customer_claims_address_correct":None,"missing_required_fields":[],"needs_clarification":False,"clarification_reason":None})
        client=FakeLiveClient(ModelResponse("anthropic","test-claude",response_text=payload,synthetic=False))
        view=run_demo("refund-success",message,mode="live",live_enabled=True,live_client_factory=lambda:client)
        self.assertEqual(client.calls,1); self.assertEqual(view["final_state"]["case_status"],"awaiting_customer_action")
        self.assertEqual(view["customer_outcome"]["title"],"Order not found")
        self.assertEqual(next(x for x in view["execution_trace"] if x["component"]=="order_lookup")["output"]["match_status"],"not_found")

    def test_extracted_ids_resolve_distinct_fixed_retailer_records(self):
        first,second=self.run_live_order("12345"),self.run_live_order("24680")
        first_order=next(x for x in first["execution_trace"] if x["component"]=="order_lookup")
        second_order=next(x for x in second["execution_trace"] if x["component"]=="order_lookup")
        self.assertEqual(first_order["input"]["order_id"],"12345")
        self.assertEqual(second_order["input"]["order_id"],"24680")
        self.assertEqual(first_order["output"]["record_id"],"retailer-order-1001")
        self.assertEqual(second_order["output"]["record_id"],"retailer-order-1002")
        self.assertNotEqual(first_order["output"],second_order["output"])
        first_shipment=next(x for x in first["execution_trace"] if x["component"]=="shipment_lookup")
        second_shipment=next(x for x in second["execution_trace"] if x["component"]=="shipment_lookup")
        self.assertNotEqual(first_shipment["output"]["tracking_id"],second_shipment["output"]["tracking_id"])
        self.assertIn("12345",first["customer_outcome"]["message"])
        self.assertIn("24680",second["customer_outcome"]["message"])

    def test_supported_orders_exercise_existing_evidence_and_authority_paths(self):
        incomplete=self.run_live_order("31415")
        over_limit=self.run_live_order("27182")
        self.assertEqual(incomplete["customer_outcome"]["title"],"More evidence needed")
        carrier=next(x for x in incomplete["execution_trace"] if x["component"]=="carrier_lookup")
        self.assertEqual(carrier["input"]["shipment_id"],"retailer-shipment-1003")
        self.assertFalse(carrier["output"]["evidence_present"])
        authority=next(x for x in over_limit["execution_trace"] if x["component"]=="refund_authority")
        self.assertEqual(authority["output"]["authorization"],"blocked")
        self.assertEqual(authority["technical_details"][0]["state_after"]["case_status"],"human_review")
        self.assertEqual(over_limit["customer_outcome"]["title"],"Escalated for authorized review")

    def test_generic_rendering_does_not_hard_code_the_default_order(self):
        source=(Path(__file__).parents[1]/"src/support_agent/demo_static/index.html").read_text()
        self.assertNotIn("order 12345",source.lower())

    def test_live_missing_order_requests_clarification_without_tools(self):
        message="My delivery is marked delivered, but it is not here."
        payload=json.dumps({"original_message":message,"issue_type":"delivered_not_received","order_identifier":None,"tracking_identifier":None,"customer_claims_package_missing":True,"customer_claims_address_correct":None,"missing_required_fields":["order_identifier"],"needs_clarification":True,"clarification_reason":"An order identifier is required."})
        client=FakeLiveClient(ModelResponse("anthropic","test-claude",response_text=payload,synthetic=False))
        view=run_demo("refund-success",message,mode="live",live_enabled=True,live_client_factory=lambda:client)
        self.assertEqual(client.calls,1); self.assertEqual(view["intake_route"],"clarification_required")
        self.assertEqual(view["customer_outcome"]["title"],"More information needed")
        self.assertEqual([x["category"] for x in view["execution_trace"]],["MODEL","VALIDATION"])

    def test_readable_trace_results_are_strings_and_json_is_collapsed(self):
        view=run_demo("refund-success"); trace=view["execution_trace"]
        self.assertTrue(all(isinstance(x["result"],str) and x["result"] for x in trace))
        self.assertEqual(next(x for x in trace if x["component"]=="order_lookup")["result"],"Order 12345 found")
        self.assertEqual(sum(x["component"]=="execution_adapter" for x in trace),1)
        self.assertNotIn("execution_result",[x["component"] for x in trace])
        action=next(x for x in trace if x["component"]=="execution_adapter")
        self.assertEqual([x["event"] for x in action["technical_details"]],
            ["tool_called","tool_returned","execution_result_recorded"])
        raw=view["raw_workflow_trace"]
        self.assertIn("workflow_started",[x["event"] for x in raw])
        self.assertIn("workflow_completed",[x["event"] for x in raw])
        source=(Path(__file__).parents[1]/"src/support_agent/demo_static/index.html").read_text()
        self.assertIn('function readableFields(fields)',source)
        self.assertIn('row.display_input',source)
        self.assertIn('Raw input and result',source)
        self.assertNotIn('<b>Result</b><pre>',source)
        self.assertNotIn('Next:',source)

    def test_carrier_picture_proof_summary_uses_independent_source_field(self):
        with_picture=self.run_live_order("12345")
        without_picture=self.run_live_order("24680")
        carrier=lambda view: next(x for x in view["execution_trace"] if x["component"]=="carrier_lookup")
        self.assertEqual(carrier(with_picture)["result"],"Delivered event found · picture proof available")
        self.assertEqual(carrier(without_picture)["result"],"Delivered event found · no picture proof available")

    def test_raw_trace_is_separate_complete_and_ordered(self):
        view=run_demo("refund-success"); raw=view["raw_workflow_trace"]
        self.assertEqual([x["sequence"] for x in raw],list(range(len(raw))))
        self.assertEqual(raw[0]["event"],"budget_initialized")
        self.assertEqual(raw[-1]["event"],"workflow_completed")
        self.assertFalse(any("raw_workflow_trace" in detail for row in view["execution_trace"] for detail in row["technical_details"]))

    def test_interactive_disposition_is_explained_as_evidence_derived(self):
        row=next(x for x in run_demo("refund-success")["execution_trace"] if x["component"]=="resolution_selector")
        self.assertEqual(row["output"]["disposition"],"approve_refund")
        self.assertEqual(row["output"]["facts_consumed"]["carrier_delivery_status"],"delivered")
        self.assertIn("complete evidence",row["output"]["rule"])

    def test_real_address_comparison_match_mismatch_and_missing(self):
        now=datetime(2026,9,1,tzinfo=UTC)
        order=OrderReference("retailer-order-1",MatchStatus.MATCHED,"42.00 USD","apparel","42 Synthetic Market St",now,RetrievalStatus.SUCCESS)
        make=lambda address:SyntheticSupportCaseInput("case-1","message","customer-1","42","shipment-1","agent",now,address)
        compare=DeterministicAddressComparison()
        self.assertIs(compare(make("42 synthetic market st."),order),AddressMatchResult.MATCH)
        self.assertIs(compare(make("99 Different Road"),order),AddressMatchResult.MISMATCH)
        self.assertIs(compare(make(None),order),AddressMatchResult.UNKNOWN)

    def test_demo_address_uses_independent_support_channel_fixture(self):
        self.assertEqual(SYNTHETIC_CUSTOMER_CONFIRMED_ADDRESSES["24680"], "42 Synthetic Market St")
        view=self.run_live_order("24680")
        row=next(x for x in view["execution_trace"] if x["component"]=="address_comparison")
        self.assertEqual(row["result"], "Customer-confirmed address matches order shipping address")
        self.assertEqual(row["input"]["customer_confirmed_support_channel_address"], "value present")
        self.assertEqual(row["input"]["retailer_order_shipping_address"], "value present")

    def test_demo_validation_checks_only_report_recorded_trace_evidence(self):
        checks=run_demo("refund-success")["model"]["validation"]["named_checks"]
        self.assertEqual(checks, {"schema_parse_valid": True, "structured_extraction_valid": True})
        self.assertNotIn("missing_required_fields_consistent", checks)
        self.assertNotIn("clarification_fields_consistent", checks)

    def test_model_row_exposes_available_per_call_usage_metadata(self):
        message="Order 12345 says delivered but I never got it."
        payload=json.dumps({"original_message":message,"issue_type":"delivered_not_received","order_identifier":"12345","tracking_identifier":None,"customer_claims_package_missing":True,"customer_claims_address_correct":None,"missing_required_fields":[],"needs_clarification":False,"clarification_reason":None})
        response=ModelResponse("anthropic","test-claude",response_text=payload,synthetic=False,
            input_token_count=101,output_token_count=29,latency_ms=84.5,request_id="req-test",finish_reason="end_turn")
        view=run_demo("refund-success",message,mode="live",live_enabled=True,
            live_client_factory=lambda:FakeLiveClient(response))
        model_call=view["execution_trace"][0]["technical_details"][0]["model_call"]
        self.assertEqual(model_call,{"provider":"anthropic","model":"test-claude","request_id":"req-test",
            "input_tokens":101,"output_tokens":29,"latency_ms":84.5,"finish_reason":"end_turn"})
        self.assertNotIn("estimated_model_cost",model_call)

    def test_eval_examples_are_existing_fixtures(self):
        evidence=eval_evidence()
        self.assertEqual([x["title"] for x in evidence["coverage"]],["Extraction correctness","Semantic robustness","Grounding / hallucination control","Trajectory correctness","Authorization safety","Failure handling","Idempotency"])
        self.assertTrue(all(x["passed"] for x in evidence["coverage"]))
        self.assertEqual([x["source"] for x in evidence["examples"]],["extraction fixture: complete-order","extraction fixture: invented-order","trajectory fixture: correct_outcome_execution_before_disposition","trajectory fixture: over_limit_refund"])
        self.assertTrue(all(x["passed"] for x in evidence["examples"]))
        trajectory=next(x for x in evidence["examples"] if x["title"]=="Trajectory control")
        self.assertEqual(trajectory["actual"]["outcome_failures"],[])
        self.assertEqual(trajectory["actual"]["trajectory_failures"],["disposition must occur before execution_started"])
        self.assertIn("offline",evidence["note"])

    def test_removed_sections_are_not_rendered(self):
        source=(Path(__file__).parents[1]/"src/support_agent/demo_static/index.html").read_text()
        for removed in ("System pipeline","Decision timeline","Technical case details","Implementation map"): self.assertNotIn(removed,source)
        self.assertIn("Execution trace",source); self.assertIn("Evaluation coverage",source); self.assertIn("Representative examples",source); self.assertNotIn("setTimeout",source)

if __name__=="__main__": unittest.main()
