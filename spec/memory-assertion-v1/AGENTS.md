# Memory core 工作区约定

**作用域**：本文件只约束 `spec/memory-assertion-v1/` 子树。仓库根的 `AGENTS.md`（若存在）与 `research/next-prep/AGENTS.md` 管理仓库其余部分，两者互不覆盖。本子树于 2026-08-09 从独立目录 `Memory core` 并入 `ke-memory-demo`，内部布局保持不变，因此 `tools/validate_specifications.py` 的 `ROOT` 仍解析为本目录。

本项目保存 `memory-assertion/v1` 的活动规范、Schema、示例和后续实现。它不继承旧工作区中的第二套合同，也不因为规范已经写定而声称运行时已经实现。

## 修改前必读

修改任何字段、枚举、示例、hash 规则或语义边界前，必须完整阅读：

1. `README.md`
2. `docs/specifications/memory-assertion-v1/README.md`
3. `docs/specifications/memory-assertion-v1/normative-vocabulary.md`
4. `docs/specifications/memory-assertion-v1/ke-semantic-syntax-standard.md`
5. `docs/specifications/memory-assertion-v1/ontology-standard.md`
6. `docs/specifications/memory-assertion-v1/ontology-snapshot-packaging.md`
7. `docs/specifications/memory-assertion-v1/nl2ke-integration-requirements.md`
8. `docs/specifications/memory-assertion-v1/foundation-ontology-v1-build-plan.md`
9. `docs/specifications/memory-assertion-v1/2026-08-08-memory-assertion-v1-contract-migration-design.md`

## 单一合同

- 上游 Ontology Storage Specification v1 定义 `Ontology`、`Concept`、`Operator`、分片结构和 hash ID。
- `memory-assertion/v1` 只通过 `Concept.supply.memory_assertion` 与 `Operator.supply.memory_assertion` 收紧语义。
- `Ontology = Concept + Operator`。不得增加其他本体身份层。
- `canonical_name` 在本 Profile 中承担 Canonical Symbol；不得增加平行的 symbol 字段。
- KE 是真实的 many-sorted equality，机器方向固定为 `OperatorApplication = LeafTerm`。
- Snapshot 的唯一生产形态是 manifest 引用上游互斥分片。expanded bundle 只能是可删除的测试派生视图。
- 设计文档、Schema 和测试向量不能替代运行时实现证据。未运行的 validator、parser、provisioner 或 compiler 必须明确标为未实现。

## 同步修改

任何字段、枚举、约束或示例发生变化时，必须在同一变更中同步检查并更新：

- 规范 README 和 `normative-vocabulary.md`；
- 对应的语义规范；
- `schema/*.schema.json`；
- `schema/examples.json` 及其 request/response/error/capabilities/readiness 正反例；
- 所有使用统一示例表的文档。

任何新文档必须先在 `docs/specifications/memory-assertion-v1/README.md` 登记责任边界。未登记文档不得自称规范。

禁止通过兼容别名保留旧字段。若两个活动文件对同一字段给出不同含义，变更不得合入。

## 验证要求

完成变更前至少验证：

- 所有 JSON 均为 UTF-8 且可解析；
- 所有 Schema 声明 Draft-07、自身可加载，并拒绝未知字段与未知枚举值；
- 示例按 `expected_valid` 得到预期结果；
- 上游 ontology、concepts、operators 分片保持互斥顶层；
- ontology/concept/operator ID、相对路径、SHA-256 和引用闭包满足合同；
- Snapshot manifest 恰好引用一个 ontology 分片，且至少引用一个 concepts 和一个 operators 分片；
- Canonical Text 对五类 `LeafTerm` 和八种 v1 literal codec 完成 JSON round-trip/fail-closed 向量，且拒绝裸叶项等式；
- 全文示例 ID、Canonical Symbol、Operator 签名与统一示例表一致；
- 文档将“合同已定义”“代码已实现”“评测已通过”作为三个独立结论。

标准验证入口（从仓库根运行）：

```bash
scripts/ci/check-spec.sh
```

或直接在本目录运行：

```bash
python tools/validate_specifications.py
python -m unittest tools.test_validate_specifications tools.test_canonical_text_reference
```

验证依赖为 Python + `jsonschema>=4`，以及 Node.js。`tools/jcs.mjs` 只使用 Node.js 标准库，无 npm 依赖。统一入口会验证三个 Draft-07 Schema、全部 JSON 解析、五类交换文档、request/response 配对摘要、Evidence 回放、ID/DAG/类型最小语义闭包、LeafTerm/诊断/literal 向量、Profile 旧字段拒绝、Snapshot/JCS 向量、Canonical Text reference round-trip、真实 Snapshot fixture 的分片 hash、根 hash、记录数、reference manifest 和本地 Markdown 链接。它仍不是生产 NL2KE compiler、生产 Canonical Text parser、通用 Snapshot provisioner 或 Admission 实现。
