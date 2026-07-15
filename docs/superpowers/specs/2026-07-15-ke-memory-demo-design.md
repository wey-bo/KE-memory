# KE Agent Memory 效果验证 Demo 设计

日期：2026-07-15

状态：对话设计已确认，书面规格等待用户复核

项目目录：`/public/home/wwb/KE_mem/ke-memory-demo`

## 1. 目标

本项目构建一个独立、可复现的研究型 Demo，用知识方程（Knowledge
Equation，KE）表达和组织 Agent 对话记忆，并在 BEAM 100K 的固定小子集上与
四个主流开源 Agent Memory 系统进行横向效果验证。

Demo 要回答三个问题：

1. 一轮对话能否在保留原文的同时，形成可追溯、可匹配的 KE 表达。
2. 多层归纳和跨 Session 语义聚合能否得到单轮检索难以直接获得的任务、目标、
   决策、状态、偏好、事件链和长期模式等抽象记忆。
3. KE 符号召回与独立 embedding 召回结合后，能否在矛盾处理、知识更新、事件
   排序、跨 Session 推理、摘要和时间推理等问题上优于或补足现有系统。

研究结果不预设 KE 系统一定优于基线。工程完成标准和研究效果结论分开：前者由
数据完整性、可追溯性、可复现性和实验完备性决定；后者由固定协议下的实际指标
决定。

## 2. 范围与非目标

### 2.1 本期范围

- 以一轮 `user message + 紧随其后的 assistant message` 为最小处理单元。
- tool call/result 可以作为该轮中的附属事件，并参与抽取和证据回溯。
- 实际实现 Turn KE 抽取、Session 归纳、跨 Session 语义聚合 DAG、原文证据链、
  正交 embedding 和 Git memory snapshot。
- 使用真实 Elasticsearch 领域词表索引作为当前领域本体，且只读访问。
- KE query 和 KE match 由 LLM 模拟，不实现完整符号统一或定理证明器。
- 使用统一回答模型和独立 Judge，在固定 BEAM 子集上比较本 Demo 与 Mem0 OSS、
  Graphiti、Hindsight、MemPalace。

### 2.2 明确非目标

- 不构建生产级 REST 服务、前端、多租户、权限、删除合规或高可用系统。
- 不把跨 Session 层级固定为 Task；Task 只是通用语义聚合节点的一种类型。
- 不复制或 snapshot 整个 Elasticsearch 词表。
- 不做 `embedding-only`、`turn-KE`、`hierarchical-KE`、`KE+embedding` 四组内部
  消融实验。
- 不修改四个 baseline 的源码，只使用其公开写入、召回和配置接口。
- 不参考 `/public/home/wwb/memory`、fusion-memory 或其任何派生材料。
- 不把 KE 本身宣称为原文的无损替代。无损性由原始消息、精确 span 和 coverage
  共同保证。

## 3. 允许使用的输入与冻结版本

| 输入 | 本地位置 | 冻结版本 |
|---|---|---|
| KEOL | `/public/home/wwb/KE_mem/KEOL` | `2970fb331178391fb7db5ccfd090938cdb1dc1be` |
| Ontology Specification | `/public/home/wwb/KE_mem/Ontology-Specification` | `7e17e52d41963676da6658b4131482b26c153e72` |
| Agent Memory SOTA study | `/public/home/wwb/memory-sota-study` | 以该目录研究文档记录的源码 SHA 为准 |
| BEAM | `/public/home/wwb/datasets/BEAM.zip` | SHA-256 `690106a93ab88dac46e8fef1e84884acc889518424240f57a47428d3efbe6346` |

Baseline 源码版本固定为：

| Baseline | SHA |
|---|---|
| Mem0 OSS | `87276ef96879ee406690e640d34060de546560a5` |
| Graphiti | `62ff03ac5662d288ebd9f6aafb70d6ae4070c632` |
| Hindsight | `f00d3c7f666e560bb051c51fba3977b38885f46a` |
| MemPalace | `18a9788961afce013efc9e2da23ea2b17ab72381` |

## 4. KEOL 基础模型

本 Demo 采用 KEOL 当前设计中的以下核心语义：

```text
Ontology = Concept + Operator
Knowledge = Assertion
Assertion(A, B) := A = B
```

其中：

- `Concept` 表示世界中可被谈论的类、实体类型、事件、状态、资源和抽象对象。
- `Individual` 表示观察到的具体实例或被正规化后的实体实例。
- `Operator` 表示关系、动作、推理、变换或验证算子，具有输入和输出类型。
- `OperatorApplication` 表示算子作用于参数后的表达式，在 Assertion 中内联出现。
- `Assertion` 是最小可追溯知识单元，把两个 ontology expression 以等式连接。

Assertion 的左右两侧允许是 Concept、Individual、Operator、OperatorApplication 或
嵌套 Assertion。典型事实可写为：

```text
Assertion(Apply(current_status, project_x), deployment_ready)
Assertion(Apply(prefers, user), concise_answers)
Assertion(Apply(instance_of, flask), web_framework)
```

本 Demo 中“KE”指一个带运行时语义信封的 Assertion。等式表达是核心，证据、
时间、说话者、模态、生命周期和本体绑定属于可追溯记忆系统所需的外围元数据，
不改变 KEOL 的等式定义。

## 5. KE 与 Ontology 的关系

Ontology 定义可使用的语义词汇和操作方式；KE 使用这些词汇表达具体知识。
两者的职责严格分开：

| 层 | 职责 | 本 Demo 来源 |
|---|---|---|
| 固定元模型 | 定义 Concept、Individual、Operator、OperatorApplication、Assertion | KEOL |
| 领域本体 | 提供领域词条、类型、别名和关系 | Elasticsearch 只读词表 index |
| 记忆知识 | 表达某轮或聚合层得到的具体 Assertion | LLM 抽取并经程序校验 |
| 证据与生命周期 | 记录来源、时间、状态、派生关系和版本 | Demo memory model |

Elasticsearch 词表在本体系中具有以下特点：

1. **外部维护**：Demo 不拥有词表，不写入、不修复、不自动新增词条。
2. **领域化**：词表可能对 BEAM 的通用话题覆盖不足，未命中是正常现象。
3. **开放世界**：未命中不等于概念不存在，只形成 `unresolved` 本体绑定。
4. **别名和关系可用**：别名用于正规化，关系帮助识别 Concept/Operator 间联系。
5. **会演进但不复制**：运行记录 index、index UUID、mapping hash 和命中的文档 ID，
   不保存整份词表 snapshot。
6. **不是事实库**：ES 词条只约束表达语言，不决定某条对话事实是否为真。

`Ontology-Specification` 中 Concept 的 `name/comment/id` 和 Operator 的
`name/input/output/comment/id` 为 ES 字段适配提供最低语义目标。实际 ES 字段名通过
配置映射，不假设线上 index 与示例字段完全相同。

## 6. 什么是 KE，以及如何抽取 KE

### 6.1 KnowledgeEquation 数据结构

每条 KE 至少包含：

```text
KnowledgeEquation
  id                    deterministic ID
  revision              object revision
  level                 turn | session | aggregate
  lhs                   typed expression tree
  rhs                   typed expression tree
  gloss                 human-readable normalized statement
  modality              fact | belief | preference | goal | plan |
                        instruction | hypothesis | question
  polarity              positive | negative | unknown
  lifecycle             active | superseded | contradicted | retracted |
                        uncertain
  speaker               user | assistant | tool | derived
  temporal              mentioned_at, event_time, valid_from, valid_to
  ontology_bindings[]   ES binding or unresolved record
  evidence_refs[]       exact message spans
  derived_from[]        lower-level KE or aggregate IDs
  contradicts[]         conflicting KE logical IDs
  supersedes[]          prior KE logical IDs replaced by an update
  confidence            extraction confidence
  produced_in_run_id    producing run
  produced_in_stage     producing stage
```

表达式树只允许受控节点类型，不接受自由 JSON：

```text
ConceptRef | IndividualRef | OperatorRef |
OperatorApplication(operator, arguments[]) |
AssertionRef
```

`id` 由 schema version、level、规范化表达式、source references 或 derived references
的 canonical JSON 计算；`revision` 是规范化对象内容 hash。对象不嵌入包含自身的 Git
commit SHA，避免内容和 commit hash 的循环依赖。对象属于哪个 snapshot 由 Git tree
和 snapshot manifest 确定。

### 6.2 Turn KE 抽取流程

1. 无损保存 Exchange 的 user、assistant 和可选 tool events，并计算内容哈希。
2. LLM 从完整 Exchange 中识别事实、偏好、目标、约束、计划、决策、状态、更新、
   否定和不确定表达，同时返回 source span。Span 使用已保存 Unicode 字符串上的
   `[start_char, end_char)` code-point offset，并附原文片段 hash。
3. 对抽取出的 surface terms 查询 ES：先正规化文本，再匹配 canonical term、alias、
   type 和关系候选。
4. LLM 只能从返回候选中选择 ES ID；没有合法候选时保存原始 surface form，并将
   binding 标为 `unresolved`。
5. 程序校验表达式类型、span、ES ID、时态、模态和引用完整性。不存在于原文的
   span、未查询到的 ES ID、悬空引用和非法表达式一律拒绝。
6. 为 Exchange 生成 coverage map，说明哪些信息由哪些 KE 表达，哪些是上下文、
   非记忆内容或抽取失败内容。

coverage 状态为：

- `represented`：由一个或多个 KE 表达。
- `context_only`：用于理解但不形成独立长期记忆。
- `non_memory`：寒暄、纯格式等无需持久化为 KE 的内容。
- `extraction_failed`：应该处理但未得到有效结构，导致该阶段不通过。

每个 message 的 coverage entries 必须无间隙覆盖完整 `[0, len(content))` 区间；
同一字符可以被多个 `represented` KE 引用，但最终 coverage classification 不能互相
冲突。空白、标点和格式片段也必须明确归入 `context_only` 或 `non_memory`，从而让
“完整 coverage”成为可由程序检查的条件，而不是主观描述。

“完整保留原始信息”的验收依据是原文哈希完全一致、每个消息可按原始 ID 定位、
每个 KE 有精确 span、每轮有完整 coverage。不能仅以 KE 数量判断完整性。

### 6.3 矛盾与更新

KE 不覆盖旧知识。新旧 KE 通过标准化主体、Operator、时间范围、模态和 polarity
形成候选冲突组。每批新 KE 写入前运行一次 lifecycle matcher，判断
`contradicts`、`updates` 或无冲突；召回时另运行 query matcher。两者使用相同的
结构化 match schema，但 lifecycle matcher 可以更新对象状态，query matcher 只读。
普通矛盾只建立双向 `contradicts` 关系，双方保持可见，系统应请求澄清；只有明确的
后续更新才把旧 KE 标为 `superseded`，明确撤回才标为 `retracted`，有充分证据判定
无效时才标为 `contradicted`。Lifecycle transition 追加同一 logical ID 的新 revision，
不改写旧 revision。新 KE 保存 `derived_from` 或 `supersedes` 关系，因此系统可以
同时回答“当前是什么”和“之前说过什么”。

## 7. 对话结构与多层语义聚合

### 7.1 结构层级

```text
Conversation
  Session
    Exchange
      user Message
      tool call/result Event (optional)
      assistant Message
```

结构层级反映输入组织，不直接等于语义层级。

### 7.2 Session 归纳

每个 Session 读取其 Turn KE、coverage 和必要原文证据，产生：

- Session 摘要；
- Session 级 KE；
- 仍未解决的冲突、约束和开放问题；
- 每条派生内容到 Turn KE 和原文 span 的证据链。

LLM 只能提出派生 Assertion。程序会检查所有 `derived_from` 引用、证据闭包和
时间一致性；无法回源的归纳内容被拒绝，而不是作为“合理推断”保存。

### 7.3 通用语义聚合 DAG

跨 Session 不建立单一 Task 树，而建立允许重叠的有向无环图。`AggregateNode`
可表示：

```text
Task, Project, Topic, Goal, EventChain, EntityTimeline, Decision,
State, Constraint, Preference, Procedure, Pattern, Issue, Other
```

一个 Turn KE 可以同时属于多个节点；聚合节点也可以由较低层 AggregateNode 再次
归纳。节点包含：

```text
id, node_kind, title, summary, assertions[], member_refs[],
derived_from[], evidence_closure[], temporal_extent, confidence, revision
```

构建顺序为：

1. 从 Session KE 的共享主体、Operator、时间和显式引用生成候选组。
2. LLM 判断候选组是否形成稳定语义单元，并选择 node kind。
3. LLM 生成摘要和聚合 KE，但必须逐条给出下层引用。
4. 程序验证无环、引用存在、证据闭包、时间范围和 Assertion 合法性。
5. 如多个第一层节点仍形成更高层稳定模式，则只再执行一次归纳。Session 之上的
   `max_semantic_depth` 固定为 2，Demo 不做无限自动归纳。

Embedding 不参与聚合候选生成，避免 embedding 路径和 KE 路径在生成阶段耦合。

## 8. 召回与回答

### 8.1 KE 符号候选

查询先由工作模型抽成 Query KE。候选生成使用 SQLite 中的 Concept/Individual、
Operator、ES binding、正规化 unresolved surface form、lifecycle、时间和 aggregate
membership 索引，不调用向量相似度。Query KE 使用和 Turn KE 相同的表达式 schema
及 ES resolver，但只存在于当前请求 trace，不写入长期记忆。

LLM matcher 接收 Query KE 和有限候选，输出：

```text
match_type = exact | equivalent | subsumes | related |
             contradicts | updates | temporal_precedes | temporal_follows |
             no_match
candidate_ke_id
confidence
reason
```

Matcher 是符号匹配效果的 LLM 模拟器，不被描述为完整的逻辑统一引擎。

### 8.2 正交 embedding 路径

默认使用本地 `Qwen/Qwen3-Embedding-0.6B`，上游 revision 固定为
`97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`。`embedding.local_path` 必须指向独立的
本地模型目录，加载时启用 `local_files_only`，正式运行不下载模型。Preflight 计算
模型 config、tokenizer 和 weight files 的确定性内容指纹并写入 experiment manifest；
路径缺失、文件不完整或内容指纹在同一实验中变化时运行失败。Embedding 文档包括：

- 原始 Exchange 的分块文本；
- Turn KE gloss；
- Session 摘要和 Session KE；
- AggregateNode 摘要和聚合 KE。

长文本按 1024 tokenizer tokens、128 tokens overlap 确定性切分。向量以 float32
保存并做 L2 normalization，使用完整 1024 维输出。Query text 使用固定模板
`Instruct: Given an agent-memory question, retrieve conversation evidence needed to answer it.\nQuery: {question}`；
document 编码不加 instruction。Instruction 和编码参数均进入 prompt/config hash。
Demo 数据量下使用精确 cosine，不引入独立向量数据库。

正交性约束为：

- embedding 候选生成看不到 KE/ES match 分数；
- KE 候选和 LLM matcher 看不到 embedding 分数；
- 两路结果只在统一 evidence fusion 层相遇；
- 两路的候选、分数和来源分别记录，便于解释，但不形成内部消融实验。

### 8.3 Evidence fusion 与回答

融合层执行：

1. 合并两路候选并按原始 source span 去重。
2. 保留命中通道、匹配类型、lifecycle 和聚合层级。
3. 对派生节点同时加入最小充分的原文证据，不只向回答模型提供摘要。
4. 在工作模型 tokenizer 下使用固定 8192-token evidence budget。
5. 使用固定 prompt 和 `gpt-5.4` 生成最终回答，`max_output_tokens` 固定为 1024。

证据选择优先满足问题所需的不同时间点、冲突双方和跨 Session 来源，而不是单纯
取最高相似度的多个近重复片段。

## 9. Elasticsearch 只读适配器

配置必须提供 endpoint、index 和字段映射：

```text
id field
canonical term field
type field
aliases field
relations field: relation type + target ID
source-type to Concept/Individual/Operator role mapping
```

适配器只暴露：

```text
health()
resolve_terms(surface_terms[])
fetch_terms(ids[])
fetch_relations(ids[])
index_identity()
```

实现只允许 Elasticsearch 的 health、mapping、`_search` 和 `_mget` 等只读调用，
不实现 index、update、delete 或 bulk write 方法。运行开始和结束都校验 index UUID
和 mapping hash；实验期间发生变化则该运行失败，不能混用两版词表绑定。

ES 正常返回但无命中时产生 `unresolved`。连接失败、认证失败、字段映射错误和超时
属于 adapter failure，不能批量伪装成 `unresolved`。测试 fixture 只用于单元测试，
不能用于正式 BEAM 结果。

## 10. Snapshot 设计

### 10.1 两个 Git 仓库

- `ke-memory-demo`：代码、配置模板、prompt、schema、测试和文档。
- `ke-memory-demo-state`：规范化实验状态和结果，独立于代码仓库。

State repo 中 Git commit SHA 就是 `snapshot_id`。SQLite 是可从 JSONL 重建的运行时
缓存，不提交。Canonical artifact 和本次 commit 的 manifest 不写入自身 commit
SHA；commit 成功后由 `git rev-parse HEAD` 获得 snapshot ID，后一个 snapshot 可以
通过 `parent_snapshot_id` 引用前一个 commit。

### 10.2 Snapshot 阶段

```text
ingested
turn-ke-extracted
session-aggregated
semantic-dag-built
embedding-ready
evaluation-complete
```

每次 commit 之前先验证该阶段完整性，再写 manifest。Manifest 至少记录：

- run ID、stage、parent snapshot；
- code commit、配置 hash、prompt hash、schema version；
- BEAM archive hash 和固定 conversation IDs；
- 模型名、provider、参数和响应 usage，不含密钥；
- ES index identity 和命中文档引用，不含完整词表；
- 对象数量、对象内容 hash、失败计数；
- baseline SHA、容器或依赖版本；
- 创建时间和逻辑 stage ID。

State repo 保存规范化 JSONL、脱敏 LLM trace、manifest、小规模 embedding、回答、
Judge 输出和报告。Trace 中的 Authorization header、API key、cookie 和已知 secret
字段在落盘前统一删除。BEAM 数据只用于本地实验，manifest 保留其 CC BY-SA 许可
信息；项目不会默认发布 state repo。

Git snapshot 提供整体 checkpoint；每个 KE 和 AggregateNode 仍独立保留 revision、
derived_from 和 lifecycle，以支持对象级追溯。

## 11. 模型与密钥配置

`config/models.toml` 只保存非秘密配置：

| 用途 | 模型 | Base URL | Key 环境变量 |
|---|---|---|---|
| KE 抽取、归纳、match、统一回答 | `gpt-5.4` | `https://api.penguinsaichat.dpdns.org/v1` | `KE_MEMORY_WORK_API_KEY` |
| 独立 Judge | `deepseek-v4-pro` | `https://api.deepseek.com/v1` | `KE_MEMORY_JUDGE_API_KEY` |
| 正交 embedding | `Qwen/Qwen3-Embedding-0.6B@97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3` | 本地文件系统 | 无 |

用户提供的实际 key 只写入项目根目录 `.env.local`。该文件必须加入 `.gitignore`、
权限设为 `0600`，且不得进入 trace、报告或 snapshot。由于 key 已在对话中出现，
正式长期使用前应轮换。

模型 preflight 必须分别执行最小请求，验证 endpoint、model ID、结构化输出和 usage
字段。任何模型不可用时停止对应阶段，不静默替换模型。温度设为 0（provider 支持
时），并记录 provider 返回的 request ID 和实际 model 名。

Embedding preflight 不访问网络，只验证 `embedding.local_path`、固定 revision 元数据、
模型维度、一次测试编码的有限数值和模型文件内容指纹。

Baseline 内部需要 LLM 时，当且仅当其公开配置接受 OpenAI-compatible endpoint 和
自定义 model ID，才配置为同一 `gpt-5.4`。当且仅当公开配置接受兼容的自定义本地
embedder，才配置为同一固定 embedding 模型。不能为了统一组件而修改 baseline
源码；不满足条件时使用该冻结源码的 upstream default，并在 manifest 和报告中记录。

## 12. BEAM 固定子集与规范化

### 12.1 预注册选择规则

BEAM 100K 的 20 个目录先按 topic category 分为：

- `formal`：目录 1-5，Coding 或 Math；
- `artifact`：目录 6-10、13-15，Writing Assistant 或 Recommendation；
- `human`：目录 11-12、16-20，Philosophy、Lifestyle、Therapy 或 Legal。

每组对目录 ID 计算：

```text
sha256("ke-memory-demo:BEAM-100K:<archive_sha>:<stratum>:<directory_id>")
```

取字典序最小的 digest。该规则得到：

| BEAM 目录 | topic.id | category | title | Session | Exchange | Questions |
|---|---:|---|---|---:|---:|---:|
| `100K/4` | 7 | Math | Exploring the Geometry of Triangles | 3 | 106 | 20 |
| `100K/15` | 20 | Asking Recommendation | Choosing Comfortable and Stylish Sneakers for Daily Wear | 5 | 136 | 20 |
| `100K/17` | 22 | Lifestyle | Time Management for a Balanced Life | 5 | 143 | 20 |

合计 385 Exchange、60 道问题。每个对话包含 10 类问题，每类 2 道：abstention、
contradiction resolution、event ordering、information extraction、instruction
following、knowledge update、multi-session reasoning、preference following、
summarization、temporal reasoning。

### 12.2 Conversation 规范化

- `chat.json` 每个顶层 batch 转成一个 Session。
- batch 内 `turns` 的数组可能含 2、4 或 6 条消息，不能把整个数组当成一轮。
- 按源顺序扫描消息；每个 user message 开启 Exchange，紧随其后的 assistant
  message 关闭 Exchange，中间 tool call/result 归入该 Exchange。
- orphan assistant、连续 user 未闭合、非法 role 或重复 source ID 使导入失败。
- 保存 BEAM directory ID、topic ID、batch number、turn group index、message ID、
  role、原文、原始 index 和全局 ordinal。
- BEAM `time_anchor` 为空时不虚构事件时间。需要 ingestion/reference time 的系统
  使用按全局 ordinal 单调增加的 synthetic timestamp，并标记
  `synthetic_order_only`，不得把它解释成对话中的真实日期。
- Probing question 的参考答案字段按 `ideal_answer`、`ideal_response`、`answer` 的
  明确优先级正规化，同时保留原字段和值；`rubric` 缺失或为空使数据预检失败。
- Probing questions 只在全部记忆写入完成后用于检索和评测，不能进入任何 memory
  system 的写入上下文。

## 13. Baseline 对比协议

### 13.1 统一 Adapter

```text
prepare(run_scope) -> AdapterIdentity
ingest(exchange) -> IngestReceipt
await_ready() -> ReadinessReceipt
retrieve(question, evidence_budget) -> Evidence[]
stats() -> UsageAndLatency
reset() -> ResetReceipt
```

`Evidence` 统一字段为：

```text
evidence_id, text, source_exchange_ids[], source_message_ids[],
system_record_ids[], score, rank, channel, metadata, token_count
```

若 baseline 的公开返回无法暴露来源，只能标为 `unattributed`，不得猜测 source ID。
写入 receipt 和公开返回记录 ID 可用于建立来源映射，但禁止直接查询 baseline 数据库
补标签。

### 13.2 公共 API 映射

| Baseline | 写入 | 召回 |
|---|---|---|
| Mem0 OSS | `Memory.add(messages, user_id, metadata)` | `Memory.search(query, filters)` |
| Graphiti | `add_episode(..., group_id, reference_time)` | `search(query, group_ids)` |
| Hindsight | `aretain_batch(bank_id, one-item batch)` | `arecall(bank_id, query)` |
| MemPalace | MCP `mempalace_add_drawer` | MCP `mempalace_search` |

每个 system/conversation/run 使用全新隔离 namespace。每轮单独调用并按原顺序等待
成功，不把多个 Exchange 合并成 baseline 特供的大文档。metadata 支持时传入 source
Exchange ID；不支持时使用公开的 episode name、document ID 或 source file 字段。

所有 baseline 只返回证据，不使用其自带回答或 reflect API。统一 Answer Model 接收
相同问题、相同系统 prompt 和相同 8192-token 证据预算。Baseline 自己的抽取、
consolidation、图构建和检索是被比较系统的一部分。

### 13.3 公平性

- 相同 Exchange 文本、顺序和 conversation isolation。
- 相同 question、answer prompt、answer model、输出上限和 evidence token budget。
- 每个 baseline 使用冻结 SHA 和公开配置，不做源码定制。
- 写入、内部处理、召回、统一回答和 Judge 的 token、延迟、调用次数分别计量。
- 系统标签在 Judge prompt 中隐藏；每次只评一个回答，避免答案顺序偏差。
- 一个系统失败不记为零分；该运行标记 incomplete，修复后对同一冻结输入重跑。

## 14. 评测与报告

### 14.1 Judge

DeepSeek V4 Pro 接收 question、ideal answer、BEAM rubric 和匿名 candidate answer，
输出结构化结果：

```text
rubric_items[]: satisfied | not_satisfied + reason
answer_score: satisfied_count / rubric_item_count
factual_error: boolean
unsupported_claim: boolean
abstention_correct: boolean | not_applicable
short_rationale
```

Judge 不接收 memory system 名称、内部 KE、检索分数或 baseline 信息。Judge 输出必须
通过 Schema；失败重试后仍无效的题目不进入聚合结果，并使 experiment incomplete。

### 14.2 指标

主要指标：

- Answer rubric score：总体、10 类和每个 conversation 的平均分。
- Source evidence recall：检索证据覆盖 gold source Exchange 的比例。
- Complete evidence rate：是否同时找齐问题所需的全部来源。
- Unsupported claim rate 和正确 abstention rate。
- 写入、召回、回答、Judge 的 token、wall-clock latency 和模型成本。

Source gold mapping 在运行任何系统前从 probing question 的结构化 source IDs 和
conversation references 生成并 snapshot。解析器只接受结构化整数 ID，或能通过
固定 `chat_id`/`Session` 数字模式唯一映射到一个 source Exchange 的引用；零个或
多个候选都视为不可映射。不可映射题目从 source recall 分母中排除并单独报告覆盖
率；它们仍参与回答分数。

重点报告：

- contradiction resolution：冲突双方证据是否同时出现，回答是否指出矛盾；
- knowledge update：是否区分旧状态、更新和当前状态；
- event ordering：证据和答案顺序是否正确；
- multi-session reasoning：是否跨 Session 找齐来源；
- summarization：是否覆盖必要片段且不过度编造；
- temporal reasoning：是否区分 mention time、event time 和有效期。

### 14.3 “其他系统做不到”的操作定义

- **KE unique success**：BEAM `rubric` 数组中的每一项都视为 mandatory。本 Demo
  满足全部 rubric 且 gold source recall 为 1.0，同时四个 baseline 各至少缺失一个
  rubric 或 gold source。没有可映射 gold source 的题目不参与 unique success 判定。
- **KE comparative advantage**：本 Demo 的 rubric score 高于每个 baseline，且
  source recall 不低于最高 baseline。
- 对每个候选案例展示匿名答案、检索证据、KE match、聚合证据链和 Judge rubric，
  不只展示总分。

报告提供 question-level paired difference，并以 experiment manifest hash 派生随机
种子，执行 10,000 次 question-level paired bootstrap，给出 95% confidence
interval。样本仅 60 题，分类结果属于探索性证据，不能表述为普遍 SOTA 结论。

## 15. 工程模块边界

```text
ke-memory-demo/
  config/
    models.toml
    experiment.toml
    es_vocab.toml
  prompts/
  schemas/
  src/ke_memory_demo/
    core/          IDs, schemas, provenance, lifecycle
    ingestion/     BEAM loading and Exchange normalization
    ontology/      Elasticsearch read-only vocabulary adapter
    extraction/    Turn KE and coverage extraction
    aggregation/   Session induction and semantic DAG
    retrieval/     query KE, symbolic candidates, LLM match,
                   embeddings, fusion and evidence packing
    answering/     common answer model
    baselines/     adapter protocol and four implementations
    snapshots/     state serialization and Git checkpoints
    evaluation/    experiment runner, Judge, metrics and reports
    infra/         model client, retries, redaction and telemetry
    cli.py
  tests/
    unit/
    contract/
    integration/
    golden/
  docs/superpowers/specs/
```

依赖方向从外层 pipeline 指向稳定 domain model。Ontology adapter、LLM client、
embedding backend、snapshot store 和 baseline adapter 都通过 Protocol/接口注入，
核心数据模型不依赖 Elasticsearch、某个模型 SDK 或某个 baseline 包。

Demo 提供分阶段 CLI，而不是服务：

```text
preflight -> ingest -> extract-turn-ke -> aggregate-session ->
build-semantic-dag -> embed -> run-baselines -> evaluate -> report -> verify-snapshot
```

阶段具有确定性输入 manifest 和幂等对象 ID，可以从最近成功 snapshot 继续。

## 16. 故障与恢复策略

### 16.1 错误分类

- transient：网络超时、429、可恢复 5xx；
- authentication/configuration：key、model、index 或字段配置错误；
- structured-output：LLM JSON/Schema 不合法；
- invariant：span、引用、DAG、hash、coverage 或对象类型违规；
- external-system：baseline 或 ES 不健康；
- experiment-incomplete：缺答案、缺 Judge、缺来源或部分写入。

Transient 请求最多四次总尝试，遵守 `Retry-After`，否则采用 1、2、4 秒退避。
结构化输出允许一次原请求和最多两次带校验错误的 repair 请求。认证、配置和
invariant 错误不盲目重试。

### 16.2 原子阶段

每阶段先写临时 run area，完成 Schema、引用、数量和 hash 校验后再提升为 canonical
artifact 并创建 snapshot。失败阶段不产生成功 snapshot。幂等 ID 和 ingest receipt
允许在同一 run namespace 内恢复；如果 baseline 的写入幂等性无法由公开 API 保证，
则丢弃该 baseline namespace 并从头重跑，不能重复追加。

### 16.3 特殊故障规则

- ES outage 不降级为全量 unresolved。
- LLM 无效结构不降级为自由文本。
- 聚合证据不完整时不保留无来源摘要。
- embedding 缺失或维度/数值错误时不生成 `embedding-ready` snapshot。
- baseline 失败不以零分污染排名。
- Judge 缺失时只保留 raw answer，不进入成对统计。

## 17. 测试策略

### 17.1 Unit tests

- 2/4/6 message group 和 tool events 的 Exchange 状态机。
- 确定性 ID、原文 hash、span 和 coverage 校验。
- KE expression union、模态、polarity、lifecycle 和引用校验。
- ES canonical/alias/type/relation mapping、未命中和 outage 区分。
- Session/Aggregate 证据闭包、重叠节点和 DAG cycle detection。
- KE 与 embedding 候选互不可见的正交性约束。
- token budget、去重、冲突双方和跨 Session evidence packing。
- secret redaction 和 manifest hash。

### 17.2 Golden tests

构造一个小型多 Session 对话，覆盖：

- 用户偏好；
- 一个跨多个 Session 的项目/任务；
- 明确否定和后续更正；
- 状态更新；
- 有顺序的事件链；
- 无法由 ES 解析的词条；
- tool result 证据。

Golden 断言原文不变、预期 KE 结构合法、冲突和更新关系正确、聚合节点跨 Session、
回答证据能回到原始 span。

### 17.3 Contract tests

四个 baseline adapter 使用统一 contract suite，验证全新 namespace、逐轮写入、
公开 readiness、召回、证据归一化、计量和 reset。Mock contract 在 CI 运行；正式
实验前对冻结源码实例各运行一轮 live smoke test。

### 17.4 Integration tests

- 使用测试 index 验证真实 Elasticsearch 客户端只读行为；正式运行另做 live
  field mapping 和 index identity preflight。
- 对工作模型和 Judge 各执行一个最小结构化请求。
- 完成一个多 Session fixture 的 ingest → KE → aggregate → embedding → recall →
  answer → Judge → snapshot 流程。
- checkout state snapshot，删除 SQLite 后重建，并比较对象 hash 和检索索引数量。

### 17.5 BEAM end-to-end

先对一个 conversation、一题做 smoke run，再运行固定的 3 个 conversation 和全部
60 题。正式结果不允许使用只跑重点类别或临时更换样本得到的部分报告。

## 18. 验收标准

### 18.1 工程验收

1. BEAM archive hash 和选择 manifest 匹配；固定子集恰好为目录 4、15、17。
2. 恰好导入 385 个 Exchange；所有 role、顺序、source ID、原文和 hash 与 BEAM
   一致，无 orphan message。
3. 每个 Exchange 都有成功抽取状态和 coverage；每条 KE 的 source span 可验证。
4. 所有 Session KE 和 AggregateNode 均有完整 evidence closure；DAG 无环、无悬空
   引用、无不存在的 ES binding。
5. ES adapter 在正式运行中连接真实只读 index，未调用任何写接口；运行前后 index
   identity 一致。
6. KE 和 embedding 候选分别生成并分别留痕，只在 fusion 层合并。
7. 每个成功阶段都有 Git snapshot；任一 snapshot checkout 后可重建 SQLite 并得到
   相同规范化对象 hash。
8. 五个系统各完成 60 个回答和 60 个有效 Judge，共 300 个回答结果，无静默缺失。
9. 报告包含总体、10 类、重点 6 类、source evidence、token、延迟、成本、失败和
   外部组件版本。
10. 仓库和 state snapshot 的 secret scan 不含 API key；`.env.local` 未被 Git
    跟踪且权限为 `0600`。

### 18.2 研究结论验收

研究结论必须直接对应冻结结果：

- 有 unique/comparative advantage 案例时，逐例给出证据链和 rubric；
- 没有此类案例时明确报告未观察到优势；
- 分数差异附 paired confidence interval；
- baseline incomplete 时不发布排名结论；
- 不把 3 个 conversation、60 题的探索性结果外推为通用 SOTA 声明。

## 19. 实施顺序约束

本规格通过用户书面复核后，下一步仅编写详细 implementation plan。实现阶段按以下
依赖顺序展开：domain schema 与无损 ingestion、ES adapter、Turn KE、聚合 DAG、
snapshot、embedding/recall、baseline adapters、evaluation/report。任何正式 BEAM
调用前先通过 synthetic/golden 测试和外部服务 preflight。
