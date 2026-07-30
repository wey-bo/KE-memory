# Fusion Memory 工作区约定

这不是运行时代码仓库，而是记忆系统设计、验证和逐步实现的工作区。开始任何实现前，先阅读本文件、`安排.md` 和 `docs/reference/memory实现方案汇报.pdf`。本文件是持续维护的工作区事实源：完成一个波次、改变一个接口或得到新的实验结论后，更新对应章节。

## 当前范围

- 当前工作区路径：`/public/home/wwb/KE-mem/KE-memory-next-prep-20260727`
- 方案文档：`docs/reference/memory实现方案汇报.pdf`
- 执行安排：`安排.md`
- 参考仓库：
  - KEOL: <https://github.com/genuineknowledge/KEOL>
  - psi-agent: <https://github.com/genuineknowledge/psi-agent>
- H100 可核对的 KEOL 副本：`/public/home/wwb/KE_mem/KEOL-44631e6`
  - 分支：`feature/onto-drop-instance-of-assertion-+-change-description-metadata`
  - 当前提交：`44631e6`
- 强制隔离：不得阅读、参考、复制或复用之前 Fusion Memory 项目的代码、测试、架构实现、评测逻辑或实验结论。本工作区必须从当前方案、KEOL、psi-agent 和 BEAM 原始数据独立实现。

### 当前目录布局

- `data/gold-candidates/`：候选原文和来源配置。
- `knowledge_pipeline/`：当前知识优先抽取实现。
- `knowledge-extraction/`：正式结果、不可变抽取账本、模型原始输出和历史关键词批次。
- `tools/keol_baseline/`：KEOL baseline 的适配、编排和视图导出工具。
- `artifacts/keol-baseline/`：KEOL baseline 输入、中间结果、原生产物与人工视图。
- `archive/legacy-ke-v0.2/`：已作废的自定义 KE v0.2，只允许历史核对，不得复用。
- `docs/designs/`、`docs/plans/`、`docs/reference/`：设计、实施计划和方案参考。

## 核心术语

### KE：Knowledge Equation（知识方程）

本项目中的 KE 不是 Knowledge Extraction。KEOL 本体层的基本定义是：

```text
Ontology = Concept + Operator
Knowledge = Assertion
Assertion(A, B) := A = B
```

KE 是一个最小、可追踪的知识断言。`A`、`B` 可以是 `Concept`、`Individual`、`Operator`、`OperatorApplication` 或另一个 `Assertion`。最常见的关系事实，在当前严格表面语法中写为：

```text
created_by(Model_GPT_4)=Org_OpenAI
```

在 JSON 模型中，`Assertion` 至少包含：

- `lhs`、`rhs`：递归的 `Term`；
- `confidence`、`status`；
- `evidence_ids`：原文证据；
- `derived_from_assertion_ids`：推导链；
- `workflow_run_id`、`temporal_scope`、`metadata`。

每条逐轮抽取的 KE 都必须是闭合数据包：两侧表达式、对象引用、Operator、Evidence、来源轮次和置信度都存在。信息不完整表示为后续新的补充 KE 或带明确状态的候选，不允许留下悬空的 lhs/rhs 或裸值。

重要边界：

- 符号 `A = B` 是统一表示，不等于已经实现数学等号的对称、传递和替换推理；当前实现按有方向的 `lhs/rhs` 计算哈希。
- 普通个体归属放在 `Individual.concept_ids`，不要机械生成重复的 `instance_of` 断言。只有归属本身有独立证据、置信度或时间语义时才生成该断言。
- 时间、布尔值、序数、时长和文本等查询值要实体化为有类型的 `Individual`/`Concept`，不要使用无类型裸值。
- 用户陈述和 Agent 生成内容必须区分来源与认识论状态；Agent 生成内容可被记录，但默认不能当作现实事实。

#### 当前 KEOL baseline 表示（取代 v0.2 自定义运行时）

此前工作区自定义的 v0.1/v0.2 表面语法、`ke-runtime.mjs` 和相关统计全部作废。本轮以 KEOL 最新可见提交 `44631e64fd07c9b85f22e36035bf49c882dba592` 的 `Node/Edge/KnowledgeGraph`、`Concept/Individual/Operator/Assertion/Evidence/WorkflowRun` 为事实源。模型只返回 nodes/edges，KEOL builder 再把 edge 确定性转换为：

```text
Apply(operator, source_individual) = target_individual
```

KEOL schema 允许递归 `Term`，但当前 rawdata edge -> builder 路径只自动产生单层 `OperatorApplication`；不要把 `KE.txt` 的显示字符串当作可反向解析的语言。日期、时长和数量在 baseline 中通常是带 Concept 归属的 Individual，字面量类型和 `user/agent` 认识论状态仍是未决扩展。

当前 KEOL operator 的语义由 normalization plan 归一：只有 `specific` operator 绑定紧类型 input/output Concept，`broad`、`meta`、`noisy`、`needs_review` 不绑定误导性窄 schema。Normalization 不创建 ID，seeded operator 的 provenance 必须保持 `seeded`。

权威实现参考：

- `C:\Users\86137\Desktop\Haitun-agent\KEOL\src\onto\ONTOLOGY_BUILD_DESIGN.md`
- `C:\Users\86137\Desktop\Haitun-agent\KEOL\src\onto\ONTO_SCHEMA_IO_DESIGN.md`
- `C:\Users\86137\Desktop\Haitun-agent\KEOL\src\onto\models.py`

### KEOL

KEOL 是 `genuineknowledge/KEOL` 项目的名称，实际承担“从原始资料抽取候选知识、构建/归一化本体、校验和导出 Agent 可用知识资产”的流水线。其本体表示以 `Concept`、`Individual`、`Operator`、`Assertion`、`Evidence` 和 `WorkflowRun` 为核心，并可扩展行动本体（Skill、Tool、Action）。

仓库没有在所有文档中给出一个必须固定的英文全称。因此在本项目中不要把某个未经规范仓库确认的展开写成事实；工作定义是：**KEOL 是以 KE 为知识基本单元的本体构建/本体语言工程**。它既不是普通 RDF/OWL 编辑器，也不是完整的描述逻辑推理机；内部 JSON 是当前事实源，RDF/OWL 导出是下游能力。

KEOL 的程序职责边界：LLM 可以做语义判断和归一化，程序负责稳定 ID、证据绑定、引用闭合、JSON/Pydantic 校验、去重和落盘。KEOL adapter 应优先复用这些已有语义与约束；它们不自动成为整个记忆系统唯一的 canonical schema。

### 表示语言与能力契约边界（2026-07-27 更新）

KE/KEOL 是候选表示语言与适配器，不是项目唯一 canonical memory format。系统固定的是更高层的能力契约：稳定身份、事件/角色/谓词词义、原始证据回指、来源与认识论状态、三类时间、生命周期与不可变修订、冲突/supersession、L2 到 L1 派生链、证据闭包、约束执行、版本化 round-trip 和 guarded embedding fallback。扩展 AMR、KEOL、属性图或其他格式均可参与选型；任何格式若把这些语义降为未校验 metadata、丢失引用或无法执行，只能是 `partial`/`projection_only`。

当前 `semantic_ir.py` 是 conformance reference carrier，不是已选定数据库；当前 KEOL projection 是可选 materialized view，不是稳定持久层。Extended-AMR 已被用户选为后续主候选 carrier，但其权威性仍来自表示无关契约与可执行 gate，而不是 AMR 语法本身。原文、evidence-backed semantic record 与不可变 provenance 才构成恢复链。

## 记忆方案

总体方向是“**双重表征、符号优先、向量补足**”：

1. 以一轮对话为最小操作单元；一轮 = 一次 user 输入和对应 agent 输出。
2. 对每轮抽取完整、证据闭合的 L1 memory unit，同时保全原始对话和精确 EvidenceSpan，原文永远是恢复底座。
3. 先建立 representation-neutral semantic contract，再评估 KEOL、扩展 AMR、ES 词表/人工本体或其他 profile 的表达、投影损失和执行能力。
4. 建立多层级索引和摘要：轮次、session 内摘要、跨对话/跨 session 的高层概念（例如 `Task`）。高层 L2 unit 必须回指底层轮次、L1 unit 和证据闭包。
5. 建立表示无关的符号执行器：canonical predicate、角色绑定、AND/OR、多跳、时间、来源/认识论状态、冲突与闭包。具体 profile 通过 adapter 接入。
6. 只在符号表达能力缺口处做 embedding 实验；比较纯符号和“符号 + embedding”，观察召回提升是否只发生在一次性细粒度表达，且不污染符号精确率。
7. 根据实验结果落地融合策略，默认候选是“符号主、embedding 兜底”，但必须由实验决定 fallback 还是加权。
8. 用 snapshot 记录 raw turn、memory unit revision、profile projection、diff 和回看路径，支持双时态追溯以及新对话背景选择。

### 证据与持久化原则

- 原始 turn 必须可单独读取；派生 memory unit、摘要、归一化结果和各 profile projection 都保留 source turn/span。
- 单轮写入要有明确的事务边界，失败时不能留下不完整的 memory bundle。
- 去重只合并相同语义记录的证据，不覆盖冲突事实；冲突、废弃、revision 和时间有效性要显式记录。
- 查询结果必须能回到 `memory claim/unit -> EvidenceSpan -> raw turn revision`，否则不算可验收的命中。

## 执行波次

以 `安排.md` 为准，以下是验收摘要：

| 波次 | 目标 | 依赖/验收 |
| --- | --- | --- |
| 0 | gold set、仓库骨架/CI、绑定 semantic contract、turn 存储 | 每条 gold 有原文、期望 memory semantics、证据和期望查询 |
| 1 | 评测 harness、wordnet/词表归一、单轮 L1 抽取骨架 | term -> canonical identity；抽取可写入候选 profile |
| 2 | representation profile go/no-go、单轮抽取接归一、最小查询 Q0 | 用 gold 衡量 KEOL/AMR/其他 profile 覆盖与表达损失；Q0 能返回结果 |
| 3 | 多轮/跨 session L2 抽象；查询 Q1 | predicate/角色绑定、AND/OR、多跳、时间/闭包、归一接入 |
| 4 | embedding 缺口实验和兜底实现 | 只在标注缺口接 embedding；输出纯符号/混合对比 |
| 5 | 融合策略、snapshot 薄版 | 策略由实验结论驱动；快照可 diff/回看 |
| 6 | 端到端串联、全 gold 评测、三假设结论 | turn -> memory unit -> selected profile -> 查询 -> 追溯完整可演示 |

人的工作是 gold 标注、缺口分类、representation profile go/no-go、查询形态和 embedding 结论；Agent 的工作是骨架、contract/profile 绑定、存储、抽取、归一、查询、评测和 snapshot。不要把关键判断隐含在代码默认值里。

## 外部参考

### psi-agent

psi-agent 的有用边界是其 workspace 运行模型：AI、Session、Channel 解耦；workspace 中的 `tools/*.py`、`systems/system.py` 和 `skills/*/SKILL.md` 定义 Agent 行为；Session 维护 JSONL history 和 turn 级提交/回滚。

记忆接入优先遵循 `examples/fusion-memory-workspace` 的 HTTP-only 方式：Agent 通过 `memory_add`、`memory_search`、`memory_answer_context` 访问独立的 Fusion Memory 服务，Session 进程不直接加载数据库、模型或 MemoryService。这样可以保持 Agent 核心无状态、记忆服务可独立验证。

### ES 搜索引擎词表

当前工作区没有固定的词表文件或版本。这里的“ES 词表”先按归一层输入处理：候选术语、别名、分词/同义词和类型提示，用于 `term -> canonical identity`，并作为候选 representation profile 的归一辅助。

词表不是事实源，也不能无条件覆盖人工定义或候选 profile 的 canonical identity policy。接入时必须记录：词表版本、命中方式、canonical ID、冲突/歧义、未命中率和覆盖率。波次 1 的 W 和波次 2 的 representation profile go/no-go 要把这些指标写进评测结果。具体 ES index、analyzer、dictionary 导出格式和更新责任人仍是未决项。

### BEAM benchmark

本项目关注的是长期 Agent memory 的 BEAM（Beyond a Million Tokens）基准，而不是同名的其他项目。公开 HF 数据集当前常用 `100K`、`500K`、`1M` 三档；最小可运行档是 `100K`，上一轮核对的版本为 20 个样本、约 100K token 上下文，Parquet 约 5.18 MiB。

BEAM 使用规则：先跑最小/开发切片和针对性 probe，再跑全量；报告命中率、分类别指标、证据包/KE 追溯、延迟、token 和失败样本。任何提升都要证明没有牺牲原始证据保全和产品语义。

### 当前执行状态

Wave 0 的 gold-set 候选片段已完成第五轮重采样，当前工作区已从 `fusion-memory` 重命名为 `KE-memory`。结果保存在 `data/gold-candidates/KE-test.json`，抽取与来源配置保存在 `data/gold-candidates/KE-test-config.md`。JSON 每条候选包含 `id`、`source` 和按轮交错的 `turns`，每个 `turns` 元素包含一个 `user` 和一个 `agent`。共 10 条待人工筛选片段：7 条 WildChat 管理/学习日志、1 条 Taskmaster-2 任务对话、1 条 τ-bench 工具轨迹和 1 条保留自 BEAM。候选长度有意不统一，覆盖 3、4、5、6 轮；WildChat、Taskmaster 和 τ-bench 均按用户消息切分并保留同一轮内的连续 Agent 回复、工具调用和工具结果。展示文本已翻译为中文，且保留来源坐标、数字、地点、产品名和原始顺序。

候选仍处于待人工筛选状态，下一步由人进行片段筛选，再按轮抽取基础 KE。源对话中的日期、价格、状态和逻辑矛盾不作为自动淘汰条件；当前候选中已明确保留一条 BEAM 遗嘱执行人片段的日期矛盾。不得以翻译或人工筛选为理由修正源数据事实。τ-bench 候选必须同时标明其用户为模拟器生成，不能把工具轨迹的任务真实性写成真人对话真实性。

可重复的当前验证包括：JSON 解析、候选数与交错 `turns` 长度检查、每个轮对象的 `user`/`agent` 字段检查、WildChat 的 `conversation_hash/user_ordinal/toxic/redacted` 检查，以及按 Taskmaster 的 `conversation_id/utterance_index`、τ-bench 的 `record_index/trial/user_ordinal` 或 BEAM 的 `split/conversation_id/session_index_zero_based/message_index` 重新读取源数据。此阶段只使用公开数据原始对话、当前方案/安排文档和允许的 KEOL、psi-agent 参考，不得访问或复用旧 Fusion Memory 实现。

KE 本体与抽取实验设计已获用户批准，记录在 `docs/designs/2026-07-21-ke-ontology-extraction-design.md`。设计阶段已完成自检。

用户已确认设计。实现计划记录在 `docs/plans/2026-07-21-ke-ontology-extraction-plan.md`，计划自检通过并已按四个任务执行。

当前 KEOL baseline 已完成并集中保存在 `artifacts/keol-baseline/`：10 条候选、43 个 user+agent turn、405 个模型 graph node、371 条 edge、164 个 Concept、229 个 Individual、161 个 Operator、309 条 Assertion、774 条 Evidence；共有 323 个 Assertion-turn 证据链接，42/43 个 turn 至少关联一条 Assertion，唯一未关联的是 `TASKMASTER2-CAND-001` 第 6 轮。normalization 5 批共更新 164 Concept/161 Operator，应用 113 个具体 operator schema。KEOL strict validation 为 0 error、0 warning。原生产物在 `artifacts/keol-baseline/native-output/KE-test/onto/`，视图在 `artifacts/keol-baseline/views/`，编排模块在 `tools/keol_baseline/`。这些结果仍是 KEOL baseline，不替代人工 gold 标注；已知缺口是嵌套 KE 未由当前 edge 路径自动生成、Evidence 为 chunk 级、核心 Assertion 无认识论状态、operator 粒度和方向仍需人工审核。

另生成了面向人工查看的 `artifacts/keol-baseline/views/KE.txt`：按 `对话id` 和轮次分组，显示原生 KEOL Assertion 的可读投影；事实源仍是 `artifacts/keol-baseline/native-output/KE-test/onto/assertions.json`，不能从纯文本反向恢复完整 Term/ID。

当前已采用独立于 KEOL baseline 的两阶段知识抽取方法：先逐个 user-agent turn 独立抽取，再用完整对话做不可变首轮记录上的 `confirm`、`correct`、`supersede`、`conflict`、`add` 校正。最终确定性投影得到 390 条 active knowledge。完整 Prompt、上下文补全边界、`user_reported`/`agent_generated`/`tool_observed` 区分、evidence 规则和 subagent 调用策略记录在 `knowledge-extraction/knowledge-extraction-prompt-and-strategy.md`；后续不得仅凭摘要重写该方法。

关键词 v3 已在上述 390 条知识上完成 subagent 抽取、独立语义复审和程序全批校验。正式结果位于 `knowledge-extraction/keyword-pass-v3/`：10 个候选共 1501 个原子关键词，其中 1066 个映射到实际 WordNet 3.0 synset，435 个领域词、标识符或难归类词保持未映射，归一后共有 628 个 canonical keyword。展示文件 `knowledge-extraction/KE-knowledge-keywords.json` 是由 43 个 turn 组成的数组，每个 turn 只能有 `原始文本`、`知识`、`关键词` 三个字段，字段内部按 `user`/`agent` 区分；不显示 dialogue ID、turn index、knowledge ID 或审核元数据。关键词对象只含关键词本身与可选 `wordnet`，关键词组与同角色知识数组按位置对应；跨轮知识放入最后一个 evidence turn。律师请假抽取切片位于 `knowledge-extraction/keyword-v3-preview-lawyer-leave.json`，同样只有三个字段。

2026-07-24 已完成工作区结构化整理：根目录只保留 `README.md`、`AGENTS.md`、`安排.md` 和一级职责目录；候选数据、KEOL baseline、旧 v0.2、设计/计划和方案 PDF 已分别归入 `data/`、`artifacts/`、`archive/` 和 `docs/`。迁移后路径、大小和 SHA-256 清单位于 `artifacts/project-structure/2026-07-24-move-manifest.json`；清单明确记录迁移前哈希未成功持久化，不能把它表述为前后哈希对比。知识三字段导出用关键词 v3 默认路径重放后字节一致，完整测试为 241 passed。

2026-07-24 已启动 AMR 单句表示小实验的实施阶段，设计与计划分别位于 `docs/designs/2026-07-24-amr-single-sentence-pilot-design.md` 和 `docs/plans/2026-07-24-amr-single-sentence-pilot.md`。当前已从 Taskmaster-2、tau-bench 和 BEAM 的授权英文原始来源恢复 12 个独立句子，每个四类语义现象各 3 条；输入、来源记录和哈希清单位于 `artifacts/amr-pilot/inputs/`。独立语义检查表草案位于 `artifacts/amr-pilot/gold/semantic-checklists.draft.json`，包含 12 个 checklist、47 个显式加权语义项，其文件 SHA-256 为 `88bfbf4b844fca2a79806441bb94413fb0d33fa0bd7054c3026d3f3f6a180772`。用户已批准该精确草案，绑定记录位于 `artifacts/amr-pilot/gold/approval.json`，状态为 `approved`。

AMR pilot 的正式质量/结构运行 `run-20260724T125522Z` 已固定使用平衡型 `gpt-5.6-terra`。C 路线的 12 个原子知识结果、A 路线的 12 个直接 AMR 和 B 路线的 12 个知识前置 AMR 均已写入不可变 raw/sidecar 账本；A 为 12/12 首轮 PENMAN 结构有效，B 为 11/12 首轮有效，`AMR-S001` 的首轮缺失闭合括号已保留并按规则进行唯一一次成功重试。官方 PropBank v3.4.0 frame inventory 下载失败，因此只验证 PENMAN 与结构闭合，frame membership 状态保持 `unavailable`，不得把未知 frame 表述为已验证。subagent 通道的 token、cost 和逐调用 latency 均不可得，所有 sidecar 显式记录 `unavailable`，最终效率门只能为 `undecidable`。

36 个最终候选已在不暴露 A/B/C 映射的情况下由两名隔离 reviewer 完成双盲语义评审，评审提示词 SHA-256 为 `39451d0786221af4ea53dcf4c4d3522038a68741bb6b0602e6b53fd9ac531ae6`。程序校验确认两名 reviewer 均完整覆盖 36 个候选及其全部 gold item；当前共有 7 个 `supported`/`omitted`/`incorrect` 分歧，没有 hallucination 集合分歧。正式结果位于 `artifacts/amr-pilot/reports/review-results.json`，待裁决项位于 `artifacts/amr-pilot/reports/adjudication.json` 和 `adjudication-needed.md`。状态为 `pending_user`；在用户完成这 7 项裁决前不得生成最终分数、gate report 或 AMR 节点通过结论。其他 memory 系统仍只收集可追溯的作者/官方结果，不在本项目复跑。

2026-07-25 本体化记忆优势实验已按已批准设计完成实现和首轮真实模型运行。冻结 v2 数据位于 `artifacts/ontology-memory-experiment/gold-v2/`：60 个英文基础场景、12 个 dev、48 个 hidden、33,000 条 distractor；hidden 决策运行是 `run-20260725T150000Z-real-hidden`，使用 384 维 `qdrant/bge-small-en-v1.5-onnx-q@5239827`，得到 1,728 个结果行、0 execution error，并通过 run hash/grid/证据回指验证。oracle `O+` 的 Evidence Set Exact Match、答案正确率和约束满足率均为 1.0，`B2` 的对应值为 0.0、0.597、0.0，表明充分类型化表示和精确执行在受控结构任务上存在明确能力优势；`O-` exact match 仅 0.062，说明建模不足的“伪本体”不能替代所需 primitive。automatic `O+` 的 exact match/答案/约束为 0.250/0.562/0.500，只保留相对 `B2` oracle 增益的 22.9%，低于预注册 70% 门槛，因此总 gate 为 `fail`：当前自动抽取/查询编译器不得进入主架构。`O+E` fallback 触发率为 0，形式上的 lexical/fallback gate 通过不能解释为 embedding 有效。完整结论见 `artifacts/ontology-memory-experiment/reports/experiment-summary.md` 和 `gate-report.md`；官方外部结果只作不可直接比较的上下文，见 `external-context.md`。

2026-07-26 v4 fresh hidden 已完成真实 dense 重跑，冻结输入位于 `artifacts/ontology-memory-experiment/gold-v4/`，正式 hidden 运行是 `artifacts/ontology-memory-experiment/runs/run-20260726T021000Z-v4-real-hidden/`。该 run 使用 `.venv-dense` 中的 `fastembed==0.8.0` 与 384 维 `qdrant/bge-small-en-v1.5-onnx-q@52398278842ec682c6f32300af41344b1c0b0bb2`，覆盖 51 个 hidden 场景、1,836 个 arm/track/scale 结果、0 execution error，并通过 `verify-run`。gate 报告为 `artifacts/ontology-memory-experiment/reports/v4-real-hidden-gate-report.md`，总决策仍为 `fail`：oracle 结构门、critical false positive、500 distractor、lexical recall 和 fallback limits 均通过，但 `automatic_retained_gain=0.47058823529411764`，低于预注册 0.70。automatic `O+E` hidden ESEM 为 0.5294117647058824，fallback rate 为 0.058823529411764705，structural-family fallback rate 为 0.0；失败集中在 roles/quantity 家族多取 provenance/context turn，以及 conjunction/multihop 家族漏取闭包证据 turn。该 v4 是 fresh hidden，结论取代 v3 post-hoc pass 作为当前 go/no-go：自动管线仍不得进入 LoCoMo、BEAM、LongMemEval 大 benchmark。

2026-07-26 v5 fresh hidden 已在 dev/诊断修复后完成 clean gate，冻结输入位于 `artifacts/ontology-memory-experiment/gold-v5/`，正式 hidden 运行是 `artifacts/ontology-memory-experiment/runs/run-20260726T041000Z-v5-real-hidden/`。该 run 使用同一真实 dense encoder `qdrant/bge-small-en-v1.5-onnx-q@52398278842ec682c6f32300af41344b1c0b0bb2`，覆盖 51 个 hidden 场景、1,836 个结果、0 execution error，并通过 `verify-run`；gate 报告 `artifacts/ontology-memory-experiment/reports/v5-real-hidden-gate-report.md` 的总决策为 `pass`。所有 6 个门均通过：structural exact match、critical false positive reduction、500 distractor、automatic retained gain、lexical recall、fallback limits。automatic `O+` hidden ESEM/Answer/Constraint 均为 0.9411764705882353，automatic `O+E` hidden ESEM/Answer/Constraint 均为 1.0，`automatic_retained_gain=0.9411764705882353`，fallback rate 为 0.058823529411764705，structural-family fallback rate 为 0.0。该结果授权进入下一阶段预注册自然 benchmark 小切片或扩大受控集，但仍不能写成产品优越性、用户体验提升、或 Mem0/Graphiti/Hindsight/MemPalace 的本地分数；这些系统本轮仍未复跑。

2026-07-26 自然 benchmark 小切片 v1 已冻结并验证，设计和计划分别位于 `docs/designs/2026-07-26-natural-benchmark-slice-design.md` 与 `docs/plans/2026-07-26-natural-benchmark-slice-plan.md`。原始源快照保存在 `artifacts/natural-benchmark-slices/raw/`：BEAM `100K-00000-of-00001.parquet`、LoCoMo `locomo10.json`、LongMemEval `longmemeval_oracle.json`；源清单位于 `artifacts/natural-benchmark-slices/source-manifest.json`。冻结 slice 位于 `artifacts/natural-benchmark-slices/slice-v1/`，共 32 个 item：BEAM 10、LoCoMo 10、LongMemEval 12；`slice.json` 不含答案/证据/rubric，`gold.json` 单独保存答案、证据引用和评分 caveat。LoCoMo category 5 仍是 `manual_required`，因此只能用于 evidence/adversarial probe，不能直接计入 answer correctness。gold ref 到 raw text 的闭合映射位于 `artifacts/natural-benchmark-slices/slice-v1/gold-evidence.json`，属于 gold-side artifact，不得并入 public slice。外部 memory 系统结果账本为 `artifacts/natural-benchmark-slices/external-results-ledger.json`，13 条记录均为上下文用途，不含本地复跑分数。当前验证：`tests/natural_memory_benchmark` 为 28 passed，`validate-slice` 返回 32 public/32 gold 且状态 `valid`，`validate-ledger` 返回 13 entries 且状态 `valid`。已新增 scorer/result 合同与 `score-results` CLI，可消费 `dense_reference`、`symbolic`、`symbolic_fallback` 的结果文件并输出 Evidence Set Exact Match、All-Evidence@K、Evidence Recall、Evidence Precision、answer exact diagnostic、abstention、critical FP、fallback、latency/token 指标；Mem0、Graphiti、Hindsight、MemPalace、Zep 等仍不得本地复跑。

2026-07-26 自然 benchmark 的首个本项目 arm `dense_reference` 已完成真实 FastEmbed 运行，结果位于 `artifacts/natural-benchmark-slices/slice-v1/dense-reference-fastembed-results.json`，评分位于 `dense-reference-fastembed-score.json`，人工报告位于 `dense-reference-fastembed-report.md`。运行使用 `.venv-dense` 中的 FastEmbed `BAAI/bge-small-en-v1.5`，缓存源为 `qdrant/bge-small-en-v1.5-onnx-q@52398278842ec682c6f32300af41344b1c0b0bb2`，TopK=10；优化后将共享文本去重批量编码，墙钟约 58 秒，评分中的摊销 mean latency 为 1747.16 ms/item。整体 Evidence Set Exact Match 为 0.375，All-Evidence@10 为 0.59375，Mean Evidence Recall@10 为 0.66146，Mean Evidence Precision@10 为 0.425，abstention correctness 为 0.0，critical false positives 为 2。分源：BEAM Recall@10 为 0.6167、All-Evidence@10 为 0.5；LoCoMo Recall@10 为 0.3、All-Evidence@10 为 0.2；LongMemEval 为 1.0 但这是因为 v1 使用 `longmemeval_oracle.json` 的 oracle haystack sessions，不能外推到完整 LongMemEval 检索。`answer_exact_match=0.0` 只是因为 dense arm 当前只做检索、不生成答案。该结果证明 dense 对证据恢复有帮助，但在 abstention、角色绑定、精确 evidence-set 控制上存在当前主流向量路径的典型漏洞。

2026-07-26 自然 benchmark 的第二个本项目 arm `symbolic` 已完成规则/槽位 baseline v1，结果位于 `artifacts/natural-benchmark-slices/slice-v1/symbolic-results.json`，评分位于 `symbolic-score.json`，报告位于 `symbolic-report.md`。该 arm 只使用 public question 与 `evidence-corpus.json`，采用 token/phrase/number/LoCoMo speaker-name 绑定，不读 `gold.json`，不生成答案，不触发 embedding fallback。整体 Evidence Set Exact Match 为 0.375，与 dense 持平；All-Evidence@10 为 0.625，Mean Evidence Recall@10 为 0.71875，Mean Evidence Precision@10 为 0.49410，abstention correctness 为 0.5，critical false positives 为 1，mean latency 为 74.58 ms/item。分源：BEAM ESEM/Recall/Precision 为 0.1/0.65/0.31；LoCoMo 为 0.0/0.55/0.1711；LongMemEval 为 0.9167/0.9167/0.9167，仍受 oracle haystack 限制。该结果说明浅层符号能部分修复 dense 的角色绑定和过量召回，但仍无法解决 causal answerability、冲突/更新闭包、证据边界和 LoCoMo 同说话者相似事件过召回；不得写成完整本体记忆能力。

2026-07-26 自然 benchmark 的第三个本项目 arm `symbolic_fallback` 已完成真实 FastEmbed guarded fallback v1，结果位于 `artifacts/natural-benchmark-slices/slice-v1/symbolic-fallback-fastembed-results.json`，评分位于 `symbolic-fallback-fastembed-score.json`，报告位于 `symbolic-fallback-fastembed-report.md`。该 arm 先运行 `symbolic`，仅在 symbolic 空结果且非 abstention item 时触发 FastEmbed fallback，不向非空 symbolic 结果追加 dense 证据。整体 Evidence Set Exact Match 为 0.40625，All-Evidence@10 为 0.65625，Mean Evidence Recall@10 为 0.75，Mean Evidence Precision@10 为 0.52535，abstention correctness 为 0.5，critical false positives 为 1，fallback trigger rate 为 0.03125，mean latency 为 131.17 ms/item。唯一 fallback 项是 `LONGMEMEVAL-6d550036`，symbolic 对 “led/currently leading projects” 空结果，fallback 找回 4/4 gold session evidence。该 slice-level retrieval gate 暂时满足“不低于 dense recall、结构 false positive 不高于 dense、abstention 不触发 fallback、证据 ID 可回指”的条件；但 fallback reason taxonomy 仍粗，且唯一 fallback 项属于 multi-session group，后续扩大自然 benchmark 前必须机器化区分 lexical/predicate missing-link recovery 与 structural reasoning failure。仍不得宣称 full benchmark、产品优势或外部 memory 系统本地对比分数。

2026-07-26 已完成 `symbolic_fallback` taxonomy v1，代码位于 `tools/natural_memory_benchmark/fallback_policy.py` 和 `symbolic_fallback_runner.py`，测试位于 `tests/natural_memory_benchmark/test_symbolic_fallback_runner.py`。新运行 `run-20260726Tsymbolic-fallback-taxonomy-fastembed` 的结果位于 `artifacts/natural-benchmark-slices/slice-v1/symbolic-fallback-taxonomy-fastembed-results.json`，评分为 `symbolic-fallback-taxonomy-fastembed-score.json`，报告为 `symbolic-fallback-taxonomy-fastembed-report.md`。指标与 guarded fallback v1 相同：ESEM 0.40625、All-Evidence@10 0.65625、Recall 0.75、Precision 0.52535、critical FP 1、fallback trigger rate 0.03125；但 metadata 现在记录 `fallback_decision`、`fallback_reason_candidate` 和 `fallback_allowed`。本轮 30 项 `not_needed`、1 项 `blocked`（`BEAM-100K-C001-abstention-002`，`abstention_or_answerability_missing`）、1 项 `triggered`（`LONGMEMEVAL-6d550036`，`lexical_predicate_missing_link`）。AMR-style ontology extension 设计备注已写入 `docs/designs/2026-07-26-amr-style-ontology-extension-note.md`；其中 KEOL 固定落库假设已被后续 representation-agnostic contract 取代，KEOL 当前仅为 optional projection adapter。

2026-07-26 已完成 `symbolic_fallback` answerability v2，代码新增 `tools/natural_memory_benchmark/answerability_policy.py` 并接入 `symbolic_fallback_runner.py`，测试覆盖 `tests/natural_memory_benchmark/test_answerability_policy.py` 与 `test_symbolic_fallback_runner.py`。正式 v2 运行 `run-20260726Tsymbolic-fallback-answerability-v2-fastembed` 的结果位于 `artifacts/natural-benchmark-slices/slice-v1/symbolic-fallback-answerability-v2-fastembed-results.json`，评分为 `symbolic-fallback-answerability-v2-fastembed-score.json`，报告为 `symbolic-fallback-answerability-v2-fastembed-report.md`。该 gate 只处理窄 causal/how answerability：区分“证据提到反馈与 UI/UX”和“证据说明反馈如何造成具体改动”，并修正 `led` 词义误判，只把 `led to/lead to` 当作因果。slice-v1 指标：ESEM 0.4375、All-Evidence@10 0.6875、Recall 0.78125、Precision 0.5565972222222222、abstention correctness 1.0、critical FP 0、fallback trigger rate 0.03125；唯一 answerability block 是 `BEAM-100K-C001-abstention-001`，唯一 fallback 仍是 `LONGMEMEVAL-6d550036`。该结果支持 AMR-style extended ontology IR 需要显式 causal role、predicate sense 与 `answerable_by`/证据完整性约束；仍不能写成外部 memory 系统本地对比或产品优势。

2026-07-27 已固化事件-角色-证据闭包表示设计，文档位于 `docs/designs/2026-07-27-event-role-evidence-closure-representation-design.md`，并回指 `docs/designs/2026-07-26-amr-style-ontology-extension-note.md`。当前方案将用户的两层建模扩展为 `L1 原子事件-角色层 -> linking/normalization/lifecycle/closure 中间层 -> L2 跨轮/跨 session 抽象层`：L1 面向单句/单轮局部事件、状态、偏好、任务和属性；中间层负责 entity linking、predicate sense、canonical predicate identity、event identity、temporal normalization、lifecycle、closure 与 admission；L2 只允许生成可回指 L1 和 raw evidence 的派生抽象。物理表示格式保持开放，必须通过统一 conformance gate。

2026-07-27 事件-角色-证据闭包最小 IR 与诊断 runner/report 已完成第一版实现。实施计划位于 `docs/plans/2026-07-27-event-role-evidence-closure-implementation-plan.md`；核心 IR 代码位于 `tools/natural_memory_benchmark/semantic_ir.py`；runner/report 位于 `tools/natural_memory_benchmark/semantic_ir_runner.py`；测试位于 `tests/natural_memory_benchmark/test_semantic_ir.py` 和 `tests/natural_memory_benchmark/test_semantic_ir_runner.py`。当前实现只使用手写 IR，不含模型抽取、不扩大 benchmark、不改变 slice/gold 合同。已覆盖：严格 L1/L2/Closure/QuerySlotPlan 合同、L1 evidence 必填、L2 abstracts/closure/provenance 必填、closure completeness、结构缺口禁止 fallback、lexical/evidence candidate 缺口允许 fallback、`led/manage` vs `led-to/cause`、feedback causal answerability、multi-session evidence closure、current preference supersession。正式诊断产物为 `artifacts/natural-benchmark-slices/slice-v1/semantic-ir-diagnostic-results.json` 和 `artifacts/natural-benchmark-slices/slice-v1/semantic-ir-diagnostic-report.md`，运行 `run-20260727Tsemantic-ir-diagnostic` 为 5/5 pass、1 个预期 abstention、0 个 fallback allowed。验证结果：`test_semantic_ir.py` 为 13 passed，`test_semantic_ir_runner.py` 为 4 passed，`tests/natural_memory_benchmark` 为 53 passed，`validate-slice` 和 `validate-ledger` 均 valid。真实 slice item 映射已在下一条状态中完成；后续不是直接接模型抽取，而是先扩展更多真实 item 与多 profile conformance 映射。

2026-07-27 真实 slice semantic IR 映射诊断已完成第一版。计划位于 `docs/plans/2026-07-27-real-slice-semantic-ir-mapping-plan.md`，实现位于 `tools/natural_memory_benchmark/semantic_ir_slice_runner.py`，测试位于 `tests/natural_memory_benchmark/test_semantic_ir_slice_runner.py`。正式产物为 `artifacts/natural-benchmark-slices/slice-v1/semantic-ir-slice-diagnostic-results.json` 和 `semantic-ir-slice-diagnostic-report.md`；运行 `run-20260727Tsemantic-ir-real-slice` 为 5/5 pass。5 个真实冻结 item 覆盖 causal answerability、lexical fallback elimination、conflict evidence closure、update supersession closure 和 temporal chain closure；IR evidence exact 为 5/5，现有 `symbolic_fallback + answerability v2` evidence exact 为 3/5，IR evidence-exact improvement 为 2，现有 fallback triggered 为 1，IR fallback allowed 为 0，IR abstention 为 1。该结果仍是 hand-authored mapping，不含模型抽取、不生成答案、不授权完整 benchmark 或产品优势宣称。验证结果：`test_semantic_ir_slice_runner.py` 为 4 passed，`tests/natural_memory_benchmark` 为 57 passed，`validate-slice` 和 `validate-ledger` 均 valid。下一步应将相同 L1/L2 bundle 映射到多个候选 profile，并比较 round-trip、closure parity 与 query semantics。

2026-07-27 semantic IR 到 KEOL-shaped JSON 的最小 projection adapter 已完成第一版。计划位于 `docs/plans/2026-07-27-semantic-ir-keol-projection-plan.md`，实现位于 `tools/natural_memory_benchmark/semantic_ir_keol_projection.py`，测试位于 `tests/natural_memory_benchmark/test_semantic_ir_keol_projection.py`，正式产物为 `artifacts/natural-benchmark-slices/slice-v1/semantic-ir-keol-projection.json`。该产物基于上述 5 个真实 slice IR case，生成 13 条 Evidence、19 条 Assertion，保留 `semantic_ir_unit_id`、level、predicate sense、source status、lifecycle、role bindings、derived assertion IDs 和 closure metadata。该 adapter 只验证字段映射合同，不写入或修改 `artifacts/keol-baseline/`，不代表 KEOL baseline 已支持完整 IR 自动落库。验证结果：`test_semantic_ir_keol_projection.py` 为 4 passed，`tests/natural_memory_benchmark` 为 61 passed，`validate-slice` 和 `validate-ledger` 均 valid。后续已完成 KEOL native validation 与 raw-evidence trace；这些属于 optional-adapter assessment，不是存储选型步骤。

2026-07-27 semantic IR KEOL projection 回查链已完成第一版。实现位于 `tools/natural_memory_benchmark/semantic_ir_keol_trace.py`，测试位于 `tests/natural_memory_benchmark/test_semantic_ir_keol_trace.py`，正式产物为 `artifacts/natural-benchmark-slices/slice-v1/semantic-ir-keol-trace.json` 和 `semantic-ir-keol-trace-report.md`。该报告验证 `Assertion -> Evidence -> source quote` 链路：19 条 Assertion 中 19 条都有 evidence trace，6 条同时有 derived provenance，broken evidence refs 为 0。该报告只验证本地 projection 的追溯链，不代表 KEOL runtime ingest、自动抽取或答案生成已经完成。验证结果：`test_semantic_ir_keol_trace.py` 为 4 passed，`tests/natural_memory_benchmark` 为 65 passed，`validate-slice` 和 `validate-ledger` 均 valid。该历史下一步已被 representation conformance 与 KEOL projection v2 assessment 覆盖，不再作为主线。

2026-07-27 representation contract 与 conformance v3 已完成。设计为 `docs/designs/2026-07-27-representation-agnostic-memory-contract-design.md`，实现为 `representation_contract.py`、`representation_conformance_runner.py`，正式有效产物为 `representation-conformance-results-v3.json` 和 `representation-conformance-report-v3.md`。bundle integrity valid、exact round-trip、5/5 scoped query probes；较早 v1 conformance 缺少 query scope，存在跨-case matched-unit 串扰，已作废并保留审计。v3 将 raw-source revision binding、immutable lifecycle revision、structured L2 semantics 与 closure-evaluation versioning 设为 hard capabilities；Semantic IR 仅为 `reference_carrier`，`authoritative_ready=false`。

2026-07-27 KEOL optional adapter 原生验证与 projection v2 已完成。旧 v1 projection 为 0 native error/36 warnings，且 closure parity mismatch 4；新 v2 在投影前物化 closure，parity mismatch 0、native error 0、warning 30。v2 仍无 reverse round-trip 与 runtime constraint execution，classification=`projection_only`。不得把 Pydantic 可解析、0 error 或 trace 完整写成最终存储选型通过。

2026-07-27 Extended-AMR conformance v4 已完成。实现位于 `tools/natural_memory_benchmark/extended_amr_adapter.py`，测试位于 `tests/natural_memory_benchmark/test_extended_amr_adapter.py`；正式不可变产物为 `representation-conformance-results-v4.json` 和 `representation-conformance-report-v4.md`。`extended-amr-memory-graph-v1` 使用显式 predicate/entity/abstraction/reference nodes、角色/派生 edges 与 typed memory annotations，不保存 opaque L1/L2 副本。正式运行中 exact round-trip、bundle integrity 和 5/5 scoped query probes 均通过；但 `raw_source_revision_binding`、`lifecycle_and_revision`、`structured_l2_semantics`、`closure_evaluation_versioning` 仍为 unsupported，所以 `status=fail`、`authoritative_ready=false`。该结果只证明候选 adapter 无损，不构成最终存储选型、自动抽取质量或 benchmark 优势结论。新鲜验证为 `tests/natural_memory_benchmark` 84 passed，`validate-slice` 与 `validate-ledger` 均 valid。

### Gold-set 数据源评估

- **WildChat-1M（当前管理/学习主来源）**：<https://huggingface.co/datasets/allenai/WildChat-1M>。数据卡说明约 1M 条人类用户与 ChatGPT 的交互，当前版本已去标识、移除已识别的 PII/敏感内容并过滤有毒对话，许可证为 ODC-By。本轮从一个公开 Parquet 分片中筛选管理、学习和技术排错主题；Agent 内容默认标记为 `generated_unverified`，不直接当作现实事实。
- **Taskmaster-2 WOZ（保留自然任务对话）**：<https://huggingface.co/datasets/DeepPavlov/TaskMaster2>。本轮只保留一条航班候选，作为多约束方案比较和任务完成的对照；其余客服化 Taskmaster 候选已移除。
- **τ-bench historical trajectories（保留行动轨迹）**：<https://github.com/sierra-research/tau-bench/tree/main/historical_trajectories>。本轮只保留一条含确认、退货、取消、工具执行和后续任务推进的成功轨迹；用户由模拟器生成，不把它当作真人语言真实感来源。
- **ABCD（后续动作/状态来源）**：<https://github.com/asappresearch/abcd>。超过 10K 条真人客服对话，包含 55 类用户意图及显式 `action` 消息，适合后续 Action/State 本体和多步策略验证；由于原始消息流中的 `action` 会打断 `customer/agent` 交替，本轮不直接作为三轮窗口主来源。
- **LongMemEval（后续长时记忆评测）**：<https://github.com/xiaowu0162/LongMemEval>。包含 500 个问题、约 115K 或更长的时间戳会话历史，覆盖信息抽取、多 session 推理、知识更新、时间推理和拒答；其会话适合证据回指和查询评测，但部分 assistant 回复模板化，本轮不作为自然对话主来源。
- **LoCoMo（后续跨 session 参考）**：<https://github.com/snap-research/locomo>。包含 10 条很长、自然度较高的跨时间对话，但主要是两个说话者之间的社交对话，不满足当前 user-agent 角色约束；可用于后续跨 session 摘要、事件和高层 KE 研究。
- **BEAM（保留比较项）**：<https://huggingface.co/datasets/Mohammadta/BEAM>。保留一条此前人工指定的日期矛盾片段，用于比较其事实冲突与其他来源任务状态的抽取差异；不再把 BEAM 的所有候选自动视为 gold-set 主来源。
- **schema.org（属性槽位参考）**：<https://schema.org/>。只参考 `Action`、`Event`、`Order`、`duration`、`agent`、`object`、`result`、`status` 等通用属性槽位，不把 schema.org 词汇自动写成事实或强制覆盖 KEOL。
- **Ontology-Specification（私有电商本体参考）**：<https://github.com/genuineknowledge/Ontology-Specification>。只参考 Concept/Operator 的粒度、输入输出和描述字段；本轮实际运行以 KEOL `44631e6` schema 为准，不把私有仓库内容复制进 gold。

2026-07-27 identity resolution v1 续：已按用户决定将 Extended-AMR 作为主候选 carrier，并实现表示无关的 identity-aware v4 合同、schema.org 30.0 启发的本地概念注册表、`merge/keep_distinct/reject_merge/split/abstain` 决策、身份证据闭包、作用域化 identity snapshot 和安全 `count_distinct`。schema.org 参考冻结自官方 `schemaorg/schemaorg` 提交 `f72e60b7f67578b4af9445fa20fc8ec3fe1c9b93`；`Project` 因本地概念覆盖个人/课程项目只作 `related` 映射，`sameAs` 只作外部 URL 模式且不具事实或身份权威。Extended-AMR v3 显式编码 concept/entity/decision/closure/snapshot/aggregate 图并可精确反解 native v4。冻结诊断 `gold-v1` 含 4 dev + 4 hidden 手写场景；正式运行 `run-20260727T080000Z-identity-v1` 为 `pass`：critical false merge 0，answerable count/evidence/abstention/revision/closure 均 1.0，structural fallback rate 0，Native v4 与 Extended-AMR v3 round-trip/query parity 均 1.0。JSON/报告 SHA-256 为 `e7cc632ae20f6436156fcd9c777352eac0f8286e63cb24f42ddee05875ae633c`、`bc032cf6a5590a8d1f12adf5d523af9da65d599b66ceddac52667d213b920ae8`，隔离重放字节一致；完整 `tests/natural_memory_benchmark` 为 133 passed。`identity_authoritative_ready=true` 只适用于该手写身份契约诊断，不代表自动 entity linking、最终存储或产品优势；冻结 v5 LongMemEval 仍保持 `structured_l2_identity_unresolved`，其结果哈希未变。下一步应预注册更大的自然 identity/membership slice 或模型只提议、程序 gate 接受的 identity proposal 实验。

2026-07-27 natural identity/membership proposal v1 已完成，设计与计划为 `docs/designs/2026-07-27-natural-identity-membership-proposal-design.md`、`docs/plans/2026-07-27-natural-identity-membership-proposal-plan.md`。冻结 12 个自然文本 case（6 dev + 6 hidden），正式数据与结果位于 `artifacts/identity-memory-experiment/natural-v1/`；`public.json`、`authority.json`、`gold.json` 严格分离，reference proposer 只读 public，identity/membership 的接受权只属于 deterministic evidence/policy gate。正式运行 `run-20260727T090000Z-natural-identity-reference-v1` 为 `gate_safety_ready=true`、`proposal_quality_ready=false`：raw accuracy 0.8333333333333334、raw critical false merge 1、gate intervention 2；gated accuracy 1.0、gated critical false merge/membership 均 0、evidence exact 1.0、structural fallback 0。两个 intervention 分别把无权威证据的 budget-repository `keep_distinct` 和 LongMemEval project `merge` 降为 abstain。score/report SHA-256 为 `d346eb0f0d277be39fad363da8f4f89f98b0fc4a49be2a95c0970f62abf562b2`、`45d0dd7452873e0df8545b9930b19aad6938b2ea764cc2177a16de3e05ba380a`，7 个生成文件隔离重放字节一致；完整自然 memory 测试 143 passed，slice/ledger valid，冻结 identity v1 与 authoritative v5 哈希保持不变。`核心影响：无`：未修改基础本体、动态扩展接口、L1/L2 抽取、问题处理、召回或 embedding fallback。其后真实模型读取冻结 `public.json` 的 proposal-only run 已完成，但因 public 标识符带有结果暗示而不能作为 clean model-quality evidence；仍不授权自动 merge 或 membership 写入，`LONGMEMEVAL-6d550036` 继续以 `structured_l2_identity_unresolved` abstain。

2026-07-27 H100 真实 proposal-only 模型运行完成：全新 `fork_turns="none"` proposer 仅读取冻结 `public.json`，以 `codex-gpt-5.6-sol@2026-07-27` 生成 `run-20260727T104020Z-codex-gpt-5-6-sol-proposal-only-v1` 的完整 12-case 候选。scorer 机械结果为 `gate_safety_ready=true`、`proposal_quality_ready=true`；raw/gated accuracy、raw abstention F1、proposal/required evidence exact 均为 1.0，raw/gated critical false merge/membership 均为 0，gate intervention、structural fallback 和失败 case 均为 0。public/authority/gold/manifest 文件 SHA-256 分别为 `2020abb0f13cb91648e0bdf64eb53cc27b3ca8b12783e3aedba0280280270cf3`、`c5a877ea2420ec65aa41020d77febaba6314528ef7586abfe1c42dbeaebf8985`、`347f185e7364920a1a041074dfb9a74de7585111cb49d726336e3efb97df839b`、`023c6a06ddab7d71d21c8483d48da7b655d245ebf41265cbdd021f4eafd75d0d`；proposal 文件/canonical hash 为 `69fb067e6352f23c7b2abc873653545a82ed0f9f65f3f9ef668f8631b141a376`/`d42622f050d39d398a1d424efa91227395b3e340c7a65d88ac8f5d106feaa4b8`，score/report 文件哈希为 `94d804b3ba2b25acd77c1173e3fb4835778e36e99ac164088c52c3edb87eef9f`、`194037cda17a4466ba2d9ee23d7235884b958c3f347fed75867d4df493f6c1b7`；scorer 原位重放一致，三份新产物已设为只读。只读复审确认 `public.json` 的 proposer 可见 `case_id`/`mention_id` 包含 `distinct`、`mismatch`、`member`、`unresolved` 等 outcome-bearing token，可能泄露预期动作；因此 `gate_safety_ready=true` 仍是有效的 gate 安全诊断，而 `proposal_quality_ready=true` 只记录 scorer 合同下的机械值，不能充当无污染的模型质量证据。该 run 与 public v1 保持不可变。`.venv-h100` 使用 Python 3.13.5 与最小测试依赖；H100 迁移只修正两处测试路径 fixture，核心 runner/骨架未修改。focused 10 passed、完整 natural memory 143 passed，natural identity/slice/ledger valid，identity-v1、authoritative-v5 与 reference 哈希不变。`核心影响：无`。clean model-quality evidence 尚未取得；本轮不授权自动 merge/membership/L2 写入，`LONGMEMEVAL-6d550036` 继续保持 `structured_l2_identity_unresolved`。下一步必须先预注册并冻结 opaque-ID v2 slice，再由新的隔离 proposer 重跑，不能把本次机械 gate pass 外推为存储、产品、UX 或外部系统优势。

2026-07-27 opaque-ID v2 clean model run 已完成。`natural-v2` 冻结 12 个与 v1 语义等价的 case，public ID 只匹配 `case-[0-9a-f]{16}`/`mention-[0-9a-f]{16}`，public SHA-256 为 `66e52df63f55c087e63de3f667e926c362252d5076834bb092719184cc86bbcf`。新 `fork_turns="none"` proposer 仅读取冻结 prompt/public，proposal/provenance 在 authority/gold scoring 前冻结；proposal SHA-256 为 `55034bc117c589baf434c6181439eaa57e3158b9a404f9ffa102769a1c5d7f8d`，provenance 记录 `authority_or_gold_read_before_freeze=false`，隔离只声明为 declarative file-access contract。正式 scorer 分开给出 `gate_safety_ready=true`、`proposal_quality_ready=false`：raw accuracy `0.8333333333333334`、critical false merge `1`、critical false membership `0`、abstention F1 `0.0`、evidence exact `1.0`；dev repository/application case 错误 merge，hidden LongMemEval project case错误 keep-distinct，二者 gold 均为 abstain。gate 两次均降为 abstain，gated accuracy `1.0` 且 gated critical error 为 0，但不得用该安全结果掩盖 raw 失败。score/report SHA-256 为 `3124ade877c4aaf8d81518f75587ac219acc1ff8060b80acfadff06650d8875e`、`76ae0df98040eb269467ca4a4454955434e7bc8f899455d0abd7d76466560037`，隔离重放字节一致。最终审查后 validator 已增加固定 namespace/派生 ID 重算、v1 -> v2 public/authority/gold canonical equivalence、strict preregistration boundary 与只读权限检查；focused 27 passed、完整 natural memory 160 passed、四个 validator valid、13 项受保护哈希不变，正式 v2 文件全部 `0444`。renderer 固定的 reference-proposer 文案未改，真实身份以冻结 metadata 为准。`核心影响：无`；下一步只允许用 dev/诊断数据修复 false merge/abstention，再冻结新版本和 fresh hidden，仍不授权自动 merge/membership/L2 写入，`LONGMEMEVAL-6d550036` 保持 `structured_l2_identity_unresolved`。

2026-07-27 dev repair 与 fresh-v3 已完成。policy-v2 的真实 dev run raw quality 失败并保持冻结；只根据 dev false merge 新增可观察 coreference 限制后，policy-v3（SHA-256 `781184fe9605f401781ac3461b9f85a718236fd3b7479c0877cbb0cb02fe85c0`）在 6 个 dev case 上 raw accuracy/abstention F1/evidence exact 均为 1.0，critical false merge/membership 为 0/0。policy/final prompt 先冻结，之后才创作 6 个 fresh hidden case；`natural-v3-fresh` 共 12 cases，六类 hidden action 各 1，3 个 cross-session，v2 ID/source-ID/evidence-combination overlap 均为 0，formal 8 个 JSON 为 `0444`。final 单消息零历史 proposer `run-20260727T160000Z-claude-sonnet-4-6-fresh-v3` 的 proposals 在 authority/gold scoring 前冻结；raw `proposal_quality_ready=true`（accuracy `0.9166666666666666`、critical false merge/membership `0/0`、abstention F1 `0.8571428571428571`、evidence exact `1.0`），但完整 `gate_safety_ready=false`，因为 hidden membership actor-mismatch case 被错误 abstain，gate 按设计不反向补写 exclude，gated accuracy 仍为 `0.9166666666666666`。proposals/score/report/error-analysis SHA-256 为 `8621abdf18359fe04d4c3f9ea965c8ef676331eab691d11eac6115ab13831f36`、`5a4b9163acff61652cc6650cebb816587eb4f4dca3b89315f75d3af05c6f933d`、`95ccdaeed364b1c16f1ad84d7b777aa4584725fc004da98223c576f97ec11f47`、`eb1cf665893ae692ff945a19f741635d4f21f653fedd115f0832ff135713e5b6`；score/report 重放一致。最终审查后，dev source 现在必须只读并与已验证冻结 opaque-v2 source 字节一致；正式 chronology 现在检查 policy freeze < 完整 passing dev run < hidden source，并由只读 `chronology-receipt-v3.json`（SHA-256 `ad7e5e9fd8865be16afbb4e73416600455bdf7b909db60df31fe7fea77b04240`）绑定这些文件的哈希与 mtime；正式 fresh root 只接受正式 v2/policy/hidden 路径，不能用临时副本跳过收据。该收据是 posthoc filesystem audit，不是外部可信时间戳；模型隔离仍只能按 declarative transport/provenance 边界解释。focused 42 passed、完整 natural memory 175 passed、fresh/opaque/base/slice/ledger validators valid、25 项受保护哈希不变、26 个正式与审计文件均不可写。`核心影响：无`。只允许保留 public-only proposer -> immutable proposal queue -> unchanged gate 的候选设计，pipeline 接入仍延期；不得用 fresh hidden 改 policy-v3，不授权自动写入，`LONGMEMEVAL-6d550036` 保持 unresolved。

## 未决问题

以下问题在得到实验或人工裁决前，不要擅自写成架构事实：

1. 各 representation profile 与 ES 词表/人工本体的 canonical identity 优先级、冲突合并和稳定 ID 策略；KEOL 只是其中一个 adapter。
2. representation profile go/no-go 的最低覆盖率、表达力、round-trip、closure/query 等价和运行成本阈值。
3. 当前 KEOL baseline 只在 turn metadata 保留 user/agent 顺序，核心 Assertion 尚未承载 `extracted`、`generated_unverified`、`tool_observed` 等认识论状态；哪些 Agent 输出可以升级为现实事实及其判据仍未决。
4. 跨 session 高层概念（尤其 `Task`）的聚合触发条件、回指结构和生命周期。
5. Q1 必须支持的查询集合、时间区间/最近事件语义和并列结果规则。
6. embedding 缺口的标注规范、融合策略和精确率保护阈值。
7. ES 词表的实际来源、索引结构、导出格式和刷新机制。
8. KEOL 当前 edge -> builder 单层路径如何扩展为可验证的嵌套 Term，以及复合 operator 的拆分/合并规则。
9. AMR 单句 pilot 已完成生成和双盲评审，但 7 个语义判断仍待用户裁决；在裁决完成前，A/B/C 最终质量分数、gate decision 和节点是否通过均未决。token、cost、逐调用 latency 以及 PropBank frame inventory 仍为 `unavailable`，对应效率和 frame-membership 结论不得伪造为可判定。
10. 本体化记忆优势实验首轮 gate 为 `fail`：充分表示的 oracle ceiling 已通过，但 automatic `O+` 只保留 22.9% 相对增益。下一步仍未决的是最小充分物理表示、自动 temporal provenance/supersession 闭包、normalized conjunction/multihop 编译、alias/sense/absence 表达，以及能实际触发且不覆盖显式约束的 embedding fallback。修复只能在 dev 上开发，并须以新版本重新冻结 hidden；不得把 oracle 结果写成当前端到端系统能力，也不得把 0 fallback 触发写成 embedding 有效。
11. 2026-07-25 v3 automatic compiler 已完成 dev-only 修复，记录在 `artifacts/ontology-memory-experiment/reports/v3-dev-compiler-report.md`。修复覆盖 temporal provenance/supersession closure、`linked_to` conjunction/multihop、`sense_of` lexical context 和 explicit absence owner query；`run-20260725T172000Z-v3-diagnostic-dev` 为 432 rows、0 error、verify valid，automatic `O+`/`O+E` 在 diagnostic dev 上 ESEM/Answer/Constraint 均为 1.0。该结果不是新的 hidden gate；real dense dev 当时未在本地复跑，因为 Windows `D:\Anaconda\python.exe` 缺少 `fastembed`。`O+E` fallback 仍为 0，embedding 兜底仍未被证明。
12. 2026-07-25 v3 fallback probe 已冻结并 diagnostic 验证，记录在 `artifacts/ontology-memory-experiment/reports/v3-fallback-probe-report.md`。`artifacts/ontology-memory-experiment/gold-v3/` 含 64 scenarios、35,200 distractors，新增 4 个 lexical uncovered-predicate fallback probes（1 dev、3 hidden）。`run-20260725T181000Z-v3-diagnostic-all` 为 2,304 rows、0 error、verify valid；automatic `O+E` fallback rate 为 0.0625，structural-family fallback rate 为 0.0，新增 probes 上 `O+` 为 0.0 而 `O+E` 为 1.0。该结果只证明 guarded fallback 路径在 diagnostic encoder 下非空且可约束执行，不是 real dense hidden gate，也不能写成 embedding 模型有效。收尾时修复了 `validate-gold` 的 manifest 默认行为：未传 `--manifest` 时按 `--source` 所在目录读取 `manifest.json`，避免用 v3 文件误配 v2 manifest。
13. 2026-07-25 v3 real dense 已在工作区隔离环境 `.venv-dense` 中完成，记录在 `artifacts/ontology-memory-experiment/reports/v3-real-dense-report.md`，gate 报告为 `artifacts/ontology-memory-experiment/reports/v3-real-hidden-gate-report.md`。`run-20260725T190000Z-v3-real-dev` 为 468 rows、0 error、verify valid；`run-20260725T192000Z-v3-real-hidden` 为 1,836 rows、0 error、verify valid，模型为 `qdrant/bge-small-en-v1.5-onnx-q@52398278842ec682c6f32300af41344b1c0b0bb2`。真实 hidden gate 仍为 `fail`，唯一失败门是 `automatic_retained_gain=0.16339869281045752`；automatic `O+E` hidden ESEM/Answer/Constraint 为 0.294/0.627/0.706，fallback rate 为 0.0588，structural-family fallback rate 为 0.0。真实 embedding fallback 已证明能解决 3 个 hidden lexical fallback probes，但自动本体/查询管线整体仍不得进入 LoCoMo、BEAM、LongMemEval 等大 benchmark。
14. 2026-07-25 parser 修复 post-hoc 续跑已完成，记录在 `artifacts/ontology-memory-experiment/reports/v3-parser2-posthoc-repair-report.md`，post-hoc gate 报告为 `artifacts/ontology-memory-experiment/reports/v3-parser2-posthoc-hidden-gate-report.md`。本轮只改 automatic 表示适配器，新增 4 个回归测试，覆盖 `connected`/`exact set contains`、`Before ... log recorded ... as active`、`used ledger for ...`、`denotes ... rather than ...` 和显式 owner absence。`run-20260725T202000Z-v3-parser2-diagnostic-all` 为 2,304 rows、0 error、verify valid，automatic `O+E` diagnostic ESEM/Answer/Constraint 均为 1.0；`run-20260725T203000Z-v3-parser2-real-dev` 为 468 rows、0 error、verify valid，automatic `O+E` real dev 仍为 1.0；`run-20260725T204000Z-v3-parser2-real-hidden` 为 1,836 rows、0 error、verify valid，post-hoc gate 为 `pass`，`automatic_retained_gain=0.8431372549019608`，automatic `O+E` hidden ESEM/Answer/Constraint 均为 1.0，fallback rate 为 0.0588，structural-family fallback rate 为 0.0。该 pass 只是已暴露 v3 hidden 上的回归检查，不能作为 clean go/no-go；下一步必须冻结 v4 fresh hidden 后重跑，才能决定是否进入 LoCoMo、BEAM、LongMemEval。
15. 2026-07-26 v4 fresh hidden 已重跑，记录在 `artifacts/ontology-memory-experiment/reports/v4-real-hidden-gate-report.md` 和 `v4-real-hidden-metrics.json`。clean gate 仍为 `fail`，唯一失败门是 `automatic_retained_gain=0.47058823529411764`；automatic `O+E` hidden ESEM 为 0.5294117647058824，fallback rate 为 0.058823529411764705，structural-family fallback rate 为 0.0。当前未决问题变为：automatic roles/quantity 证据边界需要避免把上下文/provenance turn 并入 gold evidence set；automatic conjunction/multihop 需要补足最后一跳/闭包证据回收；这些只能先在 dev 或新诊断集上修复，之后再冻结新的 fresh hidden。不得把 v3 post-hoc pass 或 v4 oracle pass 写成端到端可进入大 benchmark 的能力。
16. 2026-07-26 v5 fresh hidden clean gate 已通过，记录在 `artifacts/ontology-memory-experiment/reports/v5-real-hidden-gate-report.md` 和 `v5-real-hidden-metrics.json`。v5 的 dev/诊断修复只针对已定位的 automatic evidence boundary 与 multihop evidence closure：query 编译增加 `expected/supposed to approve` 的 planned modality，automatic representation 增加 `exact set includes/comprises` 闭包证据支持，并新增 v5 hidden 表面式和 `route` fallback probe。`run-20260726T040000Z-v5-real-dev` 为 468 rows、0 error、verify valid，automatic `O+E` dev ESEM/Answer/Constraint 均为 1.0；`run-20260726T041000Z-v5-real-hidden` 为 1,836 rows、0 error、verify valid，gate 为 `pass`，automatic `O+E` hidden ESEM/Answer/Constraint 均为 1.0。下一步应进入预注册自然 benchmark 小切片设计/冻结，或扩大受控集到每个 family 至少 50 独立场景；仍不得跳到全量 benchmark 或产品级优势宣称。
17. 2026-07-26 自然 benchmark slice-v1 已冻结并通过结构验证，记录在 `artifacts/natural-benchmark-slices/`。该切片只授权小范围本项目 arm 对照，不授权全量 benchmark、不授权产品级优势宣称，也不授权本地复跑 Mem0、Graphiti、Hindsight、MemPalace、Zep 等外部系统。当前 scorer、gold evidence resolver、evidence corpus、真实 FastEmbed `dense_reference`、规则/槽位 `symbolic` v1、guarded `symbolic_fallback` v1、fallback taxonomy v1 和 answerability v2 已完成；36 个 `tests/natural_memory_benchmark` 测试通过，`validate-slice` 与 `validate-ledger` 均 valid。symbolic v1 暴露了伪本体/浅层符号的能力上限；symbolic_fallback taxonomy v1 支持 embedding 作为受控证据恢复；answerability v2 证明窄因果可答性 gate 能移除该切片上的剩余 critical FP，但尚未证明可扩展到完整 benchmark 或产品环境。
18. 2026-07-27 事件-角色-证据闭包表示设计、最小 IR 合同/执行器与诊断 runner/report 已完成，设计记录在 `docs/designs/2026-07-27-event-role-evidence-closure-representation-design.md`，实施计划记录在 `docs/plans/2026-07-27-event-role-evidence-closure-implementation-plan.md`，实现位于 `tools/natural_memory_benchmark/semantic_ir.py` 和 `tools/natural_memory_benchmark/semantic_ir_runner.py`。
19. 2026-07-27 真实 slice semantic IR 映射诊断已完成第一版，计划记录在 `docs/plans/2026-07-27-real-slice-semantic-ir-mapping-plan.md`，实现位于 `tools/natural_memory_benchmark/semantic_ir_slice_runner.py`，测试位于 `tests/natural_memory_benchmark/test_semantic_ir_slice_runner.py`。正式产物为 `artifacts/natural-benchmark-slices/slice-v1/semantic-ir-slice-diagnostic-results.json` 和 `semantic-ir-slice-diagnostic-report.md`。本轮手写映射 5 个真实冻结 item：`BEAM-100K-C001-abstention-001`、`LONGMEMEVAL-6d550036`、`BEAM-100K-C001-contradiction_resolution-001`、`BEAM-100K-C001-knowledge_update-002`、`LONGMEMEVAL-gpt4_2655b836`；运行 `run-20260727Tsemantic-ir-real-slice` 为 5/5 pass，IR evidence exact 为 5/5，现有 `symbolic_fallback + answerability v2` evidence exact 为 3/5，IR evidence-exact improvement 为 2，现有 fallback triggered 为 1，IR fallback allowed 为 0，IR abstention 为 1。该结果只证明 hand-authored semantic IR 可以表达这些真实 slice 错误类型，不证明模型抽取质量、不生成答案、不授权完整 benchmark 或产品优势宣称。当前未决问题更新为：自然数据自动抽取、多个候选 profile 的 conformance、冲突/更新闭包的更多真实样本、证据边界、answer generation/judge、LoCoMo category 5 人工答案，以及 scorer 的 answer exact diagnostic 是否需要升级为 LLM judge 或 rubric-based judge。
20. 2026-07-27 semantic IR 到 KEOL projection adapter 已完成第一版，计划记录在 `docs/plans/2026-07-27-semantic-ir-keol-projection-plan.md`，实现位于 `tools/natural_memory_benchmark/semantic_ir_keol_projection.py`，产物位于 `artifacts/natural-benchmark-slices/slice-v1/semantic-ir-keol-projection.json`。该结果只证明 L1/L2/closure 可以 deterministic 投影为 KEOL-shaped Evidence/Operator/Individual/Assertion/WorkflowRun JSON，并保留 evidence 与 derived provenance；后续原生校验仍把它分类为 `projection_only`。KEOL-specific 未决项是 warning 消除、reverse round-trip 和 runtime constraint execution，不是把 projection 强制合并进 KEOL store。
21. 2026-07-27 projection 回查报告已完成第一版，产物位于 `artifacts/natural-benchmark-slices/slice-v1/semantic-ir-keol-trace.json` 和 `semantic-ir-keol-trace-report.md`。该结果证明当前 projection 内部没有断裂的 Assertion -> Evidence 链；候选 profile 的共同未决项是 native validation、reverse round-trip、runtime constraint execution、revision/raw-source binding、自然数据自动抽取和 answer generation/judge。真正写入/读取 KEOL store 仅属于 KEOL adapter 子项，不是主架构前置条件。
22. 最终物理表示仍未选定。历史 Extended-AMR v4 的四项 hard-capability 缺口已由 authoritative v3/v5 与 Extended-AMR v2 补齐；后续 identity-aware v4 与 Extended-AMR v3 又在冻结手写 identity 诊断上通过 round-trip、query parity、closure freshness 和安全聚合 gate。当前未决项已转为：更大的预注册自然 identity/membership slice、模型提出 identity candidate 的 false-merge/abstention 质量，以及最终存储的效率和运维比较。KEOL v2 仍是 `projection_only`，旧 KEOL v1 closure mismatch 与 conformance v1 query-scope 串扰继续保留为失败证据。真实 LongMemEval project identity 仍未解决，不能用诊断场景强行改成 count=2。
23. 2026-07-27 authoritative memory contract v3/v5 已完成收尾。实现位于 `tools/natural_memory_benchmark/authoritative_memory.py`、`extended_amr_v2_adapter.py`、`authoritative_conformance_runner.py`，正式 CLI 为 `run-authoritative-conformance`；不可变产物为 `representation-conformance-results-v5.json` 与 `representation-conformance-report-v5.md`。正式运行 `run-authoritative-conformance-v5` 中 source validation 有效并重放 13 个 source record，6/6 closure evaluation fresh、6/6 result parity、5/5 frozen correctness；Native v3 与 Extended-AMR v2 均 exact round-trip、5/5 query parity。五项 correctness oracle 已独立冻结（SHA-256 `cfebd096c369c4a982e9db0b09cb4b32a98cb165853f005cf52fe049a45d8659`），覆盖 matched claim；stale/incomplete active-L2 负向拒绝、逐 carrier correctness 和 measured capability gates 均进入 hard-gate 决策。两者只是同一 authoritative contract 的不同 carrier，最终存储表示仍未选定。LongMemEval count case 保留四份 evidence candidate，但 project identity 尚未归一，必须以 `structured_l2_identity_unresolved` abstain，因此两种 carrier 均 `authoritative_ready=false`；不得为得到 display count=2 而删除或放宽此 hard gate。正式结果与报告 SHA-256 分别为 `3ec6656c037200f8591fac44cd7e1e4bf2caa3aa9447f3fa5ba9854324d4cc33`、`9ef73e7a4a16409ef9f5edbb74e38b2c1b1b628821a4b13ce2bc0698f03a011a`，隔离回放字节一致，`tests/natural_memory_benchmark` 为 117 passed。该结果只证明表示契约、证据闭包、查询一致性和 correctness gate；不证明 AMR、KEOL、本体记忆或本项目优于外部 memory 系统，embedding fallback 也仍不是事实权威。

## 开发与维护规则

### 2026-07-26 A+B 在线记忆模块

- H100 实现已 fast-forward 合并到 `/public/home/wwb/KE_mem/ke-memory-demo` 的 `main`，当前提交 `6d44868`；原分支 `feature/ontology-agent-memory-ab` 和对应 worktree 已清理。固定 KEOL 源为 `/public/home/wwb/KE_mem/KEOL-44631e6`。
- 已完成 admission、闭合 KEOL bundle、SQLite/WAL 事务存储、抽取与生命周期适配、符号优先检索、受控 dense fallback、warmup context、纠错/遗忘和 FastAPI 接口。原始 turn 不可变，纠错与遗忘追加 revision/tombstone。
- 2026-07-26 从远程 worktree 根目录复验：`754 passed, 1 skipped`，Ruff 全通过，Pyright `0 errors`，`git diff --check` 通过。
- 合并前的离线服务曾在 H100 `127.0.0.1:8787` 通过 health/smoke，返回 `mode=offline`、`extraction_ready=false`、`database_integrity=ok`；为清理 worktree 已停止 PID `1196192`，对应 177 KB 临时 `state/` 已随 worktree 清理。离线 smoke 只验证原始 turn、幂等和空检索，不生成伪 KE。
- 生产抽取尚未 live-verify：服务进程未获得 `KE_MEMORY_WORK_API_KEY` 和 ES 配置。不得把离线 health/smoke 表述为生产抽取已可用，也不得把该工程完成状态外推为已经优于主流方案或已经改善 UX。
- 该阶段结束时仓库尚未配置 Git remote；此状态已被下方 2026-07-27 的结构重构与 GitHub 发布记录取代。

### 2026-07-27 H100 仓库结构与 CI/CD 基础

- 重构已 fast-forward 合并到 H100 `/public/home/wwb/KE_mem/ke-memory-demo` 的 `main`，并以非强制推送同步到 `git@github.com:wey-bo/KE-memory.git`；H100 `main` 与 GitHub `origin/main` 均为 `15da1ca7703dccfa91d0418efed581c2a3be024f`。`feature/restructure-ci-foundation`、`codex-sync/restructure-ci-foundation` 和对应 worktree 已清理。
- 可安装包边界已拆分为 `src/ke_memory_demo`（抽取、存储、检索、生命周期核心）、`service/ke_memory_service`（HTTP、MCP、runtime、用户/主体注册）和 `ontology/ke_memory_ontology`（本体合同、ES 与 KEOL profile adapter）。旧导入路径只保留显式兼容 facade；`MCPMemoryFacade` 保持 SDK-neutral，`PrincipalRegistry` 当前提供确定性的内存参考实现，持久化 adapter 仍是后续工作。
- CI/CD 基础包括 `.github/workflows/ci.yml`、`scripts/ci/check.sh`、布局与 wheel 产物验证、Hatch/uv 打包、`Dockerfile`、`.dockerignore` 和 `Makefile`。部署配置支持 `KE_MEMORY_ONLINE_MODE`、`KE_MEMORY_DATABASE_PATH`、`KE_MEMORY_HOST`、`KE_MEMORY_PORT`；容器以非 root 用户运行并把 `/app/state` 声明为持久卷。
- 2026-07-27 在提交 `15da1ca` 上分别从 feature worktree 和合并后的 H100 `main` 根目录 fresh 验证：两次均为 `767 passed, 1 skipped`，Ruff 全通过，Pyright `0 errors`，布局检查通过，sdist/wheel 构建通过；`ke_memory_demo`、`ke_memory_service`、`ke_memory_ontology` 均已从构建出的 wheel 隔离导入。该验证同时补上了 `core` 与 `infra` 的显式包初始化，避免源码树可导入但 wheel zipimport 失败。
- H100 上 Docker CLI 可见但 daemon `unix:///run/user/1025/docker.sock` 不可连接，因此不能宣称镜像 build 或 container smoke 已通过。生产抽取、真实 ES、用户持久化和 MCP SDK/transport 注册也仍未 live-verify。

- 先读本文件和相关方案/计划，再改代码或数据格式。
- 不得访问或借鉴之前 Fusion Memory 项目的任何代码、测试、架构实现、评测逻辑和实验结论；发现相关路径或材料时跳过。
- 优先复用与能力契约兼容的 KEOL 语义，但不得为了兼容 KEOL 丢失角色、时间、认识论状态、闭包或证据粒度；任何 profile 新增字段必须说明兼容性和来源。
- 任何抽取、归一或查询功能都要有最小 gold/fixture 和可重复的验证命令。
- 不用 embedding 掩盖符号 schema 缺失；先记录缺口，再做实验。
- 不把一次性 benchmark 规则、qid、gold answer 或自然语言模板写成产品语义。
- 修改后更新本文件的当前状态、未决问题或执行波次；保持它与 `安排.md` 同步。

### 2026-07-30 Typed extractor fresh-v3 qualification

- 正式 fresh-v3 qualification run label 为 `20260730T061218Z`。L1/L2 dispatch 先全部冻结，再各执行一次 `deepseek-chat` 请求；请求数严格为 `1/1`，两层均在 raw response 产生前收到 `HTTPError: HTTP Error 403: Forbidden`，未 retry 或 fallback。
- 由于两层均无 raw response，未生成 proposal/provenance/score/layer qualification，也未进入 authority/gold scoring。最终结论是 `incomplete_not_qualified`，表示 transport/authorization 未完成，不是已测得的 extraction-quality fail；自动抽取效果仍未测量。
- L1/L2 failure receipt SHA-256 为 `5bf32c6357ec856c5e5dfe741c0d048c685ec3fff13a51a3de06f912d99fa8aa` / `a5645f0d863c49063a619a2823e53ff0b11d9bc292522bf61c2c3ffffdb6a21d`；overall score/report/chronology SHA-256 为 `28b0719b767328c45dde84ebe8a025b2747bb8a41acd6d4f67eb75eec6b9c8ef` / `04b814d02c2715ba446f668628fcb2d7c6a4cae3bed77199da3cf0db0261e883` / `2a7d1653213ba74574cb2bb7fc1ee7394e22227ef0c5ab692f2a9438619420d0`。九类 automatic write 均为 `0`。
- 后续无评测数据 probe 证明当前 API key 有效且 `deepseek-v4-pro` 可用；服务端明确以 `key_model_access_denied` 拒绝 `deepseek-chat`。旧 qualification 产物不可覆盖或补写；任何模型替换重测必须使用新的独立 run/结论链。

### 2026-07-27 本地冻结与 H100 迁移

- 本地 `C:\Users\86137\Desktop\KE-memory` 已完成瘦身并冻结为审计副本。后续实现、模型调用和实验只能在 H100 `/public/home/wwb/KE-mem/KE-memory-next-prep-20260727` 执行；不得继续在本地工作区运行。
- 主清理报告与测试后清理报告均为 `status=cleaned`、`remaining_target_count=0`。主批次删除 36 个目标、97,055 个文件、3,094,694,597 bytes；测试后再删除 6 个文件、16,414 bytes。清理报告和受保护哈希表位于 `artifacts/project-structure/`。
- H100 迁移已验证 6,586 个文件、7,426 个文件系统/归档条目、1,412,143,854 个文件字节；迁移包 SHA-256 为 `7249031b62a04afb75407e2a95e3660df6b46b5dbde1aa0986bd115b955e1b85`，六项受保护产物哈希一致，远端临时迁移包已删除。
- `.venv-dense` 是 Windows 环境快照，不得在 Linux/H100 复用。H100 已创建独立 `.venv-h100`，且不得修改或删除迁移保留的 Windows 快照。
- 核心骨架锁定：基础本体、动态本体扩展接口、L1 基础抽取、L2 摘要/跨轮抽象、问题处理、符号优先召回和 guarded embedding fallback 非必要不得修改。schema.org 只作概念建模参考，Extended-AMR 是主候选 carrier，不是事实权威或已选定持久层。
- opaque-ID v2、dev repair 与 fresh-v3 已完成；v2 raw failure、policy-v2 dev failure、policy-v3 dev pass 和 fresh-v3 final result 均是不可变审计证据，不得改写或用另一道门的结果覆盖。
- actor-binding v4.1、fresh-v4 和 candidate-generation integration assessment v3 均已完成；fresh-v3 hidden false abstention 未直接进入调参，修复只发生在独立 dev/诊断数据。当前第一 TODO 转为自动 L1/L2 抽取、问题编译、证据闭包、跨 session 聚合和真实 benchmark 扩展；candidate queue 仍不得自动写入 identity、membership、closure、snapshot、aggregate 或 L2。
- `LONGMEMEVAL-6d550036` 必须继续保留 `structured_l2_identity_unresolved`，除非未来独立证据和程序化 authority gate 真正解决身份。完整远程接手说明见 `docs/handoffs/2026-07-27-h100-ke-memory-next-handoff.md`。
- 2026-07-28 actor-binding v4.1/fresh-v4 已完成。实际可用 proposer 为 `claude-sonnet-4-6`；未执行的 Codex-named freeze 只保留审计，不得伪报模型 metadata。passing dev run 与 fresh-v4 final run 的 raw/gated accuracy、abstention F1、evidence exactness 均为 `1.0`，critical false merge/membership 与 gate intervention 均为 `0`；final proposals/score/report SHA-256 为 `aba38ed3f30fa5faf1208ff6f3ae9847822854a4d5b166679c755e6c33a386d2`、`6a47808b49302d1c14e34dad4d67c062484909892c7de8137eed795e05259b75`、`5851955aebc8dc0726cb7ae617c2b3fdcb3067b5509e947e92cd2a59ad328007`。
- fresh-v4 是 6-case hidden-only 小型 gate，不授权自动 merge、membership 或 L2 写入。下一步只评估 non-authoritative candidate generation 接入，然后继续自动 L1/L2 抽取、问题编译、证据闭包、跨 session 聚合和真实 benchmark 扩展；最终存储 profile 仍不得预选。
- 2026-07-28 candidate-generation integration assessment v3 已完成。实现只读取 frozen public/proposals/score，输出 immutable non-authoritative review queue 与 assessment；不读取 authority/gold，不调用 proposer，不修改 `identity_resolution.py`。v3 拒绝 duplicate public case/mention，严格复核 score validation/regressions/claim boundary/readiness/metrics，按 subject ref 计算 entity binding，并要求 L1 evidence span 与唯一 source revision 形成 chain；membership actor 不得冒充 member entity。正式结果为 4 个 `eligible_for_manual_review`、2 个 `gate_abstained`，existing entity/L1/source/evidence-chain binding rate 均为 `0.0`，automatic authoritative writes 为 `0`，guard state fingerprint 前后相同，`candidate_generation_integration_ready=false`。
- 复审前 v1/v2 freeze 保留为审计证据；最终 v3 queue/assessment/report SHA-256 为 `518ead9de8627a9a4384df8cdd9b8728a21fcf797f6b0f3d208dfcb28ac41c0f`、`49ef708c77561680703e578de140a9d664a0a774dd48dfda0af038bbdc09c7cf`、`a4ab8ac584bfde78469244c42e8adc63cd79eecbe14a6eb27f636b9fd74f1b3b`；三份文件均为 `0444` 且原位重放一致。最终新鲜验证为 focused assessment `16 passed`、全部 identity `82 passed`、完整 natural benchmark `219 passed`、`compileall` 成功，七类 formal validator 均为 `valid`，fresh-v4 受保护 proposal/score/report 哈希不变。下一 TODO 是自动 L1/L2 抽取、问题编译、证据闭包、跨 session 聚合和真实 benchmark 扩展，仍不得自动写入 identity/membership/closure/snapshot/aggregate/L2。
- 2026-07-28 automatic L1/L2 extraction bridge assessment v3 已完成。实现只重放现有 43 turn-pass、10 dialogue reconciliation、416 projected/390 active knowledge，不重跑模型，不修改抽取核心或权威写入面。Raw structure 单独报告：402 single-turn、14 cross-turn、436 evidence references，evidence binding/source-status admissibility 均为 `1.0`，required surface completeness `1.0`，object present `397/416`，condition/scope/non-explicit derivation records 为 `51/79/68`；这些不是 gold semantic accuracy。Bridge safety 单独报告：L1/L2 candidates `402/14`，authoritative-ready `0/0`，416 条全部 blocked，automatic L1/L2/unit-revision/closure/identity/membership writes 全为 `0`；memory kind/predicate sense/operator/typed roles/local IDs 各缺 `416`，typed time `64`，unsupported modality `52`，condition/scope/derivation typed gaps 为 `51/79/68`，14 个 L2 全部缺 support/claim/abstraction/closure/source coverage。guard fingerprint `e184b6caf2998acf1c8700bc84d24bbafd49ab9c8f15738d1af8cc484ee5ebcc` 未变，`automatic_extraction_integration_ready=false`。
- bridge-v1/v2 保留为不可变审计产物，不再作为 typed-extractor 完整合同。复审修复包括：精确 envelope record/candidate coverage、optional object 指标、condition/scope、derivation/inference provenance、evidence speaker binding、同 candidate lifecycle references，以及从冻结 dialogue validated files 重建 operation ID -> candidate ownership 并拒绝 unknown/cross-candidate `confirmed_by`/`added_by`；operation provenance 现在逐 envelope 保留。正式 bridge-v3 ledger/assessment/report SHA-256 为 `2ed9e6fdeaca81964fff542287adfc2980145b978b7ef9ed6dfc5f914ebca7c0`、`d5d00b2edebdaf7b2409f09a647c0bce41d1ce29e5c2e1d3c67e646fb5f5e92e`、`b7e29b605ac46b0ff85c1be963f9d3fca7693f3c445a64188f67b8eecc3d9bf9`，均为 `0444` 且隔离重放字节一致；bridge-v1/v2 哈希未漂移。新鲜验证为 focused bridge `51 passed`、knowledge pipeline `197 passed`、natural benchmark `270 passed`、`compileall` 成功。下一步按 `docs/plans/2026-07-28-typed-extractor-v2-l1-dev-qualification-plan.md` 只在 dev/诊断数据上执行 L1 qualification，L1/L2 dev gate 通过前不创建 fresh hidden，也不得发布 authoritative L1/L2/identity/membership/closure/revision 写入。
- 2026-07-28 typed extractor v2 L1 dev qualification 已通过。初始 prompt 因未暴露精确嵌套 schema 导致 staged output 在 freeze 前被严格拒绝；后续 dev-v1/dev-v2 raw failures 与 gate safety pass 均只读保留。最终 formal root 为 `artifacts/automatic-extraction-assessment/typed-extractor-v2-dev-v3/`，passing run `run-20260728T060140Z-deepseek-v4-pro-typed-l1-dev-v6` 的真实 proposer 为 `openai-compatible-api` / `deepseek-v4-pro@2026-07-28-prompt-v4-policy-v2`，通过全新无历史请求只读取 frozen public/prompt；proposals/provenance 在 authority/gold scoring 前冻结。raw proposer quality 与 deterministic gate safety 均为 true：coverage/schema/decision/abstention F1/evidence/kind/predicate/modality/time/lifecycle/derivation/operation accuracy 均为 `1.0`，role/local-entity 与 condition/scope 为 `0.8888888888888888`，critical false emission、gate intervention、deterministic critical false materialization 均为 `0`；唯一残留是 `case-4ffef5523d302472` 的 condition participant/local-entity error。guard fingerprint `e184b6caf2998acf1c8700bc84d24bbafd49ab9c8f15738d1af8cc484ee5ebcc` 前后不变，所有 automatic writes 为 `0`。final proposals/score/report SHA-256 为 `7c765a4185c4b28ecdbb0bf23702e0bbf1931c7c11a4d9b5c420bf80b3952899`、`db0fcc05e9ab3a4c64eac45062eb1a35447e7740b2566baa5fbd8575a3bcbefe`、`c1f088f8e13b962cd4a1ea2719ac4aee8f38a3ef4ef2c1d7fb7c6d3bed6e1ace`，正式文件均为 `0444`，score/report/error-analysis 隔离重放一致。新鲜验证为 focused `22 passed`、knowledge `197 passed`、natural `292 passed`、compileall 成功，八类 formal validators valid，bridge-v3 重放一致，既有保护哈希不变。该结果当时只解锁 L2 dev qualification；L2 已由下述 v9/v12 完成。
- 2026-07-28 typed extractor v2 L2 dev qualification 已通过。最终 root 为 `artifacts/automatic-extraction-assessment/typed-extractor-v2-l2-dev-v9/`，passing run 为 `run-20260728T084011Z-deepseek-chat-official-typed-l2-dev-v12`。dispatch 请求别名为 `deepseek-chat`，raw response 返回模型为 `deepseek-v4-flash`；provenance v2 分开绑定二者，并绑定 dispatch/raw/proposals 与 freeze sequence。隔离是 declarative fresh-agent file-access contract，不是 OS/container 强制证明。v8/v11 的单个 `structured_claim_error` 保持为 raw-fail/gate-safe 证据；v7/v10 因旧 scorer threshold/provenance 审计缺口仅作历史。
- v12 raw decision/abstention/evidence/support/kind/claim/abstraction/closure/source coverage/summary accuracy 均为 `1.0`，raw critical false emission、gate intervention、deterministic critical false materialization 均为 `0`；raw proposer quality 与 deterministic gate safety 均为 true。guard fingerprint `e184b6caf2998acf1c8700bc84d24bbafd49ab9c8f15738d1af8cc484ee5ebcc` 前后不变，automatic L1/L2/revision/closure/identity/membership writes 全为 `0`。proposals/score/report SHA-256 为 `655c696154d7e623ae417d3c5978a23ac7f7fb611e1b9f27ef21f7e25344e2c9`、`e27be9f426a78bf67fb03938ce97aeccc697e071bf866494d9a1d319fed4db57`、`c7cdd49adb166112c5a6ba6a64ef3c398f01c979bd4591c3135d911eafe8d600`，重放一致且 v7-v9 正式文件均为 `0444`。
- 最终验证为 focused L2 `31 passed`、knowledge pipeline `197 passed`、natural benchmark `352 passed`、compileall 成功；L1/L2、natural identity v1/v2/v3/v4、slice/ledger validators valid，bridge-v3 重放一致，candidate v3 queue 哈希未漂移且四项人工裁决未物化。下一步只预注册 fresh hidden typed-extraction evaluation；不得直接接入 pipeline 或授权 L1/L2/identity/membership/closure/revision/snapshot/aggregate 写入。`LONGMEMEVAL-6d550036` 仍为 `structured_l2_identity_unresolved`。

- 2026-07-28 fresh hidden 预注册前完成 L1 provenance v2 对称审计。新增 L1 OpenAI-compatible API runner；dispatch/provenance 分别绑定 requested alias、response model、raw response、proposals 和冻结顺序，scorer 重验完整链。官方 DeepSeek v7/v8 的 raw failure 与 gate safety pass 均保持不可变；prompt V6 只根据 dev 的 unresolved-time、causal modality 和 qualifier closure 错误修复，v9 `run-20260728T091848Z-deepseek-chat-official-typed-l1-dev-v9` 双门通过。requested alias 是 `deepseek-chat`，raw response model 是 `deepseek-v4-flash`；隔离仍为 declarative contract。v9 raw decision/abstention/evidence/kind/predicate/modality/time/derivation/operation 为 `1.0`，role/condition/lifecycle 为 `0.8888888888888888`；一个 lifecycle 错误被 gate 降为 abstain，gated accuracy `0.9166666666666666`，不得掩盖 raw error。proposals/provenance/score/report SHA-256 为 `dd28482420680604a8ac85c10bf6506079420f882300393af1cb0fdb2bdfeac2`、`400217f3cb0343ceb2d61c03f905bc9f32147cf937e648f9497525adbecc52cc`、`e2bd3a3c613b927d4f065b8c2fbfd4d33fe43b8c05f6fa9c25b5173195443612`、`8837be4319a390024faea9eb04b12d990a44a3d10df51a371977bb9320ab72f1`。
- L2 继续绑定其历史 v6 L1 qualification，而不自动切换到新 v9。`artifacts/automatic-extraction-assessment/typed-extractor-v2-dev-v3/l2-source-qualification-receipt.json` 以 SHA-256 `27e5f46e1bf8614bc5573b388a573309117233f2ed1608c0fc6a72131fd70544` 显式选择原五项 artifact hash，解决多个 passing L1 run 导致 L2 replay 失败的问题，既有 L2 manifest 未变化。新鲜验证：typed focused `58 passed`、knowledge `197 passed`、natural `364 passed`、compileall 成功，L1/L2、identity v1-v4、slice/ledger validators valid；candidate v3 queue 哈希仍为 `518ead9d...41c0f`，四项人工裁决未物化，密钥未落盘，automatic writes 全为 `0`。下一步仍只能先冻结 fresh hidden typed-extraction preregistration，再创作 hidden case。
- 2026-07-28 typed-extractor fresh-hidden v1 预注册已在 hidden root 不存在时冻结。设计/计划为 `docs/designs/2026-07-28-typed-extractor-fresh-hidden-evaluation-design.md` 与 `docs/plans/2026-07-28-typed-extractor-fresh-hidden-evaluation-plan.md`；contract/CLI 为 `tools/natural_memory_benchmark/typed_extractor_fresh_prereg.py`。正式 `preregistration.json` 位于 `artifacts/automatic-extraction-assessment/typed-extractor-v2-fresh-hidden-prereg-v1/`，SHA-256 `9ec35f71c86c0e2c0257438d01445d9f0a490eee57a0d582ccb01024ffc0921c`、mode `0444`，validator 为 valid（L1 24、L2 8、hidden absent）。L1 selection 使用公开结构 strata + namespace hash，L2 使用全部 8 条 unused cross-turn records；prompt、阈值、input/code hash、requested model 与零写入边界已固定。后续只能先 deterministic selection/author gold，再各运行一次 isolated proposer；hidden failure 禁止原地调参。
- 2026-07-28 typed-extractor fresh-hidden v1 已完成并关闭。L1 24-case 与 L2 8-case 均使用无历史、public-only、requested `deepseek-chat` 的 official request，response model 均为 `deepseek-v4-flash`，proposal/provenance 在 authority/gold scoring 前冻结。两层 raw proposer quality 均 fail、deterministic gate safety 均 pass，必须分开解释：L1 raw decision/abstention F1/evidence 为 `0.7916666666666666/0.5714285714285715/0.8947368421052632`，critical false emission `3`，gate intervention `4`、critical materialization `0`；L2 raw decision/abstention F1 为 `0.625/0.0`，critical false emission `3`，abstraction/structured claim 为 `0.4/0.6`，gate intervention `6`、critical materialization `0`。总体结论为 fail，不授权 integration 或权威写入。
- 正式总报告为 `artifacts/automatic-extraction-assessment/typed-extractor-v2-fresh-hidden-v1/overall-report.md`。chronology receipt SHA-256 `2f2c38e475a8b25a3a553333ea4733f6428f505a5adb8e6c95bdfd0964fbc699`，bridge 与两层 score/report/error-analysis 重放字节一致。fresh-focused `14 passed`、typed `72 passed`、knowledge `197 passed`；identity v1-v4、benchmark slice/ledger、typed dev、fresh L1/L2/chronology validators valid。candidate v3 queue SHA 仍为 `518ead9de8627a9a4384df8cdd9b8728a21fcf797f6b0f3d208dfcb28ac41c0f`，四项用户人工裁决仍未物化，automatic writes 为 `0`，密钥未落盘，`LONGMEMEVAL-6d550036` 仍为 `structured_l2_identity_unresolved`。
- 下一步必须新建 dev/diagnostic 数据，按 L1 false emission、false abstention、evidence、condition/scope、time、role、lifecycle，以及 L2 abstention、abstraction、structured claim、kind 分类修复。dev 双门通过后另行预注册 fresh-hidden v2；不得重跑或修改 v1。并行 query compiler/executor 工作可继续保持 candidate-only，但不得把失败的 extractor 输出提升为权威输入或授权任何 L1/L2/identity/membership/closure/revision/snapshot/aggregate 写入。
- 此前缺失的 query compiler assessment 模块已由并行工作补齐；当前新的并发 `test_query_execution_snapshot_adapter.py` 已出现但实现模块尚未落盘。无条件 natural-memory suite 因该独立 collection blocker 失败；本阶段不得补写、删除或回滚 query 文件。排除该孤立文件后的新鲜结果为 `464 passed`，typed extractor 为 `105 passed`，knowledge pipeline 为 `197 passed`，`compileall` 成功。

## Typed extractor diagnostic public-contract v2 baseline

2026-07-28 prompt-complete diagnostic public contract v2 与 unchanged-prompt baseline 已完成。旧 v1 public catalog 在模型请求前被 preflight 拒绝，未发送请求且保持不可变。正式 roots 为 `artifacts/automatic-extraction-assessment/typed-extractor-v2-l1-dev-repair-v2/` 和 `typed-extractor-v2-l2-dev-repair-v2/`；L1 V6/L2 V8 prompt SHA-256 分别为 `a4d03b0e3717be47a3cd32358f6ca881d4be55bac804bc343999b6b22b835586`、`55fddf350d4a2c821000436aa4ce4c614da589ffe053ea5ab4c1bb7e774e60c7`。两层均以无历史、public-only 请求 `deepseek-chat`，raw response 均为 `deepseek-v4-flash`，proposal/provenance 在 authority/gold scoring 前冻结。

L1 run `run-20260728T120704Z-deepseek-chat-official-typed-l1-dev-repair-v2` 严格 raw quality fail、gate safety pass；除 `role_or_local_entity_accuracy=0.9166666666666666` 外 strict metric 全为 `1.0`，唯一错误是未将 `a review with Dana` 的显式 participant `Dana` 分解为独立 local entity，gate intervention `0`。L2 run `run-20260728T120705Z-deepseek-chat-official-typed-l2-dev-repair-v2` 严格 raw quality/gate safety 均 fail；`abstraction_accuracy=0.875`、`structured_claim_accuracy=0.875`、gate intervention `1`，错误为 persistent state 错选 `coreference_resolution` 和 archive coreference claim 复用 L1 `document.archive_request` sense。两层 raw critical false emission、false abstention、evidence error、critical materialization 和 automatic write 均为 `0`，guard fingerprint 仍为 `e184b6caf2998acf1c8700bc84d24bbafd49ab9c8f15738d1af8cc484ee5ebcc`。

下一步只执行 `docs/plans/2026-07-28-typed-extractor-v2-diagnostic-prompt-repair-v1-plan.md`：L1 修复显式 participant 分解；L2 修复 abstraction dominance，并新增 versioned `operator_sense_bindings` public contract。双层所有 strict metric 为 `1.0` 且 gate intervention 为 `0` 前，不得预注册 fresh-hidden v2；仍不授权 pipeline integration、自动 L1/L2/revision/closure/identity/membership 写入。candidate v3 queue SHA 保持 `518ead9de8627a9a4384df8cdd9b8728a21fcf797f6b0f3d208dfcb28ac41c0f`，人工裁决未物化，`LONGMEMEVAL-6d550036` 继续 unresolved。

2026-07-28 diagnostic prompt repair 已完成。L2 正式 v3 contract/run 为 `typed-extractor-v2-l2-dev-repair-v3` / `run-20260728T123925Z-deepseek-chat-official-typed-l2-dev-repair-v9`，所有 strict metric 为 `1.0`，gate intervention 和 critical counts 为 `0`。L1 V7/V8/V9 的 raw failures 均保持只读：V7 有 participant-head 与 requested modality 两项错误，V8 有 4 个 role/local-entity 错误，V9 有 1 个 question-only decision error 与 1 个 participant-head 错误；deterministic gate safety 没有被用来覆盖这些错误。

最终 L1 V10 run `run-20260728T130544Z-deepseek-chat-official-typed-l1-dev-repair-v10` 使用无历史、public-only official `deepseek-chat` 请求，raw response model 为 `deepseek-v4-flash`，proposals/provenance 在 authority/gold scoring 前冻结。所有 L1 strict exact metrics 为 `1.0`，raw critical false emission、gate intervention、deterministic critical materialization 均为 `0`；prompt/proposals/provenance/score/qualification SHA-256 为 `b868bb2baaf1dfb3c27f99e2fe29888e2af0c57e56be3d2ecf70bfb6d2bcdfcf`、`7cca8c171d784fbee1ea4849c52403fa6446f3d78fe746cec4134a3effb95c39`、`8a2ef39bf2da9a059a24537505b05f5391a1806f5012642fa173864746dbf483`、`993200f235b075b4f7e5e72bf37d19cc8427d360ce75ab5375f91f3e7923ba43`、`377d91553db76fa1e3d48602e739aed255b107fca3856a35908234c769cb93a0`。双层 strict diagnostic gate 现已通过，但只授权 fresh-hidden v2 预注册；不得直接创建 hidden、接入 pipeline 或执行任何 L1/L2/revision/closure/identity/membership 写入。guard fingerprint 仍为 `e184b6caf2998acf1c8700bc84d24bbafd49ab9c8f15738d1af8cc484ee5ebcc`，candidate v3 queue 未漂移，人工裁决未物化，`LONGMEMEVAL-6d550036` 继续 unresolved。

最终新鲜验证为 typed extractor `114 passed`、knowledge pipeline `197 passed`、完整 natural memory benchmark `485 passed`、`compileall` 成功；L1/L2 scorer/qualification 重放哈希一致，L1 v2/L2 v3 validators valid，正式 run 文件均不可写，key-pattern scan 为 `0`。额外 workspace hygiene 为 `19 passed, 1 failed`，唯一失败是既有 Windows 反斜杠 duplicate-path fixture 在 Linux 上先报 missing target；未执行 cleanup 删除，也未扩大本阶段范围修改该模块。fresh-hidden v2 root 仍不存在。

### QuerySlotPlan V2 当前状态（2026-07-28）

问题编译主线已完成独立 V2 compiler、deterministic gate、V1 lowering、V2 executor、formal assessment hardening、standalone CLI 和 verified Git execution snapshot adapter。权威执行入口必须遵循：`typed proposal -> deterministic materialization -> MemoryUnitRevision -> closed TurnBundle/admitted L2 closure -> Git checkpoint -> verified execution snapshot -> executor`；typed extractor proposal、gate score 或 display-only L2 不得直接变成 execution fact。

snapshot adapter 已绑定 authoritative Git commit、bundle logical ID、current L1 ownership、TurnBundle closure、L2 support evidence union、transaction time 和 identity scope。scope 外实体一律 unresolved；L1 fact provenance 的 revision ID 必须与 fact ID 一致。executor 对 missing/invalid latest time、unverified provenance、explicit absence 和 unsupported time operator 保守 abstain。当前 active L2 只支持单 structured claim；上游未具备 per-claim closure 前不得放宽。

新鲜验证为 Query focused `55 passed`、相邻权威契约 `116 passed`、完整 natural-memory `485 passed`，`compileall`、`tabnanny` 与行长扫描通过。formal query compiler assessment 仍默认 `formal_readiness=false`；raw natural-query proposer 尚未评测。下一步按 TODO 绑定 ontology/identity registry revision、补 per-claim closure/absence/time execution contract、冻结自然 query dev/fresh-hidden，并接入 evidence/answer eval。不得消费 typed-extractor fresh-v1 失败候选作为权威输入，不得借 Query 波次授权任何自动写入。

### 2026-07-28 Typed Extractor Fresh-Hidden V2 Preregistration

- fresh-hidden v2 预注册已在 authoring code/test、implementation receipt 和 evaluation root 全部不存在时冻结。设计/计划为 `docs/designs/2026-07-28-typed-extractor-fresh-hidden-v2-preregistration-design.md` 与 `docs/plans/2026-07-28-typed-extractor-fresh-hidden-v2-preregistration-plan.md`，独立 contract/CLI 为 `tools/natural_memory_benchmark/typed_extractor_fresh_v2_prereg.py`。首个 prereg-v2（SHA-256 `0ac045b0cbed26a2fb624bc1f70d8275ae94edb41a57e868bae78c6effadc243`）因 review 发现 coercive Pydantic types 和虚假 mtime chronology 声明而 superseded，旧文件保持 `0444` 不改写，且在 hardened validator 下明确失败。
- 当前正式 `preregistration.json` 位于 `artifacts/automatic-extraction-assessment/typed-extractor-v2-fresh-hidden-prereg-v3/`，schema `typed-extractor-fresh-v2-preregistration-v2`，freeze time `2026-07-28T14:08:22Z`，SHA-256 `1455bb7d5bb35b61809c78180ebf766573c1561e39bbeddda4a80f939a893760`，size `11016` bytes，mode `0444`；validator 为 valid（L1 24、L2 12、future absent、hidden not created）。hardened contract 启用 strict types 和真实 UTC 解析，chronology 只声明实际具备的 `filesystem-presence-plus-sha256`，freeze time 标记为 untrusted caller-supplied label。合同绑定最终 L1 V10/L2 v9 passing chains、final dev/diagnostic/fresh-v1 exclusions、47 个 input hash、9 个 code hash、L1/L2 14/12 个 exact-1.0 quality metrics 和三项 zero safety count。
- v2 authoring protocol 使用新的 deterministic authored-hidden namespace，不复用已耗尽的 bridge L2 pool。L1 六个 family 各 4 条，L2 六个 family 各 2 条，全部使用且禁止 semantic filtering、case replacement 和 post-generation resampling。实现与测试已完成；L2 primary claim validator 逐条强制 public predicate、subject、object/theme 和 support-set literal binding，travel case 现为一个 aggregate travel claim，两个 rail/lodging L1 support 继续分离。
- 提前冻结的 v1 `authoring-implementation-receipt.json` 保持 mode `0444`、SHA-256 `4bb2575d985126dfbd91d01a3111d3f4acb2ebe57c3bfd62b1d60ee847d7314d`，但它绑定修复前 module，已被 append-only v2 supersede，不能作为 active authority。当前 active `authoring-implementation-receipt-v2.json` 的 freeze time 为 `2026-07-29T00:30:16Z`，schema `typed-extractor-fresh-v2-authoring-receipt-v2`，size `7364` bytes，mode `0444`，SHA-256 `4ce77c20c2941a66c3e74c1bd561e9d5ceee360a3723b75eed694fc47267c94b`；active resolver 已验证选择 v2，并绑定 current module/test、dependency、blueprint manifest 和 47 个 prior input hash。第三轮独立只读复审无 Critical/Important；一个 Minor 建议补 active-selector corrupted-v2 的直接回归覆盖，当前 selector 已 fail closed。
- 新鲜验证为 focused authoring `49 passed`、全部 typed extractor `177 passed`、knowledge pipeline `197 passed`、完整 natural memory benchmark `580 passed`、`compileall` 成功。下一步只允许 one-time formal hidden materialization，且 materializer 必须先调用 `validate_fresh_v2_active_authoring_receipt`；本阶段仍不得调用模型。formal hidden 冻结后，proposer 仍必须无历史、public-only、每层一次 semantic run，proposal/provenance 先冻结，scoring 后读 authority/gold，raw quality 与 gate safety 分开报告。
- materialization 前 formal evaluation root 不存在，model request 与所有 automatic L1/L2/revision/source-revision/closure/identity/membership/snapshot/aggregate write count 均为 `0`，不授权 integration。guard fingerprint 为 `e184b6caf2998acf1c8700bc84d24bbafd49ab9c8f15738d1af8cc484ee5ebcc`，candidate v3 queue 为 `518ead9de8627a9a4384df8cdd9b8728a21fcf797f6b0f3d208dfcb28ac41c0f`，人工裁决未物化，LongMemEval identity 为 unresolved；Ruff 在 `.venv-h100` 中不可用，未为此修改环境。

### 2026-07-29 Typed Extractor Fresh-Hidden V2 Materialization

- one-time formal root 已原子发布到 `artifacts/automatic-extraction-assessment/typed-extractor-v2-fresh-hidden-v2/`：L1 24、L2 12、十个 source/public/authority/gold/manifest 文件和一个 chronology receipt。11 个 JSON 均为 `0444`，root/layer 目录为 `0775`，无 `model-runs` 或 proposal/scoring 路径。
- 首轮独立 review 的两个 Important 已按 TDD 修复：materializer 现在固定 active v2 receipt SHA `4ce77c20c2941a66c3e74c1bd561e9d5ceee360a3723b75eed694fc47267c94b`，并使用 Linux `renameat2(RENAME_NOREPLACE)` 拒绝并发创建的空目标。re-review 无 Critical/Important。materializer module/test SHA 为 `57a8e6df5c6fc4739b50cf842f53063610f2c5bfc0ada21b84de0d87ab65a606` / `84f88ce70ca818a27b520b21d5a43a7f46a3bba8d2393bf0ee5417afc24191ac`。
- chronology 的 caller-supplied UTC label 为 `2026-07-29T02:10:29Z`，SHA-256 为 `278d9ba8f4d466984b11644de920b815de11cbdb56b49dff0dd797543b12b05e`。public validator 为 `valid`，L1/L2 deterministic payload replay 为 `10/10` byte-identical；prereg、active/v1 receipt、authoring module/test、candidate queue 和 guard fingerprint 未漂移。
- 冻结前为 focused `64 passed`、typed `192 passed`、knowledge `197 passed`、natural `603 passed`；冻结后为 focused `63 passed, 1 deselected`、typed `191 passed, 1 deselected`、knowledge `197 passed`、natural `602 passed, 1 deselected`。deselected 节点是 receipt-bound 的 pre-materialization-only root-absence 测试；不得修改它或 authoring module 来掩盖阶段迁移。
- model request 和九类 automatic write count 仍为 `0`，四项人工 identity 裁决未物化，candidate v3 queue SHA 仍为 `518ead9de8627a9a4384df8cdd9b8728a21fcf797f6b0f3d208dfcb28ac41c0f`，guard fingerprint 仍为 `e184b6caf2998acf1c8700bc84d24bbafd49ab9c8f15738d1af8cc484ee5ebcc`，`LONGMEMEVAL-6d550036` 继续保持 `structured_l2_identity_unresolved`。
- 无历史、public-only proposer 与独立 scoring 已按序完成。L1 run 为 `run-20260729T024500Z-deepseek-chat-official-typed-l1-fresh-hidden-v2`，L2 run 为 `run-20260729T024501Z-deepseek-chat-official-typed-l2-fresh-hidden-v2`；两层均只请求一次 official `deepseek-chat`、无 semantic retry，raw response model 均为 `deepseek-v4-flash`。proposal/provenance 在 scoring 读取 authority/gold 前冻结，proposal SHA-256 分别为 `5e0ac9cf0ed5dd50cf2bffa78add1e988d599856ba94820639e5f763527c4a05` / `59e1f052c2157782c1f8266d91a9ae319a2ba87cb7b065d58bf8a6adbd8a9da6`。
- fresh-v2 最终状态为 `not_qualified`。L1 raw quality fail：decision `0.9583333333333334`、abstention F1 `0.8571428571428571`、evidence `1.0`、role/local entity `0.5555555555555556`、time `0.8888888888888888`、condition/scope `0.9444444444444444`、critical false emission `1`；L2 raw quality fail：decision/abstention/evidence/support/kind/source/summary 均为 `1.0`，structured claim `0.0`、abstraction `0.7777777777777778`、closure `0.5555555555555556`、critical false emission `0`。两层 deterministic critical materialization 均为 `0`，但各有 `4` 次 gate intervention，违反 prereg 的 zero-intervention 门，因此最终 deterministic gate safety 也均为 fail；不得用 legacy scorer 的较宽 readiness 字段覆盖最终 qualification。
- 旧 scorer 只接受三项 manifest output hash，L2 还硬编码旧 dev threshold shape；正式 manifest 未修改，只用临时只读 compatibility view 评分。L1 首次绝对 guard 路径得到已记录的 `9f81...` fingerprint，随后不重跑模型、按 canonical 相对路径生成最终 `score-v2.json`；`scoring-supersession-receipt.json` 保留完整 supersession 链。最终 L1/L2 score SHA-256 为 `f09d754e6848ade7fbbc0fc723899c63a7e24947c3c2cb6a13401ae1bbd0dbc8` / `6d656d9883803f1b8ca5a200babfa285547f98e99e048fc3908517dc31e8c092`，qualification SHA-256 为 `5e189d02b9e08df8b8713151297cf02676c66756145439adf98a7b4cac41dfd9` / `5c63013aa9320da636e8fbdb4e44e9d7be22358ac5bb5f233ec585971a73453a`。
- 最终只读审计 `117/117` 通过：chronology 十个 payload、raw/proposal/provenance、canonical score replay、prereg qualification、所有 `0444` mode、guard/candidate queue 和 protected scorer hash 均闭合；credential pattern 为 `0`。两个字节相同的 `.tmp` proposal 副本及空目录已删除，正式冻结副本未变。新鲜回归为 typed `191 passed, 1 deselected`、knowledge `197 passed`、natural `602 passed, 1 deselected`，`compileall`/`tabnanny` 通过；唯一 deselection 是 `test_bundle_is_deterministic_and_does_not_mutate_formal_artifacts`，它绑定 pre-materialization formal-root absence，不得修改。
- 下一阶段只能在新的 dev/diagnostic 数据上修复：L1 `false_emission`、role/local entity、time、condition/scope；L2 structured claim、abstraction、closure。只有 raw strict metrics 全过且 gate intervention 降为 `0` 后，才允许另行预注册新的 fresh hidden。当前 automatic authoritative write 为 `0`、pipeline integration 未授权、人工 identity 裁决未物化，candidate v3 queue SHA 仍为 `518ead9de8627a9a4384df8cdd9b8728a21fcf797f6b0f3d208dfcb28ac41c0f`，`LONGMEMEVAL-6d550036` 继续保持 `structured_l2_identity_unresolved`；不得进入 closure、aggregate 或 benchmark 扩展。

### 2026-07-29 Typed Extractor Taxonomy Dev V1

- fresh-v2 后的唯一允许修复波次已在全新 `diagnostic_authored` 数据上完成；不得从该设计、source、prompt 或 error analysis 反推、读取或复用 fresh-v2 hidden case 内容。L1/L2 formal roots 分别有 20/12 case，source SHA-256 为 `d830246820c1df017baaace328111105f04858ce30f86d624b4a890be49d37b5` / `693cea99322c9589864749213ad1705ba6eabf3323bd3a19d6e5ec85d9a98418`，manifest SHA-256 为 `10292706e91d1eca7a0285fc83fd57cf0912ad51faff519fe54000864683029d` / `bed50074ee41a3119a6e5803a0a24d403aa7557f75ceb8491c54ba132b31cdf8`。两个 validator 均为 valid，prior identifier/evidence overlap 均为 0，formal/model-run 文件均为 `0444`。
- unchanged-prompt L1 baseline `run-20260729T041500Z-deepseek-chat-official-typed-l1-taxonomy-baseline-v1` 是严格 `not_qualified`：raw 唯一失败为 `role_or_local_entity_accuracy=0.9375`，尽管 deterministic gate safety、zero intervention 和 critical counts 均通过。共享 qualifier 的 `status=qualified` 只表示已执行资格检查，必须以 `dev_repair_ready=false` 和 raw/gate 字段为准，不能掩盖 raw proposer 错误。
- unchanged-prompt L2 `run-20260729T041501Z-deepseek-chat-official-typed-l2-taxonomy-baseline-v1` 严格双门通过，无需无意义的 L2 prompt revision。L1 repair-v1 `run-20260729T042500Z-deepseek-chat-official-typed-l1-taxonomy-repair-v1` 只根据新 diagnostic 的 role taxonomy 加强通用 participant 分解顺序；其 14 项 strict raw metrics 全为 `1.0`，raw critical false emission、gate intervention、deterministic critical materialization 均为 `0`。repair prompt/proposals/score/qualification SHA-256 为 `a5250a453863f3cfd388613d6633d8a529485a11c5226d2965c8235a9c1dc342` / `db468cc0251abe48bfb1c98dead13471b16e32556df3a61da528e3e29de95750` / `dfbb8a415e6654b89f4ac09e0ae72bc45d1687cec13e69cbd2211f6ef295bb92` / `92e627fb72ba18ef1458aa9ef810bf8bf9b5efad3a12cc0f7559231e07a3c3de`。
- 所有 proposer 都是 single-request、no-history、public-only `deepseek-chat`，raw response model 为 `deepseek-v4-flash`；dispatch -> raw response -> proposals -> provenance 在 authority/gold scoring 前完成冻结。67 项最终只读审计通过，candidate v3 queue SHA 仍为 `518ead9de8627a9a4384df8cdd9b8728a21fcf797f6b0f3d208dfcb28ac41c0f`，guard fingerprint 仍为 `e184b6caf2998acf1c8700bc84d24bbafd49ab9c8f15738d1af8cc484ee5ebcc`，credential pattern 与所有 automatic write count 均为 0。最终回归：taxonomy focused `19 passed`、typed `210 passed, 1 deselected`、knowledge `197 passed`、natural `637 passed, 1 deselected`、`compileall`/`tabnanny` pass。
- 现在只授权创建一个独立的 typed-extractor fresh-hidden-v3 preregistration；不得创建 hidden source 或请求模型，直到该 prereg 冻结并验证。pipeline integration、automatic authoritative L1/L2/revision/closure/identity/membership 写入、external-system rerun、candidate v3 人工裁决 materialization 与 `LONGMEMEVAL-6d550036` identity resolution 继续未授权；embedding 不是任何事实、身份或成员关系权威。

### 2026-07-29 Typed Extractor Fresh-Hidden V3 Preregistration

- 独立 v3 preregistration 已在 authoring/materialization module/test、receipt 和 evaluation root 全部不存在时冻结；formal root 只有 `preregistration.json`。freeze label 为 `2026-07-29T04:51:35Z`，schema/evaluation ID 为 `typed-extractor-fresh-v3-preregistration-v1` / `typed-extractor-v3-fresh-hidden-v1`，SHA-256 `183cf6fc2991361e5da57b17e06a5970f651000986d50b87e8af2e6796440204`，size `10998` bytes，mode `0444`。
- validator 为 valid：L1 24、L2 18、future absent、hidden not created、model request `0`。L1 八个 taxonomy family 各 3 条，L2 九个 taxonomy family 各 2 条；全部 blueprint 必须使用，semantic filtering、replacement 和 post-generation resampling 均禁止，invalid generation 必须中止。
- 合同绑定 taxonomy L1 repair-v1、L2 unchanged baseline、fresh-v2 exclusions，共 39 个 immutable input hash、11 个 code/test hash、L1/L2 14/12 个 exact-1.0 quality metric 与三项 zero safety count。未来 proposer 只能 no-history/public-only、每层一个 semantic run；proposal/provenance 先冻结，independent scoring 后读 authority/gold，raw proposer quality 与 deterministic gate safety 分开判定。
- 最终回归：v3 focused `16 passed`、adjacent prereg `34 passed`、typed `226 passed, 1 deselected`、knowledge `197 passed`、natural `653 passed, 1 deselected`，`compileall`/`tabnanny` 通过。唯一 deselection 仍为 receipt-bound pre-materialization root-absence test。candidate queue/guard 保持 `518ead9de8627a9a4384df8cdd9b8728a21fcf797f6b0f3d208dfcb28ac41c0f` / `e184b6caf2998acf1c8700bc84d24bbafd49ab9c8f15738d1af8cc484ee5ebcc`，credential pattern 与 automatic writes 为 0。
- deterministic v3 authoring 与 normalized-snapshot relocation receipt 已完成。原 `2026-07-29T13:42:32Z` 匿名 inode 尝试在 JuiceFS 上产生 descriptor 关闭后失效的 ghost，不构成正式 freeze；同挂载诊断 30/30 复现后，publisher 改为 named staging + `renameat2(RENAME_NOREPLACE)`，并在 rename 前通过 fd 复核 staging bytes/size/mode/inode。最终独立 reviewer 无遗留 Critical/Important/Minor。
- 唯一正式 receipt 的 caller-supplied UTC label 为 `2026-07-29T14:35:02Z`，schema `typed-extractor-fresh-v3-authoring-receipt-v2`，SHA-256 `c810f421d5a3b0726b862ec2f12c89e0d638e0747892637e2a32977587b7ef8c`，size `9370` bytes，mode `0444`，`nlink=1`；formal prereg root 精确包含 preregistration 与 receipt。Git recovery chain 固定 commit `00fa803ee44bcef5a299babb9a8e2b7ba9f994e4` 和 blob `6433fef43d7c2d68f064d900ff28172f94b4968e` / `bbe36a908ce7210c2919bb66328d4d4275851fe9` / `d92a28b2dae92bc4ddeecaca05f7520b864f24c2`，current relocation module/test SHA 为 `1a630625c84380fb910e5b8d62f3cfbd607ba8d33062ae244bb3a5f5cc0382f6` / `7c0326560e23c54c8a34b46f300d11a43d3a4ab4728246a4f1711e209659a6a5`。
- pre-freeze gate 为 relocation `23 passed`、adjacent authoring `77 passed`、phase-aware typed `310 passed, 1 deselected`、v3 prereg phase `5 passed, 11 deselected`、runtime `773 passed, 1 skipped`；static、credential、candidate queue/live guard 和 zero-write audit 通过。normalized broad gaps 明确保留：knowledge collection 缺 `nltk`；natural broad 的 36 个既有 failure 分为 12 个旧 phase 测试与 24 个缺 `duckdb`/冻结旧绝对路径，均不是本阶段通过项。
- post-freeze validator/exact audit valid；formal root 仍只有两个 JSON，evaluation/materialization/staging residue 缺失，receipt identity 与 protected state 未漂移。phase-aware typed 合计 `389 passed, 15 deselected`，runtime `773 passed, 1 skipped`；正确 prep cwd 的 tracked natural 合计 `832 passed, 24 failed, 15 deselected`，24 项仍仅是缺 `duckdb` 或冻结旧绝对路径。knowledge 仍因缺 `nltk` 有 6 个 collection error。Ruff、`compileall`、`tabnanny`、diff、Git ancestry/blob、credential `0`、candidate queue/live guard 和 zero-write audit 通过。
- receipt 只授权另行设计 one-time fresh-v3 hidden materialization；proposer、scoring、pipeline integration、authoritative writes、manual identity adjudication materialization、LongMemEval identity resolution 和 external rerun 仍未授权。embedding 非权威，`LONGMEMEVAL-6d550036` 保持 `structured_l2_identity_unresolved`。
- one-time fresh-v3 hidden materialization 已于 caller-supplied UTC label `2026-07-30T04:44:31Z` 正式完成；official root 为 `artifacts/automatic-extraction-assessment/typed-extractor-v3-fresh-hidden-v1/`，public validator 为 `valid`，L1/L2 `24/18`，freeze 时 model request/run 均为 `0`。11 个 JSON 均为 `0444`，root/layer 为 `0775`，十个 payload replay `10/10` byte-identical，无 staging、model、proposal、provenance、scoring 或 result 路径。
- chronology SHA-256 为 `fe3cfbd739de477d99089c4ed6f85322236e00deb9b405596f038366bee16cca`；materializer module/test SHA-256 为 `1e134fcc005da9e10f9f5be95cf46f3451b39f16556b1a088c9f034d02f6bc7e` / `76f5e2377b153b68eef1d5a84be7a865af8a24cbf30b4e5adb7b49915646ab80`。review 为 Critical/Important/Minor `0/0/0`；pre-freeze 为 focused `45 passed`、phase-aware prereg/authoring/snapshot `54 passed, 62 deselected`、typed `255 passed, 1 deselected`、runtime `773 passed, 1 skipped`、natural `775 passed, 24 allowlisted failures, 1 deselected`，knowledge 精确保留 6 个缺 `nltk` collection error。post-freeze 精确 phase rerun 为 `61 passed, 100 deselected`；validator、11-file audit、static、credential `0`、protected hashes 和 zero-write checks 通过。
- materialization 不授权 proposer/scorer。下一步只能先提交独立 no-history/public-only proposer-freeze/qualification 设计与计划并取得用户明确批准；不得自行执行 proposer、读取 authority/gold 评分、接入 pipeline、执行 authoritative write、closure/aggregation、扩展 benchmark 或复跑外部系统。九类 automatic write 和 manual identity adjudication materialization 仍为 `0`/false，embedding 非权威，`LONGMEMEVAL-6d550036` 继续 unresolved。

## 2026-07-30 后续开发权威计划与边界

本节是当前唯一有效的后续推进顺序和授权边界。与本节冲突的旧“下一步”、旧 403/incomplete 状态或并行 worktree 说明均由本节覆盖，但历史文件、失败记录、冻结 hash 和 Git 提交保持不可变，不得回写或删除。

### 当前事实与结论边界

- 唯一允许写入的工作树是 `/public/home/wwb/KE_mem/ke-memory-demo/.worktrees/e2e-closure-20260730/research/next-prep`，分支 `codex/e2e-closure-20260730`；本节写入前 HEAD 为 `882d2e0d0f14`。不得写入 main、next-prep 原工作树、旧 extraction/Query worktree，不得新建 worktree。
- fresh-v3 已完成真实 `deepseek-v4-pro` official-v2 资格测试，不是“尚未运行”。L1 覆盖 `24/24`、L2 覆盖 `18/18`，总体结论为 `not_qualified`，权威提交为 `882d2e0`。
- fresh-v3 L1 主要失败为 `role_or_local_entity_accuracy=0.0`、`kind_accuracy=0.75`、`raw_abstention_f1=0.6666666666666666`、`raw_critical_false_emission_count=1`、`gate_intervention_count=1`。L2 主要失败为 `structured_claim_accuracy=0.0`、`summary_accuracy=0.0`、`closure_accuracy=0.8`、`kind_accuracy=0.6`、`raw_critical_false_emission_count=2`、`gate_intervention_count=4`。两层 deterministic critical false materialization 均为 `0`，不能据此覆盖 raw proposer 质量失败。
- official-v2 的九类 automatic authoritative write 均为 `0`，不授权 pipeline integration、自动生产写入、closure/aggregate 扩展或 benchmark 扩展。
- v8 已有 2 条 L1、1 条 L2 和有效 Git snapshot。旧 Query 产生合同不支持的 `entity_list`，系统正确 fail-closed；当前 Query 合同已收窄到执行器真实支持的 `fact`/`count`。
- v8 query-only 成功最多证明“一次真实模型写入后的受控查询闭环”成立，不会使 fresh-v3 从 `not_qualified` 变为 qualified，也不证明自动抽取已达到生产质量。

### 强制推进顺序

后续只能按以下状态机推进，不得跳步或并行绕过门禁：

```text
A. v8 query-only 受控闭环
-> B. 新 diagnostic/dev 数据上的自动抽取修复
-> C. 新版本 fresh-hidden 自动抽取资格门
-> D. 无人工注入的真实自动端到端闭环
-> STOP-1，在仓库整理前向用户汇报并等待具体整理要求
[用户批准整理范围后] -> E. 仓库整理门
[用户批准 benchmark 范围后] -> F. memory benchmark
-> STOP-2，向用户汇报并讨论下一阶段
```

授权状态：**2026-07-31 已授权完成 Phase A-D**。Phase B、C、D 已授权，但分别受前一阶段 hard gate 约束；只有前一阶段正式通过后才能切换。Phase E/F 只是顺序占位，不等于已批准具体仓库整理或 benchmark 范围。Phase D 正式通过后必须执行 STOP-1。

### A-D 统一失败处理协议（2026-07-31）

- 任一阶段失败后进入 `failure -> freeze failed attempt -> reproduce -> root-cause classification -> falsifiable hypothesis -> failing regression/diagnostic test -> minimal repair -> focused verification -> independent review -> new versioned attempt -> gate re-evaluation`，不得因首次失败结束 A-D。
- 原失败 attempt 必须 append-only 保留 run ID、输入/prompt/code/model hash、raw response 或 transport failure、failure taxonomy、模型调用次数、automatic write count，以及根因与修复绑定；禁止覆盖、删除或补写成成功。
- 修复后必须使用新的 attempt/run/version。语义行为改变时必须绑定新的 prompt/code hash；对应失败测试须完成 red -> green，相邻回归通过，且上一失败事实保持不可变。
- 每个 attempt 仍固定 `max_attempts=1`、无 automatic retry、无 fallback、无模型切换；不得重复执行输入、代码、prompt 和模型完全相同的 attempt。
- A-D 必须最终全部通过。普通测试失败、模型语义失败或实现困难都属于 RCA/repair loop；只有 key/权限缺失、provider 持续不可达、唯一权威输入无恢复链或需要新增授权/外部数据时才构成外部阻塞。

### Phase A：v8 query-only 受控闭环（已授权，当前执行起点）

目标：复用 v8 已写入的 2 条 L1、1 条 L2 和既有有效 Git snapshot，只补足 checkpoint recovery 与 query-only 入口，完成一次官方 `deepseek-v4-pro` Query 调用和确定性执行。

实施边界：

- 只允许按最小需要修改现有 `tools/natural_memory_benchmark/e2e_openai_runtime.py`、`e2e_pipeline.py`、`query_execution_snapshot_adapter.py` 及 `tests/natural_memory_benchmark/test_e2e_pipeline_smoke.py`；优先复用现有函数，不新增通用 harness、spec、plan、worktree 或非必要文档。
- Query 前先恢复并重新验证既有 checkpoint：Git commit、bundle logical ID、TurnBundle/L2 closure、registry/identity scope、artifact hash 和 snapshot authority 必须全部闭合。不得创建新的 L1/L2、不得重跑 v8 extraction、不得修改既有 memory bundle 或 snapshot。
- 外部通道 preflight 必须先于任何 receipt/冻结层扩建：验证 `OPENAI_BASE_URL`、`OPENAI_API_KEY`、`OPENAI_MODEL=deepseek-v4-pro` 可用和目标模型一致。密钥只能来自环境变量，禁止写入命令行、日志、异常、request/response artifact、receipt、测试 fixture 或 Git。
- Query 只允许一次 semantic request，`max_attempts=1`，不得 retry、fallback 或切换模型。返回必须是执行器支持的 `fact` 或 `count`；`entity_list`、unsupported time、absence 或其他 projection 必须继续 fail-closed。
- 只增加一个必要的 query-only integration test，证明恢复既有 checkpoint 后不会调用 L1/L2 producer、不会产生 memory write、只发出一次 Query 请求，并经 verified snapshot adapter 返回 evidence-backed answer。
- 聚焦验证至少覆盖新增 integration test、`test_query_execution_snapshot_adapter.py`、`test_query_plan_v2_executor.py`、`test_query_compiler_v2_openai_producer.py`、`compileall`、`git diff --check` 和 credential pattern scan。既有 pytest frozen-directory warning 本阶段明确延期，不得顺手修改。
- 独立代码审查必须达到 Critical/Important `0`；任何 query answer 缺 evidence、authority hash、checkpoint/commit binding，或发生第二次模型请求、任何 L1/L2 write，都判定该 attempt 失败，冻结后进入上述 RCA/repair loop。

Phase A 通过标准：同一既有 snapshot 上，Query 的 `fact`/`count` 结果可由 executor 重放，答案完整回指 `MemoryUnitRevision -> EvidenceSpan -> raw turn revision`，且 L1/L2 extraction call count 为 `0`、Query call count 为 `1`、automatic memory write count 为 `0`。该结果必须标注为 `controlled_query_only_closure`，不得标注为 extraction qualified、production ready 或 benchmark ready。

### Phase B：自动抽取质量修复（已授权，受 Phase A gate 约束）

目标：只在新建且与 fresh-v3 隔离的 diagnostic/dev 数据上修复 official-v2 暴露的真实模型质量问题，不在 hidden 结果上调参。

实施边界与门禁：

- 禁止重跑、修改、替换、重采样或反向读取 fresh-v3 hidden case；fresh-v3 official-v2 的 prompt、proposals、raw response、score、report 和 chronology 全部保持只读。
- diagnostic 必须覆盖 L1 participant/角色分解、局部实体边界、memory kind、abstention/false emission，以及 L2 kind、structured claim、summary、support/closure；不得扩大到 AMR、identity/ontology 扩测、额外 benchmark 或持久层选型。
- 修复目标是 raw proposer 质量，deterministic gate 只允许拒绝危险 proposal，不得“纠正”语义字段或用 gated safety 掩盖 raw error。不得降低 scorer threshold、删除难例或增加 post-hoc special case。
- 先写失败测试/diagnostic scorer 断言，再最小修改 prompt、producer 或 deterministic validation；每次模型请求必须 no-history、public-only、计数、绑定 requested/response model，并在读取 authority/gold 前冻结 proposal/provenance。
- dev 退出门为 L1 全部 preregistered strict metrics `1.0`、L2 全部 preregistered strict metrics `1.0`、两层 `raw_critical_false_emission_count=0`、`gate_intervention_count=0`、`deterministic_critical_false_materialization_count=0`，且 automatic write 仍为 `0`。任一项未达标就停留在 Phase B。

### Phase C：新的 fresh-hidden 自动抽取资格门（已授权，受 Phase B gate 约束）

目标：在 Phase B 完整通过后，以新的 versioned root 和未见数据测量修复是否泛化；这不是 fresh-v3 rerun，也不得覆盖 fresh-v3 结论。

实施边界与门禁：

- 复用现有最小 prereg/materialization/proposer/scorer 合同，不扩建 fresh-v3/Query 通用 harness；只有现有合同无法表达硬门时才允许最小补丁。
- 在创建 run artifact 前先做传输 preflight，确认 key、endpoint、`deepseek-v4-pro` 访问和 response model 一致。传输失败只记录一个紧凑 failure receipt 并停止，不得先扩建多层恢复/冻结设施。
- 新 hidden 必须与所有 dev/diagnostic/fresh-v1/v2/v3 数据隔离；composition、全部使用、no-filter/no-replacement/no-resampling、public-only/no-history、每层一次请求、proposal-before-scoring 和 raw/gated 分离报告继续是硬约束。
- 资格门与 Phase B 相同：所有 strict raw metrics 精确 `1.0`，critical false emission、gate intervention、critical false materialization 均为 `0`。任何失败都禁止进入 Phase D/F，只能回到新 diagnostic 数据修复，不能针对本次 hidden 原地调参。

### Phase D：真实自动端到端闭环（已授权，受 Phase C gate 约束）

目标：证明以下真实链路在没有人工 proposal 注入、没有 gold 暴露、没有跳过 admission/materialization 的情况下成立：

```text
raw user-agent turns
-> automatic L1 extraction
-> automatic L2 extraction/closure
-> admission and immutable MemoryUnitRevision materialization
-> atomic Git checkpoint
-> natural Query compilation
-> verified execution snapshot
-> deterministic executor
-> evidence-backed answer/abstention
```

验收至少覆盖一个 L1/L2 `fact`、一个跨证据 `count` 和一个应 fail-closed/abstain 的场景。每个场景必须满足：无人工 typed candidate 注入、无 gold-side 输入、失败事务无半成品、Git checkout 可字节级恢复、query plan/registry/snapshot revision 一致、答案值与完整 evidence set 精确、critical false positive 为 `0`、trace completeness 为 `1.0`。v8 query-only 不替代本阶段。

只有 Phase C 与 Phase D 同时通过，才可称“自动抽取到查询的受控端到端闭环通过”。这仍不是生产可用结论。达到此处必须立即停止，不得开始仓库盘点、清理、移动/删除文件、修复 hygiene warning 或执行 benchmark；先向用户提交端到端证据和剩余风险，等待用户给出仓库整理要求。

### 第一强制停止点：Phase D 后、仓库整理前

Phase D 正式通过后必须停止当前开发链并向用户报告：fresh qualification、真实端到端结果、所有失败 attempt 及修复关系、automatic write、Git/evidence replay、代码审查和剩余风险。Phase D 未通过时继续按 RCA/repair loop 处理，不得进入仓库整理。没有用户随后给出的具体整理目标、保留范围、删除边界和明确授权，不得执行任何仓库整理动作，也不得为整理预先新增 manifest、脚本、测试或文档。

### Phase E：仓库整理门（范围待用户给出，当前不得执行）

Phase E 的具体 inventory、`keep/archive/delete` 分类、路径 allowlist、是否处理 pytest frozen-directory warning、允许生成的 manifest 和验收命令均由用户后续要求决定，不能由开发 session 预设。无论后续要求如何，正式 gold/source snapshot、official model raw/provenance/score/report/receipt、有效 Git snapshot 和已引用 hash/manifest 默认不得删除或改写；任何删除仍须使用显式路径 allowlist 并做前后验证。Phase E 未获批准或未通过，不得进入 Phase F，也不得讨论 production rollout。

### Phase F：memory benchmark（需新授权）

前置条件：Phase C 自动抽取 fresh qualification、Phase D 真实自动端到端闭环以及用户后续定义并批准的 Phase E 仓库整理门全部通过。绿色 schema/test 或 Phase A query-only 不能替代这些前置条件。

执行顺序与边界：

- 先在现有冻结 32-item natural slice 上跑完整自动链，而不是只对 gold-side evidence corpus 重放已有 symbolic/dense retrieval：BEAM 10、LoCoMo 10、LongMemEval 12。ingestion、extraction 和 query execution 只能读取 public/raw 输入；result/provenance 冻结后，独立 scorer 才可读取 `gold.json` 和 `gold-evidence.json`。
- 32-item gate 通过后，再按已批准范围运行 BEAM 100K、LoCoMo 和 LongMemEval。LongMemEval 若仍使用 oracle haystack，必须明确标为 oracle retrieval 条件，不得外推到完整长期检索；LoCoMo category 5 的 `manual_required` 边界继续保留。
- 同源、同问题、同 TopK/预算下报告本项目 automatic symbolic memory、guarded fallback 和 dense reference。embedding 只允许在预先分类的 lexical/predicate missing-link 缺口触发，不得用于身份、事实、成员关系或 structural reasoning 权威。
- 必报指标包括：fresh qualification 与有语义标注子集上的 L1/L2 extraction strict quality、Evidence Set Exact Match、All-Evidence@K、Evidence Recall/Precision、answer correctness、abstention correctness、critical false positive、fallback trigger/reason、trace completeness、Git replay、latency、token/cost 和失败样本 taxonomy。表示质量、检索质量、答案质量和产品结论必须分开。
- Mem0、Graphiti、Hindsight、MemPalace、Zep 等外部系统仍不本地复跑；作者/官方结果只作不可直接比较的上下文。不得宣称相对产品优越性、用户体验提升或 production ready。

### 第二强制停止点：benchmark 后

完成 Phase F 的冻结结果、评分、失败样本和审计报告后必须停止，向用户汇报：通过项、失败项、证据强度、已知偏差、仓库状态以及是否具备进入生产化讨论的资格。未经新一轮用户决策，不得继续生产部署、扩大到 BEAM 500K/1M、选择最终 AMR/KEOL/数据库持久层、复跑外部 memory 系统、自动 authoritative deployment 或清理更多历史资产。

### 跨阶段质量规则

- 所有阶段 fail-closed：preflight、schema、hash、evidence closure、snapshot、review 或模型质量任一硬门失败时，立即停止该 attempt 和阶段切换，冻结失败并进入 RCA/repair loop；不得以补写 receipt、放宽 threshold、静默重试模型或扩大 harness 绕过。
- 冻结数据 append-only；新实验必须使用新的 versioned root。测试通过、`0 error/0 warning`、完整 proposal coverage 或 gate safety 都不能单独证明模型语义质量。
- 实现采用 TDD 和最小变更；聚焦测试后跑相关回归与静态检查。已知失败只能使用执行前固定的精确 allowlist，任何新增失败都必须解释并阻止阶段通过。
- 每个阶段结束都要更新本 `AGENTS.md` 的事实状态、Git commit、模型/数据版本、关键指标、automatic write count 和下一授权边界；不得用摘要替代正式 artifact 路径与 hash。
- 密钥和敏感 header 永不落盘；正式产物和提交前必须做 credential pattern scan。独立 review 的 Critical/Important 必须为 `0`，Minor 必须显式记录且不得影响验收语义。
