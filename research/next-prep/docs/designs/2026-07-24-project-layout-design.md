# KE-memory 项目目录整理设计

状态：用户已选择结构化整理方案，保留全部审计历史，不执行历史版本删减。

## 目标

当前根目录同时包含权威文档、输入数据、执行脚本、KEOL baseline 生成物和已作废的自定义 KE v0.2 文件。整理后的目录应让新参与者能够快速判断：什么是事实源、什么是当前代码、什么是可重建产物、什么只是历史比较项。

本次只改变文件位置和导航，不改变知识抽取、KEOL baseline 或关键词 v3 的数据语义。

## 目录职责

```text
KE-memory/
  AGENTS.md                         # 持续维护的工作区事实源
  README.md                         # 项目入口与常用命令
  安排.md                           # 执行波次和当前状态
  data/gold-candidates/             # KE-test 候选原文和来源配置
  knowledge_pipeline/              # 当前知识优先抽取实现
  knowledge-extraction/            # 当前结果、模型原始输出与审计历史
  tools/keol_baseline/             # KEOL baseline 适配、运行和导出工具
  artifacts/keol-baseline/         # KEOL baseline 输入、中间结果、原生产物和视图
  archive/legacy-ke-v0.2/          # 已作废的自定义 KE v0.2 实验
  docs/designs/                    # 已确认设计
  docs/plans/                      # 可执行计划
  docs/reference/                  # 方案 PDF 等参考资料
  tests/                           # 自动化测试
```

## 保留边界

- `knowledge-extraction/` 内的 `turn-pass`、`dialogue-pass`、关键词 v1/v2/v2.1/v3 和 archive 保持原位。本轮不删除、压缩或重写审计记录。
- `knowledge-extraction/KE-knowledge-keywords.json`、`keyword-v3-preview-lawyer-leave.json`、`keyword-pass-v3/keyword-pass.json`、`run.json` 和抽取策略文档继续作为当前正式结果。
- KEOL baseline 仍是比较项。根视图移动到 `artifacts/keol-baseline/views/` 后，完整事实源仍是 `artifacts/keol-baseline/native-output/KE-test/onto/assertions.json`。
- 自定义 `ke-runtime.mjs`、`ke-specs.mjs` 及其构建/校验脚本已经作废，只归档，不删除。
- 空 `.git` 目录不转换为仓库，也不以其提供回滚保证。

## 路径兼容策略

- Python 默认输入改为 `data/gold-candidates/KE-test.json`。
- KEOL 工具统一通过 `python -m tools.keol_baseline.<module>` 运行，模块内部使用项目根目录解析默认路径。
- 测试、设计文档、计划、`AGENTS.md` 和 `安排.md` 同步更新，不保留会继续制造根目录混乱的旧路径副本。
- 新增项目布局测试，防止旧 v0.2 文件、KEOL 生成视图或候选数据重新散落到根目录。

## 验收

1. 根目录只保留入口文档和一级职责目录，不再混放脚本、JSON 产物或 PDF。
2. `artifacts/project-structure/2026-07-24-move-manifest.json` 记录全部迁移后路径、大小和 SHA-256；由于 Windows PowerShell 不支持初始脚本使用的 `Path.GetRelativePath`，迁移前哈希未成功持久化，此限制必须保留在清单中。
3. 完整 Python 测试通过。
4. `knowledge_pipeline` 的 CLI 默认路径指向新数据位置。
5. 文档和源码扫描不再包含作为当前路径使用的旧根目录引用；历史说明中的旧路径必须明确标为历史。
