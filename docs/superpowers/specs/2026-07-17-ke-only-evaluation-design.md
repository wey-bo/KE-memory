# KE Memory Demo：KE 主线评测设计增补

日期：2026-07-17

状态：对话设计已确认，书面规格等待用户复核

本文件增补并覆盖
`docs/superpowers/specs/2026-07-15-ke-memory-demo-design.md` 中与 embedding 主评测、
baseline 本地对跑、Turn KE 双轨损失指标和 evaluation 执行方式冲突的部分。未被本文件
覆盖的原规格继续有效。

## 1. 已选方案与范围

采用方案 A：只正式运行 KE 主线，以独立 DeepSeek Judge 评价结果；其他记忆系统只做
有来源的公开结果和能力对照。

未采用的方案为：

- 方案 B：在本轮加入 KE 与 embedding 的内部消融。embedding 实现保留，但暂不进入
  主评测。
- 方案 C：本地部署并统一运行 Mem0、Graphiti、Hindsight 和 MemPalace。该工作取消，
  不实现 baseline adapter，也不运行 baseline。

正式流程固定为：

```text
ontology preflight -> ingest -> Turn KE -> Session KE -> semantic DAG ->
symbolic recall -> common answer -> DeepSeek Judge -> Git evaluation snapshot
```

本轮要验证的是 KE 体系是否能：

1. 从一轮对话形成可验证、可回源的形式化知识表达。
2. 从跨 Turn、跨 Session 的片段归纳出重叠且可能复杂耦合的高层语义单元。
3. 通过 KE query、符号候选和 LLM match 找齐回答所需证据。
4. 正确处理矛盾、明确更新、事件顺序、时间状态和跨 Session 推理。

研究结论只针对固定 BEAM 100K 小子集，不外推为通用 SOTA 结论。

## 2. Ontology 必须先于 KE

真实 Elasticsearch 领域词表仍是本 Demo 的运行时领域本体，只读加载词条、类型、
别名和关系。任何 Turn KE 抽取开始前必须完成 ontology preflight，并冻结本次运行的：

- endpoint 的非秘密身份信息；
- index 名称、index UUID 和 mapping hash；
- 字段映射配置和 normalization mode；
- 本次实际命中的词条文档 ID 与必要字段。

normalization mode 固定记录为 `bounded-best-effort`，报告不得声称 exhaustive
normalized recall。词表未命中可形成 `unresolved` binding；认证失败、schema 不匹配、
index identity 漂移或 ES 不可用必须阻断对应阶段，不能降级为全量 unresolved。

Git snapshot 不复制完整 ES 词表。每个会解析本体词条的阶段在开始和提升 snapshot 前
复核 index identity，确保 KE 的 ontology binding 可追溯到同一外部本体版本。

## 3. Turn KE 的保真边界

Turn 仍定义为一个 user message 与紧随其后的 assistant message，tool call/result 是该轮
的可选附属事件。原始消息、顺序、角色、tool event 和内容 hash 继续逐字保存；KE 不被
视为原文的无损替代。

本轮不实现 Turn KE 双轨信息损失指标，也不新增一个由另一条抽取路径或另一个模型计算
的 loss score。Turn KE 的工程验收继续依赖已有的硬约束：

- 每条 KE 的精确原文 span、消息引用和片段 hash 可验证；
- 每轮 coverage 完整覆盖原文，且 `extraction_failed` 会阻断阶段；
- ontology binding 只能选择 ES 返回的候选，否则必须保留 surface form 并标为
  `unresolved`；
- KE、coverage、原始 Exchange 和 lifecycle revision 之间不存在悬空引用；
- 报告提供少量有代表性的 `raw exchange -> Turn KE -> evidence span` 对照案例，供人工
  观察形式化后是否遗漏重要信息，但不把该观察包装成自动化损失分数。

## 4. 高层语义归纳

Session KE 和跨 Session semantic DAG 继续使用当前实现，不把高层节点限定为 Task。
允许的节点包括 Task、Project、Topic、Goal、EventChain、EntityTimeline、Decision、
State、Constraint、Preference、Procedure、Pattern、Issue 和 Other。

一个 Turn KE 可以属于多个 AggregateNode；AggregateNode 可以跨 Session、彼此重叠，
并在最大语义深度 2 内再次归纳。高层结果预期可能复杂耦合，因此不以“是否得到一棵
整洁 Task 树”作为成功标准。每条摘要和聚合 KE 必须具有完整 `derived_from` 与原文
evidence closure；无法回源的归纳结果被拒绝。

重点观察：

- 分散在多个 Session 的同一任务、项目、目标或问题是否被聚合；
- 决策、约束、状态和事件链是否能同时出现在不同重叠节点中；
- 旧状态、明确更新与当前状态是否保持可区分；
- 高层节点参与召回时，最终证据是否仍能闭包到原始消息 span。

## 5. KE-only 召回与回答

Query KE、SQLite 符号候选、LLM matcher、evidence closure、token packing 和统一回答模型
继续使用已实现的 Task 10 路径。主评测不调用 embedding backend，且 `KEMemorySystem`
的 KE-ready 状态不得依赖 `embedding-ready`。

embedding 代码保留为可选、默认关闭的补充能力，不删除其已有测试和接口；本轮正式
manifest 明确记录 `embedding.enabled = false`。报告不得把未运行的 embedding 描述为
本轮效果来源。

回答必须附带可解析 citation。citation 只能指向本次召回 evidence，并能进一步回溯到
原始 Exchange/message/span；回答模型不得看到理想答案、rubric 或 Judge 输出。

## 6. 独立 Judge 与 KE 指标

保留官方 `deepseek-v4-pro` Judge。每个问题单独发送匿名 candidate answer、BEAM
question、ideal answer 和 rubric；Judge 不接收系统标签、内部 KE、match 分数或
baseline 资料。结构化输出仍包含：

```text
rubric_items[]: satisfied | not_satisfied + reason
answer_score
factual_error
unsupported_claim
abstention_correct | not_applicable
short_rationale
```

正式报告至少包含：

- Judge answer rubric score：总体、conversation、十类问题和重点类别；
- gold-source recall 与 complete-evidence rate，仅对可确定映射的问题计算；
- citation validity 与原文 traceability；
- unsupported claim、factual error 和 abstention correctness；
- contradiction resolution、knowledge update、event ordering、temporal reasoning、
  multi-session reasoning 和 summarization 的分类结果；
- 能体现跨 Session 归纳价值的逐例证据链，包括 Query KE、命中 KE、AggregateNode、
  下层 KE 和原文 span。

缺失或 schema 无效的 Judge 结果不能静默跳过，也不能记为零分。重试耗尽后该问题标记
失败，整个正式 run 标记 incomplete；有效结果仍可用于诊断报告，但不能宣称完整评测。

## 7. Evaluation 有界并发

evaluation 以提高吞吐为目标采用可配置的有界并发，但不改变语义依赖：

1. ontology preflight 和输入冻结串行执行一次。
2. Turn KE 的 LLM 抽取可按 Exchange 并行；结果先写临时 artifact，再按 source ordinal
   确定性合并，并串行执行 lifecycle reconciliation。
3. Session 归纳可在不同 Session 间并行；同一 Session 必须等待其全部 Turn KE 通过。
4. 不同 conversation 的 semantic DAG 可并行；同一 conversation 内按语义层深顺序
   构建。
5. memory snapshot 就绪后，60 个问题的 recall 与 common answer 可按题并行。
6. Judge 使用独立 semaphore，可与其他已保存 answer 的 Judge 请求并行，不与回答共享
   限流器。

并发配置至少包含 `turn_workers`、`session_workers`、`question_workers`、
`judge_workers`、每 endpoint 请求上限和退避参数。实际值、重试次数、request ID、开始与
结束时间写入 manifest/trace。输出文件按稳定 ID 分片，最终报告按 conversation、category
和 question ID 排序，因此 worker 完成顺序不影响内容 hash。

任一并行任务失败时不提升该阶段 snapshot。成功分片可作为恢复 checkpoint；重跑只处理
缺失或无效分片。artifact 聚合和 Git commit 使用单写者，防止并发写入破坏状态仓库。

## 8. Baseline 资料调研，而非对跑

baseline 报告是独立的资料表，不参与本 Demo 的 Judge、统计检验或数值排名。每条公开
结果必须记录：来源 URL/本地冻结文件、发布日期或源码 SHA、dataset、split、metric、
top-k、answer/Judge 模型、是否 vendor self-report、是否有逐题结果或复现脚本。

状态标签固定如下，单条结果可以组合多个标签：

- `公开结果`：找到来源和足够的协议说明；
- `未复现`：只引用公开结果，本项目没有本地重跑；
- `未找到`：在官方仓库、论文或官方报告中未找到相应结果；
- `不可直接比较`：dataset、split、metric、模型、检索深度或 Judge 与本 Demo 不同。

初查日期为 2026-07-17，来源为本地冻结仓库及其对应官方页面：

- Mem0：`memory-sota-study/repos/mem0@87276ef96879ee406690e640d34060de546560a5`
  与 <https://github.com/mem0ai/mem0>；
- Graphiti：`memory-sota-study/repos/graphiti@62ff03ac5662d288ebd9f6aafb70d6ae4070c632`
  与 <https://github.com/getzep/graphiti>；
- Hindsight：
  `memory-sota-study/repos/hindsight@f00d3c7f666e560bb051c51fba3977b38885f46a`
  与 <https://github.com/vectorize-io/hindsight>；
- MemPalace：
  `memory-sota-study/repos/mempalace@18a9788961afce013efc9e2da23ea2b17ab72381`
  与 <https://github.com/MemPalace/mempalace>。

当前初查结果如下：

| 系统 | 找到的公开结果 | 本项目标记 |
|---|---|---|
| Mem0 | 官方 README 报告 LoCoMo 91.6、LongMemEval 94.8、BEAM 1M 64.1、BEAM 10M 48.6 | 公开结果、vendor self-report、未复现；BEAM 规模和协议与本 Demo 的 100K 子集不同，不可直接比较 |
| Hindsight | 官方 README 图表报告 LongMemEval overall 94.6%，并声明由外部研究合作者复现 | 未复现；不是 BEAM，不可直接比较 |
| MemPalace | 官方仓库报告 LongMemEval R@5 96.6%，450 题 held-out R@5 98.4%，LoCoMo R@10 88.9% | 公开结果、vendor self-report、未复现；这是 retrieval recall，不是本 Demo 的端到端 Judge score，不可直接比较 |
| Graphiti/Zep | 冻结 Graphiti 仓库含 LongMemEval eval 脚本，但初查未见带完整协议的官方结果表 | 未找到；第三方图表中的数字不作为 Graphiti 官方结果 |

禁止把上述不同 benchmark 的数字放在同一排序列中，也禁止据此声称 KE 优于或弱于某个
baseline。资料对照只用于说明不同系统已公开验证的能力面与本 Demo 结果的关系。

## 9. Snapshot、故障和恢复

继续使用独立 Git state repository。成功阶段至少包括：

```text
ingested
turn-ke-extracted
session-aggregated
semantic-dag-built
ke-ready
evaluation-complete
```

`embedding-ready` 可存在于可选路径，但不是 `ke-ready` 或正式 evaluation 的先决条件。
snapshot 保存规范化 JSONL、manifest、脱敏 trace、回答、Judge 输出、指标、baseline 资料
来源清单和报告；不保存 SQLite、密钥、完整 ES 词表或未脱敏请求头。

Transient 请求按配置重试；认证、配置、ontology identity、schema、span、coverage、DAG、
证据闭包和引用 invariant 错误不盲目重试。只有完整通过校验的阶段才产生 Git commit，
checkout 后必须能重建 SQLite 并验证规范化对象 hash。

## 10. 精简测试策略

测试只覆盖高风险边界，不为每个数据组合扩张文件规模：

- ontology preflight 必须先于 Turn KE，且 identity drift 阻断 snapshot；
- KE-ready 不依赖 embedding-ready，正式配置不调用 embedding；
- 并发执行的结果按稳定 ID 合并，且 lifecycle、语义层深和 Git commit 保持顺序；
- Judge 并发、重试、无效结果和 incomplete 状态；
- citation、gold source、derived evidence closure 和 snapshot checkout；
- 一个使用 fake ES/model/Judge 的多 Session golden workflow。

相似边界使用参数化和共享 fixture。Unit/golden tests 不发起真实模型、ES、BEAM 或
baseline 调用；真实服务只通过显式 live smoke 和正式 run 使用。

## 11. 覆盖原计划的实施边界

后续 implementation plan 应按本增补重写剩余任务：

1. Core Task 11：Git snapshots、ontology-first/KE-only pipeline、CLI、可恢复并发和
   golden E2E。
2. Core Task 12：格式、lint、类型、精简非 live 测试、secret scan 和固定 BEAM 数量
   验证。
3. Baseline Tasks 1-7：标记为取消，不执行、不实现 adapter。
4. Evaluation：缩减为 question/gold normalization、KE-only runner、独立 Judge、指标与
   报告、公开 baseline 资料表和正式 BEAM 子集运行。

在用户复核本书面规格后，下一步仅更新 implementation plan；实现、live preflight 和
正式 evaluation 在新计划获准后继续。
