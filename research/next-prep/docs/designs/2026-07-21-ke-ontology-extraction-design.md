# KEOL KE-test 抽取设计

状态：2026-07-21 执行。此前自定义 KE v0.1/v0.2 设计已被取代。

## 目标

观察最新 KEOL 对 `data/gold-candidates/KE-test.json` 的真实抽取、本体构建和 Assertion 表示，不再由工作区自行发明 operator runtime 或表面语法。模型遵循 KEOL Pydantic 契约；机械工作交给程序。

## 数据流

```text
data/gold-candidates/KE-test.json
  -> build_turn_units
  -> 43 个 turn 文档 + JSON Pointer
  -> subagent KnowledgeGraph(nodes, edges)
  -> graph contract validation
  -> KEOL rawdata chunk JSON
  -> KEOL OntologyBuilder
  -> KEOL NormalizationPlan
  -> KEOL Agent projection/store
  -> KEOL strict validator
```

一轮是一次 user 输入及对应 Agent 输出。每个 turn 单独成为一个 KEOL chunk，避免 JSON reader 固定长度切分破坏轮次。

## 模型阶段

图抽取严格使用 KEOL `Node/Edge/KnowledgeGraph` schema。模型不直接写 Assertion，也不读取旧 v0.2 KE。输入优先保留用户事实、约束、偏好、时间和数量；Agent 只抽明确具体信息或任务状态，不抽礼貌语和泛化填充。

归一阶段使用 KEOL `NormalizationPlan`：不创建新 ID；Concept 表示类；Operator 表示 property/predicate/action/reasoning operator；只有 `specific` 绑定紧类型 input/output Concept；broad/meta/noisy/needs_review 不绑定误导性 schema；seeded provenance 不丢失。

## 确定性护栏

- 43 个 unit 精确覆盖，不缺失不重复；
- node id 在 unit 内唯一；
- edge source/target 引用同一 unit node；
- normalization plan ID 与对应 payload 完全一致；
- 原生 `Assertion -> Evidence -> chunk -> turn -> KE-test JSON Pointer` 闭合；
- 最终使用 KEOL strict validator。

## 输出与边界

原生事实源在 `artifacts/keol-baseline/native-output/KE-test/onto/`。`artifacts/keol-baseline/views/` 中的三个文件只是视图：`KE-ontology.json` 聚合 ontology/agent/action；`KE-extraction.json` 连接 turn、模型图和 Assertion；`KE.txt` 显示人工可读 Assertion。

KEOL schema 允许递归 Term，但现有 edge -> builder 路径只自动生成单层 OperatorApplication；Evidence 是 chunk 级而非字符 span 级；认识论状态不在核心 Assertion 中。这些缺口保留到人工 gold 和后续 KEOL go/no-go，不用 embedding 或自定义 runtime 掩盖。
