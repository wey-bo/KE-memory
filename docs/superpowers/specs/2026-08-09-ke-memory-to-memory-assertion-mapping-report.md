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

这是本次对照最重要的发现。`Modality` 的 8 个取值不属于同一范畴，因此整体映射必然失败。

**但拆分方式比初稿设想的更复杂。** 已实测
`src/ke_memory_demo/online/admission.py:29-36`：8 个取值**全部**被映射到 `MemoryKind`，
后者进一步驱动 Admission 阈值（`PREFERENCE: 0.9`、`TASK: 0.95`）。所以 `modality` 同时是

- 命题语义的一部分，以及
- **Admission 的分类输入**。

规范明确 Admission 不属于本 Profile，因此这个字段的迁移必须先把两种用途分开——不能整体搬进
内容 Operator，否则 Admission 策略会混入 KE 语义。

| 取值 | 范畴 | 去向 | `MemoryKind` |
| --- | --- | --- | --- |
| `fact` | 无标记 | KE 本身，不加修饰 | `FACT` |
| `belief` | 命题态度 | `believes(Person, Assertion)`，fixture 已有 | `FACT` |
| `hypothesis` | 认识模态 | `possible(Assertion)`，fixture 已有 | `OTHER` |
| `question` | 言语行为 | `CandidateMetadata.speech_act = question` | `OTHER` |
| `instruction` | 言语行为 | `speech_act = command` | `CONSTRAINT` |
| `preference` | **待分型** | 见评审包 v2 的 R2 | `PREFERENCE` |
| `goal` | **待分型** | 见评审包 v2 的 R2 | `TASK` |
| `plan` | **待分型** | 见评审包 v2 的 R2 | `TASK` |

后三项**不给建议签名**。初稿曾建议 `prefers(Person, Assertion)` 等三个 Operator，该方案已被
否决：golden 数据（`tests/golden/test_memory_pipeline.py:274-281`）中内容 Operator **已经是**
`prefers(user, tea)`，包装成 `prefers(user, Assertion::"prefers(user,tea)")` 会重复并改写原
语义。参数类型也未经分析——「更喜欢 A 而非 B」是三元关系，主体不限于 Person。详见评审包 v2。

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

但新增 Operator 有自己的硬要求（`ontology-standard.md:413-461`）：

- 每条 Lexicalization 必须带至少一项 `source_attestations`；
- `source_kind` 是封闭枚举：`wordnet | propbank | schema_org | human | domain_corpus`；
- `wordnet` 必须带 `wn30:` 前缀 `sense_id`，`propbank` 必须带 `pb3.4:` 前缀 `roleset_id`，
  其余三类禁止这两个字段；
- 无版本前缀的 `create.v.01` 必须拒绝。

**关键限制**（`ontology-standard.md:461` 原文）：

> SourceAttestation 证明词面来源，不自动证明 owner 语义与外部资源完全等价。

因此 `source_kind=human` **只证明词面来源，不构成 Operator 语义的授权**。Operator 语义必须
来自版本化、且进入 `source_manifest` 的 Core Ontology 决策记录；`provenance_refs` 必须指向
构建/审计系统中的既有记录，不能指向评审文档。

**实测结论**：`wn30:negate.v.01` 的 WordNet 释义是 **"be in contradiction with"**，即两条断言
之间的矛盾关系，不是一元逻辑否定。因此禁止用它为 `negated` 作 attestation。

**Snapshot 缺 Operator 时的诊断 code**：报 `missing_operator`（Ontology gap，见
`nl2ke-integration-requirements.md:389` 之后的枚举），**不是** `unsupported_construct`。
后者是 Capability Gap，规范禁止二者互相报告。

## 新增 Operator 的连带影响

新增任何 Operator 都会改变 Operator 分片内容、记录数、Snapshot hash 与所有 hash echo 示例。
必须同步更新：

- `fixtures/ontology-snapshot-example/operators/core.json` 及 `snapshot.manifest.json` 的
  hash 与记录数；
- `schema/examples.json`、`ontology-profile-and-manifest-vectors.json` 中含 snapshot ref 的向量；
- `schema/canonical-text-reference-vectors.json`（若涉及新 Operator 的 Canonical Text）；
- 两处统一示例表；
- 相关集成测试。

`tools/validate_specifications.py` 的基线计数会随之变化，变化必须先解释再接受。因此
「1760 个测试一个不改」只适用于旧 `domain` 侧测试，不适用于 `spec/` 子树。

## 结论

- **11 个字段的去向明确，不需要新增本体**，其中 `lifecycle`、`contradicts`、`supersedes`、
  `revision`、`level` 是"不该迁移"而非"没有去向"——它们本就属于记忆系统。
- **1 项需要新增 Operator**：`negated`，但其语义授权必须来自版本化的 Core Ontology 决策记录，
  而不是 `human` attestation（见治理要求）。
- **4 项经评审后：R1、R3 带修订确认；R2、R4 退回补充事实。** 裁决与退回理由见
  `2026-08-09-memory-assertion-v1-migration-review-packet-v2.md`。

R2 与 R4 的补充事实到位前，不得开始第二步（边界转换层）。

## 影响面数字的读法

上表的「文件 / 引用」是**代码行计数**，不是数据量。例如 `polarity` 的 140 是含该标识符的
代码行数，不等于 140 条 `negative` 数据。真实数据分布尚未测量，且仓库无持久化 KE JSON，
因此只能从抽取产物或运行时统计得到。任何按这些数字估算迁移工作量的推断都不成立。

## 明确不做

- 不改任何代码，不新增任何 Operator 记录。
- 不把本报告的映射写成已验证：它是文档对照，尚无一条经过 round-trip 测试。
- 不为 `goal`/`plan`/`preference` 提出签名——分型完成前提签名就是让旧 schema 决定本体身份。
- 不给出 R4 的通用展开规则：`assertion_ref` 只承载完整 Proposition，值函数复合需要分类处理。
