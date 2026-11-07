import inspect
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from app.agents.identity import (
    AgentRole,
    IdentityContractViolation,
    IdentityValidationResult,
    audit_identity_response,
    audit_identity_response_async,
    build_identity_anchor,
    get_identity_contract,
)


class _StructuredAuditStub:
    def __init__(self, results):
        self._results = iter(results)
        self.messages = []

    def with_structured_output(self, *_args, **_kwargs):
        return self

    def invoke(self, messages):
        self.messages.append(messages)
        return next(self._results)

    async def ainvoke(self, messages):
        self.messages.append(messages)
        return next(self._results)


class AgentIdentityContractTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.contract = get_identity_contract("hard_boss")

    def test_contract_is_canonical_and_immutable(self):
        self.assertEqual(self.contract.customer.name, "王强")
        self.assertEqual(self.contract.customer.role, AgentRole.CUSTOMER)
        self.assertEqual(self.contract.sales.role, AgentRole.SALES)
        self.assertEqual(self.contract.sales.name, "")

        with self.assertRaises((AttributeError, TypeError)):
            self.contract.customer.name = "任意姓名"

    def test_anchors_are_derived_from_the_same_contract(self):
        customer_anchor = build_identity_anchor(self.contract, AgentRole.CUSTOMER)
        sales_anchor = build_identity_anchor(self.contract, AgentRole.SALES)

        self.assertIn("你的唯一姓名：王强", customer_anchor)
        self.assertIn("对方个人姓名：未指定", customer_anchor)
        self.assertIn("你的个人姓名：未指定", sales_anchor)
        self.assertIn("对方姓名：王强", sales_anchor)
        self.assertIn("泰康人寿", customer_anchor)
        self.assertIn("泰康人寿", sales_anchor)

    def test_identity_module_has_no_dialogue_keyword_or_name_blacklist(self):
        import app.agents.identity as identity_module

        source = inspect.getsource(identity_module)
        for forbidden in (
            "_is_identity_question",
            "_self_claim_windows",
            "build_identity_safe_fallback",
            "re.search",
            "re.findall",
            "小张",
            "老张",
            "张顾问",
            "你是谁",
        ):
            self.assertNotIn(forbidden, source)

    def test_semantic_audit_uses_contract_and_latest_turn(self):
        auditor = _StructuredAuditStub([
            SimpleNamespace(is_consistent=False, reasoning="回复声称了与契约不一致的销售身份")
        ])
        result = audit_identity_response(
            "这里是一条与契约冲突的任意表达。",
            self.contract,
            AgentRole.CUSTOMER,
            latest_counterpart_message="请介绍一下您在本次会话中的角色。",
            auditor=auditor,
        )

        self.assertFalse(result.is_valid)
        self.assertIn("销售身份", result.violations[0])
        audit_payload = str(auditor.messages[0])
        self.assertIn("王强", audit_payload)
        self.assertIn("customer", audit_payload)
        self.assertIn("请介绍一下您在本次会话中的角色", audit_payload)

    async def test_async_semantic_audit_accepts_consistent_response(self):
        auditor = _StructuredAuditStub([
            SimpleNamespace(is_consistent=True, reasoning="与身份契约一致")
        ])
        result = await audit_identity_response_async(
            "我是本次对练中的客户王强。",
            self.contract,
            AgentRole.CUSTOMER,
            latest_counterpart_message="方便自我介绍一下吗？",
            auditor=auditor,
        )

        self.assertTrue(result.is_valid)


class _SyncLLMStub:
    def __init__(self, replies):
        self._replies = iter(replies)

    def invoke(self, _messages):
        return AIMessage(content=next(self._replies))


class _AsyncLLMStub:
    def __init__(self, replies):
        self._replies = iter(replies)

    async def ainvoke(self, _messages):
        return AIMessage(content=next(self._replies))


class AgentIdentityGuardIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def test_customer_retries_from_contract_before_checkpoint(self):
        with patch.dict(os.environ, {"RAG_PRELOAD_FALLBACK": "false"}):
            from app.agents import customer_graph

        state = {
            "messages": [HumanMessage(content="请说明您在这里扮演什么角色。")],
            "current_stage": "INTRODUCTION",
            "turn_count": 0,
            "persona_id": "hard_boss",
            "tool_calls_log": [],
            "force_objection": False,
            "stage_reasoning": "",
            "decision_strike": 0,
            "pending_shutdown": False,
            "detected_stage_raw": "INTRODUCTION",
        }
        invalid = "我负责向您推荐保险产品。"
        corrected = "我是王强，是本次对练中被销售保险的客户。"
        audits = iter([
            IdentityValidationResult(False, ("角色与契约不一致",)),
            IdentityValidationResult(True),
        ])

        with (
            patch.object(customer_graph, "llm_with_tools", _SyncLLMStub([invalid])),
            patch.object(customer_graph, "llm", _SyncLLMStub([corrected])),
            patch.object(customer_graph, "audit_identity_response", side_effect=lambda *_a, **_k: next(audits)),
        ):
            output = customer_graph.customer_node(state)

        self.assertEqual(output["messages"][-1].content, corrected)
        self.assertNotEqual(output["messages"][-1].content, invalid)

    async def test_sales_retries_before_any_sse_text_is_published(self):
        from app.agents import sales_agent

        invalid = "我是本次来购买保险的客户。"
        corrected = "我是泰康人寿的保险销售顾问。"
        audits = iter([
            IdentityValidationResult(False, ("角色与契约不一致",)),
            IdentityValidationResult(True),
        ])
        events = []
        with (
            patch.object(sales_agent, "sales_llm_with_tools", _AsyncLLMStub([invalid])),
            patch.object(sales_agent, "sales_llm", _AsyncLLMStub([corrected])),
            patch.object(sales_agent, "audit_identity_response_async", side_effect=lambda *_a, **_k: next(audits)),
            patch.object(sales_agent.asyncio, "sleep", new=AsyncMock()),
        ):
            async for event in sales_agent.sales_agent_step(
                session_id="identity-test",
                strategy_id="consultant",
                persona_id="hard_boss",
                current_stage="INTRODUCTION",
                turn_count=2,
                conversation_history=[{"role": "customer", "content": "请介绍一下您的角色。"}],
            ):
                events.append(event)

        visible_text = "".join(
            event.get("content", "") for event in events if event["type"] == "sales_token"
        )
        self.assertEqual(visible_text, corrected)
        self.assertNotIn(invalid, visible_text)

    def test_customer_blocks_second_contract_violation_without_fallback_dialogue(self):
        with patch.dict(os.environ, {"RAG_PRELOAD_FALLBACK": "false"}):
            from app.agents import customer_graph

        state = {
            "messages": [HumanMessage(content="介绍一下自己。")],
            "current_stage": "INTRODUCTION",
            "turn_count": 0,
            "persona_id": "hard_boss",
            "tool_calls_log": [],
            "force_objection": False,
            "stage_reasoning": "",
            "decision_strike": 0,
            "pending_shutdown": False,
            "detected_stage_raw": "INTRODUCTION",
        }
        audits = iter([
            IdentityValidationResult(False, ("第一次冲突",)),
            IdentityValidationResult(False, ("第二次冲突",)),
        ])

        with (
            patch.object(customer_graph, "llm_with_tools", _SyncLLMStub(["错误回复一"])),
            patch.object(customer_graph, "llm", _SyncLLMStub(["错误回复二"])),
            patch.object(customer_graph, "audit_identity_response", side_effect=lambda *_a, **_k: next(audits)),
        ):
            with self.assertRaises(IdentityContractViolation):
                customer_graph.customer_node(state)


if __name__ == "__main__":
    unittest.main()
