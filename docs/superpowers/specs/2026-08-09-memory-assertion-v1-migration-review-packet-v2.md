# 迁移评审包 v2：裁决结果与退回项

日期：2026-08-09
状态：R1/R3 已裁决（A+），R2/R4 退回补充事实
关联：`2026-08-09-ke-memory-to-memory-assertion-mapping-report.md`
取代：本文件 v1 的四项建议。v1 的 R2 方案与 R4 方案含语义错误，见下方各项「v1 错在哪」。

## 裁决摘要

| 项 | 裁决 | 状态 |
| --- | --- | --- |
| R1 `negated` | A+（带修订确认） | 可执行，须按修订项办 |
| R2 三种 modality | A′ 分型方案，**不批准 v1 的 A** | 退回：需补主体/对象类型与原文分型 |
| R3 `gloss` | A+（带修订确认） | 可执行，须按修订项办 |
| R4 递归扁平化 | C′：先分类测量再制定转换矩阵 | 退回：v1 的通用展开规则语义错误 |

---

## R1：`negated` —— A+，四项修订

**已确认**：`negated` 新增为 KE Core Operator。建议签名：

```text
negated(Proposition) -> Boolean
proposition_operation = modifier
```

**修订 1：`source_kind=human` 的效力被我高估了。**

`ontology-standard.md:461` 原文：

> 只有 lemma 而没有精确 sense/roleset 的记录不得声称来自 WordNet 或 PropBank，必须改用
> `human` 或 `domain_corpus`。**SourceAttestation 证明词面来源，不自动证明 owner 语义与外部
> 资源完全等价。**

所以 `human` 只证明「negated」这个词面的来源，**不构成 Operator 语义的授权**。v1 把它当作
「本项目决定」的凭据，是误读。

Operator 语义必须来自版本化、且进入 `source_manifest` 的 Core Ontology 决策记录。
`provenance_refs` 不能指向本评审包这类桌面文档——它必须是构建/审计系统中的既有记录。

**修订 2：禁止 `wn30:negate.v.01`。**

实测该 sense 的 WordNet 释义为 "be in contradiction with"，即两条断言之间的矛盾关系，
不是一元逻辑否定。v1 已得出同一结论，此处保留为禁止项。

**修订 3：Snapshot 缺 `negated` 时报 `missing_operator`，不是 `unsupported_construct`。**

已核实 `nl2ke-integration-requirements.md:389` 之后的 Ontology gaps 枚举含
`missing_operator`。v1 的选项 C 用错了 code：Snapshot 缺 Operator 是 Ontology Gap，
不是 Capability Gap。规范另有明确规定，二者不得互相报告。

**修订 4：「140 引用」不是数据量。**

那是含 `polarity` 的**代码行数**，不等于 140 条 negative 数据。v1 用它衡量影响面，属于把
代码引用当数据规模。真实的 negative 数据量尚未测量。

---

## R2：三种 modality —— 退回

**不批准 v1 的 A 方案。** v1 建议新增 `prefers(Person, Assertion)`、`intends(Person, Assertion)`、
`plans(Person, Assertion)`，该方案有三类错误。

**v1 错在哪（一）：把 Admission 输入当成内容语义。**

已实测 `src/ke_memory_demo/online/admission.py:29-36` 是完整的 8 值映射：

```python
Modality.PREFERENCE: MemoryKind.PREFERENCE
Modality.GOAL:       MemoryKind.TASK
Modality.PLAN:       MemoryKind.TASK
Modality.INSTRUCTION: MemoryKind.CONSTRAINT
Modality.FACT:       MemoryKind.FACT
Modality.BELIEF:     MemoryKind.FACT
Modality.HYPOTHESIS: MemoryKind.OTHER
Modality.QUESTION:   MemoryKind.OTHER
```

`MemoryKind` 进一步驱动 Admission 阈值（`PREFERENCE: 0.9`、`TASK: 0.95`）。所以 `modality`
不是纯命题语义，它是 Admission 的分类输入。把它整体搬进内容 Operator，会把 Admission 策略
混入 KE 语义——而规范明确 Admission 不属于本 Profile。

**v1 错在哪（二）：内容 Operator 已经存在，包装会重复语义。**

已实测 `tests/golden/test_memory_pipeline.py:274-281` 的 golden KE 是：

```text
lhs = prefers(user, tea)     modality = PREFERENCE
```

内容 Operator **已经是** `prefers`。v1 方案会产出
`prefers(user, Assertion::"prefers(user,tea)=Boolean::true")`——同一语义包了两层，且外层改写了
内层含义。同理 golden 里已有 `has task`。

**v1 错在哪（三）：参数类型未经分析。**

- 「喜欢某实体」不是命题态度，宾语是 Individual 而非 Proposition；
- 「更喜欢 A 而非 B」是三元比较关系，二元签名表达不了；
- `plan` 可能是 Plan Individual，而非对命题的态度；
- 主体不限于 Person——组织、团队、Agent 都可以有目标，`Person` 过窄；
- `wn30:intend.v.01`（"have in mind as a purpose"）与 `plan.v.01` 高度重叠，仅因旧枚举有两个
  值就建立两个 Canonical Operator，是让旧 schema 决定本体身份。

WordNet 只能证明英文词面来源，不能决定 Operator 的参数与身份。v1 反了这个方向。

**退回要求**：先回看原文、旧 KE 的 predicate、主体类型与对象类型，据此分型，再定 Operator。
分型前不提签名。

---

## R3：`gloss` —— A+，一项修订

**已确认**：`gloss` 不进入 KE、`CandidateMetadata`、Lexicalization 或 Snapshot。该边界由
`normative-vocabulary.md:184` 支持。

**修订：不得物理删除。** v1 说「留在 personal-org 侧」但未说明它仍在承担什么。实际用途至少有四处：

- embedding 输入；
- fallback 检索文本；
- lifecycle matcher（`extraction/lifecycle.py` 的 `old_gloss`/`new_gloss`）；
- 报告展示。

因此应保留为**记忆系统侧可重建的非权威展示/检索投影**，并关联原 candidate 与 Evidence。
明确禁止：参与 KE 语义身份、参与 Admission、参与反向解析。

---

## R4：递归扁平化 —— C′，先分类测量

**v1 的 A 方案语义错误。** v1 建议后序遍历展开、内层先得 candidate id、外层用 `assertion_ref`
指向。这在通用情形下不成立。

`ke-semantic-syntax-standard.md:20` 规定 `assertion_ref` 引用的是一条完整 Proposition，
不是任意子表达式的计算结果。因此

```text
f(g(x)) = y
```

不能通用改写为

```text
g(x) = ?
f(AssertionRef(g(x)=?)) = y
```

这会把 `g(x)` 的值改成 Proposition，类型和语义都变了。

**实测印证**：`tests/integration/test_sqlite_rebuild.py:151` 的实际嵌套是

```text
believes(likes(user)) = tea
```

按 v1 方案需要先写出 `likes(user) = ?`，但原式中 `likes(user)` 没有独立 rhs——它的值就是
`tea`。`?` 无从确定，方案在此直接失效。

**C′ 要统计的维度**（不只是深度）：

1. 嵌套所在位置（哪个参数槽）；
2. 外层参数是否要求 `Proposition`；
3. 内层 Operator 的 `output_concept`；
4. 是否存在可恢复的合法 `rhs`；
5. 分类计数：完整命题嵌套 / 值函数复合 / 可方向化 / 不可转换。

**转换规则（据分类而非统一）**：

- **完整命题嵌套**：可提升为 non-root candidate 并用 `assertion_ref` 引用；
- **值函数复合**：需要已知的兼容 `LeafTerm` 才能转换；
- **其余**：必须 fail-closed，不得猜测 `rhs`。

**Candidate ID**：基于**原 KE ID 加 AST 路径**，不能只用内容 hash——纯内容 hash 会把携带
不同 Evidence 的相同子式合并。

**已测得的部分事实**：`OperatorApplication(` 在 28 处被构造，其中生产代码 2 处
（`extraction/turn_ke.py:598`、`retrieval/query.py:626`），两者都经由递归的
`_build_expression`/`_bind_expression`，所以嵌套深度取决于模型输出而非固定上限。完整的五维
分类统计尚未进行。

---

## 全局修订：新增 Operator 会改变 Snapshot hash

v1 的一处遗漏，影响前述所有裁决项。

新增任何 Operator 都会改变 Operator 分片内容、记录数、Snapshot hash 以及所有 hash echo 示例。
因此 v1 那句「1760 个测试一个不改」最多只适用于旧 `domain` 侧测试。必须同步更新：

- `spec/memory-assertion-v1/fixtures/ontology-snapshot-example/operators/core.json` 及其
  `snapshot.manifest.json` 的 hash 与记录数；
- `schema/examples.json` 与 `ontology-profile-and-manifest-vectors.json` 中含 snapshot ref
  的向量；
- `schema/canonical-text-reference-vectors.json`（若涉及新 Operator 的 Canonical Text）；
- 统一示例表（`README.md` 与 `docs/.../README.md` 各一份）；
- 相关集成测试。

`tools/validate_specifications.py` 的基线计数（当前 `operators`、`fixture_artifacts=3`、
`required_files=23` 等）会随之变化，变化必须先解释再接受。

---

## 下一步

R1 可执行，但须先建立版本化的 Core Ontology 决策记录并纳入 `source_manifest`——在此之前
不要写入 fixture。R3 可执行。

R2、R4 需要补充事实后重新提交：

- **R2**：原文分型 + 旧 KE predicate + 主体/对象类型统计；
- **R4**：五维分类统计。

两项都不改代码即可完成。要我先做哪一项？
