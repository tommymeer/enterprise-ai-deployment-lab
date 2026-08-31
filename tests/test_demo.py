import json, os, unittest
from pathlib import Path
from unittest.mock import patch
from support_agent.demo import demo_options, eval_evidence, run_demo
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
        self.assertEqual(next(x for x in trace if x["component"]=="execution_adapter")["status"],"Failed")

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
        self.assertEqual(authority["output"]["decision"],"blocked")
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
        trace=run_demo("refund-success")["execution_trace"]
        self.assertTrue(all(isinstance(x["result"],str) and x["result"] for x in trace))
        self.assertEqual(next(x for x in trace if x["component"]=="order_lookup")["result"],"Order 12345 found")
        self.assertEqual(sum(x["component"]=="execution_adapter" for x in trace),1)
        self.assertNotIn("execution_result",[x["component"] for x in trace])
        action=next(x for x in trace if x["component"]=="execution_adapter")
        self.assertEqual([x["event"] for x in action["technical_details"]],
            ["tool_called","tool_returned","execution_result_recorded"])
        raw=trace[-1]["technical_details"][-1]["raw_workflow_trace"]
        self.assertIn("workflow_started",[x["event"] for x in raw])
        self.assertIn("workflow_completed",[x["event"] for x in raw])
        source=(Path(__file__).parents[1]/"src/support_agent/demo_static/index.html").read_text()
        self.assertIn('Result:</b> ${esc(row.result)}',source)
        self.assertNotIn('<b>Result</b><pre>',source)

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
        evidence=eval_evidence(); self.assertEqual([x["source"] for x in evidence["examples"]],["extraction fixture: complete-order","extraction fixture: invented-order","trajectory fixture: correct_outcome_execution_before_disposition"]); self.assertTrue(all(x["passed"] for x in evidence["examples"]))

    def test_removed_sections_are_not_rendered(self):
        source=(Path(__file__).parents[1]/"src/support_agent/demo_static/index.html").read_text()
        for removed in ("System pipeline","Decision timeline","Technical case details","Implementation map"): self.assertNotIn(removed,source)
        self.assertIn("Execution trace",source); self.assertIn("How I evaluated this system",source); self.assertNotIn("setTimeout",source)

if __name__=="__main__": unittest.main()
