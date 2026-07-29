# KE-test 知识优先抽取与词表对齐设计

状态：设计已确认，等待用户审阅本文档后进入实现计划。

## 1. 背景与目标

当前 KEOL baseline 在 `data/gold-candidates/KE-test.json` 上出现跨对话实体污染、关系方向错误、对象误合并，以及把 Agent 建议当作现实事实等问题。本轮暂不采用 KEOL 抽取结果，也不在知识抽取阶段强制生成 KE。

新实验先验证两个独立问题：

1. 模型能否在保全证据和认识论状态的前提下，完整、正确地抽取知识；
2. 能否从已确认的知识中抽取关键词，并可靠地生成 schema.org、WordNet 等词表的候选映射。

旧 KEOL 产物保留作比较项，但不得作为本轮模型输入、提示示例或语义来源。

## 2. 总体流程

```text
data/gold-candidates/KE-test.json
  -> A. 逐轮独立上下文补全与知识抽取
  -> B. 整段对话复核与追加式校正
  -> C. 确定性生成最终有效知识视图
  -> D. 按最终知识抽取类型化关键词
  -> E. 程序查询 schema.org / WordNet 候选
  -> F. subagent 对真实候选排序和标注映射关系
  -> G. 确定性验证、落盘和人工审阅视图
```

一轮固定定义为一次 User 输入和对应的完整 Agent 输出。A 阶段一次只看到一轮；B 阶段看到一段对话的完整原文和该对话全部 A 阶段结果。

语义抽取、复核、关键词生成和候选语义排序都由 subagent 完成。主线程不直接补写知识或关键词，只组织 prompt、分发输入、查询实际词表、验证契约、合并结果和生成报告。

## 3. A 阶段：逐轮独立抽取

### 3.1 输入隔离

每个 subagent 单元只包含：

- `candidate_id`、`turn_index` 和 source coordinate；
- 当前轮原始 User 文本；
- 当前轮完整 Agent 文本，包括其中显式标记的工具调用和工具结果；
- 字段契约、推断边界、完整性清单和禁止事项。

不得提供前后轮、其他候选对话、本轮 KEOL 结果或旧 KE 结果。每个候选的命名空间独立，禁止跨候选复用实体。

### 3.2 上下文补全层

模型先输出显式的上下文补全记录，而不是静默改写原文。补全类型包括：

- `coreference`：代词或指代表达；
- `ellipsis`：省略的主语、宾语或动作；
- `role_resolution`：当前轮能够确定的说话者或对象角色；
- `temporal_resolution`：仅凭当前轮能够确定的相对时间；
- `pragmatic_inference`：高置信度意图、担忧、偏好、条件、承诺或因果假设；
- `unresolved`：仅凭当前轮不能可靠确定的解释。

每条补全记录包含原始片段、补全后的简短解释、类型、证据、置信度和是否仍有歧义。模型可以做高置信度语用推断，但不得利用外部常识补成现实事实。

### 3.3 原子知识抽取

模型在补全层基础上抽取原子知识，覆盖：

- 实体及其在当前话语中的角色；
- 事件、状态、目标、偏好、约束和计划；
- 时间、地点、数量、价格、顺序和范围；
- 条件、原因、目的、否定、可能性和假设；
- User 的陈述、请求、问题、选择和承诺；
- Agent 的建议、解释、方案、声称和承诺；
- 工具调用、工具返回和由工具结果支持的状态变化。

礼貌语、空泛鼓励和不承载后续价值的套话默认不抽。无法确定的指代必须保持 `unresolved`，不能为了填满槽位而猜测。

## 4. 知识记录模型

每条知识至少包含：

```json
{
  "knowledge_id": "K_<candidate>_<turn>_<index>",
  "candidate_id": "...",
  "turn_index": 1,
  "statement": "用户计划在 12 月 15 日至 12 月 26 日出国休假。",
  "subject": "用户",
  "predicate": "计划",
  "object": "出国休假",
  "qualifiers": {
    "time": ["12 月 15 日至 12 月 26 日"],
    "condition": [],
    "cause": [],
    "purpose": [],
    "location": [],
    "quantity": [],
    "modality": "planned",
    "polarity": "positive"
  },
  "source_status": "user_reported",
  "derivation": "context_completed",
  "evidence": [
    {
      "message": "user",
      "quote": "说明 12 月 15 日到 26 日出国",
      "occurrence_index": 0,
      "start": 31,
      "end": 49,
      "evidence_role": "explicit_support"
    }
  ],
  "inference_basis": "“出国”沿用当前轮已说明的休假安排。",
  "confidence": 0.96
}
```

### 4.1 语义字段

- `statement` 是信息保全底座，必须是完整、可独立理解的中文陈述。
- `subject/predicate/object` 只承担基础结构；时间、条件、原因、目的、数量、模态和否定放入 `qualifiers`。
- `source_status` 枚举为 `user_reported`、`agent_generated`、`tool_observed`。
- `derivation` 枚举为 `explicit`、`context_completed`、`inferred`。
- `modality` 至少支持 `asserted`、`questioned`、`requested`、`preferred`、`planned`、`hypothetical`、`possible`、`advised`、`committed`、`claimed_completed`、`observed`。
- `polarity` 为 `positive` 或 `negative`。

Agent 的建议、解释或完成声称默认是 `agent_generated`，不能自动升级为现实事实。只有显式工具结果支持的状态才标记为 `tool_observed`。

### 4.2 证据规则

- 每条知识至少绑定一段原文 Evidence；允许一条知识引用同一轮 User 和 Agent 的多个片段。
- subagent 必须返回逐字引文和从 0 开始的 `occurrence_index`；程序据此计算 `start/end`。如果引文不存在或出现序号越界，该 Evidence 校验失败。
- `start/end` 使用 Unicode 字符索引并满足左闭右开区间；它们是程序生成的派生坐标，不依赖模型手算。
- `context_completed` 和 `inferred` 必须提供简短的 `inference_basis` 和所有支持片段。
- `inference_basis` 只记录可审阅的推断依据，不要求或保存冗长推理过程。
- 缺少证据、证据越界或引文不匹配的知识不得进入有效视图。

## 5. B 阶段：整段对话复核

B 阶段使用全新 subagent。输入为一段完整原始对话及其全部 A 阶段记录，重点处理：

- 跨轮指代和第一遍 `unresolved` 项；
- 同一对象在不同轮次中的状态变化；
- 用户选中、放弃或修改的方案；
- Agent 是建议、完成声称，还是有工具结果证明完成；
- 日期、价格、路线、数量和关系方向冲突；
- 重复知识、错误主体、错误对象和错误归因；
- 只有结合多轮才能成立的新知识。

B 阶段不得修改或删除 A 阶段文件，只能追加复核操作和新知识。操作类型为：

- `confirm`：完整对话支持原知识；
- `correct`：原知识有误，创建 replacement knowledge 并取代旧记录；
- `supersede`：旧知识在当时可能正确，但被后续状态或选择取代；
- `conflict`：多条受证据支持的知识互相冲突，保留全部并显式关联；
- `add`：新增只能通过多轮上下文得到的知识。

示例：

```json
{
  "operation_id": "R_...",
  "operation": "correct",
  "targets": ["K17"],
  "replacement": "K44",
  "reason": "完整对话表明“19 号”是返程日期，不是去程日期。",
  "evidence": [
    {"turn_index": 1, "message": "user", "quote": "往返航班"},
    {"turn_index": 2, "message": "user", "quote": "19 号回来"}
  ],
  "confidence": 0.99
}
```

`correct` 必须引用新建 replacement knowledge；`conflict` 不自动裁决真值。没有足够证据时保留多种解释或 `unresolved`，不能强行选择。

## 6. C 阶段：最终有效知识视图

程序按固定规则从不可变账本生成最终视图：

- 未被 `correct` 或 `supersede` 指向的知识默认有效；
- replacement knowledge 在引用和 Evidence 全部闭合后生效；
- 被 `correct` 或 `supersede` 的知识仍保留，但不进入默认有效集合；
- `conflict` 两侧均保留在有效集合并带冲突标记；
- `add` 创建的新知识与 A 阶段知识使用同一 schema；
- 所有状态均由账本和复核操作计算，不回写原记录。

同一原子陈述的重复项可以形成等价组，但不得以去重为理由丢失 Evidence。

## 7. D-F 阶段：关键词与词表候选

### 7.1 类型化关键词

关键词 subagent 只读取最终有效知识。每条知识抽取零到多个关键词；若没有可抽关键词，必须输出明确原因。类型包括：

- `entity`
- `concept`
- `action`
- `event`
- `property`
- `relation`
- `time`
- `quantity`
- `condition`
- `modality`

每个关键词保留中文 `surface`、规范化中文 `normalized_zh`、语境限定的英文 `query_lemma`、`keyword_type`、在知识中的 `semantic_role`、来源位置和翻译置信度。

### 7.2 实际词表查询

程序使用版本固定的 schema.org 和 WordNet 数据查询候选：

- schema.org 用于类型、属性、Action、Event 等结构项；
- WordNet 用于名词、动词、形容词和副词词义；
- 人名、订单号、日期、价格等具体值保留为本地关键词，只对其类型做映射；
- 每个词表最多保留 5 个实际存在的候选；
- 每次运行记录词表版本、文件摘要、命中率和未命中率。

程序查询完成后，将真实候选交给新的 subagent 排序。该 subagent 只能在候选白名单中选择或拒绝，不能创建 schema.org URI 或 WordNet synset。它输出 `exact`、`narrow`、`broad`、`related` 映射类型、匹配分数和简短依据。

`selected_candidate` 在本实验中保持 `null`，不自动宣布唯一 canonical term。

## 8. Prompt 与 subagent 编排

主线程为四类模型任务分别维护版本化 prompt：

1. `turn_knowledge_extraction`：逐轮上下文补全和知识抽取；
2. `dialogue_reconciliation`：整段复核、追加操作和多轮知识；
3. `knowledge_keyword_extraction`：类型化中文关键词与英文 query lemma；
4. `vocabulary_candidate_ranking`：对真实词表候选排序和标注映射关系。

每个 prompt 包含：任务边界、输入范围、JSON 契约、字段枚举、完整性清单、证据规则、禁止事项和少量不来自 `KE-test` 的合成示例。运行记录保存 prompt 版本、内容摘要、subagent 标识、输入分片、输出文件和时间。

禁止事项统一包括：

- 跨候选复用实体；
- 把 Agent 建议或完成声称当成已发生事实；
- 把工具调用本身当成成功结果；
- 强制补全无法确定的指代；
- 使用外部常识生成现实事实；
- 虚构词表 ID；
- 读取旧 KEOL、旧 KE 或其人工可读视图来影响本轮语义结果。

## 9. 输出布局

```text
knowledge-extraction/
  prompts/
  turn-pass/
  dialogue-pass/
  final-knowledge.json
  keyword-pass.json
  vocabulary-alignment.json
  run.json

Knowledge.txt
knowledge-extraction-report.md
```

- `turn-pass/` 是不可变第一遍结果；
- `dialogue-pass/` 保存复核操作和新增知识；
- `final-knowledge.json` 是确定性计算视图，不是新的模型输出；
- `Knowledge.txt` 按对话和轮次显示原文、有效知识、推断类型、证据及校正链；
- 旧 KEOL 目录和根视图保留，但明确标记为暂停采用的比较项。

## 10. 验证与验收

确定性校验至少覆盖：

1. 10 个候选、43 个轮次完整且唯一覆盖；
2. 原始 User/Agent 文本逐字保全；
3. Evidence 引文、字符位置和消息来源完全匹配；
4. knowledge ID、replacement、target 和 conflict 引用闭合；
5. 不存在跨候选引用；
6. 每条知识都有来源状态、派生类型、模态、极性和置信度；
7. `context_completed`/`inferred` 均有推断依据；
8. A 阶段结果在 B 阶段后仍逐字、逐条保留；
9. 最终有效视图能够完全由账本重算；
10. 每条最终知识有关键词或明确的无关键词原因；
11. schema.org URI 和 WordNet synset 均在固定版本词表中存在；
12. 候选排序结果不能出现检索白名单之外的 ID。

实验报告统计：逐轮知识数、多轮新增数、确认/纠正/取代/冲突数、按 `source_status`/`derivation`/`modality` 的分布、未解决指代数、Evidence 校验失败数、关键词覆盖率、各词表命中率和候选分布。

人工审核重点是知识完整性、事实正确性、来源归因、推断是否越界、校正是否合理，以及关键词和候选词义是否符合语境。当前输出是 gold-set 候选，不自动成为人工确认的 gold。

## 11. 非目标

本轮不做以下工作：

- 不把知识转换为 KE 或重新设计 KE 语言；
- 不建立完整产品本体；
- 不做 embedding、检索或融合实验；
- 不自动选定唯一 canonical term；
- 不删除或覆盖旧 KEOL 实验产物；
- 不把本轮模型抽取直接视为人工 gold。
