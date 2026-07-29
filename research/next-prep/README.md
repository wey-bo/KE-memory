# KE-memory

KE-memory 是记忆系统设计、验证和逐步实现工作区，不是已完成的运行时产品仓库。项目当前验证“逐轮原文保全 -> evidence-backed semantic extraction -> 可替换 representation profile/adapter -> 符号查询与证据闭包”的路线。KEOL、扩展 AMR 或其他结构化格式都必须通过同一能力契约，embedding 只负责允许的候选缺口。

## 开始阅读

1. `AGENTS.md`：术语、事实源、边界、当前结论和未决问题。
2. `安排.md`：Wave 0-6 的执行顺序和当前状态。
3. `docs/reference/memory实现方案汇报.pdf`：符号优先、向量补足的原始方案。
4. `docs/designs/`：已经确认的设计。
5. `docs/plans/`：对应的实施计划和历史执行记录。

## 目录

| 路径 | 职责 |
| --- | --- |
| `data/gold-candidates/` | 10 条候选对话及来源配置，仍待人工筛选 |
| `knowledge_pipeline/` | 当前知识优先抽取、校正、投影和导出代码 |
| `knowledge-extraction/` | 当前结果、模型原始输出、验证清单和审计历史 |
| `tools/keol_baseline/` | KEOL baseline 适配、构建和视图导出工具 |
| `artifacts/keol-baseline/` | KEOL baseline 的输入、中间结果、原生产物和人工视图 |
| `tools/natural_memory_benchmark/` | BEAM/LoCoMo/LongMemEval 自然 benchmark 小切片冻结、校验和后续 evaluator 工具 |
| `artifacts/natural-benchmark-slices/` | 自然 benchmark 原始快照、source manifest、slice/gold 分离文件和外部结果账本 |
| `artifacts/identity-memory-experiment/` | schema.org 参考快照、identity/membership 冻结诊断、正式运行和报告 |
| `archive/legacy-ke-v0.2/` | 已作废的自定义 KE v0.2 实验，仅供历史核对 |
| `tests/` | 结构、抽取、证据、投影、关键词和 KEOL 适配测试 |

## 当前正式结果

- 人工展示：`knowledge-extraction/KE-knowledge-keywords.json`
- 律师请假切片：`knowledge-extraction/keyword-v3-preview-lawyer-leave.json`
- 关键词 v3 审计结果：`knowledge-extraction/keyword-pass-v3/keyword-pass.json`
- 确定性知识视图：`knowledge-extraction/final-knowledge.json`
- 运行与方法记录：`knowledge-extraction/run.json`、`knowledge-extraction/knowledge-extraction-prompt-and-strategy.md`

这些结果仍是 gold 候选，不等于人工确认的长期记忆事实。

## 常用验证

当前 H100 工作区使用独立的 `.venv-h100`；本波次常用验证命令为：

```bash
.venv-h100/bin/python -m pytest tests/natural_memory_benchmark -q --import-mode=importlib -p no:cacheprovider --basetemp .tmp/nbm
.venv-h100/bin/python -m tools.natural_memory_benchmark.cli validate-natural-identity-slice --root artifacts/identity-memory-experiment/natural-v1 --workspace-root .
.venv-h100/bin/python -m tools.natural_memory_benchmark.cli validate-slice --root artifacts/natural-benchmark-slices --slice-id slice-v1
.venv-h100/bin/python -m tools.natural_memory_benchmark.cli validate-ledger --path artifacts/natural-benchmark-slices/external-results-ledger.json
```

pytest 使用工作区内的短 `--basetemp`，避免污染系统临时目录。`.venv-h100` 未安装 FastEmbed；需要 dense 依赖的历史实验不得据此宣称已在 H100 重放。当前 `.git` 为空目录，不是有效 Git 仓库；不要假设存在提交或回滚能力，也不要自动初始化。

## 本体化记忆优势实验

- 冻结输入：`artifacts/ontology-memory-experiment/gold-v2/`
- hidden 决策运行：`artifacts/ontology-memory-experiment/runs/run-20260725T150000Z-real-hidden/`
- 实验结论：`artifacts/ontology-memory-experiment/reports/experiment-summary.md`
- gate 报告：`artifacts/ontology-memory-experiment/reports/gate-report.md`
- v3 dev 自动编译器修复记录：`artifacts/ontology-memory-experiment/reports/v3-dev-compiler-report.md`
- v3 fallback probe 冻结记录：`artifacts/ontology-memory-experiment/reports/v3-fallback-probe-report.md`
- v3 real dense 运行记录：`artifacts/ontology-memory-experiment/reports/v3-real-dense-report.md`
- v3 real hidden gate 报告：`artifacts/ontology-memory-experiment/reports/v3-real-hidden-gate-report.md`
- v3 parser 修复 post-hoc 记录：`artifacts/ontology-memory-experiment/reports/v3-parser2-posthoc-repair-report.md`
- v4 fresh hidden 冻结输入：`artifacts/ontology-memory-experiment/gold-v4/`
- v4 fresh hidden gate 报告：`artifacts/ontology-memory-experiment/reports/v4-real-hidden-gate-report.md`
- v5 fresh hidden 冻结输入：`artifacts/ontology-memory-experiment/gold-v5/`
- v5 fresh hidden gate 报告：`artifacts/ontology-memory-experiment/reports/v5-real-hidden-gate-report.md`
- 外部作者结果上下文：`artifacts/ontology-memory-experiment/reports/external-context.md`

早期 v2 gate 为 `fail`：oracle 证明充分本体表示具有受控能力优势，但当时 automatic 管线只保留 22.9% 相对增益。2026-07-26 v5 fresh hidden clean gate 已为 `pass`，只授权进入预注册自然 benchmark 小切片或扩大受控集。其他 memory 系统没有在本项目复跑，外部数字不能与本实验 arm 直接横比。

2026-07-25 已完成 v3 automatic compiler 的 dev-only 修复：temporal provenance/supersession closure、`linked_to` multihop、`sense_of` lexical context 和 explicit absence owner query 在 dev diagnostic grid 上达到 1.0 ESEM/Answer/Constraint，运行 `run-20260725T172000Z-v3-diagnostic-dev` 为 432 rows、0 error、verify valid。该结果不是新的 hidden gate；`O+E` fallback 仍为 0，embedding 兜底仍未被证明。下一步需要冻结能真实触发 fallback 的 v3 probe 和新 hidden split。

2026-07-25 续：已冻结 `artifacts/ontology-memory-experiment/gold-v3/`，新增 4 个 lexical uncovered-predicate fallback probes（1 dev、3 hidden），总计 64 scenarios 和 35,200 distractors。`run-20260725T181000Z-v3-diagnostic-all` 为 2,304 rows、0 error、verify valid；automatic `O+E` fallback rate 为 0.0625，structural-family fallback rate 为 0.0，新增 probes 上 `O+` 为 0.0 而 `O+E` 为 1.0。该结果只证明 guarded fallback 路径在 diagnostic encoder 下非空且可约束执行，不是 real dense hidden gate。

2026-07-25 再续：已在工作区隔离环境 `.venv-dense` 中安装 `fastembed==0.8.0` 并完成 v3 real dev/hidden。`run-20260725T190000Z-v3-real-dev` 为 468 rows、0 error、verify valid；automatic `O+E` 在 dev 上 ESEM/Answer/Constraint 均为 1.0。`run-20260725T192000Z-v3-real-hidden` 为 1,836 rows、0 error、verify valid；真实 hidden gate 仍为 `fail`，唯一失败门是 `automatic_retained_gain=0.16339869281045752`，低于 0.70。真实 `O+E` 解决全部 hidden fallback probes，且 structural-family fallback rate 为 0.0，但 automatic `O+E` hidden ESEM 只有 0.294，不能进入大 benchmark。

2026-07-25 parser 修复续跑：新增自动表示回归测试覆盖 `connected`/`exact set contains`、`Before ... log recorded ... as active`、`used ledger for ...`、`denotes ... rather than ...` 和显式 owner absence。`run-20260725T202000Z-v3-parser2-diagnostic-all` 为 2,304 rows、0 error、verify valid，automatic `O+E` diagnostic ESEM/Answer/Constraint 均为 1.0。`run-20260725T203000Z-v3-parser2-real-dev` 为 468 rows、0 error、verify valid，automatic `O+E` dev 仍为 1.0。`run-20260725T204000Z-v3-parser2-real-hidden` 为 post-hoc hidden 回归检查，1,836 rows、0 error、verify valid，post-hoc gate 为 `pass`，`automatic_retained_gain=0.8431372549019608`。由于 v3 hidden 已在前序失败分析中暴露，该 pass 不能替代 clean gate；下一步必须冻结 v4 fresh hidden 再做有效 go/no-go。

2026-07-26 v4 fresh hidden：`run-20260726T021000Z-v4-real-hidden` 为 1,836 rows、0 error、verify valid，使用真实 `qdrant/bge-small-en-v1.5-onnx-q@52398278842ec682c6f32300af41344b1c0b0bb2` dense encoder。clean gate 仍为 `fail`，唯一失败门是 `automatic_retained_gain=0.47058823529411764`；automatic `O+E` hidden ESEM 为 0.5294117647058824，fallback rate 为 0.058823529411764705，structural-family fallback rate 为 0.0。当前不能进入 LoCoMo、BEAM、LongMemEval；先修 automatic evidence boundary 和 multihop evidence closure。

2026-07-26 v5 fresh hidden：修复 automatic evidence boundary 与 multihop evidence closure 后，已冻结 `gold-v5` 并完成 `run-20260726T041000Z-v5-real-hidden`。该 run 为 1,836 rows、0 error、verify valid，clean gate 为 `pass`；automatic `O+E` hidden ESEM/Answer/Constraint 均为 1.0，`automatic_retained_gain=0.9411764705882353`，fallback rate 为 0.058823529411764705，structural-family fallback rate 为 0.0。下一步是预注册自然 benchmark 小切片或扩大受控集，不是直接宣称产品优越性。

## 自然 benchmark 小切片

- 设计：`docs/designs/2026-07-26-natural-benchmark-slice-design.md`
- 计划：`docs/plans/2026-07-26-natural-benchmark-slice-plan.md`
- 事件-角色-证据闭包表示设计：`docs/designs/2026-07-27-event-role-evidence-closure-representation-design.md`
- 事件-角色-证据闭包最小实现计划：`docs/plans/2026-07-27-event-role-evidence-closure-implementation-plan.md`
- 真实 slice semantic IR 映射计划：`docs/plans/2026-07-27-real-slice-semantic-ir-mapping-plan.md`
- semantic IR 到 KEOL projection 计划：`docs/plans/2026-07-27-semantic-ir-keol-projection-plan.md`
- 事件-角色-证据闭包最小 IR：`tools/natural_memory_benchmark/semantic_ir.py`、`tests/natural_memory_benchmark/test_semantic_ir.py`
- 事件-角色-证据闭包诊断 runner/report：`tools/natural_memory_benchmark/semantic_ir_runner.py`、`tests/natural_memory_benchmark/test_semantic_ir_runner.py`
- 真实 slice semantic IR runner/report：`tools/natural_memory_benchmark/semantic_ir_slice_runner.py`、`tests/natural_memory_benchmark/test_semantic_ir_slice_runner.py`
- semantic IR 到 KEOL projection：`tools/natural_memory_benchmark/semantic_ir_keol_projection.py`、`tests/natural_memory_benchmark/test_semantic_ir_keol_projection.py`
- semantic IR KEOL projection 回查链：`tools/natural_memory_benchmark/semantic_ir_keol_trace.py`、`tests/natural_memory_benchmark/test_semantic_ir_keol_trace.py`
- 表示无关能力契约与 conformance harness：`tools/natural_memory_benchmark/representation_contract.py`、`tools/natural_memory_benchmark/representation_conformance_runner.py`
- Extended-AMR 候选 adapter：`tools/natural_memory_benchmark/extended_amr_adapter.py`、`tests/natural_memory_benchmark/test_extended_amr_adapter.py`
- KEOL 可选 adapter 原生验证：`tools/natural_memory_benchmark/semantic_ir_keol_validate.py`
- 原始快照与 source manifest：`artifacts/natural-benchmark-slices/raw/`、`artifacts/natural-benchmark-slices/source-manifest.json`
- 冻结切片：`artifacts/natural-benchmark-slices/slice-v1/slice.json`
- gold/rubric/证据引用：`artifacts/natural-benchmark-slices/slice-v1/gold.json`
- gold evidence raw-text 映射：`artifacts/natural-benchmark-slices/slice-v1/gold-evidence.json`
- evidence candidate corpus：`artifacts/natural-benchmark-slices/slice-v1/evidence-corpus.json`
- 事件-角色-证据闭包诊断产物：`artifacts/natural-benchmark-slices/slice-v1/semantic-ir-diagnostic-results.json`、`artifacts/natural-benchmark-slices/slice-v1/semantic-ir-diagnostic-report.md`
- 真实 slice semantic IR 诊断产物：`artifacts/natural-benchmark-slices/slice-v1/semantic-ir-slice-diagnostic-results.json`、`artifacts/natural-benchmark-slices/slice-v1/semantic-ir-slice-diagnostic-report.md`
- semantic IR 到 KEOL projection 产物：`artifacts/natural-benchmark-slices/slice-v1/semantic-ir-keol-projection.json`
- semantic IR KEOL projection 回查产物：`artifacts/natural-benchmark-slices/slice-v1/semantic-ir-keol-trace.json`、`artifacts/natural-benchmark-slices/slice-v1/semantic-ir-keol-trace-report.md`
- representation conformance v4：`artifacts/natural-benchmark-slices/slice-v1/representation-conformance-results-v4.json`、`artifacts/natural-benchmark-slices/slice-v1/representation-conformance-report-v4.md`
- authoritative memory contract v5：`artifacts/natural-benchmark-slices/slice-v1/representation-conformance-results-v5.json`、`artifacts/natural-benchmark-slices/slice-v1/representation-conformance-report-v5.md`
- identity/schema.org/Extended-AMR v3 设计与计划：`docs/designs/2026-07-27-identity-resolution-schemaorg-extended-amr-design.md`、`docs/plans/2026-07-27-identity-resolution-schemaorg-extended-amr-plan.md`
- identity 合同与 adapter：`tools/natural_memory_benchmark/identity_resolution.py`、`tools/natural_memory_benchmark/extended_amr_v3_adapter.py`、`tools/natural_memory_benchmark/identity_conformance_runner.py`
- identity 冻结输入与正式产物：`artifacts/identity-memory-experiment/gold-v1/`、`artifacts/identity-memory-experiment/runs/run-20260727T080000Z-identity-v1/identity-conformance-results-v1.json`、`artifacts/identity-memory-experiment/reports/identity-conformance-report-v1.md`
- KEOL projection v1 原生诊断：`artifacts/natural-benchmark-slices/slice-v1/semantic-ir-keol-native-validation.json`
- KEOL projection v2 与验证：`artifacts/natural-benchmark-slices/slice-v1/semantic-ir-keol-projection-v2.json`、`artifacts/natural-benchmark-slices/slice-v1/semantic-ir-keol-projection-v2-validation.json`
- FastEmbed dense baseline：`artifacts/natural-benchmark-slices/slice-v1/dense-reference-fastembed-results.json`
- FastEmbed dense score/report：`artifacts/natural-benchmark-slices/slice-v1/dense-reference-fastembed-score.json`、`artifacts/natural-benchmark-slices/slice-v1/dense-reference-fastembed-report.md`
- 当前最佳本项目 slice arm：`artifacts/natural-benchmark-slices/slice-v1/symbolic-fallback-answerability-v2-fastembed-results.json`、`artifacts/natural-benchmark-slices/slice-v1/symbolic-fallback-answerability-v2-fastembed-score.json`、`artifacts/natural-benchmark-slices/slice-v1/symbolic-fallback-answerability-v2-fastembed-report.md`
- 外部结果账本：`artifacts/natural-benchmark-slices/external-results-ledger.json`

slice-v1 共 32 个 item：BEAM 10、LoCoMo 10、LongMemEval 12。`slice.json` 不含答案、证据引用、rubric、adversarial answer 或 score label；`gold.json` 单独保存 gold 信息。LoCoMo category 5 仍为 `manual_required`，暂不计入 answer correctness。外部系统结果只作为上下文，不在本项目本地复跑。

当前已新增 result/scorer 合同和 CLI：`score-results` 可消费本项目 arm 的结果文件并输出 evidence exact、All-Evidence@K、recall、precision、answer exact diagnostic、abstention、critical false positive、fallback、latency/token 指标。已运行真实 FastEmbed `dense_reference`、规则/槽位 `symbolic`、guarded `symbolic_fallback`、fallback taxonomy v1 与 answerability v2。当前最佳 slice arm 是 `symbolic_fallback + answerability v2`：Evidence Set Exact Match 0.4375，All-Evidence@10 0.6875，Mean Evidence Recall@10 0.78125，Mean Evidence Precision@10 0.5565972222222222，abstention correctness 1.0，critical false positives 0，fallback trigger rate 0.03125。该 run 只做检索/证据 gate，不生成答案；其他 memory 系统仍未本地复跑，不能据此宣称产品优越性。

2026-07-27 已新增事件-角色-证据闭包最小 IR 合同、deterministic executor 和诊断 runner/report。正式诊断运行 `run-20260727Tsemantic-ir-diagnostic` 只使用手写 IR 样本，5/5 pass，覆盖 `led/manage` vs `led-to/cause`、feedback causal answerability、multi-session evidence closure 和 current preference supersession；不含模型抽取，不改变 benchmark slice/gold。验证：`test_semantic_ir.py` 13 passed，`test_semantic_ir_runner.py` 4 passed，`tests/natural_memory_benchmark` 53 passed，`validate-slice` 和 `validate-ledger` 均 valid。

2026-07-27 续：已把 5 个真实冻结 slice item 手写映射到 semantic IR，并与当前 `symbolic_fallback + answerability v2` 结果对齐比较。正式运行 `run-20260727Tsemantic-ir-real-slice` 为 5/5 pass；IR evidence exact 为 5/5，现有结果 evidence exact 为 3/5，IR evidence-exact improvement 为 2；现有结果中 1 个 fallback item（`LONGMEMEVAL-6d550036`）在 IR 中不需要 fallback；IR 对 `BEAM-100K-C001-abstention-001` 继续正确 abstain 且不允许 fallback。该结果仍是 hand-authored mapping，不含模型抽取、不生成答案、不授权完整 benchmark 或产品优势宣称。验证：`test_semantic_ir_slice_runner.py` 4 passed，`tests/natural_memory_benchmark` 57 passed，`validate-slice` 和 `validate-ledger` 均 valid。

2026-07-27 再续：已新增 semantic IR 到 KEOL-shaped JSON 的最小 projection adapter。正式产物 `semantic-ir-keol-projection.json` 来自 5 个真实 slice IR case，包含 13 条 Evidence、19 条 Assertion，并保留 `semantic_ir_unit_id`、level、predicate sense、source status、lifecycle、role bindings、derived assertion IDs 和 closure metadata。该 adapter 只验证字段映射合同，不写入或修改 `artifacts/keol-baseline/`，也不代表 KEOL baseline 已支持完整 IR 自动落库。验证：`test_semantic_ir_keol_projection.py` 4 passed，`tests/natural_memory_benchmark` 61 passed，`validate-slice` 和 `validate-ledger` 均 valid。

2026-07-27 继续：已新增 projection 回查报告，验证 `Assertion -> Evidence -> source quote` 链路。正式产物 `semantic-ir-keol-trace.json` 覆盖 19 条 Assertion，其中 19 条都有 evidence trace，6 条同时有 derived provenance，broken evidence refs 为 0。该报告仍只验证本地 projection 的追溯链，不代表 KEOL runtime ingest、自动抽取或答案生成已经完成。验证：`test_semantic_ir_keol_trace.py` 4 passed，`tests/natural_memory_benchmark` 65 passed，`validate-slice` 和 `validate-ledger` 均 valid。

2026-07-27 表示契约续：用户已明确抽取和存储不强制使用 KE。新增 representation-agnostic contract、bundle integrity validator、exact round-trip 与 query-semantics conformance。正式有效运行 `run-20260727Trepresentation-conformance-v3` 在 5 个 hand-authored real-slice probe 上 bundle integrity valid、round-trip exact、query probes 5/5；每个 query 使用独立 unit scope，修复了已作废 v1 产物中的跨-case matched-unit 串扰。v3 将 raw-source revision binding、immutable lifecycle revision、structured L2 semantics 和 closure-evaluation versioning 提升为 hard capabilities。Semantic IR 当前只通过 `reference_carrier`，`authoritative_ready=false`。

2026-07-27 KEOL adapter 续：原 v1 projection 可被 KEOL 原生 Pydantic 模型解析且 0 error，但有 36 warnings，并错误地把 5 个 closure 全投影为 incomplete，和真实诊断的 4 complete + 1 abstention 有 4 项 parity mismatch。该 v1 artifact 保留作历史失败证据。v2 projection 在投影前物化 closure，parity mismatch 降为 0，并把 lifecycle 映射限制到 KEOL 可识别状态；原生验证仍有 30 warnings、无 reverse round-trip、无 runtime constraint execution，因此分类仍是 `projection_only`，不是最终存储选型。

2026-07-27 Extended-AMR conformance v4：新增显式 predicate/entity/abstraction/reference nodes、角色/派生 edges 和 typed memory annotations 的 `extended-amr-memory-graph-v1` adapter；payload 不保存 opaque L1/L2 副本，可从图精确重建逻辑 bundle。正式运行 `run-20260727Trepresentation-conformance-v4` 中 bundle integrity valid，Extended-AMR exact round-trip，5/5 scoped query probes 等价；但 `raw_source_revision_binding`、`lifecycle_and_revision`、`structured_l2_semantics`、`closure_evaluation_versioning` 仍为 unsupported，因此 `status=fail`、`authoritative_ready=false`。这证明当前 adapter 可作无损候选表示，不构成最终存储选型、自动抽取质量或 benchmark 优势结论。新鲜验证为 `tests/natural_memory_benchmark` 84 passed，`validate-slice` 与 `validate-ledger` 均 valid。

2026-07-27 authoritative memory contract v3/v5 收尾：新增不可变 raw/source/unit revision ledger、精确 `EvidenceSpanV2`、typed L2 structured claims、分离的 claim/query closure context、版本化 `ClosureSpec`/`ClosureEvaluation`、freshness/result-parity 校验和 `run-authoritative-conformance` CLI。正式运行 `run-authoritative-conformance-v5` 中 source validation 通过并重放 13 个 source record，6/6 closure evaluation fresh、6/6 result parity、5/5 frozen correctness；Native v3 与 `extended-amr-memory-graph-v2` 均 exact round-trip、5/5 query parity。五项 correctness oracle 已独立冻结（SHA-256 `cfebd096c369c4a982e9db0b09cb4b32a98cb165853f005cf52fe049a45d8659`），并覆盖 matched claim；runner 还执行 stale/incomplete active-L2 负向拒绝和逐 carrier capability gate。两者是同一 authoritative contract 的不同 carrier，最终存储表示仍未选择。`LONGMEMEVAL-6d550036` 保留四份 evidence candidate，但因 provisional project identity 尚未归一，正确结果是以 `structured_l2_identity_unresolved` abstain；因此两种 carrier 均保持 `authoritative_ready=false`。正式 JSON/报告 SHA-256 分别为 `3ec6656c037200f8591fac44cd7e1e4bf2caa3aa9447f3fa5ba9854324d4cc33` 与 `9ef73e7a4a16409ef9f5edbb74e38b2c1b1b628821a4b13ce2bc0698f03a011a`，隔离回放字节一致；`tests/natural_memory_benchmark` 为 117 passed。该实验只验证表示契约、证据闭包、查询一致性和 correctness gate，不证明 AMR、KEOL、本体记忆或本项目优于外部 memory 系统；embedding fallback 仍不是事实权威。

## 身份解析与 Extended-AMR v3

2026-07-27 identity 波次在 authoritative v3/v5 之上新增表示无关的身份与聚合合同，并把 Extended-AMR 作为当前主候选 carrier。`identity_resolution.py` 实现 concept registry、不可变 identity decision、scoped evidence closure、correction-safe snapshot 和安全 `count_distinct`；`extended_amr_v3_adapter.py` 显式编码相同逻辑记录，不能用一个未校验的 `same-as` edge 代替身份决策。

概念建模参考冻结为 schema.org 30.0 官方仓库提交 `f72e60b7f67578b4af9445fa20fc8ec3fe1c9b93`。schema.org 只提供类型、属性和外部映射建议，不是事实权威：本地 `memory:Project` 与 `schema:Project` 为 `related` 而非 `exact`，`schema:sameAs` 也不能直接授权本地实体合并。任何 merge、keep-distinct、reject-merge、split 或 abstain 都必须有本地 evidence closure、policy gate 和可审计 revision。

正式运行 `run-20260727T080000Z-identity-v1` 在冻结的 4 dev + 4 hidden 手写诊断上为 `pass`：critical false merge 为 0；answerable `count_distinct`、evidence set、abstention、revision 和 closure freshness 均为 1.0；structural fallback 为 0；Native v4 与 Extended-AMR v3 的 round-trip/query parity 均为 1.0。结果与报告 SHA-256 分别为 `e7cc632ae20f6436156fcd9c777352eac0f8286e63cb24f42ddee05875ae633c`、`bc032cf6a5590a8d1f12adf5d523af9da65d599b66ceddac52667d213b920ae8`，隔离回放字节一致；冻结 v5 结果哈希仍为 `3ec6656c037200f8591fac44cd7e1e4bf2caa3aa9447f3fa5ba9854324d4cc33`。

`identity_authoritative_ready=true` 只适用于该手写 identity-contract 诊断，不适用于真实 LongMemEval 项目计数。`LONGMEMEVAL-6d550036` 仍缺独立、证据支持的 project membership/identity 决策，必须继续以 `structured_l2_identity_unresolved` abstain，不能强行改成 count=2。本轮也不验证自动 identity candidate 提取质量、完整 benchmark、用户体验、最终存储选型或相对外部 memory 系统的优越性。

## Natural identity/membership proposal v1

2026-07-27 已完成 12-case natural identity/membership proposal 诊断，包含 6 dev + 6 hidden，来源只使用已冻结的 BEAM、LoCoMo 和 LongMemEval 快照。`public.json`、`authority.json`、`gold.json` 三层严格分离；reference proposer 只读取 public，只有 deterministic evidence/policy gate 可接受 identity 或 membership 动作。schema.org 与 Extended-AMR 仍只提供概念/表示建议，不能授权 merge 或 membership。本波次 `核心影响：无`，未修改基础本体、动态本体扩展接口、L1/L2 抽取、问题处理、符号召回或 guarded embedding fallback。

正式 reference run 为 `run-20260727T090000Z-natural-identity-reference-v1`。`gate_safety_ready=true`、`proposal_quality_ready=false`：raw action accuracy 为 0.8333333333333334，存在 1 个 raw critical false merge；gate 将无依据的 budget-repository `keep_distinct` 和 LongMemEval project `merge` 都降为 abstain，最终 gated action accuracy 为 1.0、gated critical false merge/membership 均为 0、proposal evidence exact rate 为 1.0、structural fallback 为 0。真实 `LONGMEMEVAL-6d550036` 仍保持 `structured_l2_identity_unresolved`。

实现位于 `tools/natural_memory_benchmark/identity_proposal.py`、`identity_proposal_runner.py`，冻结与正式产物位于 `artifacts/identity-memory-experiment/natural-v1/`。正式 score/report SHA-256 分别为 `d346eb0f0d277be39fad363da8f4f89f98b0fc4a49be2a95c0970f62abf562b2`、`45d0dd7452873e0df8545b9930b19aad6938b2ea764cc2177a16de3e05ba380a`；7 个生成文件隔离重放逐字节一致。验证为 focused 10 passed、完整 `tests/natural_memory_benchmark` 143 passed，`validate-slice` 与 `validate-ledger` 均 valid。当时的下一步是读取冻结 `public.json` 的真实 proposal-only 模型运行，现已由下述 H100 run 完成；自动 merge 写入路径仍未获授权。

2026-07-27 H100 真实 proposal-only 模型运行已完成。全新 `fork_turns="none"` proposer 只读取冻结 `public.json`，以 `proposer_id=codex-gpt-5.6-sol`、`proposer_version=2026-07-27` 生成 `run-20260727T104020Z-codex-gpt-5-6-sol-proposal-only-v1` 的 12 条候选；候选、score 和报告位于 `artifacts/identity-memory-experiment/natural-v1/model-runs/run-20260727T104020Z-codex-gpt-5-6-sol-proposal-only-v1/` 并已设为只读。scorer 机械结果为 `gate_safety_ready=true`、`proposal_quality_ready=true`：raw/gated action accuracy、raw abstention F1、proposal/required evidence exact rate 均为 1.0，raw/gated critical false merge 与 false membership 均为 0，gate intervention 和 structural fallback 均为 0，accepted non-abstain coverage 为 1.0。失败 case 类型为无；12 个 case 均无需 gate 改写。

但冻结 `public.json` 的 proposer 可见 `case_id`/`mention_id` 含有 `distinct`、`mismatch`、`member`、`unresolved` 等结果暗示。它没有泄露 authority/gold 文件，却可能让模型从标识符推断预期动作。因此本次 run 的双门只表示现有 scorer 合同下的机械通过：`gate_safety_ready=true` 仍可作为 gate 安全诊断，`proposal_quality_ready=true` 不能作为无污染的模型 proposal-quality 证据。该 run 与 `public.json` 均保留为不可变审计产物，不做事后改写。

本次 scorer 输入文件 SHA-256 为 public `2020abb0f13cb91648e0bdf64eb53cc27b3ca8b12783e3aedba0280280270cf3`、authority `c5a877ea2420ec65aa41020d77febaba6314528ef7586abfe1c42dbeaebf8985`、gold `347f185e7364920a1a041074dfb9a74de7585111cb49d726336e3efb97df839b`、manifest `023c6a06ddab7d71d21c8483d48da7b655d245ebf41265cbdd021f4eafd75d0d`；proposal 文件 SHA-256 为 `69fb067e6352f23c7b2abc873653545a82ed0f9f65f3f9ef668f8631b141a376`，scorer 记录的 canonical proposal hash 为 `d42622f050d39d398a1d424efa91227395b3e340c7a65d88ac8f5d106feaa4b8`。输出 score/report 文件 SHA-256 分别为 `94d804b3ba2b25acd77c1173e3fb4835778e36e99ac164088c52c3edb87eef9f`、`194037cda17a4466ba2d9ee23d7235884b958c3f347fed75867d4df493f6c1b7`，原位 scorer 重放字节一致。现有 report renderer 的 Interpretation 段仍固定描述 reference proposer；本次 run 的真实模型身份以 proposal/score metadata 为准，冻结报告未被事后改写。

H100 环境使用独立 `.venv-h100`（Python 3.13.5；Pydantic 2.10.3、pytest 8.3.4、NumPy 2.5.1、DuckDB 1.5.5；未安装 FastEmbed）。迁移验证中仅将 KEOL 测试根切换到已指定的 `/public/home/wwb/KE_mem/KEOL-44631e6`，并把 Windows-only 的父目录逃逸 fixture 改为跨平台路径；生产模块和核心 runner 未修改。验证为 focused proposal 10 passed、KEOL path 3 passed、完整 `tests/natural_memory_benchmark` 143 passed，natural identity/slice/ledger 均 valid；identity-v1、authoritative-v5 和 reference 受保护哈希均未变化。`核心影响：无`。

模型候选仍是 non-authoritative candidates。clean model-quality evidence 尚未取得，本次小型 12-case 机械双门通过不授权自动 merge、membership 写入或 L2 聚合变更，不等于最终存储选型、产品/UX 优势或外部 memory 系统对比胜出；`LONGMEMEVAL-6d550036` 继续保持 `structured_l2_identity_unresolved`。下一步必须先预注册并冻结使用 opaque `case_id`/`mention_id` 的 v2 slice，再由新的隔离 proposer 重跑；在 clean run 完成前不能进入自动接受路径。

## Natural identity/membership opaque-ID v2

2026-07-27 已完成 outcome-bearing identifier 去污染后的 opaque-ID v2 实验。实现新增 `identity_proposal_opaque.py`、`identity_model_run.py` 及对应 CLI/测试；`artifacts/identity-memory-experiment/natural-v2/` 冻结 12 个与 v1 语义等价的 case（6 dev + 6 hidden），case/mention ID 仅允许 `case-[0-9a-f]{16}` 与 `mention-[0-9a-f]{16}`。`public.json` SHA-256 为 `66e52df63f55c087e63de3f667e926c362252d5076834bb092719184cc86bbcf`，opaque policy、reverse semantic equivalence、source replay 和 manifest integrity 均 valid。

真实模型运行 `run-20260727T124023Z-codex-gpt-5-6-sol-opaque-v2` 使用新的 `fork_turns="none"` proposer，只读取冻结 prompt 与 v2 `public.json`。prompt、dispatch、proposals、provenance 在 scoring 前依次冻结；proposals SHA-256 为 `55034bc117c589baf434c6181439eaa57e3158b9a404f9ffa102769a1c5d7f8d`，provenance 明确记录 `history_context_inherited=false`、`authority_or_gold_read_before_freeze=false`，并准确限定隔离为 declarative agent file-access contract，而非 OS/container 强制隔离。

Raw proposer quality 未过门：action accuracy `0.8333333333333334`，critical false merge `1`，critical false membership `0`，abstention F1 `0.0`，proposal evidence exact rate `1.0`。两个 raw 错误均是应 abstain 的 identity case：dev 的 repository/application case 被提议为 `merge`，构成 critical false merge；hidden 的 LongMemEval project case 被提议为 `keep_distinct`，构成 abstention miss。Deterministic gate safety 单独通过：两次 intervention 都降为 abstain，gated action accuracy `1.0`，gated critical false merge/membership 均为 `0`。因此 gated 安全不能掩盖 raw proposer 失败。

正式 score/report SHA-256 分别为 `3124ade877c4aaf8d81518f75587ac219acc1ff8060b80acfadff06650d8875e`、`76ae0df98040eb269467ca4a4454955434e7bc8f899455d0abd7d76466560037`，隔离重放逐字节一致。现有 report renderer 仍保留固定的 reference-proposer Interpretation 文案，未在本波次改写；真实 proposer 身份和本次解释以冻结 proposal/score/provenance metadata 及 `error-analysis.md` 为准。最终审查后，opaque validator 进一步绑定固定 namespace 并逐项重算派生 ID，从冻结 v1 正向重建 public/authority/gold 做 canonical equivalence comparison，把 preregistration policy/validation/claim boundary 改为 strict models，并拒绝可写正式 slice 文件。验证为 focused `27 passed`、完整 `tests/natural_memory_benchmark` `160 passed`，opaque/natural identity/slice/ledger validators 均 valid，13 项受保护哈希不变，全部正式 v2 slice/run 文件为 `0444`。

`核心影响：无`。本次失败只授权在 dev/诊断数据上修复 proposer 的 false merge 与 abstention 策略；hidden 错误不得用于迭代调参，后续评测必须重新冻结版本和 fresh hidden。模型候选继续不具权威性，不授权自动 merge、membership 或 L2 写入；embedding 仍不是身份/事实权威，`LONGMEMEVAL-6d550036` 继续保持 `structured_l2_identity_unresolved`。

## Natural identity proposer dev repair and fresh-v3

2026-07-27 已完成 dev-only proposer 修复与 fresh-v3 评测。`policy-v2` 的真实 dev run 保留为失败证据：raw accuracy `0.8333333333333334`、critical false merge `1`、abstention F1 `0.0`，gate safety 单独通过。仅根据该 dev false merge 收紧可观察 coreference 规则后，冻结 `policy-v3.md`（SHA-256 `781184fe9605f401781ac3461b9f85a718236fd3b7479c0877cbb0cb02fe85c0`）及 dev/final prompts；passing dev run `run-20260727T154000Z-claude-sonnet-4-6-dev-policy-v3` 的 raw accuracy、abstention F1、proposal/required evidence exact 均为 `1.0`，critical false merge/membership 为 `0/0`，proposals/score/report SHA-256 分别为 `01aedacb4ff30e7aea0fa2f1d58186f93a4ba35cde3b2c8b80e509b839c160ff`、`a2bfbaabdc86e44b76e987ee672f7b1b2d94236380a1a8c1672ba9521a67bd48`、`924349ed9c501ca71343e96f93d3fc20953d2f9f5f40c5ec1f24c4b80856261c`。

policy-v3/final prompt 冻结后才创作 6 个新 hidden case。`identity_proposal_fresh.py` 与新 CLI 将 unchanged v2 dev semantics 和 fresh hidden 组合后，在 `natural-identity-membership-fresh-v3:2026-07-27` 下重新派生全部 case/mention ID。formal slice 为 12 cases（6 dev + 6 hidden），hidden 的 `merge/keep_distinct/abstain_identity/include/exclude/abstain_membership` 各 1 个，3 个 hidden case 跨 session；v2 ID、v2 hidden source-ID 和 v2 hidden evidence-combination overlap 均为 0。public/preregistration SHA-256 分别为 `075f3b7df9556fe48768adbdb3a3a4c93860fbc1f28a1e11894fa9390ca09a65`、`37e382080cb7346919031d4b7a0b969eb38b3c5177698eb4ec1c9388bfeab9cd`，formal 8 个 JSON 均为 `0444`。

final run `run-20260727T160000Z-claude-sonnet-4-6-fresh-v3` 通过单消息、零历史 OpenAI-compatible transport 仅读取预冻结 final prompt/public；proposals/provenance 在 scorer 读取 authority/gold 前冻结。Raw proposer quality 通过预注册门：accuracy `0.9166666666666666`、critical false merge/membership `0/0`、abstention F1 `0.8571428571428571`、evidence exact `1.0`。完整 deterministic gate contract 未通过：gated accuracy `0.9166666666666666`，原因是 1 个 hidden membership false abstention；gate 保留 proposer abstain，不反向猜测 `exclude`，critical false merge/membership 仍为 `0/0`。proposals/score/report/error-analysis SHA-256 分别为 `8621abdf18359fe04d4c3f9ea965c8ef676331eab691d11eac6115ab13831f36`、`5a4b9163acff61652cc6650cebb816587eb4f4dca3b89315f75d3af05c6f933d`、`95ccdaeed364b1c16f1ad84d7b777aa4584725fc004da98223c576f97ec11f47`、`eb1cf665893ae692ff945a19f741635d4f21f653fedd115f0832ff135713e5b6`，score/report 隔离重放字节一致，run 文件全部 `0444`。

候选生成的接入评估只保留 `public-only proposer -> immutable proposal queue -> unchanged deterministic gate` 这一非权威形态；当前不实施 pipeline 接入，更不授权自动 merge、membership 或 L2 写入。fresh hidden 错误不得用于修改 policy-v3；如需下一版，必须先在独立 dev/诊断数据上验证 actor-binding mismatch 覆盖，再冻结新 policy 与 fresh-v4。最终审查后，dev-slice builder 进一步要求输入只读且与已完整验证的冻结 opaque-v2 source 字节一致；fresh validator 要求 policy freeze 早于通过的完整 dev run、完整 dev run 早于 hidden source，并用只读 `chronology-receipt-v3.json` 的固定 SHA-256 `ad7e5e9fd8865be16afbb4e73416600455bdf7b909db60df31fe7fea77b04240` 绑定正式 policy/dev-run/hidden 的文件哈希与 mtime。正式 fresh root 同时强制使用正式 v2 source、policy freeze 与 hidden source 路径，字节相同的临时副本不能绕过固定收据。该收据明确是 posthoc filesystem audit，不是外部可信时间戳，也不把 declarative isolation 提升为独立证明。验证为 focused `42 passed`、完整 `tests/natural_memory_benchmark` `175 passed`，fresh/opaque/base/slice/ledger validators 均 valid，25 项受保护哈希不变，26 个正式与审计文件均不可写。`核心影响：无`；embedding 仍非权威，`LONGMEMEVAL-6d550036` 继续保持 `structured_l2_identity_unresolved`。

历史 ontology-memory dense run 由 Windows `.venv-dense` 生成；该环境只作迁移审计快照，不得在 H100 复用。H100 当前最小环境未安装 FastEmbed，因此这些 dense run 本轮只做冻结产物验证，不宣称完成外部模型重放。

## 本地冻结与 H100 接手（2026-07-27）

本地工作区已完成瘦身并冻结为审计副本，后续实验和实现只能在 H100 的 `/public/home/wwb/KE-mem/KE-memory-next-prep-20260727` 进行。清理主批次删除 36 个目标、97,055 个文件、3,094,694,597 bytes；测试后清理另删除 6 个文件、16,414 bytes。两份报告均为 `status=cleaned`、`remaining_target_count=0`，见 `artifacts/project-structure/2026-07-27-workspace-cleanup-report.json` 和 `2026-07-27-workspace-post-verification-cleanup-report.json`。

迁移已核对 6,586 个文件、7,426 个文件系统/归档条目和 1,412,143,854 个文件字节；迁移包 SHA-256 为 `7249031b62a04afb75407e2a95e3660df6b46b5dbde1aa0986bd115b955e1b85`，六项受保护实验/参考产物与本地哈希一致。远端临时迁移包已删除。

核心骨架继续锁定：基础本体与动态扩展接口、L1/L2 抽取、问题处理、符号优先召回和 guarded embedding fallback 非必要不得改动。dev repair 与 fresh-v3 已完成；raw proposer quality 过预注册门，但完整 deterministic gate contract 因 1 个 false abstention 未过门。下一项工作只能先在独立 dev/诊断数据上验证 actor-binding mismatch 覆盖，不得用 fresh hidden 调参；candidate generation pipeline 接入继续延期。候选结果仍不具权威性，不得自动写入 merge/membership，`structured_l2_identity_unresolved` 必须保留。完整接手 prompt 见 `docs/handoffs/2026-07-27-h100-ke-memory-next-handoff.md`。

迁移中的 `.venv-dense` 是 Windows 环境快照，不能在 Linux/H100 复用；远端已单独创建 `.venv-h100`。本地目录从此不再运行新实验、不再继续实现，只用于核对迁移来源与历史审计。

## Identity actor-binding v4.1 and fresh-v4

2026-07-28 已完成独立 actor-binding dev repair 与 fresh-v4 评测。v4 dev 将 unchanged opaque-v2 的 6 个 dev case 与 6 个独立 membership actor-binding 诊断组合为 12 cases，诊断动作 `include/exclude/abstain` 为 `2/2/2`，与 v2/fresh-v3 hidden 的 evidence/ID overlap 均为 0。H100 API 预检未提供 `codex-gpt-5.6-sol`，因此未执行的 Codex-named freeze 保留审计；实际 formal runs 使用可用的 `claude-sonnet-4-6`，不得把 proposer metadata 写成未实际调用的模型。

policy-v4 首次真实 dev run 的 raw quality 过门，但 deterministic gate safety 因旧 dev requested-membership case 的 1 个 false abstention 未过门；该轮单独冻结并记录，没有用 gated 结果掩盖 raw 错误。只在 frozen dev 上将通用 imperative requested-member 规则操作化后，冻结 policy-v4.1（SHA-256 `788f174a9644a3375783e7f31f3f55c0a95aa8ab27d302a96cd34d2b7d0c6de6`）。passing dev run `run-20260728T013000Z-claude-sonnet-4-6-dev-policy-v4-1` 的 raw/gated accuracy、abstention F1、proposal/required evidence exactness 均为 `1.0`，critical false merge/membership、gate intervention 和 structural fallback 均为 `0`。

dev 双门通过后才冻结 hidden-only fresh-v4：6 个 case 覆盖 identity `merge/keep_distinct/abstain` 与 membership `include/exclude/abstain` 各 1 个，3 个 case 跨 session，prior evidence/ID overlap 为 `0/0`。public/preregistration SHA-256 为 `2dbdfb5e0830c66dd696abed79474b5c78e062fba6100e4480e4fe2bd864b69b`、`2dfe6dcb2d78f90c2a93bbca528290034df2e6b2c712676d9b7570961d6c4166`。final run `run-20260728T031000Z-claude-sonnet-4-6-fresh-policy-v4-1` 通过单消息、零历史 OpenAI-compatible transport，只接收 frozen final prompt 与 public JSON；proposals/provenance 在 scorer 读取 authority/gold 前冻结。

fresh-v4 raw proposer quality 与 deterministic gate safety 分别通过：raw/gated action accuracy `1.0`，raw abstention F1 `1.0`，proposal/required evidence exactness `1.0`，critical false merge/membership `0/0`，gate intervention `0`。dispatch/transport/proposals/provenance/score/report/error-analysis SHA-256 分别为 `236bf748b18b6d5a6129c790e3e9dce94b30c3cda9008cce881ea787608640b9`、`f654572ded31a54ffc70725c7c6d864ec84107e475dd1d8b1cdfc9eb43dabd3e`、`aba38ed3f30fa5faf1208ff6f3ae9847822854a4d5b166679c755e6c33a386d2`、`433d79893d647e08c30dd8b63f467c633c699eed78bbeb9ba71ccdff017d3b32`、`6a47808b49302d1c14e34dad4d67c062484909892c7de8137eed795e05259b75`、`5851955aebc8dc0726cb7ae617c2b3fdcb3067b5509e947e92cd2a59ad328007`、`cb1859f644e1f0f9127807dda0021c88c5fd13d72416c330ec8a1a47b57d2e97`；score/report replay 字节一致。

该结果只稳定了小型 proposal-only identity capability，不授权自动 merge、membership 或 L2 写入，也不把 embedding、schema.org、Extended-AMR 或任何 profile 提升为事实权威。`LONGMEMEVAL-6d550036` 继续保持 `structured_l2_identity_unresolved`。下一阶段先评估 `public-only proposer -> immutable proposal queue -> unchanged deterministic gate` 如何只读接入现有 identity candidate generation；随后验证自动 L1/L2 抽取、问题编译、证据闭包、跨 session 聚合和更大真实 benchmark，最后再比较 Extended-AMR、KEOL projection 与其他 profile 的存储效率、执行能力和运维成本。

## Identity candidate-generation integration assessment v3

2026-07-28 已完成 candidate generation 的离线只读接入评估。新增 `identity_candidate_assessment.py`、`assess-identity-candidate-generation` CLI、严格 review-envelope/queue schema、输入 SHA 绑定、duplicate public case/mention 拒绝、score outer contract/readiness/metrics 一致性复核、按 subject-ref 计数的 compatibility mapping、唯一 L1-to-source evidence-chain 校验、fail-closed mutation guard 和对应测试；没有修改 `identity_resolution.py`，也没有生成 `IdentityDecision`、membership、closure、snapshot、aggregate 或 L2 写入。assessment 只读取 frozen fresh-v4 `public.json`、`proposals.json` 与独立 scorer 的 `score.json`，不直接读取 authority/gold，也不调用 proposer。gold-dependent action accuracy 仍属于上游 scorer 证据，本阶段只复核 frozen hashes、门槛和可由 gated decisions 独立重算的结构指标。

正式 fresh-v4 assessment 生成 4 个 `eligible_for_manual_review` 候选和 2 个 `gate_abstained` 候选。raw proposer quality 与 deterministic gate safety 继续分别为 pass；case/mention mapping rate 为 `1.0/1.0`，但对代表性只读 identity guard bundle 的 existing entity、L1 evidence、source revision、evidence chain binding rate 均为 `0.0`，authoritative materialization ready count 为 `0`。4 个非 abstain 动作全部记为 blocked authoritative writes，automatic authoritative writes 为 `0`；guard bundle 的 entity/decision/closure/snapshot/aggregate/membership-write/L2 counts 和 canonical fingerprint 在前后完全不变。因此 assessment 自身为 `pass`，但 `candidate_generation_integration_ready=false`。

复审前 v1/v2 freeze 保留为不可变审计产物，不作为最终完成证据。正式只读产物位于 `artifacts/identity-memory-experiment/candidate-generation-assessment-v3/`。queue/assessment/report SHA-256 分别为 `518ead9de8627a9a4384df8cdd9b8728a21fcf797f6b0f3d208dfcb28ac41c0f`、`49ef708c77561680703e578de140a9d664a0a774dd48dfda0af038bbdc09c7cf`、`a4ab8ac584bfde78469244c42e8adc63cd79eecbe14a6eb27f636b9fd74f1b3b`，原位重放字节一致，文件均为 `0444`。最终新鲜验证为 focused assessment `16 passed`、全部 identity `82 passed`、完整 `tests/natural_memory_benchmark` `219 passed`，`compileall` 成功；natural-v1、opaque-v2、fresh-v3、dev-v4、fresh-v4、slice-v1 和 ledger validators 均为 `valid`，fresh-v4 受保护 proposal/score/report 哈希不变。该结果只证明 non-authoritative review queue 的边界和测量工具可用，不授权自动身份或成员关系写入；embedding 仍非权威，`LONGMEMEVAL-6d550036` 继续保持 `structured_l2_identity_unresolved`。下一阶段转向自动 L1/L2 抽取、问题编译、证据闭包、跨 session 聚合和真实 benchmark 扩展。

## Automatic L1/L2 extraction bridge assessment v3

2026-07-28 已完成既有两阶段真实模型抽取结果到 authoritative L1/L2 contract 的只读兼容性评估。没有重跑模型，也没有修改 `knowledge_pipeline`、authoritative memory、identity resolution、问题处理、符号召回或 guarded embedding fallback。新模块 `extraction_bridge_assessment.py` 与 CLI `assess-automatic-l1-l2-extraction` 严格重放 43 个 turn-pass、10 个 dialogue reconciliation 和 416 条 projected knowledge，逐项绑定 manifest、`run.json`、source segment、EvidenceSpan offset/occurrence 与冻结 `final-knowledge.json`；每条记录只生成 non-authoritative compatibility envelope。

Raw extraction structure 与 deterministic bridge safety 分开报告。Raw 侧有 416 projected、390 active、402 single-turn evidence records、14 cross-turn evidence records、436 evidence references，exact evidence binding rate 与 source-status admissibility rate 均为 `1.0`；这些指标不包含 gold semantic accuracy。Bridge 侧 L1/L2 candidate 为 `402/14`，authoritative-ready 为 `0/0`，416 条全部阻止 materialization，所有 L1/L2/unit-revision/closure/identity/membership automatic write count 都为 `0`。共同缺口是 memory kind、predicate sense、canonical operator、typed role bindings 和 candidate-scoped local entity IDs 各 `416`；typed time `64`、unsupported modality `52`；14 个 L2 candidate 还全部缺 supporting L1 IDs、structured claim、abstraction method、closure specification 和 source turn/session coverage。guard fingerprint 前后均为 `e184b6caf2998acf1c8700bc84d24bbafd49ab9c8f15738d1af8cc484ee5ebcc`，`automatic_extraction_integration_ready=false`。

bridge-v1/v2 均保留为不可变审计结果，但独立复审发现 v1 漏掉 condition/scope、非显式 derivation、speaker binding 等 typed gap，v2 又漏验 `confirmed_by`/`added_by` operation ownership，其中 foreign `added_by` 可改变 L1/L2 分类。v3 从冻结 dialogue validated files 重建并校验 operation ID -> candidate 映射，拒绝 unknown/cross-candidate confirm/add 引用，并在 envelope 中逐条保留 operation provenance；同时补齐 lifecycle、envelope coverage、optional object 指标和 evidence quote/occurrence/offset 直接故障路径。

正式只读产物位于 `artifacts/automatic-extraction-assessment/bridge-v3/`。ledger/assessment/report SHA-256 分别为 `2ed9e6fdeaca81964fff542287adfc2980145b978b7ef9ed6dfc5f914ebca7c0`、`d5d00b2edebdaf7b2409f09a647c0bce41d1ce29e5c2e1d3c67e646fb5f5e92e`、`b7e29b605ac46b0ff85c1be963f9d3fca7693f3c445a64188f67b8eecc3d9bf9`，三份文件均为 `0444`，隔离重放逐字节一致。v3 指标为 416 projected、390 active、402 L1、14 L2、authoritative-ready `0/0`、materialization blocked `416`、automatic writes 全部 `0`；object present `397/416`，condition `51`、scope `79`、non-explicit derivation `68`。除既有 kind/predicate/operator/role/local-ID/time/modality/L2 gaps 外，typed extractor 合同现在显式要求 condition/scope、derivation/inference provenance 和 evidence speaker binding。guard fingerprint 仍为 `e184b6caf2998acf1c8700bc84d24bbafd49ab9c8f15738d1af8cc484ee5ebcc`。

新鲜验证为 focused bridge `51 passed`、`tests/knowledge_pipeline` `197 passed`、完整 `tests/natural_memory_benchmark` `270 passed`、`compileall` exit `0`；bridge-v1/v2 哈希未漂移。为运行既有 knowledge-pipeline 回归，H100 `.venv-h100` 已补装 `nltk 3.10.0`。下一步只在 dev/诊断数据上开发 typed extractor v2，先执行 L1 dev qualification，再执行 L2 dev qualification；两个 dev gate 通过前不创建 fresh hidden evaluation，更不授权任何 authoritative write。embedding 仍非事实或身份权威，`LONGMEMEVAL-6d550036` 继续保持 `structured_l2_identity_unresolved`。

## Typed extractor v2 L1 dev qualification

2026-07-28 已完成 typed extractor v2 的 L1 dev qualification。实现新增严格 typed L1 proposal/scorer/model-run 合同和五个 CLI，使用 bridge-v3 的 frozen single-turn candidates 构造 12-case dev slice，覆盖五种 L1 kind、user/assistant/tool 来源、active/corrected/superseded lifecycle、condition/scope/operation provenance、resolved/unresolved time、2 个 abstain 和 1 个 no-memory。所有 proposal 继续是 non-authoritative candidate。

失败迭代均保留。初始 prompt 未暴露精确嵌套 JSON schema，第一份 staged output 被 freeze 层以 150 项 schema error 拒绝，原始文件只读归档为 `rejected-staged-proposals.json`，没有伪装成有效 proposal。dev-v1 的 schema-correct run 随后得到 `raw_proposer_quality_ready=false`、`deterministic_gate_safety_ready=true`，暴露 private exact labels 无法从 public input 重建；dev-v2 在 public 中冻结全局 canonical operator/sense/role/time/modality policy 后消除了 decision、evidence 和 predicate 错误，但 kind/role/qualifier/time 仍未过门。修复只发生在这 12 个 dev cases 上，没有创建 hidden 数据。

最终 formal slice 位于 `artifacts/automatic-extraction-assessment/typed-extractor-v2-dev-v3/`。passing run 为 `run-20260728T060140Z-deepseek-v4-pro-typed-l1-dev-v6`，实际 proposer metadata 是 `openai-compatible-api` / `deepseek-v4-pro@2026-07-28-prompt-v4-policy-v2`；它通过一次全新无历史 API 请求，只接收 frozen prompt/public。proposals/provenance 在 scorer 读取 authority/gold 前冻结，provenance 记录 `history_context_inherited=false` 与 `authority_or_gold_read_before_freeze=false`。raw proposer quality 与 deterministic gate safety 均通过：coverage/schema/decision accuracy/abstention F1/evidence/kind/predicate/modality/time/lifecycle/derivation/operation accuracy 均为 `1.0`，role/local-entity 与 condition/scope accuracy 均为 `0.8888888888888888`，critical false emission `0`，gate intervention `0`，deterministic critical false materialization `0`。唯一残留 raw error 是 `case-4ffef5523d302472` 的 condition participant/local-entity binding；它未被 gated 结果掩盖。

authoritative guard fingerprint 前后均为 `e184b6caf2998acf1c8700bc84d24bbafd49ab9c8f15738d1af8cc484ee5ebcc`，所有 L1/L2/unit-revision/closure/identity/membership automatic write count 为 `0`，embedding authority 为 false，`LONGMEMEVAL-6d550036` 仍为 `structured_l2_identity_unresolved`。final source/prompt/public/authority/gold/manifest SHA-256 分别为 `14b3c4972607b29370db126f0d0a44866bc843915952b306bfc4faab62bcc686`、`06010ca3c4b9a7108f2e8806ec76ec54d94b1c214aa5eaac5b87fb3825abdf28`、`ba88d08f2ab5ece4892166fbf3c1e04e06756ade942312c12aa5cbe7b5da873f`、`7eeba6b787a4d798dd48176b71351494c2b1bf7f8994b45bf8e863a2eb44be08`、`3b239173372b4e2d99312ce6b364e5d290de482462125f5bde501cc509db3336`、`690317022bd396b274744c9b968819ed68945796984fcd0f886db7f27cb11b96`；dispatch/raw-response/proposals/provenance/score/report/error-analysis SHA-256 分别为 `7474f2c201525f0218bd3f89d75bda89ea28a39bec067e46f29949b12df98d43`、`14ed372267e162f5e7113d3097bc28154ce9fad6b107a53ae25d05ccf2e3eba7`、`7c765a4185c4b28ecdbb0bf23702e0bbf1931c7c11a4d9b5c420bf80b3952899`、`10f2d2aabf78968880f09af45046c9bbac64ea38047a1b40e45c00aec4e9b612`、`db0fcc05e9ab3a4c64eac45062eb1a35447e7740b2566baa5fbd8575a3bcbefe`、`c1f088f8e13b962cd4a1ea2719ac4aee8f38a3ef4ef2c1d7fb7c6d3bed6e1ace`、`20d60fbee8c211290663434956ee6ac7577fe2ad274190670f0246bc190cd0fb`。所有正式文件为 `0444`，score/report/error-analysis 隔离重放逐字节一致。

最终新鲜验证为 typed L1 focused `22 passed`、knowledge pipeline `197 passed`、完整 natural benchmark `292 passed`、`compileall` 成功；slice/ledger、natural-v1、opaque-v2、fresh-v3、dev-v4、fresh-v4 和 typed L1 validators 均为 `valid`，bridge-v3 隔离重放字节一致，identity-v1、authoritative-v5、fresh-v4、candidate-assessment-v3 与 bridge-v3 保护哈希未变化。该结果当时只解锁 L2 dev qualification；L2 的后续结果见下节。

2026-07-28 在 fresh hidden 预注册前补齐了 L1 与 L2 对称的 provenance v2 审计链。新增 `typed_extractor_l1_api_run.py`，dispatch 现在绑定 requested model，raw response 以只读文件归档；freeze 强制 staged proposals 与 raw response 完全一致，并按 `dispatch -> raw_response -> proposals -> provenance` 冻结；scorer 再重验 dispatch/raw/proposals/public 的完整 hash 与 requested/response model 元数据。官方 `deepseek-chat` dev v7、v8 分别保留为 raw fail/gate safe 记录；只在 12 个 dev case 上修复 unresolved deictic time、causal hypothesis、scope 和 condition participant 的 public policy 后，prompt V6（SHA-256 `a4d03b0e3717be47a3cd32358f6ca881d4be55bac804bc343999b6b22b835586`）的 v9 run `run-20260728T091848Z-deepseek-chat-official-typed-l1-dev-v9` 通过双门。requested alias 为 `deepseek-chat`，raw response model 为 `deepseek-v4-flash`，隔离仍只是 declarative file-access contract。

v9 raw decision、abstention F1、evidence、kind、predicate、modality、time、derivation 和 operation provenance accuracy 为 `1.0`，role/local-entity、condition/scope、lifecycle 为 `0.8888888888888888`；`case-4ffef5523d302472` 仍有三类 raw field error，gate 因 `lifecycle_not_authorized` 将其降为 abstain，所以 gated decision accuracy 为 `0.9166666666666666`。raw critical false emission 和 deterministic critical false materialization 均为 `0`，不能用 gate demotion 掩盖该 raw error。v9 proposals/provenance/score/report/error-analysis SHA-256 分别为 `dd28482420680604a8ac85c10bf6506079420f882300393af1cb0fdb2bdfeac2`、`400217f3cb0343ceb2d61c03f905bc9f32147cf937e648f9497525adbecc52cc`、`e2bd3a3c613b927d4f065b8c2fbfd4d33fe43b8c05f6fa9c25b5173195443612`、`8837be4319a390024faea9eb04b12d990a44a3d10df51a371977bb9320ab72f1`、`18079f2db49cb42ce3bdcc7690781b428a13f86b2e3fbe5b6cd8e37054ed0283`，均为 `0444` 且评分三件套重放一致。

由于 L1 root 现在有两个合法 passing run，L2 builder 不再依赖“目录中恰好一个 pass”的脆弱假设；只读 `l2-source-qualification-receipt.json`（SHA-256 `27e5f46e1bf8614bc5573b388a573309117233f2ed1608c0fc6a72131fd70544`）显式选择 L2 原先绑定的 v6 五项 hash，现有 L2 manifest 因此保持字节不变。最终验证为 typed L1/L2 focused `58 passed`、knowledge `197 passed`、natural benchmark `364 passed`、compileall 成功；所有 formal validators valid，candidate v3 queue 仍为 `518ead9d...41c0f`，密钥模式扫描为空，automatic writes 全为 `0`。

## Typed extractor v2 L2 dev qualification

2026-07-28 已完成 typed extractor v2 的 L2 dev qualification。最终 formal slice 位于 `artifacts/automatic-extraction-assessment/typed-extractor-v2-l2-dev-v9/`，包含 6 个冻结 dev case（4 个 `emit_l2`、2 个 `abstain`），覆盖 `coreference_resolution`、`lifecycle_resolution`、`task_composition` 以及 `multi_evidence_set`、`update_supersession`。proposer 只读取 frozen prompt/public，typed L1 support pack 仍是非权威候选。

失败历史均保持不可变。v7/v10 虽得到机械双门通过，但独立复审发现 standalone scorer 可信任被降低的 manifest threshold，且 provenance 未绑定 raw response 与实际返回模型，因此只保留为审计历史。修复后 v8/v11 首次使用 provenance v2；其 raw 决策、abstention、证据、support、closure 和 coverage 均正确，但 1 个主 claim 错把 L1 support 的 predicate surface 复制到 L2 claim，`structured_claim_accuracy=0.75`，所以 `raw_proposer_quality_ready=false`，而 gate safety 单独为 true。该错误只在 dev 上按 `structured_claim_error` 修复，没有创建或查看 fresh hidden。

最终 passing run 为 `run-20260728T084011Z-deepseek-chat-official-typed-l2-dev-v12`。冻结 dispatch 请求官方别名 `deepseek-chat`，API raw response 报告实际模型 `deepseek-v4-flash`；两者在 provenance 中分开记录，不能互相替代。provenance v2 绑定 dispatch、请求模型、raw response、返回模型、proposals 和 `dispatch -> raw_response -> proposals -> provenance` 顺序，scorer 再验证 raw-to-proposal 一致性；隔离仍是 declarative fresh-agent file-access contract，不是 OS/container 强制证明。proposals/provenance 在 scoring 读取 authority/gold 前冻结。

v12 的 raw proposer quality 与 deterministic gate safety 均通过：decision accuracy、abstention F1、evidence、support、kind、structured claim、abstraction、closure、source coverage 和 summary accuracy 全为 `1.0`；raw critical false emission、gate intervention、deterministic critical false materialization 均为 `0`。guard fingerprint 前后均为 `e184b6caf2998acf1c8700bc84d24bbafd49ab9c8f15738d1af8cc484ee5ebcc`，所有 L1/L2/unit-revision/closure/identity/membership automatic write count 为 `0`。

最终 source/prompt/public/authority/gold/manifest SHA-256 分别为 `150f0f3405f82aa9c51dfd9d3912ccc2ff9f308919cd32f95d8bade343610b3e`、`55fddf350d4a2c821000436aa4ce4c614da589ffe053ea5ab4c1bb7e774e60c7`、`36b1be5abe0ae09136da83310b5ef7019c808800d34b22102ecce6457849c7ba`、`0b45b151d65954826a80288ab39a32ca4b5e49769ad183d16ac145a2445d0dc1`、`6f966803a624f6774f546cbf2096fa7a10dcc3313366f9891ed76aa3aed92c28`、`37eb0f3a2d0414ff6d318e933764c0b36b53ef4a325d7b876db05758afcd19f2`；dispatch/raw-response/proposals/provenance/score/report/error-analysis SHA-256 分别为 `c06fb1b7b27d688490efc06581e33e859c4a0f3dd2a2336a8d770a993a0fffea`、`f42e134443608a30e2570ba5f4e6e461af164c8c5ee3002028d0c19a72ed8d9b`、`655c696154d7e623ae417d3c5978a23ac7f7fb611e1b9f27ef21f7e25344e2c9`、`df905c9ed119eff40b39239243b53ef1ccfc6aced39b5b377854233fcc421d26`、`e27be9f426a78bf67fb03938ce97aeccc697e071bf866494d9a1d319fed4db57`、`c7cdd49adb166112c5a6ba6a64ef3c398f01c979bd4591c3135d911eafe8d600`、`4027cc8efb89f11b62ccabcf6b17b59ea6b4400019b23f2091b11e9cce2343e1`。v7-v9 的 39 个正式文件均为 `0444`，v12 score/report/error-analysis 重放逐字节一致。

最终验证为 focused L2 `31 passed`、knowledge pipeline `197 passed`、完整 natural benchmark `352 passed`、`compileall` 成功；L1/L2、natural identity v1/v2/v3/v4、benchmark slice/ledger validators 均 valid，bridge-v3 重放三项哈希一致，candidate v3 review queue 仍为 `518ead9de8627a9a4384df8cdd9b8728a21fcf797f6b0f3d208dfcb28ac41c0f`，未物化四项人工裁决。该 dev pass 只授权下一步预注册 fresh hidden typed-extraction evaluation；不授权 pipeline integration 或任何 authoritative write。embedding 仍非事实/身份权威，`LONGMEMEVAL-6d550036` 继续保持 `structured_l2_identity_unresolved`。

## Typed extractor fresh hidden preregistration

2026-07-28 已在任何 hidden source/public/authority/gold 创作前冻结 fresh-hidden v1 预注册。设计与计划位于 `docs/designs/2026-07-28-typed-extractor-fresh-hidden-evaluation-design.md` 和 `docs/plans/2026-07-28-typed-extractor-fresh-hidden-evaluation-plan.md`；严格 contract/CLI 位于 `tools/natural_memory_benchmark/typed_extractor_fresh_prereg.py`。正式只读文件是 `artifacts/automatic-extraction-assessment/typed-extractor-v2-fresh-hidden-prereg-v1/preregistration.json`，SHA-256 为 `9ec35f71c86c0e2c0257438d01445d9f0a490eee57a0d582ccb01024ffc0921c`，mode `0444`；冻结时 `typed-extractor-v2-fresh-hidden-v1/` 不存在，validator 返回 `status=valid`、L1 `24`、L2 `8`、`hidden_artifacts_absent=true`。

预注册固定 L1 prompt V6、最终 L2 prompt、bridge/source/dev exclusion、现有 scorer/model-run code hashes、requested model `deepseek-chat`、L1/L2 namespace、selection policy 和原阈值。L1 将按公开结构 strata 与固定哈希选 24 条；L2 将使用 6-case dev 之外全部 8 条 cross-turn records，禁止人工挑优。每层只有一次 semantic run；hidden 语义失败不能原地修 prompt，必须回到新 dev/diagnostic 并另行预注册 fresh-v2。预注册仍不授权 pipeline integration 或任何 L1/L2/identity/membership/closure/revision/snapshot/aggregate 写入，人工 identity 裁决未物化，`LONGMEMEVAL-6d550036` 保持 unresolved。

## Typed extractor fresh hidden v1 final result

2026-07-28 fresh-hidden v1 已完成并关闭，不重试、不用 hidden 原地调参。L1 24-case official DeepSeek run 请求别名为 `deepseek-chat`、响应模型为 `deepseek-v4-flash`；raw proposer quality 为 fail：decision accuracy `0.7916666666666666`、abstention F1 `0.5714285714285715`、exact evidence `0.8947368421052632`、critical false emission `3`。deterministic gate safety 单独为 pass：intervention `4`、critical materialization `0`。错误包括两个 control/no-memory 和一个未授权语义的 false emission、两个 false abstention，以及 condition/scope、time、role、evidence、lifecycle 等字段错误。

L2 8-case run 同样请求 `deepseek-chat`、响应 `deepseek-v4-flash`；raw proposer quality 为 fail：decision accuracy `0.625`、abstention F1 `0.0`、critical false emission `3`。evidence/support/source coverage/closure/summary 为 `1.0`，但 abstraction `0.4`、structured claim `0.6`；三个应 abstain case 全部错误 emit，另有三个 abstraction、两个 structured claim 和一个 kind 错误。deterministic gate safety 单独为 pass：intervention `6`、critical materialization `0`。不得用两层 gate pass 掩盖 raw failure，当前不授权 pipeline integration 或任何 authoritative write。

总报告位于 `artifacts/automatic-extraction-assessment/typed-extractor-v2-fresh-hidden-v1/overall-report.md`。prereg/chronology SHA-256 为 `9ec35f71c86c0e2c0257438d01445d9f0a490eee57a0d582ccb01024ffc0921c`、`2f2c38e475a8b25a3a553333ea4733f6428f505a5adb8e6c95bdfd0964fbc699`；L1 score/report/error SHA 为 `84940b212079127f6b16f90b93a317fda86e19822d173624266f40254611ec16`、`9cd92d83b0629159eb71ac394534a726f6fe52cce5980c3d23ebca687fa42e41`、`040b1c88209f71169553fedd3bd26e09ab604b4fdb7022de7417023ec643cfc6`，L2 为 `12fc340bafc7e9645b835289237ef709384eedefa5a7818fb5c7132e744de5d8`、`a924a8f4579f04d5f5d4d7cf4181736f71ae96ac93885f6b0240454424d6f779`、`35f8467792dfef038bb8875cf4ae23c5a51234efd7bb0167abf1a9ae35cd178f`；评分三件套与 bridge-v3 均重放一致。

最终验证为 fresh-focused `14 passed`、全部 typed `72 passed`、knowledge pipeline `197 passed`；identity v1-v4、slice/ledger、typed dev、fresh L1/L2/chronology validators 均 valid。candidate v3 queue 仍为 `518ead9de8627a9a4384df8cdd9b8728a21fcf797f6b0f3d208dfcb28ac41c0f`，四项人工裁决未物化，automatic writes 全为 `0`，密钥未落盘，`LONGMEMEVAL-6d550036` 仍为 `structured_l2_identity_unresolved`。下一步只在新 dev/diagnostic 数据上按 L1 false emission/abstention/evidence/qualifier/time/role/lifecycle 和 L2 abstention/abstraction/claim/kind 分类修复，通过后另行冻结 fresh-v2；并行 question compiler 工作不得消费失败 extractor 作为权威输入。

此前缺失的 query compiler assessment 模块已由并行工作补齐；当前又出现一个独立的 `test_query_execution_snapshot_adapter.py`，但对应 `query_execution_snapshot_adapter` 模块尚未落盘，因此无条件 natural-memory suite 在 collection 阶段失败。本轮不修改该并发 query 工作；排除这个孤立文件后的新鲜回归为 `464 passed`，typed extractor 为 `105 passed`，knowledge pipeline 为 `197 passed`，`compileall` 成功。

## Typed extractor diagnostic public-contract v2 baseline

2026-07-28 已完成 prompt-complete diagnostic public contract v2 与 unchanged-prompt baseline。旧 v1 public catalog 在模型请求前被 preflight 拒绝，未发送模型请求，并保持不可变。正式 v2 roots 为 `typed-extractor-v2-l1-dev-repair-v2` 和 `typed-extractor-v2-l2-dev-repair-v2`；L1 V6 prompt SHA-256 为 `a4d03b0e3717be47a3cd32358f6ca881d4be55bac804bc343999b6b22b835586`，L2 V8 为 `55fddf350d4a2c821000436aa4ce4c614da589ffe053ea5ab4c1bb7e774e60c7`。

两次全新无历史、public-only 官方请求均请求 `deepseek-chat`，raw response 均标识 `deepseek-v4-flash`；proposal/provenance 在 authority/gold scoring 前冻结。L1 run `run-20260728T120704Z-deepseek-chat-official-typed-l1-dev-repair-v2` 的严格 raw quality 为 fail、gate safety 为 pass：除 `role_or_local_entity_accuracy=0.9166666666666666` 外全部 strict metric 为 `1.0`，唯一错误是未把 `a review with Dana` 中显式 participant `Dana` 分解为独立 local entity，gate intervention 为 `0`。L2 run `run-20260728T120705Z-deepseek-chat-official-typed-l2-dev-repair-v2` 的严格 raw quality 与严格 gate safety 均为 fail：`abstraction_accuracy=0.875`、`structured_claim_accuracy=0.875`、gate intervention `1`；错误分别是 persistent state 错选 `coreference_resolution`，以及 archive coreference claim 复用 L1 的 `document.archive_request` sense。

两层 raw critical false emission、false abstention、evidence error、deterministic critical materialization 和 automatic write 均为 `0`，guard fingerprint 均保持 `e184b6caf2998acf1c8700bc84d24bbafd49ab9c8f15738d1af8cc484ee5ebcc`。candidate v3 queue SHA-256 仍为 `518ead9de8627a9a4384df8cdd9b8728a21fcf797f6b0f3d208dfcb28ac41c0f`，四项人工裁决未物化，`LONGMEMEVAL-6d550036` 继续为 `structured_l2_identity_unresolved`。下一步严格限制在 diagnostic prompt repair：L1 补显式 participant 分解；L2 补 abstraction dominance 和 versioned operator/sense pair catalog。双层 strict diagnostic gate 通过前不得预注册 fresh-hidden v2，更不授权 pipeline integration 或权威写入。

## Typed extractor diagnostic prompt repair final result

2026-07-28 diagnostic prompt repair 已关闭。L2 使用新增 `operator_sense_bindings` 的 v3 contract，正式 run `run-20260728T123925Z-deepseek-chat-official-typed-l2-dev-repair-v9` 的 decision、abstention F1、evidence、support、kind、structured claim、abstraction、closure、source coverage 和 summary strict metrics 均为 `1.0`，gate intervention 与两类 critical count 均为 `0`。L1 的失败迭代保持不可变：V7 修复 request modality 但仍有 2 个 role/modality 错误；V8 的 modality 已正确，但出现 4 个 role/local-entity 错误；V9 修复 3 个 source-turn 代词覆盖错误，但仍有 1 个 participant head 错误，并新增 1 个 question-only decision error。没有用各轮 deterministic gate safety 掩盖这些 raw failures。

最终 L1 V10 prompt 把 question-only `no_memory` 置于 modality 判断之前，并将显式 ` with `/` for `/` to ` participant 分解改成左右子串算法。正式 run `run-20260728T130544Z-deepseek-chat-official-typed-l1-dev-repair-v10` 请求 `deepseek-chat`、raw response 标识 `deepseek-v4-flash`；proposals/provenance 在 authority/gold scoring 前冻结。L1 的 proposal coverage、schema、decision、abstention F1、evidence、kind、predicate/operator、role/local entity、modality/polarity、time、condition/scope、derivation/speaker、lifecycle 和 operation provenance strict metrics 全部为 `1.0`，gate intervention、raw critical false emission、deterministic critical materialization 均为 `0`。L1 prompt/proposals/provenance/score/qualification SHA-256 分别为 `b868bb2baaf1dfb3c27f99e2fe29888e2af0c57e56be3d2ecf70bfb6d2bcdfcf`、`7cca8c171d784fbee1ea4849c52403fa6446f3d78fe746cec4134a3effb95c39`、`8a2ef39bf2da9a059a24537505b05f5391a1806f5012642fa173864746dbf483`、`993200f235b075b4f7e5e72bf37d19cc8427d360ce75ab5375f91f3e7923ba43`、`377d91553db76fa1e3d48602e739aed255b107fca3856a35908234c769cb93a0`。

双层 raw proposer quality、deterministic gate safety 和 strict dev-repair qualification 现在均通过。guard fingerprint 前后仍为 `e184b6caf2998acf1c8700bc84d24bbafd49ab9c8f15738d1af8cc484ee5ebcc`，automatic L1/L2/revision/closure/identity/membership writes 全为 `0`，candidate v3 queue 未漂移，人工 identity 裁决仍未物化。该结果只授权下一步冻结 fresh-hidden v2 预注册，不创建 hidden、不授权 pipeline integration 或权威写入；embedding 仍非权威，`LONGMEMEVAL-6d550036` 继续为 `structured_l2_identity_unresolved`。

新鲜验证为 typed extractor `114 passed`、knowledge pipeline `197 passed`、完整 natural memory benchmark `485 passed`、`compileall` 成功；L1/L2 scorer 与 qualification 原位重放哈希一致，L1 v2/L2 v3 contract validators 均为 `valid`，正式 run 文件全部不可写，repository key-pattern scan 为 `0`。额外 workspace hygiene 测试为 `19 passed, 1 failed`；失败是既有 Windows 反斜杠路径在 Linux 上先触发 missing-target 而非 duplicate/canonical 错误，本轮未修改 cleanup 逻辑，也未执行删除。

## QuerySlotPlan V2 自动编译与验证执行快照

2026-07-28 已完成独立、表示无关的 QuerySlotPlan V2 开发波次。设计与计划位于 `docs/designs/2026-07-28-query-slot-plan-auto-compiler-design.md` 和 `docs/plans/2026-07-28-query-slot-plan-auto-compiler-plan.md`；实现位于 `query_compiler_v2.py`、`query_plan_v2_executor.py`、`query_compiler_v2_assessment.py`、`query_compiler_v2_cli.py` 和 `query_execution_snapshot_adapter.py`。本波次没有修改 `typed_extractor_*`、fresh-hidden artifact 或共享 `cli.py`，也没有授权任何 memory/identity/membership/L2 自动写入。

当前路径为：`natural query draft -> deterministic linking/gate -> CompiledQueryPlanV2 -> verified Git memory snapshot -> representation-neutral executor -> evidence bundle or abstention`。snapshot adapter 只接受通过 authoritative bundle integrity、TurnBundle closure、精确 Git artifact 和 current-revision ownership 校验的数据；artifact 固定读取已验证 commit，bundle logical ID 必须匹配。没有 identity snapshot 时所有实体默认 unresolved；提供 snapshot 时，scope 外实体仍为 unresolved，不能绕过 `count_distinct` identity gate。fact 必须携带 revision provenance，snapshot 必须绑定 authoritative bundle ID。

executor 当前支持单事实、AND/OR、多跳共享变量、canonical identity join/count、exact/latest time、source/lifecycle/conflict、evidence closure 和显式 abstention。latest 遇到任一候选缺失或非 ISO-8601 时间会 abstain；explicit absence 在 absence closure fact 尚未实现前固定以 `explicit_absence_unsupported` abstain。active L2 当前只接受单 structured claim；多 claim 需要先把上游单一 `closure_evaluation_id` 升级为 per-claim closure，不能直接生成未闭包 fact。

验证结果：Query 五模块 `55 passed`，相邻 authoritative/Git history/TurnBundle/identity/representation `116 passed`，完整 `tests/natural_memory_benchmark` `485 passed`；`compileall`、`tabnanny` 和 100 字符行长扫描通过。生产文件 SHA-256：compiler `d7a7e6bb2cb502231842461d23a7ef174c552596d57039afce3580c3418ad34e`，executor `69fabb15770e2f271bb8de3814333434e5bcaa3be80fb6aebadaa7a3218c4138`，assessment `54691969243b364ccccf6d486ced4be45e792cfe4175696f6881bfaf06c40e2b`，standalone CLI `bc341ce9f3c6fbccae3815405c672e584aada3fab8e682c4e5334e955a69ce6b`，snapshot adapter `764b429acd4c19dae33b704625765711d28a945d3f2d7efff624dc3eb3e71e1b`。

该结果证明 compiler/executor/snapshot contract 已实现并通过当前回归，不证明自然语言 raw proposer quality、fresh-hidden formal readiness、最终存储选型、完整端到端答案生成或相对外部 memory 系统的优势。下一步仍需把 plan 的 ontology/identity revision 与 verified snapshot/registry 做程序化绑定，设计 per-claim L2 closure，冻结自然 query dev/fresh-hidden 评测，并接到下游 evidence/answer eval。

## Typed extractor fresh-hidden v2 preregistration

2026-07-28 已在 authoring implementation、authoring test、implementation receipt 和 future evaluation root 全部不存在时，冻结 fresh-hidden v2 预注册。设计、计划和独立 contract 分别位于 `docs/designs/2026-07-28-typed-extractor-fresh-hidden-v2-preregistration-design.md`、`docs/plans/2026-07-28-typed-extractor-fresh-hidden-v2-preregistration-plan.md` 和 `tools/natural_memory_benchmark/typed_extractor_fresh_v2_prereg.py`；v1 contract 与正式 preregistration 保持不变。

首个 `typed-extractor-v2-fresh-hidden-prereg-v2/preregistration.json`（SHA-256 `0ac045b0cbed26a2fb624bc1f70d8275ae94edb41a57e868bae78c6effadc243`）在 code review 后被 supersede，但保持 `0444` 不改写。原因是 schema 未启用 strict mode，字符串/布尔值可被 Pydantic 转换后通过；同时 chronology 只校验时间形状，却错误声称记录了 filesystem mtime。hardened schema v2 启用 strict types、真实 UTC 解析，并把 evidence 准确降为 `filesystem-presence-plus-sha256`，freeze time 明示为 `caller_supplied_untrusted_utc_label`；旧 v2 在新 validator 下明确失败，不再作为当前正式 prereg。

当前正式文件为 `artifacts/automatic-extraction-assessment/typed-extractor-v2-fresh-hidden-prereg-v3/preregistration.json`，冻结时间 `2026-07-28T14:08:22Z`，SHA-256 `1455bb7d5bb35b61809c78180ebf766573c1561e39bbeddda4a80f939a893760`，size `11016` bytes，mode `0444`。validator 返回 `status=valid`、L1 `24`、L2 `12`、`future_artifacts_absent=true`、`hidden_artifacts_created=false`。合同绑定 47 个 final dev/diagnostic/fresh-v1 输入和 9 个 contract/scorer/model-freeze/test 代码文件；L1/L2 分别固定 14/12 项 exact `1.0` quality metrics，raw critical false emission、gate intervention 和 deterministic critical materialization 均固定为 `0`。

v2 不再复用已耗尽的 bridge L2 remainder。deterministic authoring 已使用全部预注册 blueprint：L1 六个 family 各 4 条，L2 六个 family 各 2 条；禁止 semantic filtering、替换和 post-generation resampling。实现位于 `tools/natural_memory_benchmark/typed_extractor_fresh_v2_authoring.py`，测试位于 `tests/natural_memory_benchmark/test_typed_extractor_fresh_v2_authoring.py`。L2 primary claim 现在逐条强制精确绑定 public predicate、subject、object/theme 和完整 support set；travel case 使用一个 `aggregate_travel_profile` aggregate claim，同时保留两个独立 L1 support。

远程执行者在第二轮 review blocker 关闭前提前冻结的 `authoring-implementation-receipt.json` 保持不可变：mode `0444`、SHA-256 `4bb2575d985126dfbd91d01a3111d3f4acb2ebe57c3bfd62b1d60ee847d7314d`。它绑定修复前 module，当前 v1 validator 按预期返回 drift，不能作为 active authority。append-only `authoring-implementation-receipt-v2.json` 于 `2026-07-29T00:30:16Z` 冻结，schema `typed-extractor-fresh-v2-authoring-receipt-v2`，size `7364` bytes，mode `0444`，SHA-256 `4ce77c20c2941a66c3e74c1bd561e9d5ceee360a3723b75eed694fc47267c94b`；supersession reason 为 `post_freeze_review_primary_literal_binding_repair`。active resolver 已验证只选择 v2，并绑定 current module/test SHA-256 `ebd022168efb51e343869c4f16ca869833afa4682a766167ae215798daa334ed` / `f7f03f48526442fbd26e3a48efeec5d116c7d928f9415d072bc998742aa45a0b`、L1/L2 blueprint manifest SHA-256 `54e44c0d8b798b778effaf74ed85b4f7d02401b9378c91506162db86f288730c` / `b5fb862d7ad8bb0a75976f928c37815d8bbe5271f9d95e3fd7ccd1e558f8bf4d` 和 47 个 prior input hash。

第三轮独立只读复审无 Critical/Important；保留一个 Minor：后续可增加“v2 文件损坏后直接调用 active selector”的显式回归测试，当前实现本身已经 fail closed。新鲜验证为 focused authoring `49 passed`、全部 typed extractor `177 passed`、knowledge pipeline `197 passed`、完整 natural memory benchmark `580 passed`、`compileall` 成功。下一步只能实现并执行 one-time formal hidden materialization；materializer 必须先调用 `validate_fresh_v2_active_authoring_receipt`，只冻结 source/public/authority/gold/manifest/chronology。hidden 冻结完成后，才允许无历史、public-only proposer；proposal/provenance 仍须先冻结，随后由独立 scoring 读取 authority/gold，并分开报告 raw proposer quality 与 deterministic gate safety。

materialization 前没有 formal hidden 写入或模型请求，automatic L1/L2/revision/source-revision/closure/identity/membership/snapshot/aggregate writes 全为 `0`，不授权 pipeline integration。guard fingerprint 为 `e184b6caf2998acf1c8700bc84d24bbafd49ab9c8f15738d1af8cc484ee5ebcc`，candidate v3 queue SHA-256 为 `518ead9de8627a9a4384df8cdd9b8728a21fcf797f6b0f3d208dfcb28ac41c0f`，四项人工裁决未物化，`LONGMEMEVAL-6d550036` 为 `structured_l2_identity_unresolved`。H100 venv 未安装 Ruff，本轮没有修改环境依赖。

## Typed extractor fresh-hidden v2 materialization

2026-07-29 已完成 one-time formal hidden materialization。正式 root 为 `artifacts/automatic-extraction-assessment/typed-extractor-v2-fresh-hidden-v2/`，包含 L1 24 条、L2 12 条以及 `chronology-receipt.json`，共 11 个 JSON。所有文件 mode 为 `0444`，root 与 `l1/`、`l2/` mode 为 `0775`；未创建 `model-runs`、proposal、provenance、score 或 report 路径，也未发起模型请求。

独立复审最初阻止发布，指出 active v2 receipt 未固定到批准 SHA，以及 `os.replace` 可覆盖并发创建的空 root。两项均先由失败回归测试复现，再修复为固定批准 receipt SHA `4ce77c20c2941a66c3e74c1bd561e9d5ceee360a3723b75eed694fc47267c94b` 和 Linux `renameat2(RENAME_NOREPLACE)` no-clobber 发布；复审随后批准，无剩余 Critical/Important。materializer module/test SHA-256 为 `57a8e6df5c6fc4739b50cf842f53063610f2c5bfc0ada21b84de0d87ab65a606` / `84f88ce70ca818a27b520b21d5a43a7f46a3bba8d2393bf0ee5417afc24191ac`。

冻结标签为 `2026-07-29T02:10:29Z`，chronology SHA-256 为 `278d9ba8f4d466984b11644de920b815de11cbdb56b49dff0dd797543b12b05e`，其中绑定 prereg-v3、active authoring receipt、materializer、test 和十个正式输出 SHA。public validator 返回 `valid`，十个 payload 对 deterministic authoring bundle 的逐字节重建为 `10/10`；guard fingerprint 和 candidate v3 queue 分别保持 `e184b6caf2998acf1c8700bc84d24bbafd49ab9c8f15738d1af8cc484ee5ebcc` / `518ead9de8627a9a4384df8cdd9b8728a21fcf797f6b0f3d208dfcb28ac41c0f`，九类 automatic write count 总和为 `0`，人工 identity 裁决未物化，`LONGMEMEVAL-6d550036` 仍为 `structured_l2_identity_unresolved`。

冻结前验证为 authoring+materialization `64 passed`、typed extractor `192 passed`、knowledge pipeline `197 passed`、natural memory `603 passed`。冻结后 materialization/其余 authoring 为 `63 passed, 1 deselected`、typed extractor `191 passed, 1 deselected`、knowledge pipeline `197 passed`、natural memory `602 passed, 1 deselected`。唯一 deselected 节点是 receipt-bound 的 pre-materialization 测试，它按合同断言正式 root 尚不存在；为保持 active receipt 绑定，不修改该测试或 authoring module。

隔离、无历史、public-only proposer 和独立 scoring 已按上述顺序完成。L1/L2 run 分别为 `run-20260729T024500Z-deepseek-chat-official-typed-l1-fresh-hidden-v2` 与 `run-20260729T024501Z-deepseek-chat-official-typed-l2-fresh-hidden-v2`；每层只执行一次 official `deepseek-chat` semantic request，无 retry，raw response model 均为 `deepseek-v4-flash`。proposal/provenance 在 authority/gold 读取前冻结，proposal SHA-256 为 `5e0ac9cf0ed5dd50cf2bffa78add1e988d599856ba94820639e5f763527c4a05` / `59e1f052c2157782c1f8266d91a9ae319a2ba87cb7b065d58bf8a6adbd8a9da6`。

## Typed extractor fresh-hidden v2 final result

fresh-v2 总体为 `not_qualified`，raw proposer quality 与 deterministic gate safety 均按 prereg 独立判定。L1 raw decision accuracy `0.9583333333333334`、abstention F1 `0.8571428571428571`、exact evidence `1.0`，但 role/local entity `0.5555555555555556`、time `0.8888888888888888`、condition/scope `0.9444444444444444`，并有 `1` 个 critical false emission；错误计数为 role/local entity `8`、time `2`、condition/scope `1`、false emission `1`。L2 raw decision/abstention/evidence/support/kind/source/summary 均为 `1.0`，但 structured claim `0.0`、abstraction `0.7777777777777778`、closure `0.5555555555555556`；错误计数为 structured claim `9`、closure `4`、abstraction `2`。两层 deterministic critical materialization 均为 `0`，但各有 `4` 次 gate intervention，未满足冻结的 zero-intervention safety threshold，因此不能用 gated 安全结果或 legacy scorer readiness 掩盖 raw failure。

正式 manifest 和冻结 proposal 未修改。旧 scorer 的三键 manifest/旧 L2 threshold 限制通过临时只读 compatibility view 处理；L1 首次绝对 guard 路径的 `9f81...` fingerprint 已由 append-only supersession receipt 记录，最终 canonical 相对路径 score 为 `score-v2.json`，没有重跑模型。最终 L1/L2 score SHA-256 为 `f09d754e6848ade7fbbc0fc723899c63a7e24947c3c2cb6a13401ae1bbd0dbc8` / `6d656d9883803f1b8ca5a200babfa285547f98e99e048fc3908517dc31e8c092`，qualification SHA-256 为 `5e189d02b9e08df8b8713151297cf02676c66756145439adf98a7b4cac41dfd9` / `5c63013aa9320da636e8fbdb4e44e9d7be22358ac5bb5f233ec585971a73453a`；总报告位于 `artifacts/automatic-extraction-assessment/typed-extractor-v2-fresh-hidden-v2/overall-report.md`。

最终只读审计 `117/117` 通过，包含 pre-model chronology 十个 payload、raw/proposal/provenance、canonical score replay、prereg qualification、`0444` mode、guard/candidate queue/protected scorer hash 和 credential scan。两个与正式 proposal 逐字节相同的 `.tmp` 副本及空目录已清理。新鲜回归为 typed extractor `191 passed, 1 deselected`、knowledge pipeline `197 passed`、natural memory `602 passed, 1 deselected`，`compileall`、`tabnanny` 通过；唯一 deselected 是绑定冻结前 formal-root absence 的 `test_bundle_is_deterministic_and_does_not_mutate_formal_artifacts`，测试与 authoring module 均未修改。

下一阶段只允许在新的 dev/diagnostic 数据上修复 L1 false emission、role/local entity、time、condition/scope，以及 L2 structured claim、abstraction、closure。raw strict metrics 全过且 gate intervention 为 `0` 后才能另行预注册新的 fresh hidden。当前不授权 pipeline integration 或任何 authoritative write，不进入 closure、aggregate 或 benchmark 扩展；人工 identity 裁决未物化，candidate v3 queue 未漂移，`LONGMEMEVAL-6d550036` 继续为 `structured_l2_identity_unresolved`。

## Typed extractor taxonomy dev v1 final result

2026-07-29 已完成 fresh-v2 后的 taxonomy-only dev/diagnostic 修复波次。新 L1/L2 roots 位于 `artifacts/automatic-extraction-assessment/typed-extractor-taxonomy-l1-dev-v1/` 和 `typed-extractor-taxonomy-l2-dev-v1/`，分别含 20/12 个新 authored diagnostic cases；source SHA-256 为 `d830246820c1df017baaace328111105f04858ce30f86d624b4a890be49d37b5` / `693cea99322c9589864749213ad1705ba6eabf3323bd3a19d6e5ec85d9a98418`，manifest SHA-256 为 `10292706e91d1eca7a0285fc83fd57cf0912ad51faff519fe54000864683029d` / `bed50074ee41a3119a6e5803a0a24d403aa7557f75ceb8491c54ba132b31cdf8`。两层 prior identifier/evidence overlap 均为 0，所有正式文件均为 `0444`，provenance 固定为 `diagnostic_authored`，不属于自然 benchmark 证据。

unchanged-prompt baseline 使用无历史、public-only 官方 `deepseek-chat`，每层一次请求且无 retry，raw response model 均为 `deepseek-v4-flash`。L2 baseline 直接严格通过：所有 raw exact metrics 为 `1.0`，gate intervention、raw critical false emission、deterministic critical materialization 均为 `0`。L1 baseline 的 deterministic gate safety 通过且 intervention 为 `0`，但 raw strict quality 为 `not_qualified`：唯一失败是 `role_or_local_entity_accuracy=0.9375`，模型把一个显式介词 participant 留在复合 task surface 内；不得用 gate pass 或 shared scorer 的宽松 readiness 掩盖该 raw error。

L1 repair-v1 只依据这套新 diagnostic 的单个 role/local-entity taxonomy 错误，将已有 delimiter 规则操作化为“先分解、后编号、再绑定”的一般构造顺序；prompt 不含任何 diagnostic 完整消息或 private case ID。repair run 的所有 14 项 strict metric 均为 `1.0`，三个 safety count 均为 `0`。repair prompt/proposals/score/qualification SHA-256 为 `a5250a453863f3cfd388613d6633d8a529485a11c5226d2965c8235a9c1dc342` / `db468cc0251abe48bfb1c98dead13471b16e32556df3a61da528e3e29de95750` / `dfbb8a415e6654b89f4ac09e0ae72bc45d1687cec13e69cbd2211f6ef295bb92` / `92e627fb72ba18ef1458aa9ef810bf8bf9b5efad3a12cc0f7559231e07a3c3de`；L2 baseline proposals/score/qualification SHA-256 为 `c735225a119c546fcba44372b5c56f32a2d1bd7caba3997ab51af4dc3ee25084` / `1c04a09d29f7d23abba85df249fb4194fd99bea2faca1ef7a288aa23444ee796` / `643944140f7348347448de3728b891d9e1209f05ba96384d3885b998e6f00ea4`。

最终只读审计 `67/67` 通过；candidate v3 queue SHA 保持 `518ead9de8627a9a4384df8cdd9b8728a21fcf797f6b0f3d208dfcb28ac41c0f`，guard fingerprint 保持 `e184b6caf2998acf1c8700bc84d24bbafd49ab9c8f15738d1af8cc484ee5ebcc`，credential pattern 为 0，automatic writes 为 0，人工 identity 裁决未物化。新鲜验证为 taxonomy focused `19 passed`、typed extractor `210 passed, 1 deselected`、knowledge pipeline `197 passed`、natural memory `637 passed, 1 deselected`，`compileall`/`tabnanny` 通过；唯一 deselection 仍是既有 pre-materialization root-absence 测试。

当前只授权下一步另行冻结 typed-extractor fresh-hidden-v3 preregistration；本波次没有创建 fresh hidden。pipeline integration、自动 L1/L2/revision/closure/identity/membership 写入、外部 memory 系统复跑和 identity resolution 仍未授权，embedding 仍不是事实或身份权威，`LONGMEMEVAL-6d550036` 继续为 `structured_l2_identity_unresolved`。

## Typed extractor fresh-hidden v3 preregistration

2026-07-29 已在 v3 authoring/materialization module/test、authoring receipt 和
evaluation root 全部不存在时冻结独立 fresh-hidden-v3 preregistration。设计、
计划、合同分别位于
`docs/designs/2026-07-29-typed-extractor-fresh-v3-preregistration-design.md`、
`docs/plans/2026-07-29-typed-extractor-fresh-v3-preregistration-plan.md` 和
`tools/natural_memory_benchmark/typed_extractor_fresh_v3_prereg.py`；v1/v2
preregistration 与 shared scorer/query/authority code 未修改。

正式文件为
`artifacts/automatic-extraction-assessment/typed-extractor-v3-fresh-hidden-prereg-v1/preregistration.json`，
freeze label `2026-07-29T04:51:35Z`，schema
`typed-extractor-fresh-v3-preregistration-v1`，evaluation ID
`typed-extractor-v3-fresh-hidden-v1`，SHA-256
`183cf6fc2991361e5da57b17e06a5970f651000986d50b87e8af2e6796440204`，
size `10998` bytes，mode `0444`。validator 返回 valid、L1 `24`、L2 `18`、
future absent、hidden not created、model request count `0`；root 中只有该 JSON。

合同固定 L1 八个 taxonomy family 各 3 条、L2 九个 taxonomy family 各 2 条，
要求全部 blueprint 使用，禁止 semantic filtering、replacement 和 resampling。
它绑定 taxonomy L1 repair-v1 与 L2 unchanged baseline 的 39 个 immutable input
hash、11 个 code/test hash、L1/L2 14/12 项 exact `1.0` quality metric 和三项
zero safety count。proposer 后续仍必须 no-history/public-only、每层一次 semantic
run；proposal/provenance 冻结后，独立 scoring 才能读取 authority/gold，raw quality
与 deterministic gate safety 分开报告。

最终验证为 v3 focused `16 passed`、相邻 prereg `34 passed`、typed extractor
`226 passed, 1 deselected`、knowledge pipeline `197 passed`、natural memory
`653 passed, 1 deselected`，`compileall`/`tabnanny` 通过。candidate v3 queue 与
guard fingerprint 保持
`518ead9de8627a9a4384df8cdd9b8728a21fcf797f6b0f3d208dfcb28ac41c0f` /
`e184b6caf2998acf1c8700bc84d24bbafd49ab9c8f15738d1af8cc484ee5ebcc`；
credential pattern 和 automatic write count 均为 `0`。

下一步只授权实现 deterministic v3 authoring 并冻结 implementation receipt；尚不
允许生成 hidden、调用 proposer、评分、接入 pipeline 或执行任何权威写入。人工
identity 裁决未物化，embedding 不是权威，`LONGMEMEVAL-6d550036` 继续为
`structured_l2_identity_unresolved`，外部 memory 系统仍不复跑。
