import inspect
import unittest

from app.agents import sales_agent
from app.core.config import PERSONAS, SALES_LEADS, SALES_LEAD_FIELDS


PRIVATE_PERSONA_FIELDS = (
    "description",
    "financial_status",
    "health_status",
    "insurance_awareness",
    "risk_preference",
    "core_focus",
    "communication_style",
    "hidden_secrets",
    "objection_triggers",
)


class SalesLeadIsolationTests(unittest.TestCase):
    def test_every_persona_has_exactly_one_minimal_sales_lead(self):
        self.assertEqual(set(PERSONAS), set(SALES_LEADS))
        for persona_id, lead in SALES_LEADS.items():
            self.assertEqual(set(lead), set(SALES_LEAD_FIELDS))
            self.assertEqual(lead["persona_id"], persona_id)
            self.assertEqual(lead["customer_name"], PERSONAS[persona_id]["name"])

    def test_sales_agent_has_no_dependency_on_complete_personas(self):
        source = inspect.getsource(sales_agent)
        self.assertNotIn("PERSONAS", source)
        self.assertNotIn("hidden_secrets", source)
        self.assertNotIn("core_focus", source)
        self.assertNotIn("financial_status", source)
        self.assertNotIn("health_status", source)
        self.assertNotIn('turn["role"] == "coach"', source)

    def test_privileged_evaluator_advice_is_not_added_to_sales_history(self):
        from app.services import session_manager

        source = inspect.getsource(session_manager.SessionManager.add_evaluation)
        self.assertNotIn('add_conversation_turn(session_id, "coach"', source)

    def test_sales_prompt_exposes_lead_but_not_private_persona_values(self):
        for persona_id, persona in PERSONAS.items():
            with self.subTest(persona_id=persona_id):
                lead = SALES_LEADS[persona_id]
                prompt = sales_agent.build_sales_system_prompt(
                    strategy_id="consultant",
                    persona_id=persona_id,
                    current_stage="INTRODUCTION",
                    turn_count=0,
                )

                self.assertIn(lead["customer_name"], prompt)
                self.assertIn(lead["preferred_salutation"], prompt)
                self.assertIn(lead["occupation"], prompt)
                self.assertIn("具体需求尚待了解", prompt)

                for field in PRIVATE_PERSONA_FIELDS:
                    value = persona.get(field)
                    if isinstance(value, str) and value:
                        self.assertNotIn(value, prompt, msg=f"Sales prompt 泄露字段: {field}")
                    elif isinstance(value, list):
                        for item in value:
                            self.assertNotIn(item, prompt, msg=f"Sales prompt 泄露字段: {field}")

    def test_eager_youth_sales_view_does_not_reveal_discovery_answers(self):
        prompt = sales_agent.build_sales_system_prompt(
            strategy_id="data_driven",
            persona_id="eager_youth",
            current_stage="INTRODUCTION",
            turn_count=0,
        )

        for private_fact in (
            "年收入20万",
            "6000-8000元/年",
            "百万医疗险",
            "意外险",
            "重疾险和医疗险到底有什么区别",
            "收入补偿",
        ):
            self.assertNotIn(private_fact, prompt)


if __name__ == "__main__":
    unittest.main()
