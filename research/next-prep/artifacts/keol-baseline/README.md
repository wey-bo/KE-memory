# KEOL Baseline Artifacts

本目录保存 2026-07-21 基于 KEOL `44631e6` 生成的比较基线，不是人工 gold，也不是当前知识优先抽取的模型输入。

| 路径 | 内容 |
| --- | --- |
| `input/` | 43 个 user-agent turn 文档和 manifest |
| `model-extraction/` | subagent 生成并经程序校验的 graph nodes/edges |
| `model-normalization/` | 5 批 normalization payload 和 plan |
| `native-output/KE-test/onto/` | KEOL 原生 Concept、Individual、Operator、Assertion、Evidence 等事实源 |
| `views/` | `KE-ontology.json`、`KE-extraction.json` 和人工可读 `KE.txt` |
| `run/` | 运行摘要 |
| `config/`、`reports/` | 实验配置、统计、限制和下一步 |

运行入口：

```powershell
D:\Anaconda\python.exe -m tools.keol_baseline.run_keol_pipeline
D:\Anaconda\python.exe -m tools.keol_baseline.run_keol_pipeline prepare-normalization
D:\Anaconda\python.exe -m tools.keol_baseline.run_keol_pipeline apply-normalization
D:\Anaconda\python.exe -m tools.keol_baseline.export_keol_views
```

`native-output/` 中部分 Evidence 和 `_metadata.json` 的 `source_file` 仍记录生成当时的 `keol-input/...` 坐标。它们是不可变 baseline 的历史 provenance 标签，不表示文件仍位于工作区根目录；未来重新运行会写入新的 `artifacts/keol-baseline/input/...` 坐标。

