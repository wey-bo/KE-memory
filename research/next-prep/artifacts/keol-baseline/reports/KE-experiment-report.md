# KEOL KE-test 抽取实验报告

## 结论

自定义 KE v0.1/v0.2 已作废。本轮从 `data/gold-candidates/KE-test.json` 原文重新开始，按最新 KEOL 流程完成：

```text
turn -> KnowledgeGraph nodes/edges -> OntologyBuilder
-> NormalizationPlan -> Agent projection -> strict validation
```

这是 KEOL baseline，用于评估 KEOL 的实际抽取和表示能力，不是人工确认的最终 gold。

## 统计

| 指标 | 数量 |
| --- | ---: |
| 候选对话 | 10 |
| user + agent turn | 43 |
| speaker slot | 86 |
| 模型 graph node | 405 |
| 模型 graph edge | 371 |
| Concept | 164 |
| Individual | 229 |
| Operator | 161 |
| Assertion | 309 |
| Evidence | 774 |
| Assertion -> turn 链接 | 323 |
| 至少关联一条 Assertion 的 turn | 42 / 43 |
| normalization 批次 | 5 |
| Concept 更新 | 164 |
| Operator 更新 | 161 |
| 应用具体 operator schema | 113 |
| 未解析 operator schema | 0 |
| validation error | 0 |
| validation warning | 0 |

371 条 edge 得到 309 条 Assertion，是 KEOL 按 lhs/rhs 哈希合并相同方程并聚合 Evidence，不是漏写。

唯一未关联 Assertion 的输入单元是 `TASKMASTER2-CAND-001` 第 6 轮（`taskmaster2-cand-001__turn-006`）；它仍保留原始 turn 文本和模型图输入坐标，需在人工 gold 审核时判断是应当补抽，还是没有值得持久化的知识。

## 表达示例

```text
works_at(Individual("用户"))=Individual("律师事务所")
has_duration(Individual("出国休假"))=Individual("一周")
requires(Individual("androidx.activity 1.8.0"))=Individual("compileSdk 34")
has_deadline(Individual("遗嘱"))=Individual("2024-05-15")
```

这些是原生 KEOL `Assertion/Term` 的人工可读投影，事实源仍是 `artifacts/keol-baseline/native-output/KE-test/onto/assertions.json`。

## 模型与程序分工

两个抽取 subagent 处理 21/22 个 turn，合计 43/43；主线程独立验证 unit 覆盖、node 唯一性和 edge 闭合。五个 normalization payload 由三个 subagent 处理；每批完整覆盖 allowed IDs，不允许新增 ID。重载或跨域关系标为 `broad`、`meta`、`noisy` 或 `needs_review`，不伪造窄 schema。

## 已知限制

1. KEOL 没有 conversation-aware reader；本轮适配层只解决 turn 边界。
2. rawdata 只有 nodes/edges，builder 当前只自动生成单层 OperatorApplication，没有验证自动生成嵌套 KE。
3. KEOL `Term` 没有字面量类型；日期、时长、数值通常是带 Concept 归属的 Individual。
4. Evidence 可回到 turn chunk 和模型关系描述，但不是逐字符 source span。
5. user/agent 顺序在 turn metadata；核心 Assertion 没有认识论状态字段。
6. normalization 不能新建对象、拆分复合 operator 或自动合并同名 ID。
7. 164 Concept、161 Operator 对 43 turn 仍偏多，后续人工 gold 需审查粒度、方向、重复、事实重要性和来源。

## 下一步

人工筛查 `artifacts/keol-baseline/views/KE.txt` 与 `KE-extraction.json`，标注应保留事实、operator 粒度/方向、嵌套需求、日期/时长规范值及 user/agent/tool 的认识论状态，再形成正式 expected KE。
