# Knowledge Extraction Artifacts

本目录同时保存当前正式投影和生成它所需的审计账本。不要仅按版本号选择文件。

## 当前使用

- `final-knowledge.json`：两阶段账本确定性投影出的 390 条 active knowledge。
- `keyword-pass-v3/`：当前关键词抽取批次；`keyword-pass.json` 是正式聚合结果。
- `KE-knowledge-keywords.json`：43 个 turn 的三字段展示，只含 `原始文本`、`知识`、`关键词`。
- `keyword-v3-preview-lawyer-leave.json`：律师请假候选的同结构预览。
- `knowledge-extraction-prompt-and-strategy.md`：不可由摘要替代的方法与边界。
- `run.json`、`source-segments.json`：运行、来源片段和重放校验信息。

## 审计账本

- `turn-pass/`：逐轮独立抽取原始输出、校验结果和修正前归档。
- `dialogue-pass/`：完整对话复核的 confirm/correct/supersede/conflict/add 记录。
- `prompts/`：模型任务的版本化约束。
- `resources/`：固定 WordNet 资源。

## 保留的旧批次

`keyword-pass/`、`keyword-pass-v2/` 和 `keyword-pass-v2.1/` 是历史比较与审计记录，不是当前展示结果。本轮结构化整理保留这些目录，不删除、不合并、不重写。

