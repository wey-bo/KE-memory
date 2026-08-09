# ke-memory/v1 到 memory-assertion/v1 的语义对照

日期：2026-08-09
状态：第一步产物——只做对照，不改代码

## 这份报告回答什么

`personal-org` 的运行时用 `src/ke_memory_demo/domain/memory.py:171` 的 `ke-memory/v1`，
其中 `modality`、`polarity`、`lifecycle` 是 `memory-assertion/v1` 的禁止键。本报告逐字段、
逐取值确定去向，并把没有确定去向的项单独列出。

它**不**给出迁移步骤。迁移能否开始取决于本报告的结论，反之不成立。

## 迁移面（实测）

`personal-org` 分支上引用相关字段的规模：

| 字段 | 文件 | 引用 |
| --- | --- | --- |
| `lifecycle` | 89 | 399 |
| `speaker` | 63 | 233 |
| `gloss` | 43 | 162 |
| `modality` | 42 | 299 |
| `polarity` | 34 | 140 |
| `ontology_bindings` | 22 | 70 |

引用 `KnowledgeEquation` 的文件 43 个。

**没有持久化数据需要迁移**：全仓搜索 `"schema_version": "ke-memory/v1"` 的 JSON 得 0 命中。
因此这是纯代码迁移，不涉及数据回填或双读兼容。

## 核心结论：字段没有被删除，而是升格为断言

规范
`2026-08-08-memory-assertion-v1-contract-migration-design.md:305`
给出的机制是：

```text
negated(Assertion::candidate::"created-by-1")=Boolean::true
possible(Assertion::candidate::"created-by-1")=Boolean::true
event_time(Assertion::candidate::"created-by-1",Date::"2026-08-09")=Boolean::true
```

否定、模态、命题时间由**接受 `assertion_ref` 的 Operator** 表达。这也是结构校验层里
`AssertionRef` 存在的理由之一——它既承载命题组合，也承载模态与否定。

实质变化：一个修饰从字段变成一等 KE，因此它自身可以携带证据、置信度和来源。字段做不到这一点。
代价是每个否定或模态从 1 条 KE 变成 2 条，且需要相应 Operator 存在于 Snapshot 中。

## `modality` 混合了两种不同的东西

这是本次对照最重要的发现。`Modality` 的 8 个取值不属于同一范畴，因此整体映射必然失败，
拆开后各有去向：

| 取值 | 范畴 | 去向 |
| --- | --- | --- |
| `fact` | 无标记 | KE 本身，不加修饰 |
| `belief` | 命题态度 | `believes(Person, Assertion)`，fixture 已有 `operator_0e0ca38b526f` |
| `hypothesis` | 认识模态 | `possible(Assertion)`，fixture 已有 `operator_7e2261ee9c51` |
| `question` | 言语行为 | `CandidateMetadata.speech_act = question` |
| `instruction` | 言语行为 | `speech_act = command` |
| `preference` | 言语行为/态度 | `speech_act = suggestion`，或态度 Operator——**见待评审 R2** |
| `goal` | 意图 | 无直接对应——**见待评审 R2** |
| `plan` | 意图 | 无直接对应——**见待评审 R2** |

前五项去向明确，无需新增本体。后三项需要判断。

## 逐字段对照

| `ke-memory/v1` 字段 | 去向 | 是否需要新增 |
| --- | --- | --- |
| `lhs` / `rhs` | `KnowledgeEquation.lhs/rhs`，但 `Expression` 递归须改为扁平 `LeafTerm` + `assertion_ref` | 否 |
| `id` | `CandidateAssertion.candidate_id`（候选期）；canonical id 由记忆系统分配 | 否 |
| `revision` | 记忆系统职责，不属本 Profile | 否 |
| `schema_version` | `semantic_contract_version = "memory-assertion/v1"` | 否 |
| `level` | 记忆系统的分层，不属本 Profile | 否 |
| `gloss` | **无对应**——Display Text 不参与权威存储。见待评审 R3 | — |
| `modality` | 见上表，按取值拆分 | 部分 |
| `polarity` | `positive` = 无标记；`negative` = `negated(Assertion)`；`unknown` = 省略该 KE | **是：`negated`** |
| `lifecycle` | **不迁移**。规范明确 Admission、lifecycle、conflict 不属本 Profile，属记忆系统 | 否 |
| `speaker` | `CandidateMetadata.epistemic_mode`（`self_reported`/`other_reported`/`agent_generated`/`tool_observed`/`quoted`） | 否 |
| `temporal` | `event_time(Assertion, Date)`，fixture 已有 `operator_61921190c148` | 否 |
| `ontology_bindings` | 消失：新合同的 term 直接携带 hash id，绑定不再是独立记录 | 否 |
| `evidence_refs` | `CandidateAssertion.source_evidence_ids` + 顶层 `source_evidence_spans` | 否 |
| `derived_from` | `support_basis = context_resolved` + `context_support_refs` | 否 |
| `contradicts` / `supersedes` | 记忆系统职责，同 `lifecycle` | 否 |
| `confidence` | `CandidateMetadata.semantic_assessment.score`，注意其 `score_semantics` 为 `uncalibrated_relative` | 否 |
| `produced_in_run_id` / `produced_in_stage` | `execution` 与 `compiler` 块 | 否 |

## 治理要求（已核实）

新增 Operator **不受** crosswalk 第三方评审规则约束：那条规则针对 `foundation_v1` 的
`core_role_id` 映射，而 `core_roles`/`core_role_id` 在本合同中是 `ForbiddenLegacySupplyKey`，
整个 crosswalk 机制不适用。

但新增 Operator 有自己的硬要求（`ontology-standard.md:413-441`）：

- 每条 Lexicalization 必须带至少一项 `source_attestations`；
- `source_kind` 是封闭枚举：`wordnet | propbank | schema_org | human | domain_corpus`；
- `wordnet` 必须带 `wn30:` 前缀 `sense_id`，`propbank` 必须带 `pb3.4:` 前缀 `roleset_id`，
  其余三类禁止这两个字段；
- 无版本前缀的 `create.v.01` 必须拒绝。

因此 `negated` 的 attestation 只能是 `wordnet`（需真实 sense）或 `human`（承认是本项目决定）。

**实测结论**：`wn30:negate.v.01` 的 WordNet 释义是 **"be in contradiction with"**，即矛盾关系，
不是逻辑否定。用它为 `negated` 作 attestation 是误引来源。因此 `negated` 只能用
`source_kind=human`，这使它成为一项需要你签署的项目决定，而非可从来源推导的事实。

## 结论

- **11 个字段的去向明确，不需要新增本体**，其中 `lifecycle`、`contradicts`、`supersedes`、
  `revision`、`level` 是"不该迁移"而非"没有去向"——它们本就属于记忆系统。
- **1 项需要新增 Operator**：`negated`，且只能用 `human` attestation。
- **4 项需要你判断**，已单独整理为评审包
  `2026-08-09-memory-assertion-v1-migration-review-packet.md`。

在评审包的 4 项裁决完成前，不得开始第二步（边界转换层）：其中 R1 决定
`polarity=negative` 能否表达，而它出现在 140 处引用中。

## 明确不做

- 不改任何代码，不新增任何 Operator 记录。
- 不把本报告的映射写成已验证：它是文档对照，尚无一条经过 round-trip 测试。
- 不推断 `goal`/`plan`/`preference` 的去向——列为待裁决而非猜测。
