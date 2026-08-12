# 迁移评审包：4 项待裁决

日期：2026-08-09
状态：**已被 v2 取代**——本文件的 R2 与 R4 方案含语义错误，保留仅为审计。
当前有效版本：`2026-08-09-memory-assertion-v1-migration-review-packet-v2.md`
关联：`2026-08-09-ke-memory-to-memory-assertion-mapping-report.md`

## 怎么用这份文件

4 项裁决，每项给出事实、选项和我的建议。裁决完成前第二步（边界转换层）不能开始——R1 决定
`polarity=negative` 能否表达，它出现在 140 处引用中。

每项标注影响面，用实测引用数而非估计。所有事实均可复算，命令附在文末。

---

## R1：`negated` Operator 的来源归属

**影响面**：`polarity` 34 文件 / 140 引用。`polarity=negative` 是否可表达取决于此项。

**事实**：

规范要求否定用接受 `assertion_ref` 的 Operator 表达
（`2026-08-08-...-migration-design.md:305` 给出 `negated(Assertion::candidate::"x")=Boolean::true`）。
但 fixture 的 4 个 Operator 中**没有** `negated`——只有 `created_by`、`possible`、`event_time`、
`believes`。所以它必须新增。

新增 Operator 的每条 Lexicalization 必须带 `source_attestations`，`source_kind` 是封闭枚举
`wordnet | propbank | schema_org | human | domain_corpus`。

已实测 WordNet 3.0：`negate` 存在（4 个 verb sense），但 `wn30:negate.v.01` 的释义是
**"be in contradiction with"**——这是矛盾关系，不是逻辑否定。两者不同：矛盾是两条断言之间的
关系，否定是对单条断言的取反。用这个 sense 作 attestation 会把一个来源没有支持的含义
归给 WordNet。

**选项**：

- **A（建议）**：`source_kind=human`，`lemma` 为 `negated`，`provenance_refs` 指向本评审包的
  裁决记录。这如实承认它是本项目的设计决定，可审计、不伪造来源。
- **B**：`source_kind=wordnet`，`sense_id=wn30:negate.v.01`。代价是把"矛盾"当"否定"引用，
  与 AGENTS.md「不得把未验证结论写成已验证」冲突。
- **C**：不新增 `negated`，`polarity=negative` 报
  `reported_capability_gaps[].code=unsupported_construct`。代价是 140 处引用对应的否定语义
  在新合同下全部无法表达，抽取层必须省略这些 candidate。

**我建议 A**：它是唯一既满足 attestation 硬要求、又不误引来源的选项。`human` 正是为这种
情况设的枚举值。

**裁决**：______

---

## R2：`goal`、`plan`、`preference` 三个 modality 取值的去向

**影响面**：`modality` 42 文件 / 299 引用中的三个取值。

**事实**：

`Modality` 的 8 个取值不属于同一范畴。5 个已有明确去向（`fact` 无标记、`belief` →
`believes`、`hypothesis` → `possible`、`question` → `speech_act=question`、`instruction` →
`speech_act=command`）。剩下三个没有：

- 新合同 `CandidateMetadata.speech_act` 的封闭枚举是
  `assertion | question | request | command | suggestion | promise | other`；
- `preference` 与 `suggestion` 不等价：偏好是主体的持续状态，建议是一次言语行为；
- `goal`/`plan` 是意图，`speech_act` 里没有对应项，`promise` 只覆盖承诺给他人的情形。

WordNet 中 `prefer`、`intend`、`plan` 均存在且 sense 贴切
（`wn30:prefer.v.01` = "like better; value more highly"，
`wn30:intend.v.01` = "have in mind as a purpose"）。

**选项**：

- **A（建议）**：新增三个态度 Operator `prefers(Person, Assertion)`、`intends(Person, Assertion)`、
  `plans(Person, Assertion)`，attestation 用 `wordnet` + 上述真实 sense。与 R1 不同，这三个
  sense 的释义与所需含义一致，可如实引用。
- **B**：全部压进 `speech_act`：`preference`→`suggestion`、`goal`/`plan`→`other`。零新增本体，
  但丢失区分——`other` 无法还原成三个不同的东西。
- **C**：三者报 `unsupported_construct`，抽取层省略。

**我建议 A**，理由是这三项在 `personal-org` 的抽取 prompt 中是产出项
（`prompts/turn_ke/system.md` 要求模型给出 modality），压成 `other` 会让已有的抽取能力退化。
但这会把新增 Operator 从 1 个变成 4 个，属于本体扩展而非纯迁移，需要你确认范围。

**裁决**：______

---

## R3：`gloss` 是否保留

**影响面**：43 文件 / 162 引用。

**事实**：

`gloss` 在 `ke-memory/v1` 中是必填非空字符串，用途是人类可读摘要。

新合同把文本分三层：Authoritative JSON、Canonical Text、Display Text，并明确规定
**Display Text 不得参与解析、hash 或权威存储**（`README.md:54`）。`gloss` 正是 Display Text。
`CandidateAssertion` 与 `CandidateMetadata` 中均无对应字段。

**选项**：

- **A（建议）**：不迁移。`gloss` 留在 `personal-org` 侧作为记忆系统自己的展示字段，不进入
  KE 或 candidate 合同。理由是它本就不该参与权威存储，而记忆系统有自己的展示需要。
- **B**：迁移到 Snapshot 的 Lexicalization。代价是 `gloss` 是**每条 KE 一个**的自由文本，
  而 Lexicalization 是**每个 Operator/Concept 一个**的受控词面，二者基数不同，塞不进去。
- **C**：请求扩展 `CandidateMetadata` 增加自由文本字段。这会修改活动合同，需要独立评审。

**我建议 A**。B 在基数上不成立；C 是改合同，代价与收益不成比例。

**裁决**：______

---

## R4：`Expression` 递归结构的扁平化策略

**影响面**：`src/ke_memory_demo/domain/expressions.py` 的 `OperatorApplication` 是递归类型
（`model_rebuild()` 自引用），43 个引用 `KnowledgeEquation` 的文件都可能受影响。

**事实**：

`ke-memory/v1` 的 `Expression` 联合含递归 `OperatorApplication`，可无限嵌套。
`memory-assertion/v1` 禁止嵌套，要求每个嵌套子式提升为独立 candidate 并用 `assertion_ref` 引用。

这不是格式转换，而是**一条 KE 变多条**：嵌套深度 n 的表达式变成 n 条 candidate。因此
candidate id 的分配策略、以及 `support_basis`/`context_support_refs` 的填法都需要确定。

**选项**：

- **A（建议）**：转换时按后序遍历展开，内层先得 candidate id，外层用 `assertion_ref` 指向。
  id 用确定性方案（如内容 hash 或 `父id.子序号`），使同一输入两次转换得到同一组 id。
- **B**：拒绝转换任何含嵌套的 KE，报 `unsupported_construct`。代价是现有抽取产出中所有嵌套
  表达式失效——但我**尚未测量**实际嵌套深度分布，所以这个代价目前未知。
- **C**：先测量再定。跑一遍现有 golden fixture，统计嵌套深度分布，据此判断 A 的展开量是否
  可接受。

**我建议先做 C 再定 A 或 B**：嵌套深度分布是这项决策唯一缺失的事实，而它便宜可测。我在写本
报告时没有测，因为它需要跑 `personal-org` 的 fixture 而非只读代码——如果你同意，我下一步补上。

**裁决**：______

---

## 事实的复算命令

```bash
# 引用规模
cd /public/home/wwb/KE_mem/ke-memory-demo/.worktrees/personal-org-memory-service-20260803
for f in modality polarity lifecycle gloss speaker ontology_bindings; do
  printf '%-20s files=%-4s refs=%s\n' "$f" \
    "$(grep -rln "\b$f\b" src service tests | wc -l)" \
    "$(grep -rn "\b$f\b" src service tests | wc -l)"
done

# 无持久化数据
grep -rl '"schema_version": *"ke-memory/v1"' . --include='*.json' | wc -l   # 期望 0

# fixture 现有 Operator
python3 -c "
import json
d=json.load(open('/public/home/wwb/KE_mem/ke-memory-demo/spec/memory-assertion-v1/fixtures/ontology-snapshot-example/operators/core.json'))
print([o['canonical_name'] for o in d['operators']])"

# WordNet sense 释义
python3 - <<'EOF'
import zipfile, re
z = zipfile.ZipFile('/public/home/wwb/datasets/ontology-sources/wordnet-3.0-nltk.zip')
data = z.read('wordnet/data.verb').decode('utf-8', errors='replace').splitlines()
idx = z.read('wordnet/index.verb').decode('utf-8', errors='replace').splitlines()
for lemma in ('negate', 'prefer', 'intend', 'plan'):
    line = [l for l in idx if l.startswith(lemma + ' ')][0].split()
    off = [t for t in line if re.fullmatch(r'\d{8}', t)][0]
    for d in data:
        if d.startswith(off):
            print(f'wn30:{lemma}.v.01 = {d.split("|", 1)[1].strip()[:90]}')
            break
EOF
```

## 裁决后的下一步

R1–R3 裁决完成、R4 补测后，第二步（边界转换层）才具备完整输入。第二步只在 `online`/`service`
出入口做转换，不动 `domain`，因此 1760 个测试一个不改；转换层暴露的不可映射项就是本报告
结论的实证检验。
