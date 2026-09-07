"""Canonical loader for the insurance RAG corpus and its stable document IDs."""

from __future__ import annotations

import json
from pathlib import Path


SOURCE_FILENAMES = (
    "insurance_rules.json",
    "insurance_law_structured.json",
    "insurance_definitions_structured.json",
)


def source_paths(data_dir: Path) -> list[Path]:
    return [data_dir / filename for filename in SOURCE_FILENAMES]


def load_insurance_corpus(data_dir: Path) -> list[dict]:
    """Load the three knowledge sources into one corpus with stable ``doc_id`` values."""
    documents: list[dict] = []

    with (data_dir / SOURCE_FILENAMES[0]).open(encoding="utf-8") as handle:
        rules = json.load(handle)
    for rule in rules:
        rule_id = rule.get("rule_id", "unknown")
        documents.append({
            "doc_id": f"rule:{rule_id}",
            "source_type": "internal_rule",
            "title": f"规则ID: {rule_id}",
            "content": (
                f"▶️ 核心事实：{rule.get('content', '')}\n"
                f"▶️ 内部防坑指南：{rule.get('evaluator_criteria', '')}"
            ),
            "search_text": (
                f"{rule.get('category', '')} {' '.join(rule.get('tags', []))} "
                f"{rule.get('content', '')}"
            ).strip(),
        })

    with (data_dir / SOURCE_FILENAMES[1]).open(encoding="utf-8") as handle:
        laws = json.load(handle)
    for law in laws:
        article = law.get("article_number", "unknown")
        documents.append({
            "doc_id": f"law:{article}",
            "source_type": "insurance_law",
            "title": f"《保险法》{law.get('chapter', '')} {article}",
            "content": law.get("content", ""),
            "search_text": law.get("text_for_embedding", ""),
        })

    with (data_dir / SOURCE_FILENAMES[2]).open(encoding="utf-8") as handle:
        definitions = json.load(handle)
    for definition in definitions:
        source_type = definition.get("source_type", "definition")
        entity_name = definition.get("entity_name", "unknown")
        core_suffix = " (行业统一规范核心28种重疾)" if definition.get("is_standard_28") else ""
        prefix = "重大疾病" if source_type == "disease_definition" else "术语定义"
        documents.append({
            "doc_id": f"definition:{source_type}:{entity_name}",
            "source_type": source_type,
            "title": f"[{prefix}] {entity_name}{core_suffix}",
            "content": definition.get("content", ""),
            "search_text": definition.get("text_for_embedding", ""),
        })

    return documents
