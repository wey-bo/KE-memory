# memory-assertion/v1 规范包并入与持久化

日期：2026-08-09
状态：待评审

## 问题

`/public/home/wwb/Memory core` 有一套完整的 `memory-assertion/v1` 规范包：35 个文件，含 3 个 Draft-07 Schema、5 份语义标准、可执行 conformance fixture 和 2932 行离线验证工具。它的验证器通过，但**它不是 git 仓库**——没有历史、没有 CI、没有集成路径。这批工作目前只存在于一台机器的一个目录里。

同时 `/public/home/wwb/KE_mem/ke-memory-demo` 已实现一套**不同且相互矛盾**的语义合同（`ontology/ke_memory_ontology/ke_contract_v1/` 与 `foundation_v1/`，在分支 `codex/ke-contract-v1-20260805` 上）。两套合同不能同时是活动合同。

本设计解决两件事：把规范包持久化进仓库并接入 CI；确定它与已实现合同的取代关系。

## 已测量的事实

以下均为 2026-08-09 实测。

### 规范包验证器通过

`python tools/validate_specifications.py` 在 Memory core 中输出：

```text
OK schemas=3 json_files=15 examples=42/42 leaf_terms=11 diagnostics=26 equations=4
profile_vectors=27 snapshot_vectors=8 jcs=2 jcs_errors=1 canonical_leaf=14
canonical_equations=4 canonical_errors=26 fixture_artifacts=3 references=4+2
markdown_links=10 required_files=23
```

（实际为单行输出，此处折行便于阅读。）这是本次并入的验收基线：搬迁后逐项相同。

### 验证器的路径依赖决定了搬迁方式

`tools/validate_specifications.py:40` 是 `ROOT = Path(__file__).resolve().parents[1]`，`tools/validate_specifications.py:53` 的 `MIGRATION_REQUIRED_FILES` 有 23 条全部相对该 `ROOT` 的路径。因此整棵树必须作为**一个子目录整体搬迁且内部布局逐字节不变**；只要满足这点，`ROOT` 自动指向新位置，验证器与其回归测试零改动。

拆散布局（规范进 `docs/specifications/`、fixture 进 `fixtures/`、工具进 `scripts/`）会同时打断 `ROOT` 与 23 条路径，迫使修改验证器和它自己的回归测试——即那两个"唯一能证明这套包完整"的文件。因此不采用。

### 两套合同的四处直接冲突

| 维度 | `ke_contract_v1`（已实现） | `memory-assertion/v1`（规范包） |
| --- | --- | --- |
| 算子实参 | `bindings: tuple[RoleBinding, ...]`，每项带 `role_id`（`pb34:give.01#ARG0`） | 位置化 `arguments[]`，无 role 概念 |
| CoreRole | `CoreRole` StrEnum，KE Core 自有词汇（`core:role.agent` 等） | `core_roles`、`core_role_id` 是 `ForbiddenLegacySupplyKey`，Schema 主动拒绝 |
| 嵌套 | `OperatorApplication` 递归作为 `Term` | 禁止；`arguments[]` 与 `rhs` 必须是五类 `LeafTerm`，命题组合走显式 `assertion_ref` |
| 断言作用域 | 每个 KE 带 `AssertionScope{polarity, modality, temporal}` | `polarity`、`modality`、`temporal` 三者均为禁止键，KE 标准中不存在 |

ID 体系也不同：`ke_contract_v1` 用 `pb34:`/`core:` 前缀的可读 ID，规范包用上游 hash ID（`operator_fe9dd6d99ebf`）。

冲突证据位置：`ontology/ke_memory_ontology/ke_contract_v1/terms.py:112-133`（`RoleBinding`、`OperatorApplication`）、`core.py:30`（`CoreRole`）、`equation.py:111-135`（`AssertionScope`、`KnowledgeEquation`）；对侧为 `schema/memory-assertion-ontology-profile.schema.json` 的 `ForbiddenLegacySupplyKey` 枚举与 `ke-semantic-syntax-standard.md:8-20`。

所以规范包不是"缺失的一块"，而是 `ke_contract_v1` 语义层的**替代品**。

### 规范包的 lint 与测试形态

在主仓 ruff 配置（line-length 100、py312）下，规范包有 3 处告警，量小且真实：

- `tools/validate_specifications.py:32` E402（模块级导入不在文件顶部）
- `tools/validate_specifications.py:1023` F841（`invalid` 赋值后未使用）
- `tools/test_canonical_text_reference.py:22` E402

两个测试文件是 `unittest`（非 pytest），且以 `import tools.validate_specifications` 形式导入自身包，因此运行时 cwd 必须是子树根。`tools/` 无 `__init__.py`，`unittest discover` 会报 `Start directory is not importable`，须显式列出模块名。

### 主仓测试收集基线

`pyproject.toml` 未配 `testpaths`。main 上 `uv run pytest -q --collect-only` 得 **768 个测试**（`KEOL_SOURCE=/public/home/wwb/KE_mem/KEOL-44631e6/src`）。并入后此数必须不变。

### CI 现状

`scripts/ci/check.sh` 的 ruff 显式列 `src service ontology tests scripts`，不含 `spec/`；`[tool.pyright]` 的 `include` 同理。

规范包需要 `jsonschema>=4` 与 `node`。两者都**不在**主仓的可复现环境里：

- `jsonschema` 只存在于本机 anaconda python，`uv.lock` 中没有它（`uv run python -c "import jsonschema"` 报 `ModuleNotFoundError`）。此前用裸 `python` 跑通，掩盖了这个缺口。
- `ci.yml` 无 `setup-node` 步骤。`tools/validate_specifications.py:417` 在 `shutil.which("node")` 为 `None` 时 `raise RuntimeError`，是硬失败而非跳过。

`2026-08-09-ke-memory-pr-integration-design.md` 阶段 0c 记 `ci.yml` 第 15-16 行有"重复的 `actions/checkout@v4`"。复核后该判定不成立：第 15 行 checkout 本仓，第 16-20 行 checkout `genuineknowledge/KEOL` 到 `.deps/KEOL`，用途不同，两步都必需。本轮不删任何 checkout。

## 三条不变量

1. **搬迁不改内容。** 除本文明确列出的修正外，35 个文件按原字节进入仓库。首次提交后立刻复现上述验证器基线；任何计数变化必须先解释再接受。
2. **规范不冒充实现。** 子树的成熟度用语（"合同已定义" ≠ "结构校验已实现" ≠ "评测已通过"）原样保留。并入仓库不改变任何实现声明：semantic validator、Canonical Text 生产 parser、Snapshot provisioner、NL2KE compiler 仍全部未实现。
3. **溯源记录不得改写。** `docs/references/reference-manifest.json` 的 `source_path` 与迁移设计文档正文里的 Windows 路径是历史事实记述，与 `sha256`、`bytes` 成对构成可核对断言。改成相对路径等于伪造溯源。这与 `2026-08-09-ke-memory-pr-integration-design.md` 对 `ontology_v2/decisions.py` 的 `locator` 的处理是同一原则。

## 方案

### 1. 子树搬迁

35 个文件整体进入 `spec/memory-assertion-v1/`，内部布局逐字节保持：

```text
spec/memory-assertion-v1/
  AGENTS.md
  README.md
  requirements-dev.txt
  docs/references/...
  docs/specifications/memory-assertion-v1/...
  fixtures/ontology-snapshot-example/...
  tools/validate_specifications.py
  tools/canonical_text_reference.py
  tools/jcs.mjs
  tools/test_*.py
```

`ROOT = parents[1]` 因此解析为 `spec/memory-assertion-v1/`，23 条 `MIGRATION_REQUIRED_FILES` 全部命中。

仓库内因此有两个 `AGENTS.md` 与两个 `docs/`。在 `spec/memory-assertion-v1/AGENTS.md` 顶部加一句作用域声明，避免被误读为全仓规则；仓库根的治理文件不变。

### 2. 取代关系的记录

**`codex/ke-contract-v1-20260805` 不合并。** `2026-08-09-ke-memory-pr-integration-design.md` 将它列为 PR A（第一个落地）。该判定作废：合并一套已被取代的合同会让仓库同时存在两套活动语义。

该分支与 worktree **原样保留，不删除、不归档**——132 个聚焦测试、Pyright strict 零错误是真实资产，将来按新合同重写时要逐项对照。上表四处冲突即重写的输入清单。

在集成设计文档末尾**追加**一节说明 PR A 撤下，原文不改写。PR B（personal-org）与 PR C（a1-index）的顺序与结论不受影响——两者都不碰 `ontology/`。

不给 `ke_contract_v1` 加 deprecation 警告、不改其导出、不动其测试：给一个未合并分支上的代码在 main 上加运行时标记，是标记一个 main 并不存在的东西。

### 3. CI 接入

新增 `scripts/ci/check-spec.sh`：

```bash
cd spec/memory-assertion-v1
python tools/validate_specifications.py
python -m unittest tools.test_validate_specifications tools.test_canonical_text_reference
```

cwd 必须是子树根：两个测试文件内部以 `import tools.validate_specifications` 形式导入自身包，需要 `tools` 作为可导入的命名空间包。`tools/` 没有 `__init__.py`，因此 `unittest discover` 不可用（会报 `Start directory is not importable`），必须显式列出两个模块。实测 24 个测试通过，约 125 秒。

四个接入点：

- **`scripts/ci/check.sh`** 末尾调用 `check-spec.sh`，本机全量检查覆盖规范包。
- **依赖补齐。** `jsonschema>=4,<5` 加入 `[dependency-groups] dev` 并 `uv lock`（装入 4.26.0；规范包原在 4.23.0 上验证，需确认新版本下基线不变——验证器使用已废弃的 `RefResolver`）。`ci.yml` 增加 `actions/setup-node@v4`（node 20），因为缺 node 时验证器硬失败。不删任何 `checkout` 步骤（见上）。
- **`pyproject.toml` 加 `testpaths = ["tests"]`**。仓库未配 `testpaths`，`pytest` 从根收集会捞到 `spec/.../tools/test_*.py`，而它们需要 `tools` 作为顶层包名，在主仓 `pythonpath = ["src","service","ontology"]` 下会 ImportError。限定收集范围比往 `pythonpath` 塞第四项干净：两套包体系不应互相可见。规范包测试由 `check-spec.sh` 独立驱动。
- **lint 边界。** 就地修掉 3 处 ruff 告警：F841 删除未用变量（`invalid` 仅赋值一次，从未读取或递增，不影响任何计数）；两处 E402 加 `# noqa: E402` 并注明原因——`validate_specifications.py:32` 的导入必须排在 `warnings.filterwarnings` 之后才能抑制 jsonschema 的 DeprecationWarning，`test_canonical_text_reference.py:22` 的导入依赖上一行的 `sys.path.insert`。然后把 `spec/` 纳入 `check.sh` 的 ruff 范围。**不**纳入 pyright strict：那 2932 行按独立项目写成，strict 化属于改造而非并入。

### 4. 路径修正

- `spec/memory-assertion-v1/AGENTS.md` 与 `README.md` 中的 ```powershell 块改为 bash，命令改为从仓库根出发的 `python spec/memory-assertion-v1/tools/validate_specifications.py`。
- 迁移设计文档正文的 `D:\86137\ontology.schema.json`、`C:\Users\86137\Desktop\Memory core` 与 `reference-manifest.json` 的 `source_path` **全部保留**（见不变量 3）。
- 在迁移设计文档末尾追加一节，声明其 `Memory core` 根路径现为本仓 `spec/memory-assertion-v1/`，正文路径为历史记录。

## 验证方式

每条都要有实际输出，不接受推断。

1. `python spec/memory-assertion-v1/tools/validate_specifications.py` 输出与「已测量的事实」中的基线逐项相同。
2. `python -m unittest tools.test_validate_specifications tools.test_canonical_text_reference`（cwd 为子树根）24 个测试全通过。
3. `uv run pytest -q --collect-only` 仍为 768，证明加 `testpaths` 未丢掉主仓任何测试。
4. `scripts/ci/check.sh` 全绿（需 `KEOL_SOURCE` 指向 pinned KEOL src）。
5. `git show --stat` 确认 `spec/memory-assertion-v1/` 下新增恰好 35 个文件，加上被修改的 `pyproject.toml`、`uv.lock`、`ci.yml`、`check.sh`、新增 `check-spec.sh` 与集成设计追加。本设计文档先于实施单独提交，不计入这 35 个。
6. `check-spec.sh` 在 `uv run` 下（即 CI 所用的锁定环境、jsonschema 4.26.0）复现基线，而非仅在本机 anaconda python 下通过。

交付形态：分支 `codex/memory-assertion-v1-spec-intake-20260809`，一个 PR。远端 CI 绿与本机 `check.sh` 全绿在 PR 描述中分别声明。

## 明确不做

- 不重写 `ke_contract_v1`/`foundation_v1`。
- 不删除或归档任何分支或 worktree。
- 不写 memory-assertion/v1 的运行时代码：pydantic 模型、semantic validator、Canonical Text 生产 parser、Snapshot provisioner 全部仍标未实现。
- 不改 `reference-manifest.json` 的溯源字段与迁移文档正文的历史路径。
- 不把 `spec/` 纳入 pyright strict。
- 不改写 `2026-08-09-ke-memory-pr-integration-design.md` 正文，只追加。
