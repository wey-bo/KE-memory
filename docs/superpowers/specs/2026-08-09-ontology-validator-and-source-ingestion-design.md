# Ontology 校验器与三源摄取基础设施

日期：2026-08-09
状态：待评审

## 交付边界

本阶段交付 memory-assertion/v1 Ontology Profile 的**校验器**与**三源摄取基础**。

它**不构造 Foundation Ontology v1**。后续仍必须完成跨源对齐、双通道晋升、Canonical
Concept/Operator 生成与 Snapshot 发布，才能称为「v1 ontology 已构建」。本文交付的是那件工作
所需的校验与摄取地基，不是那件工作本身。

## 问题

规范 `ontology-standard.md` 第 7 节列出 semantic validator 必须执行的 12 项检查。现状不是零
实现，而是**实现被绑死在一份 fixture 上**。

`spec/memory-assertion-v1/tools/validate_specifications.py` 已含其中约 8 项的逻辑
（`_validate_concept_dag`、`disjoint_with` 的自边/对称/祖先冲突、Symbol 唯一、
`currency_minor_units` 排序）。但全部经由 `_reference_snapshot_records()`，而该函数直接读
`FIXTURE / "snapshot.manifest.json"`。因此它只能校验随包交付的那一份 Snapshot（13 Concept /
4 Operator），无法接受任意 Snapshot。加上该文件自我声明为 conformance harness、位于 `spec/`
子树、以 `tools.*` 导入自身、被 `testpaths` 特意隔离在主仓之外——它不是可被运行时调用的库。

第 7 节的 12 项中，harness 里找不到实现的有四项：`positional_parameters[]` 与
`input_concepts[]` 一一对应、`proposition_operation` 的四条闭合规则、`required_input_indexes`
的范围与唯一性、`ExternalMapping` 与 Lexicalization 的关系字段混用。

## 已测量的事实

### 三源数据在场且已冻结

`/public/home/wwb/datasets/ontology-sources/` 三个文件均在，SHA-256 与
`artifacts/ontology-sources/source-freeze.json` 记录一致。

**三源之间不存在可用的交叉链接**（已逐一验证）：PropBank 的 `lexlink`/`rolelink` 只指向
VerbNet（11,047）与 FrameNet（5,203），其约 83 处 "WordNet" 提及全是标注者自由文本
`<note>`/`example src`，不是 sense key；schema.org 中 "wordnet"/"propbank" 出现零次，外部链接
指向 eli、IPTC、UNECE、SNOMED、Wikidata、GS1、FIBO。

因此跨源对齐必须作为 KE-Core 自有断言撰写，带显式依据与状态，不得声称由来源推导。规范
第 6.2 节亦要求：只有 lemma 而无精确 sense/roleset 的记录不得声称来自 WordNet 或 PropBank。

### 源 ID 正则必须放弃构词约束

实测：PropBank 11,206 条 roleset 中 **40 条**不符合 `<lemma>.<nn>` 形态，例如 `1500.01`、
`anticoagulate.101`、`make.LV`、`point.yy`。WordNet 有 **1,818 条** sense 行的 lemma 含点、撇号或斜杠（1,726 个不同 lemma），
其中 17 个 lemma 以标点开头，均不符合 `<lemma>.<pos>.<nn>` 形态。

所以采用来源自身的权威身份，不由本实现定义构词规则：

```text
WordNet:  wn30:<official WordNet sense key>     例 create%2:36:00::
PropBank: pb3.4:<XML 中原样 roleset-id>          例 pb3.4:make.LV
```

sense key 取自 WordNet `index.sense`，不由 lemma/pos/sense-number 拼装。

### PropBank 存在身份碰撞

`overhang.01` 同时出现在 `frames/hang.xml` 与 `frames/overhang.xml`，语义与签名不同。因此源
记录身份是三元组：

```text
(source artifact sha256, archive member path, roleset_id)
```

`roleset_id` **不得作为字典唯一键**。这也是 11,206 occurrences 与 11,205 unique IDs 相差 1
的原因。

### PropBank 冻结计数

已实测确认：**7,565** frame XML / **9,088** predicates / **11,206** roleset occurrences /
**11,205** unique roleset IDs / **28,619** roles。

`frames/license.xml` 尽管名字像许可证文件，实际是谓词 "license" 的真实 frameset，含
`license.01` 与 3 个 role。既有 `ontology_sources/propbank.py` 以 name filter 将其丢弃，导致
`source-freeze.json` 记录的 7,564 / 11,205 / 28,616 少算一个 roleset。本实现按真实计数，不沿用
该过滤。

### 既有 foundation_v1 不可直接复用

`codex/ke-contract-v1-20260805` 的 `foundation_v1/` 做过一版三源归一化，但按的是**被取代的**
`ke_contract_v1` 合同：20 条 crosswalk 全为 `proposed`/`authored` 且无一被接受，自我声明为
conformance profile 而非 Foundation Ontology（160,660 条来源记录未选取、无 hypernym 层级）。
可作参照，本轮不改动它。

## 三条不变量

1. **校验器接受任意 Snapshot。** 入口接受已解析的记录集合；随包 fixture 降级为其中一个测试
   向量。另建**第二个独立小型 Snapshot**，证明校验器没有暗中依赖那 13 Concept / 4 Operator。
2. **源摄取只读、只产出证明。** 不产出 Concept/Operator 身份、不写 Snapshot、不生成
   `resolved` 跨源等价。没有 Canonical owner 时不能生成运行时 Lexicalization，也无法确定
   `surface_relation`——那是 owner 持有者的决定。
3. **合同层不依赖运行时。** 新代码只依赖 pydantic 与标准库，不 import 任何 `ke_memory_*`。
   既有 `verify_layout.py` 与架构测试已守此边界，无需新增机制。

## 方案

### 1. 模块边界

在既有 `memory_assertion/memory_assertion_v1/` 包根下新增两个子包，与已交付的结构层同级：

```text
memory_assertion/memory_assertion_v1/
  ids.py  literals.py  terms.py  equation.py  errors.py     ← 已交付（结构层）
  ontology/
    profile.py      Concept/Operator 的 supply.memory_assertion 模型
    records.py      上游 Concept/Operator/Ontology 记录
    snapshot.py     Snapshot 视图：manifest + 分片闭包，任意来源
    validation.py   第 7 节 12 项语义校验
  sources/
    records.py      WordNetSenseRecord / PropBankRolesetRecord / SchemaOrgTermRecord
    candidates.py   build-only LexicalizationCandidate 与 ExternalMappingProposal
    attestation.py  SourceAttestation 构造（仅证明词面来源）
    wordnet.py      index.sense 解析，sense key 原样保留
    propbank.py     frame XML 解析，roleset-id 原样保留
    schemaorg.py    JSON-LD 词面提取
    lexicon.py      NFC 规范化派生索引（非权威）
```

### 2. 统一校验结果

```text
SnapshotValidationResult
  semantic_status: valid | invalid
  provisioning_status: eligible | quarantined
  violations[]
  quarantine_reasons[]
```

两个状态维度独立：结构完全合法的 Snapshot 可以同时是 `valid` 与 `quarantined`。

**收集全部违规，不遇错即停。** harness 现为 `raise AssertionError`，对构建者不够用——一次构建
要能看到所有问题。**违规排序固定**，保证构建结果可复现。

**解析错误也进结构化结果。** pydantic/枚举解析失败必须转成 violation 条目，否则「返回全部
违规」在解析阶段即失效：一个字段拼错就退化成抛异常。因此模型不能在入口处直接
`model_validate` 了事，需逐记录捕获并归集。

### 3. 12 项校验，按依赖分三批

先做身份与引用，后两批依赖其成立。

**第一批（身份闭包）**

- Concept/Operator Symbol 分域唯一（`^[A-Z][A-Za-z0-9]*$` / `^[a-z][a-z0-9_]*$`）；
- 全部 ID 引用在 Snapshot 闭包内解析。**只约束内部引用**：`ExternalMapping` 的外部标识不要求
  在 Snapshot 中解析；
- Concept 继承引用存在、无自父边、整体为 DAG；
- `deprecated`/`replaced_by`：`replaced_by` 仅在 `deprecated=true` 时允许出现；目标必须存在、
  同 kind、不得为自身；允许有限替代链但禁止环，链终点应为未废止对象。

**第二批（Concept 语义）**

`disjoint_with` 闭包算法定死：

- 计算 Concept 祖先闭包；
- 任一 Concept 同时继承 disjoint 两侧 → 判为不可满足并拒绝；
- 派生的后代 disjoint 关系**仅用于校验，不要求写回** `disjoint_with[]`；
- 显式 `disjoint_with[]` 仍必须双向物化，无自边，且不与祖先/后代冲突。

另有：`literal_value_contract` 与 `semantic_kind=literal_value` 互为必要充分；codec 枚举封闭
（8 个之外即无效）。

**第三批（Operator 签名）**——本轮实质新增

- `positional_parameters[]` 长度等于 `input_concepts[]`，index 自 0 连续覆盖，数组顺序与 index
  一致，name 在 Operator 内唯一；
- `proposition_operation` 四条闭合规则，需结合被引用 Concept 的 `semantic_kind`，故只能在闭包
  内判断：`none` 不得含 proposition 输入；`modifier` 恰一个 proposition 输入且输出非
  proposition；`attitude` 恰一个 proposition 输入加至少一个非 proposition 主体，输出 Concept
  必须用 `ke-literal:boolean/v1`；`relation` 至少一个 proposition 输入，输出同样必须是 boolean
  codec；
- `partial` 的结构校验**不被 quarantine 跳过**：`total` 禁止 `definedness_contract`、`partial`
  必须有；`required_input_indexes` 非空、唯一、范围合法；
- `ExternalMapping` 与 Lexicalization 的**字段与值域混用**：`surface_relation` 的值出现在
  `relation` 位置或反之。两个枚举自身的封闭性由 Schema 保证，不在此重复。

**quarantine 规则**：任何 `partiality=partial` 的 Operator 使
`provisioning_status=quarantined`，因为 v1 不交付可内容寻址的 definedness registry。但语义校验
**继续跑完并收集其余违规**，且多个 `partial` Operator 必须**全部**报告。

### 4. 三源摄取

三层分离：

```text
源记录（只读）        WordNetSenseRecord / PropBankRolesetRecord / SchemaOrgTermRecord
  ↓
LexicalizationCandidate（build-only）
  ↓
SourceAttestation（仅证明词面来源）
```

`SourceAttestation` 按规范 6.2 的条件矩阵：`wordnet` 必须 `sense_id` 且禁 `roleset_id`；
`propbank` 相反；`schema_org`/`human`/`domain_corpus` 两者皆禁。

`ExternalMappingProposal` 只是构建审计 DTO，不写入 Snapshot。

派生索引键为 `(language, NFC(surface_form))`，规范只允许两步规范化：语言标签保留原值、
surface_form 走 NFC。不做大小写折叠、去标点、压缩空白或词干化。

**hash 边界**：Snapshot 内嵌 Lexicalization **参与** Snapshot hash；只有从它派生的只读索引
不参与。

### 5. 测试

**校验器**

- 12 项各有注入式反例。**隔离变异**才断言「恰好一个违规」；有级联影响的变异断言**完整、稳定
  的违规集合**。没有注入反例的检查等于没被证明。
- 多错误不短路测试；多个 `partial` Operator 聚合测试；违规排序稳定性测试。
- 随包 fixture（13 Concept / 4 Operator）为正例，结果须 `valid` + `eligible`。
- 第二个独立小型 Snapshot，证明校验器不依赖那份 fixture。

**三源**

- 小型 WordNet/PropBank/schema.org fixture 测试**始终运行**；只有全量语料计数测试在数据缺失时
  skip，用仓库既有 `tests/fixtures/datasets.py` 守卫，不放宽任何断言。
- 全量测试先校验固定 archive SHA-256，再断言绝对计数。
- 补：`license.xml` 含 `license.01` 与 3 role；重复 `overhang.01` 的三元组身份；非常规
  roleset ID（`1500.01`、`make.LV`、`point.yy`）；NFC 等价；大小写与空白不折叠。

## 验证方式

每条都要实际输出。

1. 12 项注入式反例全部按预期报出；多错误不短路与排序稳定性通过。
2. fixture 与第二个 Snapshot 均 `valid` + `eligible`。
3. 三源 fixture 测试始终通过；全量计数测试在数据在场时断言上述绝对值。
4. `check-portable.sh` **显式指定不存在的 `KE_DATASETS_ROOT`**，不依赖运行机器碰巧没有数据；
   该门禁下全量三源测试 skip 而非 fail。
5. `check.sh` 绿；`pyright` strict 0 错误；`ruff` 干净。
6. 依赖方向测试仍通过（新代码不 import `ke_memory_*`）。

## 明确不做

- 不实现 8 个 literal codec 的规范化。
- 不构造 Foundation Ontology v1，不生成可发布 Snapshot。
- 不产出 `resolved` 跨源 crosswalk；跨源对齐一律 `candidate` 或 `ExternalMappingProposal`。
- 不改 `foundation_v1/`。
- 不沿用 `ontology_sources/propbank.py` 丢弃 `license.xml` 的 name filter。
- 不把 `spec/` 子树的 harness 升格为生产实现。
