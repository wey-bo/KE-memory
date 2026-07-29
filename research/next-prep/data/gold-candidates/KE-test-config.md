# KE-test 候选配置与来源说明

## 文件边界

KE-test.json 是供人工筛选的最小展示文件。每条候选只保留 id、source 和 turns；每个 turns 元素严格包含一个 user 和一个 agent，按真实对话顺序交错排列。工具调用和工具结果保留在对应的 agent 内容中。

来源坐标、许可证、采样规则、翻译规则和复核命令集中在本文件。后续人工筛选后，再在独立标注文件中补充 status、期望 KE、本体和查询。

## 质量目标

当前候选片段必须满足：

1. 至少三轮用户输入与 Agent 响应；
2. 长度不强制统一，当前集合覆盖 3、4、5、6 轮；
3. 用户请求、约束、澄清、选择、确认、纠错或失败回退之间有可读的因果推进；
4. 不把两个 Agent 的互相解释、单纯内容生成或无上下文建议当作正常 Agent 使用；
5. 原始数据中的日期、价格、状态和逻辑矛盾不自动修正；
6. 中文只作为展示层，原始英文和结构化工具事件仍以来源数据为准。

WildChat、Taskmaster 和 τ-bench 均按用户消息切分：每个 user 及其后、下一 user 之前的全部 Agent 消息合并为一个 turns 元素。WildChat 只保留 toxic=false、redacted=false 且人工检查无明显个人信息的记录；不把国家、州、IP 哈希、请求头等元数据写入候选。τ-bench 中间的工具调用和工具结果全部放入对应的 agent，不伪装成自然语言。

## 来源评估

### WildChat-1M：管理/学习主来源

- 数据集：https://huggingface.co/datasets/allenai/WildChat-1M
- 当前镜像：https://hf-mirror.com/datasets/allenai/WildChat-1M
- 当前分片：train-00008-of-00014.parquet
- 许可证：ODC-By（Open Data Commons Attribution License）。
- 数据卡说明：约 1M 条人类用户与 ChatGPT 的交互，已去标识；当前版本移除了已识别的 PII/敏感内容并过滤有毒对话。
- 限制：这是开放式 ChatGPT 日志，不保证 Agent 使用工具或事实正确；部分用户会连续切换任务。本轮只保留同一主题具有明显追问、修订或纠错的片段，并将 Agent 内容默认视为 generated_unverified，不直接当作现实事实。

### Taskmaster-2：保留自然任务对话

- 数据集：https://huggingface.co/datasets/DeepPavlov/TaskMaster2
- 本轮只保留一条航班候选 TASKMASTER2-CAND-001，用于保留日期、价格、替代方案和最终发送信息的任务推进；其余 Taskmaster 客服化候选已移除。

### τ-bench：保留工具状态轨迹

- 项目：https://github.com/sierra-research/tau-bench
- 本轮只保留 TAU-BENCH-CAND-001，因为它包含确认、退货、取消、工具执行和后续任务推进；其他重复的零售订单候选已移除。
- 限制：用户由模拟器生成，工具轨迹适合状态/Action 验证，不等同于真人语言真实感。

### BEAM：保留冲突对照

- 数据集：https://huggingface.co/datasets/Mohammadta/BEAM
- 本轮保留 BEAM-CAND-004 的 5 轮片段，用于保留此前指定的日期矛盾，并观察长上下文中的时间、家庭会议、法律有效性和监护关联。

### 已移除的来源候选

- TASKMASTER1-CAND-001、TASKMASTER1-CAND-002：客服式预约/订餐；
- TASKMASTER2-CAND-002、TASKMASTER2-CAND-003、TASKMASTER2-CAND-004：航班/酒店客服槽位重复或客服化；
- TAU-BENCH-CAND-002、TAU-BENCH-CAND-003：订单/地址/商品修改与保留的 TAU-BENCH-CAND-001 重复。

## 候选坐标表

| ID | 来源和窗口 | 轮数 | 类型 |
| --- | --- | ---: | --- |
| WILDCHAT-MGMT-CAND-001 | WildChat hash f307c772ed4efbb74c3848c4b5debba6，用户 1..5 | 5 | 工作安排/沟通管理 |
| WILDCHAT-LEARN-CAND-001 | WildChat hash 24456e5381c0c4891d80737fa4639f1d，用户 1..6 | 6 | Android 调试学习 |
| WILDCHAT-MGMT-CAND-002 | WildChat hash 4b457fcbf5d2231cf9cc4a762097fb51，用户 1..3 | 3 | 内容运营管理 |
| WILDCHAT-LEARN-CAND-002 | WildChat hash e0aeabf3573990b3b4fe5fd6dc87af3f，用户 1..4 | 4 | Praat/PSOLA 技术学习 |
| WILDCHAT-MGMT-CAND-003 | WildChat hash 385239bfd15ddb106fca3768d3f845c3，用户 1..3 | 3 | 绩效目标与管理 |
| WILDCHAT-LEARN-CAND-003 | WildChat hash 8de48fb173aa6af13b8316f180782b33，用户 1..3 | 3 | Python/Pandas 学习 |
| WILDCHAT-LEARN-CAND-004 | WildChat hash 3ca76da0eae68a26604ef25b4bb54bef，用户 1..3 | 3 | 学习科学讨论 |
| TASKMASTER2-CAND-001 | Taskmaster-2 flights，dlg-0486d642-4627-489a-a0f3-14d1c2b97068，用户 1..6 | 6 | 任务规划/方案选择 |
| TAU-BENCH-CAND-001 | τ-bench record 30，用户 6..10 | 5 | 工具确认/订单状态 |
| BEAM-CAND-004 | BEAM 100K，conversation 19，session 1，消息 0..9 | 5 | 日期矛盾/长上下文 |

## 翻译和保全规则

- 翻译策略为 faithful_zh：保留数字、日期、货币、产品名、地名、人名、技术名词、犹豫、重复和纠正；不为“像人话”而改写源事实。
- WildChat 的用户和 Agent 内容只做中文展示翻译；不补写不存在的工具调用，不把 Agent 建议升级为现实事实。
- 原始数据中连续的 Agent 回复可以在同一轮合并，但不改变事实。
- 对源数据本身的错误只做说明，不在展示文本中静默修复。例如 BEAM 日期矛盾必须保留。
- 本轮候选仍是待人工筛选状态，不包含期望 KE、本体或查询答案。

## 复核命令

验证内容包括：JSON 可解析、候选数为 10、每条 turns 至少 3 个元素、每个元素的键严格为 user/agent、WildChat 候选均来自指定分片且 toxic=false/redacted=false、source 坐标不重复、没有已移除的候选 ID。Taskmaster、τ-bench 和 BEAM 坐标可从原始文件重读；WildChat 以 conversation_hash 和用户序号复核。
