# 文件：app/core/config.py
"""集中配置管理 — 所有环境变量、模型参数、画像加载均在此处"""
import os
import json
from pathlib import Path
from dotenv import load_dotenv

# ==========================================
# 加载 .env 文件
# ==========================================
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_env_path)

# ==========================================
# 路径常量
# ==========================================
# 项目根目录（FastAPIProject/）
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"

# ==========================================
# 数据库配置
# ==========================================
DATABASE_URL = os.getenv("DATABASE_URL", "mysql+pymysql://root@localhost:3306/insurespar")

# ==========================================
# LLM 配置
# ==========================================
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
LLM_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")

# Agent 身份属于稳定业务配置，不与销售策略或客户行为画像混用。
SALES_AGENT_ID = os.getenv("SALES_AGENT_ID", "sales_agent_default")
SALES_AGENT_NAME = os.getenv("SALES_AGENT_NAME", "").strip()
SALES_AGENT_COMPANY = os.getenv("SALES_AGENT_COMPANY", "泰康人寿")
SALES_AGENT_TITLE = os.getenv("SALES_AGENT_TITLE", "保险销售顾问")

if not LLM_API_KEY:
    print("⚠️ 未检测到 DEEPSEEK_API_KEY，请在 backend/.env 中配置")

# ==========================================
# 业务逻辑配置
# ==========================================
MIN_TURNS_BEFORE_DECISION = 5  # 前5轮强制拦截决策
DECISION_STRIKES_REQUIRED = 2  # 连续判定为决策状态 N 次后，才真正结束对话

# ==========================================
# 加载客户画像配置
# ==========================================
def load_personas() -> dict:
    """从 data/personas.json 加载所有客户画像，返回 {persona_id: persona_dict}"""
    personas_path = DATA_DIR / "personas.json"
    if not personas_path.exists():
        print(f"⚠️ 画像配置文件不存在: {personas_path}")
        return {}
    with open(personas_path, "r", encoding="utf-8") as f:
        personas_list = json.load(f)
    return {p["persona_id"]: p for p in personas_list}


SALES_LEAD_FIELDS = frozenset({
    "persona_id",
    "customer_name",
    "preferred_salutation",
    "age",
    "gender",
    "occupation",
    "lead_source",
    "contact_context",
})


def load_sales_leads(personas: dict) -> dict:
    """加载 Sales 专用基础线索，并确保它与完整画像严格隔离且一一对应。"""
    path = DATA_DIR / "sales_leads.json"
    if not path.exists():
        raise RuntimeError(f"销售线索配置文件不存在: {path}")

    with open(path, "r", encoding="utf-8") as f:
        leads_list = json.load(f)

    if not isinstance(leads_list, list):
        raise RuntimeError("销售线索配置必须是 JSON 数组")

    leads = {}
    for index, lead in enumerate(leads_list):
        if not isinstance(lead, dict):
            raise RuntimeError(f"第 {index + 1} 条销售线索不是对象")

        fields = set(lead)
        if fields != SALES_LEAD_FIELDS:
            missing = sorted(SALES_LEAD_FIELDS - fields)
            extra = sorted(fields - SALES_LEAD_FIELDS)
            raise RuntimeError(
                f"销售线索字段不符合最小披露契约: persona_id={lead.get('persona_id', index)}; "
                f"缺少={missing}; 越界={extra}"
            )

        persona_id = str(lead["persona_id"]).strip()
        if not persona_id or persona_id in leads:
            raise RuntimeError(f"销售线索 persona_id 缺失或重复: {persona_id!r}")
        if not isinstance(lead["age"], int) or lead["age"] < 0:
            raise RuntimeError(f"销售线索年龄无效: persona_id={persona_id}")
        for field in SALES_LEAD_FIELDS - {"age"}:
            if not isinstance(lead[field], str) or not lead[field].strip():
                raise RuntimeError(f"销售线索字段 {field} 无效: persona_id={persona_id}")
        leads[persona_id] = lead

    persona_ids = set(personas)
    lead_ids = set(leads)
    if persona_ids != lead_ids:
        raise RuntimeError(
            "销售线索与客户画像未一一对应: "
            f"缺少线索={sorted(persona_ids - lead_ids)}; "
            f"孤立线索={sorted(lead_ids - persona_ids)}"
        )

    for persona_id, lead in leads.items():
        if lead["customer_name"] != personas[persona_id].get("name"):
            raise RuntimeError(f"销售线索与客户画像姓名不一致: persona_id={persona_id}")

    return leads


def load_sales_strategies() -> dict:
    """从 data/sales_strategies.json 加载所有销售策略，返回 {strategy_id: strategy_dict}"""
    path = DATA_DIR / "sales_strategies.json"
    if not path.exists():
        print(f"⚠️ 销售策略配置文件不存在: {path}")
        return {}
    with open(path, "r", encoding="utf-8") as f:
        strategies_list = json.load(f)
    return {s["strategy_id"]: s for s in strategies_list}


# 启动时一次性加载到内存
PERSONAS = load_personas()
SALES_LEADS = load_sales_leads(PERSONAS)
SALES_STRATEGIES = load_sales_strategies()

if PERSONAS:
    print(f"✅ 客户画像加载完成！共 {len(PERSONAS)} 个画像: {', '.join(PERSONAS.keys())}")
else:
    print("⚠️ 未加载到任何客户画像配置")

print(f"✅ Sales 基础线索加载完成！共 {len(SALES_LEADS)} 条，与完整画像隔离")

if SALES_STRATEGIES:
    print(f"✅ 销售策略加载完成！共 {len(SALES_STRATEGIES)} 种策略: {', '.join(SALES_STRATEGIES.keys())}")
else:
    print("⚠️ 未加载到任何销售策略配置")
