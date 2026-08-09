# KE-memory 并行路线整合与 PR 化开发流程

日期：2026-08-09
状态：待评审

## 问题

`/public/home/wwb/KE_mem/ke-memory-demo` 有 15 个本地分支、15 个长期 worktree，194 个提交从未推送。远端 `git@github.com:wey-bo/KE-memory.git` 只有 `main` 一个分支，停在 `15da1ca`（2026-07-27）。没有任何工作经过远端，也没有任何 PR。

需要把这个状态收敛为：远端 main 是唯一事实源，PR 是唯一集成路径，开发、测试、集成都在此之上持久化。

## 已测量的事实

以下均为 2026-08-09 用 git 与实际运行测得，不是估计。

### 分支拓扑：一条主干加三个顶端

15 个分支不是 15 条独立路线。用 `merge-base` 而非提交时间测得：

`main`(15da1ca) ⊂ `codex/e2e-closure-20260730` ⊂ `codex/repository-reorganization-20260801`(06e5754)。后者比 main 多 122 个提交，是所有现代工作的共同基点。

从 06e5754 分出三个活跃顶端：

| 分支 | tip | 提交 | 文件 | 范围 |
| --- | --- | --- | --- | --- |
| `codex/ke-contract-v1-20260805` | 5519318 | 24 | 50 | `ontology/`、domain、history |
| `codex/a1-index-baseline-20260805` | 2141272 | 28 | 91 | semantic_compiler、evaluation、infra |
| `codex/personal-org-memory-service-20260803` | eba6e24 | 35 | 68 | online 服务、organization、domain、history |

a1-index 与 personal-org 在本设计撰写期间仍在推进（a1-index 从 bdeec3d 到 2141272，personal-org 从 a9c0e18 到 eba6e24），ke-contract 未动。三个 worktree 当前均无未提交改动。并行开发是活跃的，这正是需要 PR 流程的原因。实施时须以当时的 tip 重新测量，本文的提交数与冲突结论会随之变化。

### 分支间冲突

`codex/ke-contract-v1` 与 `codex/personal-org` 之间 0 冲突、0 文件重叠。

`a1-index` 与另两条各有 1 处冲突，均在 `research/next-prep/AGENTS.md`：三条线各自在文件末尾追加本波次的治理章节（A1 live proposal 合同修复状态 / Personal-Organization Memory Service Wave）。属同位置追加，保留双方即可，不是语义对立。

`tests/architecture/test_dependency_direction.py` 被 a1-index 与 personal-org 同时修改：前者往 `LAYERS` 层内追加 `semantic_compiler`，后者追加 `organization`。语义上是并集，不互相否决，`merge-tree` 不报冲突。

### 测试收集状态（按 CI 相同方式实测）

以 `KEOL_SOURCE=/public/home/wwb/KE_mem/KEOL-44631e6/src`、`uv run pytest -q --collect-only` 实测：

- `ke-contract-v1`：1315 个测试收集成功，0 错误。
- `personal-org`：1761 个测试收集成功，0 错误。
- `a1-index-baseline`：**1290 个收集成功，6 个错误**。

a1-index 的 6 个错误全是 `ModuleNotFoundError: No module named 'scripts'`，由该分支独有的 156c83b 与 39017e3 引入——测试写 `from scripts.a1_proposal_contract_diagnostic import ...`，而 `scripts/` 无 `__init__.py`，`pyproject.toml` 的 `pythonpath = ["src", "service", "ontology"]` 也不含仓库根。这是分支缺陷而非环境差异：该 worktree 有独立 `.venv`，三个 pythonpath 项均生效。三条线中只有 a1-index 有此问题。

已验证修法：`pythonpath` 增加 `"."`，6 个错误清零，收集数 1290 → 1571。

### a1-index 先前的未提交改动已落地

先前 worktree 里 882 行未提交改动（请求拓扑校验、DTO 哈希绑定、allowlist 预检、脱敏引入）已随 0209422、605a848、203f12d、2141272 提交，其中曾缺失的 `UnsupportedResponseFormatModelError` 已实现。加上 `pythonpath` 修法后全部可收集，因此这部分工作纳入 PR C，不再是排除项。

### 本机绝对路径的真实范围

20 个文件、35 处命中、7 个数据集，其中 5 处在 `src/` 生产代码里。必须区分两类，这个区分决定改造边界：

**真实读取路径**（需可配置化，3 个文件）：
- `src/ke_memory_demo/ontology_sources/registry.py:32` — `RAW_ROOT`
- `src/ke_memory_demo/mapper_v2/source_indices.py:37` — `SOURCE_DIR`
- `src/ke_memory_demo/ontology_v3/evidence.py:27-28` — `MSC_PATH`、`SGD_SCHEMA`

**溯源记录**（不得改动，12 处）：
`src/ke_memory_demo/ontology_v2/decisions.py:373-424` 的 `locator` 字段。它们与 `content_sha256`、`observed_units` 成对出现，用途是让"PropBank 被查阅过"成为关于特定字节的可核对断言。改成相对路径会破坏记录的事实性，等于伪造溯源。

**混合用途**（需拆分，`src/ke_memory_demo/ontology_v1/decisions.py:448-452`）：
`SGD_SCHEMA_PATH`、`SGD_TRAIN_DIR`、`TASKMASTER2_DIR`、`MSC_PERSONAS_PATH`、`TAU_BENCH_DIR` 这 5 个常量既被当作 `locator` 写入记录（482、494、505、516、528 行），又被 `Path()` 包装后实际读取（474 行 `Path(SGD_SCHEMA_PATH)`、523 行 `_digest_of_file(Path(MSC_PERSONAS_PATH))`）。因此不能整体改也不能整体保留：读取处改为从 `KE_DATASETS_ROOT` 推导，记录处保留原字面值。

`config/experiment.toml:2` 的 `archive_path` 已经是配置项，`SourcePin.path(root: Path = RAW_ROOT)` 本就带 root 参数——改造成本低于表面。

### CI 现状

`.github/workflows/ci.yml` 在 main 上有重复的 `actions/checkout@v4`（第 15-16 行）。三条现代分支共享一份更新版本（blob `07e6fa8`），多一个 `conformance` job，需要 `uv sync --frozen --group evaluation`。

`scripts/ci/check.sh` 要求 `KEOL_SOURCE` 指向 pinned KEOL src。CI 从 `genuineknowledge/KEOL@44631e6` clone，该仓库可达。

`gh` CLI 未安装。

### 废弃判定（相对三个新顶端重测）

| 分支 | 依据 |
| --- | --- |
| `feature/ke-memory-demo-implementation` | main 的祖先 |
| `codex-sync/ontology-agent-memory-ab` | main 的祖先 |
| `codex/e2e-closure-20260730` | reorg 的祖先，工作随阶段 1 进 main |
| `mapper-v4-semantic-contract` / `repair` / `repository-test` / `scoring-contract` / `evaluation-audit` | 5 个分支同指 d066ccf，已含于 a1-index |
| `mapper-v4-semantic-compiler-test-20260803` | 独有提交为 0 |
| `memory-semantic-ir-ablation-20260804` | 独有提交为 0 |
| `mapper-v4-contract-audit-20260804` | 见下，其 `new_roles` 意图已被 a1-index 自行实现 |
| `next-prep-normalization-20260729` | 2 个独有提交的意图已被 a1-index 用更严格实现取代（`O_NOFOLLOW` + fd 身份校验，对比 `l1_admission.py` blob e1916e3 vs b60d8983） |

共 11 个分支废弃。

**保留但不纳入本轮**：`codex/query-compiler-v2-task7-20260730`，1 个独有提交、766 行全新代码（`research/next-prep` 下的 `query_runtime.py` 与 `query_compiler_v2_openai_producer.py`），与三条现代线零重叠。

### cherry-pick 判定已翻转

`codex/mapper-v4-contract-audit-20260804` 的 00ca079（`fix(semantic-compiler): index ontology v3 roles`）原本需要 cherry-pick。复测后不再需要：a1-index 的新提交已自行实现 `new_roles` 索引（`ontology_index.py:98-102`），且 cherry-pick 现在会产生冲突（`ontology_index.py` 已是第三个版本 blob 3ece5c5）。该分支转为可废弃。

但 00ca079 的另一半意图**仍未被吸收**：`_slot_kinds()` 遇到未知 `item_type` 仍 `return frozenset()` 静默返回空集，而非报 `OntologyIndexError`。这是一处独立的加固点，作为 PR C 的一项小改动纳入，不通过 cherry-pick。

## 三条不变量

1. **零工作丢失。** 废弃依据必须是可复算的 git 事实，不是"看起来旧"。废弃前先推 `archive/*` 到远端。
2. **CI 必须可信。** 远端只跑在任意 runner 上都成立的检查；依赖 728 MB 数据集与真实模型调用的重测留在本机，作为 PR 证据附上。"远端 CI 绿"与"实验结论已验证"是两个独立的门，PR 描述里分别声明。一个永远红的 CI 等于没有门禁。
3. **AGENTS.md 的治理不被绕过。** 它要求 crosswalk 需第三方评审、不得把未验证结论写成已验证。PR 模板把这条固化成勾选项，不靠记性。

## 方案

### 阶段 0：PR 门禁的前提

在任何 PR 之前完成，否则第一个 PR 的 CI 就是红的。

**0a 归档废弃分支。** 11 个分支推到远端 `archive/<原名>` 后删除本地分支与 worktree。`next-prep-normalization`（9 个未提交文件）、`memory-semantic-ir-ablation`（7 个）的未提交改动只在归档中保留已提交内容——这两个分支的 worktree 就地保留不删，未提交改动原样留在磁盘上，待后续单独判定。`query-compiler-v2`（6 个未提交文件）不在废弃列表，worktree 与分支都保留。

**0b 数据集根可配置化。** 引入单一 `KE_DATASETS_ROOT`，默认 `/public/home/wwb/datasets`，现有行为零变化。改造 3 个真实读取点。`ontology_v2/decisions.py` 的 12 处 locator 原样不动。`ontology_v1/decisions.py` 的 5 个常量先读用法再逐个判定。

依赖数据集的测试加 skip 守卫：路径从配置读取，文件缺失则 skip。**不放宽任何断言**——size 与 SHA-256 校验全部保留，只是在数据集缺席时不执行。`tests/unit/test_settings.py:116` 例外：它断言的是配置文件被正确解析、不需要数据集存在，硬编码值保留不改。

`tests/unit/ingestion/test_beam_loader.py` 已经用 `tmp_path` + 合成 zip 覆盖畸形归档、缺失成员、非法 JSON、非法 chat/topic 等场景，不依赖真实数据集。因此"BEAM 加载逻辑被改坏"这类回归在任何 runner 上都能被发现，无需补充新测试。

**0c 修 CI 配置。** 删掉 main 上重复的 checkout 步骤，采用三条现代分支共有的版本。新增 `scripts/ci/check-portable.sh` 供远端调用：lint、pyright strict、可移植测试、wheel 构建与校验。本机保留 `check.sh` 跑全量。

### 阶段 1：主干提升

`codex/repository-reorganization-20260801` 的 122 个提交快进推成 main。不走 PR：快进零冲突，且 122 个提交无法实际评审。推送前在本机跑完整 `check.sh`。

保留全部提交历史，不 squash——这些提交信息记录了大量冻结与验证决策。

### 阶段 2-4：三个 PR，顺序固定

| 顺序 | PR | 分支 | 提交 | 附带工作 |
| --- | --- | --- | --- | --- |
| 1 | A | `ke-contract-v1-20260805` | 24 | 无 |
| 2 | C | `a1-index-baseline-20260805` | 28 | `pythonpath` 加 `"."`；`_slot_kinds` 未知 item_type 改为报错 |
| 3 | B | `personal-org-memory-service-20260803` | 35 | rebase 处理 AGENTS.md 与架构测试的并集 |

顺序理由：ke-contract 已验证零错误，先落地建立流程基线。a1-index 排第二而非最后，因为它带一个必须修的 CI 缺陷（6 个测试收集失败），越早暴露越好。personal-org 最后，因为它最大且需处理与 a1-index 在 `AGENTS.md`、架构测试上的重叠。

PR B 与 PR C 中后合并者需 rebase：`research/next-prep/AGENTS.md` 末尾保留双方波次章节，`test_dependency_direction.py` 的 `LAYERS` 保留两个新增模块名。

每个 PR 合并后删除分支与 worktree。

### 阶段 5：流程固化

分支保护：main 要求 PR、要求远端 CI 通过、要求你本人批准。

PR 模板三部分：远端 CI 状态；本机全量验证结果（`check.sh` 输出摘要 + BEAM/conformance 重测）；AGENTS.md 合规勾选（是否引入未经第三方评审的 crosswalk、是否有未验证结论被写成已验证）。

`research/next-prep/AGENTS.md` 增补一节，声明远端 main 为事实源、PR 为唯一集成路径、worktree 生命周期以 PR 合并为终点。该文件在 main 上不存在，随阶段 1 一并进入。

后续开发模式：短周期分支 + worktree，一个任务一个分支一个 PR，合并后即删。保留 worktree 的并行能力，但不再长期堆积——15 个长期 worktree 正是当前困境的成因。

若需 Agent 自动开 PR，需安装 `gh` 并配 token。这是可选项，不装也能走完整流程（PR 在浏览器开）。

## 验证方式

阶段 0：三条现代分支上 `pytest --collect-only` 均 0 错误；在 `KE_DATASETS_ROOT` 指向空目录时，全套测试通过（数据集相关项 skip 而非 fail）。

阶段 1：推送前本机 `check.sh` 全绿；推送后远端 main 的 CI 绿。

阶段 2-4：每个 PR 远端 CI 绿 + 本机 `check.sh` 全绿，两者在 PR 描述中分别声明。合并后 main 的 CI 仍绿。

## 明确不做

- 不改 `ontology_v2/decisions.py` 的溯源 locator。
- 不把 728 MB BEAM 或其他数据集上传到 GitHub。
- 不纳入 `query-compiler-v2-task7` 的 766 行。
- 不 squash 主干的 122 个提交。
- 不放宽任何现有测试断言。

## 追加：2026-08-09 PR A 撤下

本节为事后追加，不改写上文。

`memory-assertion/v1` 规范包（原 `/public/home/wwb/Memory core`）已确定为唯一活动语义合同，并于同日并入本仓 `spec/memory-assertion-v1/`。它与 `codex/ke-contract-v1-20260805` 所实现的 `ke_contract_v1` 在四处直接冲突：算子实参（`bindings`+`role_id` 对位置化 `arguments[]`）、`CoreRole`（profile schema 将 `core_roles`/`core_role_id` 列为 `ForbiddenLegacySupplyKey`）、`OperatorApplication` 递归嵌套（新合同禁止，须走 `assertion_ref`）、`AssertionScope{polarity, modality, temporal}`（三者均为禁止键）。

因此**阶段 2 的 PR A 撤下**：合并一套已被取代的合同会让仓库同时存在两套活动语义。上文"顺序理由"中以 PR A 建立流程基线的论证随之失效。

受影响与不受影响的部分：

- PR C（`a1-index-baseline`）与 PR B（`personal-org`）的内容、顺序与冲突结论**不变**——两者都不碰 `ontology/`，与本次并入零文件重叠。原文测得的 PR A↔PR B「0 冲突、0 文件重叠」仍然成立，只是不再需要。
- **阶段 1 的范围扩大一项。** 主干 `06e5754` 的 `check.sh` 是红的：pyright strict 49 个错误，二分定位到 `d29d01b`（见并入设计的「主干的 pyright 回归」一节）。修复在 `fix/evaluation-split-types-20260809`（`9769a01`，直接坐在 `06e5754` 上），已独立通过完整 `check.sh`，与三个活跃顶端零冲突。它随阶段 1 一同推送，因此远端 main 从第一天起门禁可信——否则第一次远端 CI 就是红的，后续每个 PR 都无法判断自己是否引入了新问题。
- 规范并入分支 `codex/memory-assertion-v1-spec-intake-20260809` 现为 PR 序列的第一项，排在 PR C 之前。它建立在上述修复分支之上，因此**依赖阶段 1 先完成**：阶段 1 未推送前，它的基底还不在远端 main 上。
- PR C（`a1-index-baseline`）随后，它带的 `pythonpath` 缺陷（6 个测试收集失败）仍是必须修的一项。
- PR B（`personal-org`）最后，顺序理由不变。
- `codex/ke-contract-v1-20260805` 分支与 worktree **保留，不删除、不归档**。其 132 个聚焦测试与 Pyright strict 零错误是重写新合同实现时的对照物。这是「零工作丢失」不变量的应用，不是例外。
- 阶段 0c 关于 `ci.yml` 第 15-16 行「重复 `actions/checkout@v4`」的判定**不成立**：第 15 行 checkout 本仓，第 16-20 行 checkout `genuineknowledge/KEOL` 到 `.deps/KEOL`，用途不同。两步都必需，不删。

并入的完整设计见 `docs/superpowers/specs/2026-08-09-memory-assertion-v1-spec-intake-design.md`。
