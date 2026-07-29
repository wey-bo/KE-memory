# H100 KE-memory-next Handoff Prompt

下面的文本可直接交给远程 Codex。它是后续工作的唯一接手说明；执行目录必须是 H100，不再回到本地工作区。

```text
你正在 H100 上继续维护：

/public/home/wwb/KE-mem/KE-memory-next-prep-20260727

这个工作区用于为新版 KE-memory 做准备。Windows 本地副本已经冻结为 audit-only；不得把后续实验或实现转回本地执行。

开始前必须完整阅读：

1. AGENTS.md
2. 安排.md
3. docs/reference/memory实现方案汇报.pdf
4. docs/designs/2026-07-27-authoritative-memory-contract-v3-design.md
5. docs/plans/2026-07-27-authoritative-memory-contract-v3-plan.md
6. docs/designs/2026-07-27-identity-resolution-schemaorg-extended-amr-design.md
7. docs/designs/2026-07-27-natural-identity-membership-proposal-design.md
8. docs/plans/2026-07-27-natural-identity-membership-proposal-plan.md

工作边界：

- 核心骨架非必要不得修改：基础本体、动态本体扩展接口、L1 基础抽取、L2 摘要/跨轮抽象、问题处理、符号优先召回、guarded embedding fallback。
- schema.org 只用于概念建模参考，不能授权事实、实体合并或成员关系。
- Extended-AMR 是当前主候选 carrier，但不是事实权威，也不是已经选定的最终数据库格式。
- 原始 turn、EvidenceSpan、不可变 revision/provenance、identity/lifecycle/closure 和显式 abstention 仍是权威契约。
- embedding 只能做受控 fallback，不能成为身份、事实或 membership 的权威来源。
- 不得复跑 Mem0、Graphiti、Hindsight、MemPalace、Zep 等外部 memory 系统。
- 不得访问或复用旧 Fusion Memory 项目的代码、测试、架构、评测逻辑或结论。

环境边界：

- 迁移中的 `.venv-dense` 是 Windows 环境快照，在 Linux 上不可用。
- 首次需要 Python 执行时，在项目根目录创建独立 `.venv-h100`，按当前项目依赖最小安装；不要修改或删除 `.venv-dense`。
- 本工作区不是可用 Git 仓库时，不要初始化 Git、commit 或创建 worktree。

当前第一 TODO：运行一次真实、隔离、proposal-only 的 identity/membership 模型评测。不要先扩本体，不要改核心 runner，不要写自动 merge 路径。

隔离要求：

1. 创建一个全新 proposer agent，使用无历史上下文的隔离会话，例如 subagent `fork_turns="none"`。
2. proposer 唯一允许读取的工作区数据文件是：
   `artifacts/identity-memory-experiment/natural-v1/public.json`
3. proposer 不得读取或接收以下文件的内容：
   `authority.json`
   `gold.json`
   `source-cases.json`
   `reference-proposals.json`
   `reference-score.json`
   `reference-report.md`
   任何先前或当前 scorer 输出
4. proposer 可以接收本 prompt 中的通用任务定义和输出 schema，但不能接收 case label、expected action、critical-error 标签或 gate authority facts。
5. proposer 只生成候选，不调用 authority gate，不评分，不修改任何 memory、identity、ontology 或 membership 状态。

关系与动作：

- `relation_kind=identity` 时，`action` 只能是 `merge`、`keep_distinct`、`abstain`。
- `relation_kind=membership` 时，`action` 只能是 `include`、`exclude`、`abstain`。
- 证据不足、主体不确定、只靠词面相似、schema.org 映射、AMR 边或 embedding 相似度时必须 `abstain`。
- `evidence_mention_ids` 只能引用对应 public case 中真实存在且直接支持该判断的 mention ID；不得编造 ID。

输出必须是单个 JSON 对象，顶层 schema 为：

{
  "schema_version": "natural-identity-proposals-v1",
  "dataset_id": "<从 public.json 原样复制>",
  "run_id": "<本次唯一 run id>",
  "proposer_id": "<模型或 agent 标识>",
  "proposer_version": "<版本>",
  "case_count": 12,
  "proposals": [
    {
      "case_id": "<public case id>",
      "relation_kind": "identity|membership",
      "action": "merge|keep_distinct|include|exclude|abstain",
      "confidence": 0.0,
      "evidence_mention_ids": ["<public mention id>"],
      "reason_code": "<简短、稳定、非自然语言长解释的代码>",
      "proposer_id": "<与顶层一致>",
      "proposer_version": "<与顶层一致>",
      "run_id": "<与顶层一致>"
    }
  ]
}

输出约束：

- 恰好 12 条 proposal，每个 public case 恰好一条，不能重复或遗漏。
- 每条记录的 `case_id`、`relation_kind` 必须与 public 输入一致。
- 顶层和逐条 `run_id`、`proposer_id`、`proposer_version` 必须完全一致。
- `confidence` 范围为 0 到 1。
- 候选文件应写入新的 run 目录或新文件名，不能覆盖冻结 reference artifacts。

proposer 输出冻结后，才允许主 agent 或独立 scorer 读取 authority/gold 并运行现有评分：

.venv-h100/bin/python -m tools.natural_memory_benchmark.cli score-identity-proposals \
  --root artifacts/identity-memory-experiment/natural-v1 \
  --proposals <本次 proposal JSON> \
  --output <本次 score JSON> \
  --report <本次 report MD> \
  --workspace-root .

预注册 proposer-quality gate：

- raw action accuracy >= 0.85
- raw critical false merge count = 0
- raw critical false membership count = 0
- raw abstention F1 >= 0.80
- proposal evidence exactness >= 0.95

同时必须报告 `gate_safety_ready` 与 `proposal_quality_ready`，两者不能混为一个结论。即使 deterministic authority gate 拦截了错误并得到安全 gated 结果，也不能掩盖 raw proposer 未过门。

不可改变的结论边界：

- 所有 model proposals 都是 non-authoritative candidates。
- 本轮不授权自动 merge、自动 membership 写入或自动更改 L2 聚合。
- `LONGMEMEVAL-6d550036` 必须继续保持 `structured_l2_identity_unresolved`，除非未来有独立证据和程序化 authority gate 真正解决其身份。
- 通过小型 proposal gate 不等于最终存储选型、产品优越性、UX 提升或对外部 memory 系统的胜出。

按 TODO 持续执行，除非遇到必须由用户决定的架构范围变化、外部凭据/模型选择或不可恢复操作，否则不要中途停止。完成后更新 README.md、AGENTS.md、安排.md，记录 run id、输入/输出哈希、raw/gated 指标、是否过门、失败 case 类型和上述 claim boundary。
```

## 2026-07-28 QuerySlotPlan V2 交接增量

当前有两条隔离主线：

1. typed extractor：fresh-hidden v1 的 L1/L2 raw quality 均失败但 gate safety 通过；随后 diagnostic prompt repair 已在新 dev 数据上通过。下一动作只能是冻结 fresh-hidden v2 预注册，不能直接创建 hidden、接 pipeline 或执行权威写入。
2. QuerySlotPlan V2：compiler、executor、formal assessment、standalone CLI 和 verified Git snapshot adapter 已实现。新鲜验证为 Query focused `55 passed`、相邻权威契约 `116 passed`、完整 natural-memory `485 passed`；正式 readiness 仍为 false，raw natural-query proposer 尚未评测。

Query 执行必须使用已验证 Git checkpoint 的 snapshot。artifact 读取绑定固定 commit 和 bundle logical ID；L1 必须属于恰好一个 complete TurnBundle；scope 外 identity 保持 unresolved；fact 必须有 revision provenance；latest 时间不完整或非法时 abstain；explicit absence 未实现前 abstain。typed extractor proposal、gate score、display-only/candidate/stale L2 均不能直接成为 execution fact。

后续 TODO 按以下顺序执行，并与 typed extractor 文件隔离：

- 绑定 plan 的 ontology/identity revision 与 verified snapshot/registry。
- 设计 per-claim L2 closure；完成前拒绝多 structured-claim L2 execution mapping。
- 补 explicit absence、复杂时间、literal/answer projection 的 executor contract。
- 冻结自然 query dev 与 fresh-hidden compiler evaluation，分开报告 raw proposer quality 和 gate safety。
- 最后串联 query compile、verified snapshot、symbolic execution、evidence scorer 和下游 answer/eval。
