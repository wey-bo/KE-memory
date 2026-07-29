# 知识抽取 Prompt 与策略

本文记录 `KE-test.json` 现有知识抽取结果所采用的实际 Prompt、分阶段策略和验证边界。目标是让后续实验能够复用当前质量较好的知识层，而不依赖某次对话中的隐含说明。

## 1. 当前产物与版本

- 原始对话：`KE-test.json`
- 工具结果显式边界：`knowledge-extraction/source-segments.json`
- 逐轮抽取 Prompt：`knowledge-extraction/prompts/turn_knowledge_extraction.md`
  - 版本：`knowledge-extraction-turn-v1`
  - SHA-256：`08e83f6151841331c3f0e04efb50c3c53d9c16346a819889230306e32c614aef`
- 整段对话校正 Prompt：`knowledge-extraction/prompts/dialogue_reconciliation.md`
  - 版本：`dialogue-reconciliation-v1`
  - SHA-256：`92e7e24bdcc5476ee32611e078dffee45ad33a5afc2034995bd6ce451264026b`
- 确定性投影结果：`knowledge-extraction/final-knowledge.json`
  - active knowledge：390 条
  - SHA-256：`641c88117c206e9901c332e93c4c77e91dc5df703667f441291679dec8c03f41`

知识抽取由 subagent 完成；主流程负责准备隔离输入、约束 JSON Schema、绑定 evidence、验证引用、执行确定性投影和保存哈希。主流程不替代 subagent 做语义抽取。

## 2. 两阶段抽取策略

### 2.1 第一阶段：逐轮独立抽取

一轮定义为一次 user 输入和对应的一次 agent 输出。每轮独立处理，不读取前后轮，也不读取旧抽取结果。

这样设计的目的：

1. 保留原始轮次作为最小事务和证据单元。
2. 防止后文信息反向污染当时的陈述。
3. 分开记录 user 陈述、agent 生成内容和工具实际观察。
4. 让每条知识都能回指精确的消息、原文片段和出现次数。

第一阶段允许补全的隐藏信息非常有限，只包括当前轮内有充分依据的：

- 指代消解；
- 省略补全；
- 角色解析；
- 当前轮支持的时间解析；
- 高置信语用含义。

无法由当前轮唯一确定的内容必须标记为 unresolved，不能猜测。

### 2.2 第二阶段：整段对话校正

一段对话的全部轮次独立抽取完成后，再把完整对话和第一阶段记录交给新的 subagent。

第一阶段记录保持不可变。整段对话只能通过五种操作表达变化：

- `confirm`：后文提供了实质确认；
- `correct`：后文明确修正原知识；
- `supersede`：新状态替代旧状态；
- `conflict`：证据支持冲突，但不能判定哪条覆盖哪条；
- `add`：只有跨轮组合后才成立的新知识。

不能为了得到“干净结果”而直接修改第一阶段记录。最终 active knowledge 由程序根据操作确定性投影得到，因此原始抽取、修正过程和最终状态都可追踪。

## 3. 知识完整性策略

### 3.1 先恢复知识，再结构化

模型先理解原文表达的完整知识，包括说话者、局部上下文、指代对象、条件、时间、语气和否定，再输出结构化知识。不能只抓名词或把句子压缩成丢信息的标签。

每条知识至少包含：

- `statement`：完整且可独立理解的知识表述；
- `subject`、`predicate`、`object`；
- `qualifiers.modality`；
- `qualifiers.polarity`；
- `qualifiers.temporal`；
- `qualifiers.conditions`；
- `qualifiers.scope`；
- evidence 与来源状态；
- confidence 与 derivation。

独立事实应拆开，但拆分后不能丢失原句中的条件、时间、范围、否定和认识论状态。

### 3.2 user、agent 与工具结果分开

- `user_reported`：来自 user 原文的陈述、需求、偏好、计划、问题或观察。
- `agent_generated`：agent 提出的建议、解释、推断、计划或未经工具证明的完成声明。
- `tool_observed`：只有 evidence 完全位于显式工具结果 span 内，并且结果文本本身证明该事实时才能使用。

agent 说“已经完成”不自动等于现实完成；工具调用本身也不是成功证据。

### 3.3 Evidence 优先

每条 evidence 必须是消息中的精确 substring，并记录：

- `turn_index`；
- `message`：`user` 或 `agent`；
- `occurrence_index`；
- `quote`；
- 对整段校正操作还必须记录 `evidence_role`。

工具结果边界由 `source-segments.json` 显式提供。不能根据标点、下一处 marker 或消息结束位置自行推断边界。

## 4. Subagent 调用策略

### 4.1 输入隔离

每个 subagent 只收到当前任务所需内容：

- 第一阶段：单个 user-agent turn、显式工具结果 spans、JSON Schema、ID 前缀；
- 第二阶段：完整对话、不可变第一阶段记录、显式工具结果 spans、reconciliation schema、ID 前缀。

禁止输入旧 KEOL 输出、自定义 KE 输出、旧关键词结果、旧抽取结果或未提供的其他轮次。

### 4.2 输出约束

subagent 只能返回 JSON，且必须严格符合 payload 中的 JSON Schema。程序验证：

- ID 命名空间和连续性；
- evidence 原文与 occurrence；
- user/agent/tool evidence role；
- 引用闭合；
- 操作 target/replacement 合法性；
- supersede 无链和无环；
- 新知识恰好被一个操作引用；
- raw 文件在验证期间哈希不变。

### 4.3 复审和校正

语义抽取与语义复审使用不同 subagent。reviewer 只报告具体问题；修正者依据 `knowledge_id`、evidence 和原文定点修正。程序最后重新运行完整校验，而不是仅采信 subagent 的完成报告。

## 5. 实际 Prompt A：逐轮知识抽取

以下内容与 `turn_knowledge_extraction.md` 一致。

```text
# Turn Knowledge Extraction

## Input Boundary
Process exactly one user message and its paired agent message. Do not use earlier turns, later turns, summaries, previous extraction output, old KEOL output, custom KE output, or any artifact from a prior implementation. The supplied source metadata is provenance, not additional dialogue context.

## Output Contract
Return JSON only, conforming exactly to the supplied `TurnPassOutput` JSON Schema. Emit `context_completions` first and then atomic `knowledge` items. Use the payload's exact `candidate_namespace`, `knowledge_id_prefix`, and `context_completion_id_prefix` when assigning IDs. Every evidence item must quote exact text and include the zero-based `occurrence_index` for that exact quote.

Synthetic example: with user `My desk is blue.` and agent `Noted.`, an explicit user fact may cite `My desk is blue.` at occurrence 0. This example is synthetic and is not drawn from KE-test.

## Completeness Checklist
Capture explicit user reports, requests, preferences, commitments, and observations; separately capture eligible agent-generated advice or claims. Complete only local references that this one turn supports. Leave ambiguity unresolved rather than inventing a completion. Split independent facts into atomic knowledge items.

## Evidence Rules
Use only exact substrings from the supplied user or agent message. Preserve the message side and occurrence index. The payload supplies explicit `tool_result_spans` resolved from the source-segments sidecar; each span includes the owning `marker_occurrence_index`, starts at the first non-whitespace character after that `[工具结果]`, and retains its explicit semantic end. Use `tool_observed` only when every cited Agent evidence span is wholly inside one supplied tool-result span. Use `agent_generated` only when every cited Agent span is wholly outside both supplied tool-result spans and literal tool marker spans. Do not infer a result boundary from punctuation, marker position, the next marker, or message end. A tool call is not proof of success. Do not cite paraphrases, source metadata, or any unavailable turn.

## Epistemic Rules
Facts from the user are `user_reported`. Agent advice, suggestions, plans, and unverified claims outside the supplied tool-result spans are `agent_generated`; they are not real-world facts merely because the agent said them. A tool result can be `tool_observed` only when the evidence is contained by a supplied explicit span and the result text establishes it. Text after that span returns to `agent_generated` eligibility. Keep unresolved references unresolved.

## Forbidden Behavior
Do not read, use, infer from, or reproduce old KEOL outputs, custom KE outputs, prior extraction outputs, or other turns. Do not create unsupported facts, fabricate evidence, treat a tool call as successful execution, add vocabulary IDs, or emit prose or markdown outside the JSON result.

## Final Self-Check
Verify the candidate and turn match the input; every ID has the required candidate-scoped format; every quote and occurrence index resolve exactly; every Agent evidence role agrees with the supplied `tool_result_spans`; context completions precede knowledge; each knowledge item is atomic; and the response is JSON only.
```

## 6. 实际 Prompt B：整段对话校正

以下内容与 `dialogue_reconciliation.md` 一致。

```text
# Dialogue Reconciliation

## Input Boundary
Reconcile only the complete supplied conversation and its supplied immutable A-stage records. The first pass is immutable: never rewrite an A-stage record or its evidence. Do not read or use old KEOL outputs, custom KE outputs, prior implementation output, old dialogue outputs, or unsupplied turns.

## Output Contract
Return JSON only, conforming exactly to the supplied reconciliation schema. Treat A-stage records as immutable; express changes only as `confirm`, `correct`, `supersede`, `conflict`, or `add` operations. Use the exact `D_<candidate_namespace>_<index:03d>` prefix supplied by the payload for `new_knowledge` IDs and the exact `R_<candidate_namespace>_<index:03d>` prefix for operation IDs. Start each index at 001 and keep it contiguous. `replacement` is an ID reference, never an embedded knowledge object. A `correct` or `add` replacement must reference an ID in `new_knowledge`; a `supersede` replacement may reference an active same-candidate A-stage record or new dialogue knowledge.

Synthetic example: a new message that explicitly revises `delivery Tuesday` to `delivery Wednesday` may produce a `correct` operation. This example is synthetic and is not drawn from KE-test.

## Completeness Checklist
Identify each supported correction, supersession, conflict, or genuinely cross-turn addition. Confirm only when dialogue-level evidence materially confirms an A-stage record; do not mechanically confirm every fact. Every new dialogue knowledge record must be referenced exactly once as the replacement of a `correct`, `supersede`, or `add` operation. Retain uncertainty when evidence does not decide among alternatives.

## Evidence Rules
Every operation and every new knowledge record must cite exact source quotes using the supplied `turn_index`, `message` (`user` or `agent`), `occurrence_index`, and `quote`. Each conversation turn supplies explicit `tool_result_spans` from the source-segments sidecar; each span includes its unique `marker_occurrence_index`, exact post-marker start, and explicit semantic end. Operation evidence must also include `evidence_role` as exactly `user_reported`, `agent_generated`, or `tool_observed`; this role is required on every operation evidence item. Quotes must be exact substrings of that message in that turn. Do not infer result boundaries from punctuation, marker position, the next marker, or message end. Do not invent support or use unstated historical context.

Operation evidence item example: `{"turn_index": 2, "message": "agent", "occurrence_index": 0, "quote": "preference saved", "evidence_role": "tool_observed"}`.

## Epistemic Rules
Do not mutate A-stage facts. Distinguish user reports, agent-generated content, and observed tool results. `user_reported` evidence is user-only; `agent_generated` evidence is agent-only and wholly outside the supplied tool-result spans and literal marker spans; `tool_observed` evidence is agent-only and wholly inside a supplied tool-result span. Text after a supplied tool-result span is not tool-observed merely because it follows `[工具结果]`. A tool call or marker alone does not establish completion. Operation evidence may mix roles when every cited span declares and satisfies its own role.

## Forbidden Behavior
Do not read, use, or reproduce old KEOL/custom KE outputs or old dialogue outputs. Do not silently edit A-stage records, infer unprovided turns, create unsupported or cross-candidate references, embed replacements, add single-turn restatements, or output prose outside JSON. `confirm`, `correct`, and `supersede` targets must be A-stage IDs; only `conflict` may also target D-stage IDs. Assign each A-stage target at most one of `confirm`, `correct`, or `supersede`. A conflict must not include an ID corrected or superseded in the same output. A supersede replacement must not reference itself, an ID targeted by `correct` or `supersede`, or form a replacement chain or cycle.

## Final Self-Check
Verify every change is one of the five permitted operations, A-stage is unchanged, IDs use the supplied namespace and contiguous prefixes, every target and replacement resolves within the candidate, terminal state assignments and supersede replacements satisfy the no-chain policy, every new dialogue knowledge record has exactly one replacing operation, every operation evidence item declares the correct `evidence_role`, every Agent evidence span agrees with the supplied `tool_result_spans`, all evidence is exact, and the response is JSON only.
```

## 7. 当前方法的边界

- 第一阶段故意不使用跨轮上下文，因此会保留可在第二阶段修正的局部歧义。
- 第二阶段可以新增跨轮知识，但不能重写历史证据。
- 该知识层是事实与认识论状态的抽取结果，不等同于 KEOL ontology，也不等同于最终 Knowledge Equation。
- 后续关键词、WordNet、本体和 KE 实验应引用 active knowledge 和 evidence，不应反向覆盖原始知识。
- 日期、状态和源对话矛盾必须保留，不能为了生成一致结果而擅自修正。
