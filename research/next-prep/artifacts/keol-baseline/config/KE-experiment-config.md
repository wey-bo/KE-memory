# KEOL KE-test 抽取实验配置

## 基线

- 输入对象：`data/gold-candidates/KE-test.json`
- KEOL 仓库：`C:\Users\86137\Desktop\Haitun-agent\KEOL`
- 分支：`feature/onto-drop-instance-of-assertion-+-change-description-metadata`
- 提交：`44631e64fd07c9b85f22e36035bf49c882dba592`（2026-07-21 fetch 后远端可见分支中最新 tip）
- 模型阶段：Codex subagent；未调用 LiteLLM，不把默认 `openai/gpt-4o-mini` 写成实际模型。
- v0.1/v0.2：全部作废，不再作为当前本体、抽取结果或结论。

## 流程

```text
data/gold-candidates/KE-test.json
-> 43 个 user + agent turn 文档
-> subagent 按 KEOL KnowledgeGraph 抽 nodes/edges
-> KEOL rawdata
-> KEOL OntologyBuilder
-> subagent 按 KEOL NormalizationPlan 分 5 批归一
-> KEOL Agent projection/store
-> KEOL strict validation
-> `artifacts/keol-baseline/views/` 视图
```

KEOL 没有 conversation/turn reader。直接读取整个 JSON 会把 9234 个字符硬切为普通 chunk，破坏 candidate/turn/speaker 边界；适配层只负责无损切分和坐标绑定，不负责语义抽取。

## 文件

- turn 输入：`artifacts/keol-baseline/input/manifest.json`、`input/turns/*.txt`
- 模型图：`artifacts/keol-baseline/model-extraction/batch-a.json`、`batch-b.json`、`combined.json`
- 归一：`artifacts/keol-baseline/model-normalization/payload-*.json`、`plan-*.json`
- KEOL 原生产物：`artifacts/keol-baseline/native-output/KE-test/onto/**`
- 运行摘要：`artifacts/keol-baseline/run/KEOL-run.json`
- 视图：`artifacts/keol-baseline/views/KE-ontology.json`、`KE-extraction.json`、`KE.txt`
- 适配/编排：`tools/keol_baseline/`

## 模型边界

模型只做 nodes/edges 和已有 ID 的 NormalizationPlan。程序负责 turn 覆盖、稳定 ID、edge 闭合、payload/plan 白名单、KEOL 落盘、builder、projection、store 和 validation。Normalization 不创建 ID；seeded operator 的 `source_kind` 保持 `seeded`。

## 验证

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest tests/test_keol_ke_test_adapter.py tests/test_export_keol_views.py -q -p no:cacheprovider
$env:PYTHONPATH='C:\Users\86137\Desktop\Haitun-agent\KEOL\src'
python -m pytest tests/test_reader_dispatch.py tests/test_chunking.py tests/test_onto_builder.py tests/test_onto_validator.py -q -p no:cacheprovider
python -X utf8 -m tools.keol_baseline.run_keol_pipeline
python -X utf8 -m tools.keol_baseline.run_keol_pipeline prepare-normalization
python -X utf8 -m tools.keol_baseline.run_keol_pipeline apply-normalization
python -X utf8 -m tools.keol_baseline.export_keol_views
```

当前环境没有 `uv`、`litellm` 或 LLM API Key，因此配置驱动 CLI 的模型阶段由 subagent 产生同一 Pydantic 契约，后续确定性阶段使用未修改的 KEOL 代码。
