# memory-assertion/v1 结构校验层

日期：2026-08-09
状态：待评审

## 问题

`spec/memory-assertion-v1/` 交付了 memory-assertion/v1 的规范、3 个 Draft-07 Schema 和 42 个可执行向量，但**没有运行时实现**。子树里 4 个 `.py` 全是 conformance harness，文件头自己声明"deliberately a reference harness, not a production parser"。

这造成两个后果。一是"合同已定义"无法推进到"结构校验已实现"——规范原文把这两者列为独立结论，不允许互相冒充。二是无法开始从 `ke-memory/v1` 迁移：`personal-org` 的运行时用 `src/ke_memory_demo/domain/memory.py:171` 的 `ke-memory/v1`，要迁移得先有可对照的目标实现。

本层交付五类 `LeafTerm` 与 `KnowledgeEquation` 的 pydantic 模型，以随包交付的向量为测试。**不实现语义校验**。

## 已测量的事实

### 合同的结构形状

`schema/memory-assertion-v1.schema.json` 有 85 个 definitions。KE 相关的核心：

```text
KnowledgeEquation  = {lhs: OperatorApplication, rhs: LeafTerm}   additionalProperties: false
OperatorApplication = {kind: "operator_application", operator_id: OperatorId, arguments: [LeafTerm]}
LeafTerm = oneOf[IndividualRef, TypedValue, AssertionRef, OntologyConceptRef, OntologyOperatorRef]
```

`LeafTerm` **不含** `OperatorApplication`，所以嵌套在 Schema 层就被禁止；命题组合走 `assertion_ref`。

五类 LeafTerm 的判别字段与必填项：

| kind | 必填 | 约束 |
| --- | --- | --- |
| `individual_ref` | `scope`, `individual_id` | `scope ∈ {local, canonical}`，id 为 `RuntimeId` |
| `typed_value` | `concept_id`, `canonical_value` | value 为 `CanonicalLiteralValue`，不含 null |
| `assertion_ref` | `scope`, `assertion_id` | `scope ∈ {candidate, canonical}` |
| `ontology_concept_ref` | `concept_id` | `^concept_[a-f0-9]{12}$` |
| `ontology_operator_ref` | `operator_id` | `^operator_[a-f0-9]{12}$` |

`CanonicalLiteralValue = oneOf[boolean, string, MoneyValue, QuantityValue]`；`RuntimeId` 为
`^[A-Za-z0-9][A-Za-z0-9._:/-]*$`，长度 1–255。

### 向量构成

`schema/examples.json` 含 `leaf_term_examples` 11 条（6 合法 / 5 非法）与 `cases` 42 条
（16 `expected_valid=true` / 26 false）。42 个 case 中只有 11 个是完整文档，**31 个是
`derive_from` + JSON-Patch `operations` 派生**。

5 条非法 leaf 向量正好覆盖本层要拒绝的四类错误：

- `invalid bare leaf string`——term 是裸字符串 `"true"` 而非对象；
- `invalid nested operator application leaf`——`kind: operator_application` 出现在 leaf 位置；
- `invalid null typed value`——`canonical_value: null`；
- `invalid quantity amount field`——`{"amount": "3"}` 而合同要求 `{"value": "3"}`；
- `invalid unresolved leaf placeholder`——`kind: value_ref`，不在五类之内。

### 现有包结构与惯例

`pyproject.toml` 的 wheel packages 是三元组 `src/ke_memory_demo`、`service/ke_memory_service`、
`ontology/ke_memory_ontology`；`[tool.pyright]` 的 `include` 为 `src service ontology tests`，
`typeCheckingMode = "strict"`。

既有 pydantic 惯例（`src/ke_memory_demo/domain/expressions.py`）是私有基类携带
`ConfigDict(frozen=True, extra="forbid")`，配合 `Annotated[str, Field(min_length=1)]` 别名。

`scripts/ci/verify_layout.py` 的 `PACKAGE_ROOTS` 硬编码上述三元组，并断言 `pyproject` 的
wheel packages 与之**相等**。新增第四个包根会让它失败——这是它在履行职责，需同步更新。

## 三条不变量

1. **合同层不依赖运行时。** 新包只依赖 `pydantic`，不 import 任何 `ke_memory_demo`、
   `ke_memory_service`、`ke_memory_ontology`。将来是运行时反向依赖它。用架构测试固化。
2. **测试由随包向量驱动。** 断言的对象是 `spec/.../examples.json` 里已交付的 11 条 leaf 向量
   与 42 个 case 中的 KE，不是我另写的例子——后者只能证明模型与我的理解一致。
3. **结构校验完备，语义校验为零。** 不做跨 Snapshot 引用解析、Concept 继承 DAG 类型兼容、
   `literal_value_contract` 与具体 Concept 的绑定。规范
   （`ke-semantic-syntax-standard.md:75`）明确说这些不能只靠 Schema 判断。README 与 docstring
   如实这样写，不把本层说成 semantic validator。

## 方案

### 1. 包边界

新建第四个包根，与现有三个并列，进 wheel packages 与 pyright include：

```text
memory_assertion/memory_assertion_v1/
  ids.py        ConceptId / OperatorId / RuntimeId 受限字符串类型
  literals.py   CanonicalLiteralValue: StrictBool | StrictStr | MoneyValue | QuantityValue
  terms.py      五类 LeafTerm 判别联合 + OperatorApplication
  equation.py   KnowledgeEquation
  errors.py     结构校验失败的单一异常类型
```

不建 `snapshot.py`、`validator.py`、`parser.py`：那是语义校验、provisioner 与生产 parser 的
职责，本轮不碰，也不留空壳文件占位。

### 2. 让禁止项在类型层面不可表达

这是本层的核心设计取向——Schema 的禁止应成为类型不可表达，而非运行时才报错。

- **判别联合**：`Field(discriminator="kind")`。`kind: value_ref` 因判别值不在联合内被拒，
  不靠额外的 `if`。
- **嵌套禁止**：`OperatorApplication.arguments: tuple[LeafTerm, ...]`，而 `LeafTerm` 不含
  `OperatorApplication`。这正是与 `ke_contract_v1` 的核心分歧（后者递归）。
- **非 null 字面量**：`canonical_value` 的类型不含 `None`。
- **严格标量**：用 `StrictBool`/`StrictStr`，否则 pydantic 的联合智能匹配会把 `True`
  强转为 `"True"`，使 `boolean` 与 `string` 两支无法区分。
- **精确字段名**：`QuantityValue` 用 `extra="forbid"` 加字段名 `value`/`unit`，使
  `{"amount": ...}` 被直接判非法。
- **全部 frozen + extra="forbid"**，与既有惯例一致。frozen 的实质理由是 KE 承载断言身份，
  可变会让"同一个 KE"失去意义。

### 3. 测试

`tests/unit/memory_assertion_v1/` 三个文件：

- **`test_leaf_term_vectors.py`**——读 `leaf_term_examples`，`parametrize` 按 `name` 逐条断言
  6 合法可构造、5 非法抛 `ValidationError`。失败时直接指出哪条向量。
- **`test_equation_vectors.py`**——从 42 个 case 提取全部
  `hypotheses[].candidate_assertions[].ke` 并构造 `KnowledgeEquation`。31 个 patch 派生 case
  需先展开：测试内实现最小 JSON-Patch（仅 `replace`/`add`/`remove`），并断言展开后 case 数
  为 42。这与 `spec/` 子树的 `materialize_cases` 重复，但跨越那个包边界会破坏
  `testpaths` 建立的隔离（那些模块以 `tools.*` 导入自身），代价更大。
- **`test_contract_prohibitions.py`**——断言四处新旧合同矛盾在类型层面成立：嵌套被拒、
  `canonical_value=None` 被拒、`ke_contract_v1` 风格的 `bindings`/`role_id` 被 `extra="forbid"`
  拒、`polarity`/`modality`/`temporal` 作为 KE 字段被拒。这是迁移的回归网。

架构测试：断言新包不 import 任何 `ke_memory_*`，方式与 `verify_layout.py` 现有的
`ke_memory_service` 反向依赖检查一致。

### 4. 配套改动

- `pyproject.toml`：wheel packages 加 `memory_assertion/memory_assertion_v1`，pyright
  `include` 与 `extraPaths` 加 `memory_assertion`，pytest `pythonpath` 同加。
- `scripts/ci/verify_layout.py`：`PACKAGE_ROOTS` 加第四项，并把 `memory_assertion` 纳入
  反向依赖扫描。
- `scripts/ci/verify_wheel.py`：`PACKAGE_NAMES` 加 `memory_assertion_v1`，使新包必须能从
  wheel 导入。
- `tests/architecture/test_package_boundaries.py`：**第二处硬编码的包列表**。它逐字断言
  wheel packages 等于那个三元组，还独立维护自己的 `PACKAGE_ROOTS`。初稿只提到
  `verify_layout.py`，遗漏了这里——实施时由远端门禁的 `1 failed` 发现。四处一并更新，并
  把依赖方向断言同时做成测试：脚本守 CI，测试守开发者推送前的本机运行。

三处包根清单（`pyproject`、`verify_layout.py`、`test_package_boundaries.py`）加
`verify_wheel.py` 的包名清单，共四处必须同步。这个重复本身是既有设计，本轮不改动它。

### 5. 断言的可伪证性

依赖方向与结构禁止都要实测可伪证，不接受"通过即正确"：

- 向 `memory_assertion/` 注入 `from ke_memory_demo... import ...`，确认 `verify_layout.py`
  报错并 exit 1、`test_contract_layer_does_not_depend_on_the_runtime` 失败，再还原。
- 三个专门 patch `/ke` 路径的向量中，确认 `invalid nested operator application argument`
  与 `invalid null typed value` 被本层拒绝，而 `invalid self-referential candidate graph`
  **构造成功**——环检测需要整张 candidate 表，是语义校验的输入。这个边界写成显式断言
  （`test_semantically_invalid_cases_still_construct`），而不是留给"未被拒绝"去暗示。

## 验证方式

每条都要实际输出，不接受推断。

1. 新测试全绿；`pytest -q` 总数自 1128 增加，增量等于新测试数。
2. `pyright` 仍 0 错误（新包在 `include` 内，strict）。
3. `ruff check` 含新包根，干净。
4. `verify_wheel.py` 通过——新包根进 wheel 后可导入，这是它已有的检查。
5. `check-portable.sh`（远端门禁，无 KEOL 无数据集）与 `check.sh`（带 `KEOL_SOURCE`）均绿。
6. 架构测试证明依赖方向单向。

## 明确不做

- 不实现 semantic validator：跨引用解析、Concept DAG 类型兼容、作用域解析、hash 校验。
- 不实现生产 Canonical Text parser/renderer——`spec/` 里那个 harness 不升格为生产实现。
- 不实现 Snapshot provisioner 或 NL2KE compiler。
- 不改 `ke-memory/v1` 或 `ke_contract_v1`——本层是迁移的目标，迁移本身是后续工作。
- 不建空壳模块占位未来功能。
