# 文件：app/agents/sales_agent.py
"""销售 Agent — 可调用工具的专业销售 AI，用于 Auto-Agent 自动对战模式"""
import asyncio
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_openai import ChatOpenAI

from app.core.config import LLM_MODEL, LLM_BASE_URL, LLM_API_KEY, SALES_LEADS, SALES_STRATEGIES
from app.agents.state import DialogueStage
from app.agents.identity import (
    AgentRole,
    IdentityContractViolation,
    audit_identity_response_async,
    build_identity_anchor,
    build_identity_correction_prompt,
    get_identity_contract,
)
from app.tools.rag_tool import search_insurance_knowledge
from app.tools.calculators import query_premium_rate, query_cash_value


# ==========================================
# LLM + 工具绑定
# ==========================================
sales_llm = ChatOpenAI(
    model=LLM_MODEL,
    base_url=LLM_BASE_URL,
    api_key=LLM_API_KEY,
    streaming=True,
)

TOOLS = [search_insurance_knowledge, query_premium_rate, query_cash_value]
sales_llm_with_tools = sales_llm.bind_tools(TOOLS)

# 工具名 → 可调用函数 的映射（供手动执行工具）
TOOL_EXECUTOR = {
    "search_insurance_knowledge": search_insurance_knowledge,
    "query_premium_rate": query_premium_rate,
    "query_cash_value": query_cash_value,
}

# 阶段中文标签
STAGE_LABELS = {
    DialogueStage.INTRODUCTION:       "破冰与探寻",
    DialogueStage.OBJECTION:          "异议处理",
    DialogueStage.DECISION_SIGN:      "签单成功",
    DialogueStage.DECISION_PENDING:   "同意核保",
    DialogueStage.DECISION_FOLLOW_UP: "需要跟进",
    DialogueStage.DECISION_REJECT:    "客户拒绝",
    DialogueStage.DECISION_ABANDON:   "放弃投保",
}


def build_sales_system_prompt(
    strategy_id: str,
    persona_id: str,
    current_stage: str,
    turn_count: int,
) -> str:
    """仅使用 Sales 基础线索构建提示词，禁止读取 Customer 完整画像。"""
    strategy = SALES_STRATEGIES.get(strategy_id, {})
    lead = SALES_LEADS.get(persona_id)
    if not lead:
        raise ValueError(f"客户画像 {persona_id} 缺少 Sales 基础线索")

    identity_contract = get_identity_contract(persona_id)
    identity_anchor = build_identity_anchor(identity_contract, AgentRole.SALES)
    stage_instruction = _build_sales_stage_instruction(current_stage, turn_count)

    return f"""你是一名保险销售顾问，正在与客户进行真实的销售对话，你正在销售。

{identity_anchor}

【你的销售风格：{strategy.get('name', '专业顾问型')}】
{strategy.get('prompt_instructions', '')}

【建议开场话术】
{strategy.get('opening_template', '先礼貌问候客户并了解保障需求。')}

【Sales 可见的客户基础线索】
姓名：{lead['customer_name']}
首选称呼：{lead['preferred_salutation']}
年龄：{lead['age']}岁
性别：{lead['gender']}
职业：{lead['occupation']}
线索来源：{lead['lead_source']}
联系背景：{lead['contact_context']}

【客户信息边界（必须遵守）】
1. 上述内容是会前登记的基础线索，不代表客户已在本次对话中亲口确认。
2. 除上述基础线索外，客户的家庭结构、收入与负债、预算、健康状况、既有保障、保险认知、风险偏好、真实需求和关注问题均视为未知。
3. 未知信息必须通过自然提问逐步了解；不得声称已经掌握，不得猜测、补全或暗示后台存在更完整的客户画像。
4. 在客户确认关键信息之前，不得据此直接形成个性化方案或报价。
5. 对话中优先使用“{lead['preferred_salutation']}”或“您”，不要无缘由直呼客户完整姓名。

【销售保险信息】
现在需要销售的产品是“泰康乐享健康2026重大疾病保险”。该产品为终身重大疾病保险，仅提供终身保障，不存在任何定期版本。被保险人投保年龄必须在0至70周岁（含）之间，超出范围必须明确拒绝投保，不得承诺特殊通融。
产品支持趸交和年交两种缴费方式。年交可选1年、3年、5年、10年、15年、20年、25年、30年，但必须满足“投保年龄＋缴费年期≤75”的规则，否则不能承保。例如55岁客户最长只能选择20年交。面对客户关于缴费年期的提问，必须主动进行年龄与缴费期的合规计算并解释逻辑。
本产品等待期为90天，
理赔金额与出险时被保险人年龄相关
产品实行严格的责任互斥原则。重大疾病保险金、全残保险金、疾病终末期保险金和身故保险金仅赔付其中一项，一旦任何一项完成赔付，合同即终止，其余责任失效。不得暗示或承诺可叠加理赔。

【当前对话状态】
阶段：{current_stage} — {STAGE_LABELS.get(current_stage, '')}
回合数：第 {turn_count} 轮
{stage_instruction}

【工具使用强制规范】
- 报任何保费数字前：必须先调用 query_premium_rate 工具查实际费率
- 提到现金价值或退保金额前：必须先调用 query_cash_value 查询
- 引用任何保险条款/核保规则前：必须先调用 search_insurance_knowledge 验证

直接输出你要对客户说的话，不要有任何内心OS或前缀说明，不要使用任何MD格式标记。"""


# ==========================================
# 核心：销售 Agent 推进一步（流式生成器）
# ==========================================
async def sales_agent_step(
    session_id: str,
    strategy_id: str,
    persona_id: str,
    current_stage: str,
    turn_count: int,
    conversation_history: list,  # [{"role": "sales"|"customer", "content": "..."}]
):
    """
    销售 Agent 推进一步：
    1. 构建 System Prompt（含策略风格 + 阶段指令）
    2. 调用 LLM，若有工具调用则执行并继续
    3. 逐 token 流式生成销售最终发言

    为异步生成器，yield 各种事件字典供 SSE 端点使用。
    """
    strategy = SALES_STRATEGIES.get(strategy_id, {})
    identity_contract = get_identity_contract(persona_id)

    # ---- 构建 System Prompt ----
    system_content = build_sales_system_prompt(
        strategy_id=strategy_id,
        persona_id=persona_id,
        current_stage=current_stage,
        turn_count=turn_count,
    )

    # ---- 构建消息历史 ----
    messages = [SystemMessage(content=system_content)]
    for turn in conversation_history:
        if turn["role"] == "sales":
            messages.append(AIMessage(content=turn["content"]))
        elif turn["role"] == "customer":
            messages.append(HumanMessage(content=turn["content"]))
        # coach/evaluator 可能持有完整画像，属于特权数据域，禁止进入 Sales 上下文。

    # 如果是第一轮且没有历史，添加开场提示
    if not conversation_history:
        messages.append(HumanMessage(content="[开始销售对话]"))

    yield {"type": "sales_thinking", "content": f"🧠 销售({strategy.get('name', '')})正在制定策略..."}

    # ---- 工具调用循环 ----
    final_response = ""
    tool_round = 0
    max_tool_rounds = 5  # 防止无限循环

    while tool_round < max_tool_rounds:
        tool_round += 1
        response = await sales_llm_with_tools.ainvoke(messages)

        # 检查是否有工具调用
        if hasattr(response, "tool_calls") and response.tool_calls:
            messages.append(response)  # 把含 tool_calls 的 AI 消息加入历史

            for tc in response.tool_calls:
                tool_name = tc["name"]
                tool_args = tc["args"]
                tool_call_id = tc["id"]

                yield {
                    "type": "sales_tool_call",
                    "tool": tool_name,
                    "args": str(tool_args),
                }

                # 执行工具
                try:
                    tool_fn = TOOL_EXECUTOR.get(tool_name)
                    if tool_fn:
                        tool_result = tool_fn.invoke(tool_args)
                    else:
                        tool_result = f"工具 {tool_name} 不存在"
                except Exception as e:
                    tool_result = f"工具执行错误: {str(e)}"

                yield {
                    "type": "sales_tool_result",
                    "tool": tool_name,
                    "content": str(tool_result)[:500],
                }

                # 把工具结果加入消息
                messages.append(ToolMessage(
                    content=str(tool_result),
                    tool_call_id=tool_call_id,
                    name=tool_name,
                ))

            # 再次继续下一个 ainvoke（因为还需要 LLM 根据 tool_result 生成最终回答）
            continue
        else:
            # 无工具调用 → 输出最终销售话术
            final_response = response.content if hasattr(response, "content") and response.content else ""
            break

    # ---- 兜底策略: 如果循环结束仍无输出（工具调用超限） ----
    if not final_response:
        if hasattr(response, "content") and response.content:
            final_response = response.content
        else:
            # 放弃调用工具，强制让纯净的 LLM（不带工具）做最后一次总结生成
            yield {"type": "sales_thinking", "content": "🧠 查询次数达上限，正在总结现有信息..."}
            fallback_msg = SystemMessage(content="【系统提示】你已经查询了太多次工具。现在停止查询，请立刻基于上面已经获取的信息，直接给客户一个合理的推荐或回答。")
            messages.append(fallback_msg)
            
            # 使用没有绑定工具的原始 sales_llm 强制输出文本
            fallback_response = await sales_llm.ainvoke(messages)
            final_response = fallback_response.content if fallback_response.content else "很抱歉，我查询了太多资料可能没有找到合适答案。请问我们能先聊聊其他方面吗？"

    # 完整文本先通过身份校验，再允许进入 SSE 和会话持久化链路。
    latest_customer_message = next(
        (
            turn["content"] for turn in reversed(conversation_history)
            if turn.get("role") == "customer" and isinstance(turn.get("content"), str)
        ),
        "",
    )
    validation = await audit_identity_response_async(
        final_response,
        identity_contract,
        AgentRole.SALES,
        latest_counterpart_message=latest_customer_message,
    )
    if not validation.is_valid:
        print(f"⚠️ [销售Agent] 身份校验失败，重新生成: {validation.violations}")
        correction = SystemMessage(content=build_identity_correction_prompt(
            identity_contract, AgentRole.SALES, validation.violations
        ))
        retry_response = await sales_llm.ainvoke(messages + [correction])
        final_response = retry_response.content if retry_response.content else ""
        validation = await audit_identity_response_async(
            final_response,
            identity_contract,
            AgentRole.SALES,
            latest_counterpart_message=latest_customer_message,
        )
        if not validation.is_valid:
            print(f"⛔ [销售Agent] 身份重试仍失败，阻断本轮输出: {validation.violations}")
            raise IdentityContractViolation(
                f"销售回复连续违反身份契约: {'；'.join(validation.violations)}"
            )

    # 逐字符模拟流式推送（实际 LangChain 不支持在 ainvoke 后再 stream，这里做 chunk 分割推送）
    chunk_size = 3
    for i in range(0, len(final_response), chunk_size):
        chunk = final_response[i:i + chunk_size]
        yield {"type": "sales_token", "content": chunk}
        await asyncio.sleep(0.02)  # 模拟打字机延迟

    yield {"type": "sales_message_done", "content": final_response}


# ==========================================
# 阶段指令构建
# ==========================================
def _build_sales_stage_instruction(stage: str, turn_count: int) -> str:
    """根据阶段返回销售的行为指令"""
    if stage == DialogueStage.INTRODUCTION:
        return f"""【阶段任务 - 破冰探寻】
本阶段目标：建立信任 + 了解需求 + 引出产品话题
- 询问客户的家庭保障现状（是否已有保险）
- 了解客户最担心的风险（健康/意外/财务）
- 适当引导客户意识到保障缺口
- 不预设客户的需求、预算、健康情况或既有保障，以客户本轮实际披露的信息为准"""

    elif stage == DialogueStage.OBJECTION:
        return f"""【阶段任务 - 异议处理】
客户已提出质疑，这是关键考验。你的任务：
- 认同客户情绪，不要正面对抗
- 用工具查到的真实数据化解疑虑
- 只针对客户已经明确表达的疑虑进行回应，不引用后台画像中的潜在关注点
- 如果客户关心费率，当场查询给出精确数字
- 回合数已达 {turn_count} 轮，可以开始试探性引导决策"""

    elif stage == DialogueStage.DECISION_SIGN:
        return """【阶段任务 - 临门一脚】
客户已有购买意向，此刻最忌拖泥带水。
- 确认产品/保额/交费期
- 告知下一步投保流程
- 不要再引入新话题"""

    elif stage == DialogueStage.DECISION_PENDING:
        return """【阶段任务 - 促成核保】
客户愿意推进但需要核保流程：
- 确认客户需要提交的材料（体检报告/病历）
- 解释预核保流程和时间
- 强调核保通过后可再做最终决定，降低客户心理压力"""

    elif stage == DialogueStage.DECISION_FOLLOW_UP:
        return """【阶段任务 - 争取跟进】
客户态度不错但想拖延：
- 理解客户的考虑，不要逼迫
- 约定具体的跟进时间（不要留模糊的"改天"）
- 留下关键资料或计算结果供客户回去参考"""

    elif stage == DialogueStage.DECISION_REJECT:
        return """【阶段任务 - 挽回或收场】
客户已拒绝：
- 如有机会：抛出最后一个有力论点
- 如态度坚决：优雅收场，留好印象"""

    return ""
