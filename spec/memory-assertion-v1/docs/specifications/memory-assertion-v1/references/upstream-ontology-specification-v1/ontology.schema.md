# 本体存储 Specification

本文档说明 `ontology.schema.json` 定义的本体分片存储格式。该 Specification 使用 JSON Schema Draft-07 编写，适用于 JSON 数据，也可用于校验解析为相同数据结构的 YAML 数据。

## 1. 输出与顶层结构

本体数据按文件分片存储。同一个 Specification 可以校验三类文件：本体元数据文件、概念分片文件和算子分片文件。

| 文件类型       | 顶层字段      | 字段类型 | 说明               |
| -------------- | ------------- | -------- | ------------------ |
| 本体元数据文件 | `ontology`  | object   | 保存一条本体元数据 |
| 概念分片文件   | `concepts`  | array    | 保存一个或多个概念 |
| 算子分片文件   | `operators` | array    | 保存一个或多个算子 |

每个文件只能包含一种顶层字段，不能在同一文件中混合 `ontology`、`concepts` 和 `operators`。概念或算子可以按领域、模块或维护边界拆分到多个文件中。

推荐输出目录结构：

```text
<ontology_name>/
├── ontology.yaml
├── concepts/
│   ├── 商品与服务/                
│   │   ├── 商品类/               
│   │   │   ├── 商品基础/        
│   │   │   │   └── concepts.yaml
│   │   │   └── 价格与计价/
│   │   │       └── concepts.yaml
│   │   └── 服务类/
│   │       └── 服务基础/
│   │           └── concepts.yaml
│   └── 库存与供应链/
│       └── 库存类/
│           └── concepts.yaml
└── operators/
    ├── 商品与服务/                 
    │   └── 商品类/
    │       ├── 商品基础/
    │       │   └── operators.yaml
    │       └── 价格与计价/
    │           └── operators.yaml
    └── 库存与供应链/
        └── 库存类/
            └── operators.yaml
```

## 2. 通用字段

本体、概念和算子共用以下字段。

| 字段                   | 类型     | 约束                             | 说明                                     |
| ---------------------- | -------- | -------------------------------- | ---------------------------------------- |
| `id`                 | string   | 类型前缀加 12 位小写十六进制字符 | 使用对象类型和哈希摘要组成的稳定唯一标识 |
| `canonical_name`     | string   | 不得为空或全为空白字符           | 经过统一和规范化的名称                   |
| `description`        | string   | 不得为空或全为空白字符           | 对对象含义的明确描述或定义               |
| `sources`            | string[] | 至少包含一项且不得重复           | 原始资源的公共路径                       |
| `created_at`         | string   | RFC 3339`date-time`            | 对象第一次创建的时间                     |
| `abstraction_method` | string   | 可选，不得为空或全为空白字符     | 对象的形成方式，如抽取、推理生成         |

示例 ID：

```text
concept_16481f3880cf
```

不同对象使用不同前缀：

| 对象 | ID 格式                 |
| ---- | ----------------------- |
| 本体 | `ontology_<12位哈希>` |
| 概念 | `concept_<12位哈希>`  |
| 算子 | `operator_<12位哈希>` |

`id` 按以下统一规则生成：

1. 实体第一次创建时，使用密码学安全随机数生成器生成一个 UUIDv4，作为该实体永久不变的身份种子。UUID 使用小写的 `8-4-4-4-12` 标准文本格式。
2. 根据实体类型构造哈希输入：本体使用 `ontology:<uuid>`，概念使用 `concept:<uuid>`，算子使用 `operator:<uuid>`。字符串以 UTF-8 编码，不添加空格、换行或其他分隔符。
3. 计算哈希输入的 SHA-256，取摘要前 12 位小写十六进制字符，再分别添加 `ontology_`、`concept_` 或 `operator_` 前缀。
4. 写入前必须在当前数据存储中检查 ID 唯一性；如果发生碰撞，丢弃该 UUID，重新生成 UUIDv4 并计算 ID。
5. 生成方必须持久化实体与身份种子的对应关系。实体一旦获得 ID，不得重新生成种子，也不得因为名称、描述、来源、父概念或其他业务属性的修订而改变 ID。

例如，身份种子为 `<uuid>` 的概念，其哈希输入形式为：

```text
concept:<uuid>
```

UUID 只用于生成和维护稳定身份，不作为本 Specification 中的数据字段输出。

`created_at` 应包含时区。例如：

```text
2026-07-14T15:30:00+08:00
```

## 3. 本体 Ontology

`ontology` 保存整份本体的身份和版本信息。

| 字段                   | 类型   | 必填 | 说明                 |
| ---------------------- | ------ | ---- | -------------------- |
| `id`                 | string | 是   | 本体 ID              |
| `canonical_name`     | string | 是   | 本体统一名称         |
| `description`        | string | 是   | 本体的领域范围和定义 |
| `sources`            | array  | 是   | 本体总体定义的来源   |
| `created_at`         | string | 是   | 本体创建时间         |
| `abstraction_method` | string | 否   | 本体的形成方式       |
| `version`            | string | 是   | 语义化版本号         |

版本号采用 Semantic Versioning 格式：

```text
主版本号.次版本号.修订号
```

例如 `1.0.0`、`1.2.3` 或 `2.0.0-beta.1`。

版本号按以下规则递增：

| 位置    | 何时增加                       | 示例                                                                                 |
| ------- | ------------------------------ | ------------------------------------------------------------------------------------ |
| `Major` | Schema 发生变动，或本体发生不兼容变化 | 修改 `ontology.schema.json`；删除概念或算子；改变既有语义；修改继承关系并导致行为变化 |
| `Minor` | 本体发生兼容性新增             | 新增概念、算子或扩展能力                                                             |
| `Patch` | 不改变本体语义的修正           | 修正文案、错别字、来源路径和描述表述                                                 |

例如：

```text
1.0.0  初始版本
1.1.0  新增概念或算子
1.1.1  修正描述或来源路径
2.0.0  Schema 发生变动，或删除、重定义既有概念或算子
```

版本递增时，只增加对应位置并将其右侧位置归零。例如，`1.2.3` 的 Minor 版本增加后应为 `1.3.0`，Major 版本增加后应为 `2.0.0`。

## 4. 概念 Concept

每个概念包含通用字段以及父概念和扩展数据。

| 字段                   | 类型     | 必填 | 说明                       |
| ---------------------- | -------- | ---- | -------------------------- |
| `id`                 | string   | 是   | 概念 ID                    |
| `canonical_name`     | string   | 是   | 概念统一名称               |
| `description`        | string   | 是   | 概念定义                   |
| `sources`            | array    | 是   | 概念定义的来源             |
| `created_at`         | string   | 是   | 概念创建时间               |
| `abstraction_method` | string   | 否   | 概念的形成方式             |
| `parents`            | string[] | 是   | 直接父概念的 ID 列表       |
| `supply`             | object   | 否   | 面向下游需求的开放扩展字段 |

### parents

`parents` 只保存直接父概念，也就是当前概念的最小上界，不保存能够通过父概念继续推导出的间接祖先。

- 顶层概念使用空数组 `[]`。
- 一个概念可以有多个直接父概念。
- 同一个父概念 ID 不得重复。
- 每个父概念 ID 都应指向当前本体中已经存在的概念。
- 概念不能将自身作为父概念，概念继承关系中不能形成环。

### supply

`supply` 是可选字段。如果提供，必须是对象，但不限制内部字段；没有扩展数据时可以省略该字段，或使用空对象 `{}`。

```json
{
  "supply": {}
}
```

下游系统需要新增字段时，应优先放入 `supply`，并由使用方约定字段名称、类型和语义。通用且稳定的字段可以在后续 Specification 版本中提升为概念的正式字段。

## 5. 算子 Operator

算子表示从零个或多个输入概念得到一个输出概念的语义操作。

| 字段                   | 类型     | 必填 | 说明                             |
| ---------------------- | -------- | ---- | -------------------------------- |
| `id`                 | string   | 是   | 算子 ID                          |
| `canonical_name`     | string   | 是   | 算子统一名称                     |
| `input_concepts`     | string[] | 是   | 有序的输入概念 ID 列表，可以为空 |
| `output_concept`     | string   | 是   | 唯一的输出概念 ID                |
| `description`        | string   | 是   | 算子的语义定义                   |
| `sources`            | array    | 是   | 算子定义的来源                   |
| `created_at`         | string   | 是   | 算子创建时间                     |
| `abstraction_method` | string   | 否   | 算子的形成方式                   |
| `supply`             | object   | 否   | 面向下游需求的开放扩展字段       |

`input_concepts` 的数组顺序表示输入参数顺序。无输入算子使用空数组：

```json
{
  "input_concepts": []
}
```

`output_concept` 是单个字符串，因此一个算子必须且只能声明一个输出概念。输入和输出 ID 都应指向当前本体中存在的概念；该引用完整性需要由业务校验程序检查。

### abstraction_method

`abstraction_method` 用于说明本体、概念或算子是如何形成的，例如：

```yaml
abstraction_method: 抽取
```

```yaml
abstraction_method: 推理生成
```

该字段当前使用开放字符串，不限制枚举值，便于后续根据实际生成流程补充。项目应尽量统一用词，避免同时使用“抽取”“提取”等含义相同的不同写法。

### supply

`supply` 是可选字段。如果提供，必须是对象，但不限制内部字段；没有扩展数据时可以省略该字段，或使用空对象 `{}`。

```json
{
  "supply": {}
}
```

与概念一致，下游系统需要为算子新增字段时应优先放入 `supply`，并由使用方约定字段名称、类型和语义。通用且稳定的字段可以在后续 Specification 版本中提升为算子的正式字段。

`is_pure` 就是一个约定放入 `supply` 的示例字段，用于标注算子的纯性：

```json
{
  "supply": {
    "is_pure": true
  }
}
```

- `true`：相同输入始终得到相同输出，不受调用时间或外部可变状态影响；
- `false`：相同输入可能因为时间、库存、价格、数据库状态或其他外部状态而得到不同输出；
- 字段缺失：尚未判断或暂未声明算子的纯性。

例如，字符串长度计算通常可以标记为纯算子；查询商品实时库存通常应标记为非纯算子。

## 6. 来源 Sources

原始文件资源统一存放在约定的共享资源根目录中。每个本体、概念和算子都必须提供至少一个 `sources` 路径，数据中不重复保存资源类型、文件名和定位对象。

`sources` 使用 IRI-reference 字符串数组，支持包含 Unicode 字符的路径，建议遵循以下规则：

- 保存相对于共享资源根目录的公共路径，不保存个人电脑的绝对路径；
- 路径分隔符统一使用 `/`；
- 仅能定位到文件时，直接保存文件路径；
- 能定位到章节、段落或行时，在路径后使用 `#` 片段；
- 同一条记录中不得重复保存相同路径；
- 资源移动后，应通过资源管理机制维护路径兼容或统一迁移引用。

只引用文件：

```json
"sources": [
  "resources/product/商品数据字典.xlsx"
]
```

引用文件内的具体位置：

```json
"sources": [
  "resources/product/商品规范.md#paragraph-12",
  "resources/product/术语定义.md#sku"
]
```

共享资源根目录的实际地址由部署环境或资源服务配置，不写入每条本体数据。例如，数据中的 `resources/product/商品规范.md` 可以由系统解析到统一的对象存储、文档服务或仓库目录。

## 7. 完整示例

以下三段数据分别保存为不同文件。

### 7.1 本体元数据文件

```json
{
  "ontology": {
    "id": "ontology_b79b2fd14891",
    "canonical_name": "电商本体",
    "description": "描述电商领域中的商品、价格、交易和履约等概念及其关系。",
    "sources": [
      "resources/ecommerce/电商领域资料.md"
    ],
    "created_at": "2026-07-14T15:30:00+08:00",
    "abstraction_method": "抽取",
    "version": "1.0.0"
  }
}
```

### 7.2 概念分片文件

```json
{
  "concepts": [
    {
      "id": "concept_58fdb0941f36",
      "canonical_name": "商品",
      "description": "可以进行交易的商品对象。",
      "sources": [
        "resources/product/商品规范.md#paragraph-4"
      ],
      "created_at": "2026-07-14T15:31:00+08:00",
      "abstraction_method": "抽取",
      "parents": [],
      "supply": {}
    },
    {
      "id": "concept_f88ba99c9b34",
      "canonical_name": "SKU",
      "description": "最小可售卖、可库存和可履约的商品单元。",
      "sources": [
        "resources/product/商品规范.md#paragraph-12"
      ],
      "created_at": "2026-07-14T15:32:00+08:00",
      "abstraction_method": "推理生成",
      "parents": [
        "concept_58fdb0941f36"
      ],
      "supply": {
        "domain": "product"
      }
    }
  ]
}
```

### 7.3 算子分片文件

```json
{
  "operators": [
    {
      "id": "operator_5ca70fc0e87c",
      "canonical_name": "得到SKU",
      "input_concepts": [
        "concept_58fdb0941f36"
      ],
      "output_concept": "concept_f88ba99c9b34",
      "description": "从商品对象得到其对应的 SKU。",
      "sources": [
        "resources/product/商品规范.md#sku-operator"
      ],
      "created_at": "2026-07-14T15:33:00+08:00",
      "abstraction_method": "抽取",
      "supply": {
        "is_pure": true
      }
    }
  ]
}
```

## 8. Specification 版本维护

当存储结构发生不兼容变化时，应同时：

1. 发布新的 Specification 文件版本；
2. 记录字段变化和迁移方式；
3. 明确旧数据支持期限；
4. 对已有本体数据执行迁移和重新校验。
