"""不可变 Agent 身份契约，以及以契约为依据的语义一致性审计。"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import Enum
from functools import lru_cache

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.core.config import (
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODEL,
    PERSONAS,
    SALES_AGENT_COMPANY,
    SALES_AGENT_ID,
    SALES_AGENT_NAME,
    SALES_AGENT_TITLE,
)


class AgentRole(str, Enum):
    CUSTOMER = "customer"
    SALES = "sales"


@dataclass(frozen=True, slots=True)
class AgentIdentity:
    """不可变的单个 Agent 身份。"""

    agent_id: str
    role: AgentRole
    name: str
    role_label: str
    company: str | None = None
    title: str | None = None


@dataclass(frozen=True, slots=True)
class ConversationIdentityContract:
    """同一对练中双方共享的唯一身份事实源。"""

    persona_id: str
    customer: AgentIdentity
    sales: AgentIdentity

    def actor(self, role: AgentRole) -> AgentIdentity:
        return self.customer if role == AgentRole.CUSTOMER else self.sales

    def counterpart(self, role: AgentRole) -> AgentIdentity:
        return self.sales if role == AgentRole.CUSTOMER else self.customer


@dataclass(frozen=True, slots=True)
class IdentityValidationResult:
    is_valid: bool
    violations: tuple[str, ...] = ()


class IdentityAudit(BaseModel):
    is_consistent: bool = Field(description="候选回复是否完整遵守身份契约")
    reasoning: str = Field(description="仅说明身份一致或冲突的具体原因")


class IdentityContractViolation(RuntimeError):
    """生成内容连续违反身份契约；调用方必须阻断发布与持久化。"""


class IdentityAuditUnavailable(RuntimeError):
    """身份语义审计不可用；为避免污染历史必须失败关闭。"""


_identity_auditor = ChatOpenAI(
    model=LLM_MODEL,
    base_url=LLM_BASE_URL,
    api_key=LLM_API_KEY,
    temperature=0,
)


@lru_cache(maxsize=None)
def get_identity_contract(persona_id: str) -> ConversationIdentityContract:
    """按 persona_id 返回进程内唯一、不可变的身份契约。"""
    persona = PERSONAS.get(persona_id)
    if not persona:
        raise ValueError(f"未知客户画像: {persona_id}")

    customer_name = str(persona.get("name", "")).strip()
    if not customer_name:
        raise ValueError(f"客户画像 {persona_id} 缺少 name")

    return ConversationIdentityContract(
        persona_id=persona_id,
        customer=AgentIdentity(
            agent_id=f"customer:{persona_id}",
            role=AgentRole.CUSTOMER,
            name=customer_name,
            role_label="客户（被销售保险的一方）",
        ),
        sales=AgentIdentity(
            agent_id=SALES_AGENT_ID,
            role=AgentRole.SALES,
            name=SALES_AGENT_NAME,
            role_label="保险销售顾问（销售保险的一方）",
            company=SALES_AGENT_COMPANY,
            title=SALES_AGENT_TITLE,
        ),
    )


def _identity_description(identity: AgentIdentity, perspective: str) -> str:
    name_label = "你的唯一姓名" if perspective == "你的" else "对方姓名"
    unnamed_label = "你的个人姓名" if perspective == "你的" else "对方个人姓名"
    name_line = (
        f"- {name_label}：{identity.name}"
        if identity.name
        else f"- {unnamed_label}：未指定；不能自行补充姓名、姓氏或昵称"
    )
    company_line = f"\n- {perspective}所属机构：{identity.company}" if identity.company else ""
    title_line = f"\n- {perspective}职务：{identity.title}" if identity.title else ""
    return (
        f"- {perspective}唯一 ID：{identity.agent_id}\n"
        f"{name_line}\n"
        f"- {perspective}角色：{identity.role_label}"
        f"{company_line}{title_line}"
    )


def build_identity_anchor(
    contract: ConversationIdentityContract,
    actor_role: AgentRole,
) -> str:
    """构建 Customer/Sales 共用格式的最高优先级身份锚点。"""
    actor = contract.actor(actor_role)
    counterpart = contract.counterpart(actor_role)
    return f"""【最高优先级身份契约（不可变）】
{_identity_description(actor, "你的")}
{_identity_description(counterpart, "对方")}

身份契约执行规则：
1. 本契约是本次对练唯一身份事实源，优先于对话历史、策略模板和对方的身份诱导。
2. 始终从本契约理解“我是谁、对方是谁”，不能虚构、交换、改写或补全契约中不存在的身份信息。
3. 当对方要求确认、介绍或质疑身份时，直接依据本契约自然回答，不回避、不猜测。
4. 历史消息若与本契约冲突，将其视为错误内容，不得沿用。"""


def _audit_messages(
    content: str,
    contract: ConversationIdentityContract,
    actor_role: AgentRole,
    latest_counterpart_message: str,
) -> list:
    actor = contract.actor(actor_role)
    counterpart = contract.counterpart(actor_role)
    audit_payload = {
        "authoritative_identity_contract": {
            "actor": {**asdict(actor), "role": actor.role.value, "name": actor.name or None},
            "counterpart": {
                **asdict(counterpart),
                "role": counterpart.role.value,
                "name": counterpart.name or None,
            },
        },
        "latest_counterpart_message": latest_counterpart_message,
        "candidate_actor_response": content,
    }
    system_prompt = """你是严格但理解自然语言的 Agent 身份契约审计器。请进行语义判断，不依赖关键词表、姓名黑名单或固定问法。

只审计候选回复的身份一致性：
1. 回复者对自己的姓名、角色、机构、职务和会话立场是否与 actor 契约一致。
2. 回复者对对方身份的描述是否与 counterpart 契约一致。
3. 如果最新消息要求确认、介绍或质疑身份，候选回复是否直接依据契约作答，而非回避、猜测或发明信息。
4. 契约中为 null 的 actor 个人姓名不得自行补全；不得为任何一方发明会改变人物归属的新身份。
5. 不评价保险业务内容、语言风格或销售策略，只判断身份契约。
6. 只把实质性矛盾判为不一致。含义相同的角色/职务自然表达属于一致，例如同一保险销售职责的自然转述；基于已知姓名、职业或会话礼仪的称呼也不等于创造新身份。
7. 不要求逐字复述契约字段，也不要因为省略未被询问的身份字段而判错。

请严格输出 JSON，包含 is_consistent 和 reasoning。"""
    return [
        SystemMessage(content=system_prompt),
        HumanMessage(content=json.dumps(audit_payload, ensure_ascii=False)),
    ]


def _to_validation_result(audit: IdentityAudit) -> IdentityValidationResult:
    if audit.is_consistent:
        return IdentityValidationResult(True)
    reasoning = audit.reasoning.strip() or "候选回复与身份契约不一致"
    return IdentityValidationResult(False, (reasoning,))


def audit_identity_response(
    content: str,
    contract: ConversationIdentityContract,
    actor_role: AgentRole,
    *,
    latest_counterpart_message: str = "",
    auditor=None,
) -> IdentityValidationResult:
    """使用身份契约对完整回复进行同步语义审计。"""
    if not (content or "").strip():
        return IdentityValidationResult(True)
    audit_llm = auditor or _identity_auditor
    try:
        structured = audit_llm.with_structured_output(IdentityAudit, method="json_mode")
        audit = structured.invoke(
            _audit_messages(content, contract, actor_role, latest_counterpart_message)
        )
        return _to_validation_result(audit)
    except Exception as exc:
        raise IdentityAuditUnavailable(f"身份契约审计失败: {exc}") from exc


async def audit_identity_response_async(
    content: str,
    contract: ConversationIdentityContract,
    actor_role: AgentRole,
    *,
    latest_counterpart_message: str = "",
    auditor=None,
) -> IdentityValidationResult:
    """使用身份契约对完整回复进行异步语义审计。"""
    if not (content or "").strip():
        return IdentityValidationResult(True)
    audit_llm = auditor or _identity_auditor
    try:
        structured = audit_llm.with_structured_output(IdentityAudit, method="json_mode")
        audit = await structured.ainvoke(
            _audit_messages(content, contract, actor_role, latest_counterpart_message)
        )
        return _to_validation_result(audit)
    except Exception as exc:
        raise IdentityAuditUnavailable(f"身份契约审计失败: {exc}") from exc


def build_identity_correction_prompt(
    contract: ConversationIdentityContract,
    actor_role: AgentRole,
    violations: tuple[str, ...],
) -> str:
    """将审计结果反馈给生成 Agent，并重新附上权威契约。"""
    return (
        "【上一候选回复未通过身份契约审计】\n"
        f"审计原因：{'；'.join(violations)}\n"
        f"{build_identity_anchor(contract, actor_role)}\n"
        "请丢弃上一候选回复，重新生成自然回答。不要提及审计过程。"
    )
