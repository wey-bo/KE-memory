# KEOL KE-test 抽取执行清单

- [x] fetch KEOL 远端并确认最新可见分支 tip 为 `44631e6`。
- [x] 阅读最新 KEOL reader、graph extractor、builder、normalizer、store 和 validator。
- [x] 证明直接读取整个 `data/gold-candidates/KE-test.json` 会破坏 turn 边界。
- [x] 用 TDD 实现 43-turn 无损输入适配与 JSON Pointer。
- [x] 派出两个 subagent 生成 43 个 KEOL KnowledgeGraph。
- [x] 校验 405 nodes、371 edges、unit 覆盖和引用闭合。
- [x] 用未修改的 KEOL builder 生成 baseline ontology。
- [x] 生成 5 个 KEOL NormalizationPlan payload。
- [x] 派出三个 subagent 完成 164 Concept/161 Operator 归一。
- [x] 保留 seeded operator provenance 并增加回归测试。
- [x] 用 KEOL store/agent projection 重写原生产物。
- [x] KEOL strict validation 达到 0 error / 0 warning。
- [x] 生成 `artifacts/keol-baseline/views/KE-ontology.json`、`KE-extraction.json` 和 `KE.txt`。
- [ ] 人工逐条筛查 Assertion、operator 粒度、方向、嵌套需求和认识论状态。
