# 保险检索测试集

`insurance_retrieval_v1.jsonl` 是 InsureSpar 当前 RAG 语料的首版人工标注检索集。每行是一个独立 JSON 对象：

- `id`：稳定用例 ID。
- `query`：销售对练中可能出现的自然语言问题。
- `relevant_doc_ids`：至少一个可接受的目标文档；文档 ID 由 `app/tools/insurance_corpus.py` 统一生成。
- `category`：产品、核保、法律、定义等业务分类。
- `difficulty`：`easy`、`medium` 或 `hard`。
- `critical`：漏召回是否可能造成明显合规或业务风险。

维护规则：

1. 新用例必须由人根据原始保险资料标注，不能让被测嵌入模型生成并自行判分。
2. 改动语料后先运行单元测试，确保所有目标 `doc_id` 仍存在且唯一。
3. 调整检索参数时使用独立开发集；用于最终报告的封存测试集不得参与调参。
4. 后续优先补充真实匿名对练日志、不可回答问题、冲突条款、多文档问题和错别字/口语噪声。

运行评测：

```powershell
cd backend
python scripts/evaluate_retrieval.py --provider local
```

Qwen 对照实验需要仅在当前终端设置 `DASHSCOPE_API_KEY`，不要把密钥写入测试集、报告或版本库。
