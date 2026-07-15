# Agent Memory Baseline Adapters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add isolated, public-API-only adapters for Mem0 OSS, Graphiti, Hindsight, and MemPalace that consume the exact same exchange stream and return normalized evidence through the core `MemorySystem` protocol.

**Architecture:** Baseline dependencies run outside the core environment. Mem0 and Graphiti use JSONL-RPC bridge subprocesses in separate uv environments; Hindsight uses its public HTTP client against the frozen self-hosted service; MemPalace uses its public loopback MCP HTTP transport. A supervisor owns process lifecycle and records receipts, usage, latency, source identity, and failures without reading baseline databases.

**Tech Stack:** Core plan stack, uv-managed isolated virtual environments, asyncio subprocesses, HTTPX, Hindsight Python client, JSON-RPC 2.0, pytest contract tests.

**Design Spec:** `docs/superpowers/specs/2026-07-15-ke-memory-demo-design.md` at approved commit `90a9575f71740b399405e8c568090c282c5290b7`. This is plan 2 of 3 and starts only after the core verification gate.

## Global Constraints

- Complete `2026-07-15-ke-memory-core-implementation.md` first; import its `Exchange`, `Evidence`, `MemorySystem`, receipts, settings, redaction, and token counter unchanged.
- Baseline source roots are read-only inputs under `/public/home/wwb/memory-sota-study/repos`; never edit or commit inside them.
- Frozen SHAs: Mem0 `87276ef96879ee406690e640d34060de546560a5`, Graphiti `62ff03ac5662d288ebd9f6aafb70d6ae4070c632`, Hindsight `f00d3c7f666e560bb051c51fba3977b38885f46a`, MemPalace `18a9788961afce013efc9e2da23ea2b17ab72381`.
- Do not reference `/public/home/wwb/memory` or any fusion-memory project.
- Use only documented/public constructors, write APIs, retrieval APIs, health/version endpoints, and MCP tools. Never query a baseline database or import private persistence internals to improve evidence attribution.
- Write exactly one Exchange per call, in source order, and await success before writing the next Exchange in that conversation.
- Use one fresh namespace per system/conversation/run and retain every public ingest receipt.
- Pass source Exchange IDs through public metadata/document/episode/source-file fields where available. If retrieval cannot expose a source, return `unattributed`; never infer a source ID from answer content.
- Baselines return evidence only. Do not call a baseline answer or reflect API.
- Pass the common `gpt-5.4` endpoint only through public configuration that supports a custom OpenAI-compatible endpoint.
- Pass the common local Qwen embedder only through a public embedder extension/configuration point. Otherwise use the frozen upstream default and record that condition.
- A baseline failure makes the experiment incomplete; it is never converted to a zero score.
- `.baseline-envs`, baseline state, process logs, bearer tokens, and local databases stay Git-ignored.
- Use fake bridges/servers in unit and contract tests. Live baseline tests are opt-in and run serially.

---

### Task 1: Baseline Configuration, Source Identity, and Process Supervision

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `config/baselines.toml`
- Create: `src/ke_memory_demo/baselines/__init__.py`
- Create: `src/ke_memory_demo/baselines/settings.py`
- Create: `src/ke_memory_demo/baselines/source_identity.py`
- Create: `src/ke_memory_demo/baselines/supervisor.py`
- Create: `src/ke_memory_demo/baselines/rpc.py`
- Create: `src/ke_memory_demo/baselines/metering_proxy.py`
- Create: `scripts/setup_baseline_envs.py`
- Create: `tests/unit/baselines/test_source_identity.py`
- Create: `tests/unit/baselines/test_rpc.py`
- Create: `tests/unit/baselines/test_supervisor.py`
- Create: `tests/unit/baselines/test_metering_proxy.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: core settings, domain receipts, telemetry, and redaction.
- Produces: `BaselineSettings`, `SourceIdentity`, `JsonlRpcClient`, `ManagedProcess`, `OpenAIUsageProxy`, `BaselineSupervisor`, and four ignored isolated environments.

- [ ] **Step 1: Write failing source and JSONL-RPC tests**

```python
def test_source_identity_keeps_recorded_sha_and_tree_fingerprint(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "pyproject.toml").write_text("[project]\nname='sample'\n")
    identity = identify_source(source, recorded_sha="a" * 40)
    assert identity.recorded_sha == "a" * 40
    assert len(identity.tree_sha256) == 64


@pytest.mark.asyncio
async def test_rpc_rejects_mismatched_response_id(fake_bridge):
    fake_bridge.reply({"id": "wrong", "result": {}})
    with pytest.raises(BaselineProtocolError, match="response id"):
        await fake_bridge.client.call("prepare", {"scope": "x"})


@pytest.mark.asyncio
async def test_metering_proxy_preserves_response_and_records_usage(fake_upstream):
    fake_upstream.reply({"id": "r", "choices": [], "usage": {"prompt_tokens": 11, "completion_tokens": 4, "total_tokens": 15}})
    proxy = await OpenAIUsageProxy.start(fake_upstream.url, system_id="mem0", upstream_key="test-secret")
    response = await proxy.client.post("/v1/chat/completions", json={"model": "gpt-5.4", "messages": []})
    assert response.json()["id"] == "r"
    assert proxy.usage_records[0].input_tokens == 11
    assert proxy.usage_records[0].output_tokens == 4
    await proxy.close()
```

- [ ] **Step 2: Run tests and confirm missing modules**

Run: `uv run pytest tests/unit/baselines/test_source_identity.py tests/unit/baselines/test_rpc.py tests/unit/baselines/test_supervisor.py tests/unit/baselines/test_metering_proxy.py -v`

Expected: FAIL during import.

- [ ] **Step 3: Add exact baseline settings**

Run: `uv add 'starlette>=0.47,<1' 'uvicorn>=0.35,<1'`

Expected: the core environment gains only the loopback metering-server dependencies and `uv.lock` remains valid.

```toml
# config/baselines.toml
[mem0]
enabled = true
source_root = "/public/home/wwb/memory-sota-study/repos/mem0"
recorded_sha = "87276ef96879ee406690e640d34060de546560a5"
python = ".baseline-envs/mem0/bin/python"

[graphiti]
enabled = true
source_root = "/public/home/wwb/memory-sota-study/repos/graphiti"
recorded_sha = "62ff03ac5662d288ebd9f6aafb70d6ae4070c632"
python = ".baseline-envs/graphiti/bin/python"

[hindsight]
enabled = true
source_root = "/public/home/wwb/memory-sota-study/repos/hindsight"
recorded_sha = "f00d3c7f666e560bb051c51fba3977b38885f46a"
base_url = "http://127.0.0.1:8888"
python = ".baseline-envs/hindsight/bin/python"

[mempalace]
enabled = true
source_root = "/public/home/wwb/memory-sota-study/repos/mempalace"
recorded_sha = "18a9788961afce013efc9e2da23ea2b17ab72381"
base_url = "http://127.0.0.1:18765"
python = ".baseline-envs/mempalace/bin/python"
```

`setup_baseline_envs.py` must create each venv under `.baseline-envs`, install the local source as a non-editable package, install only required extras, run an import/version probe, and write `var/baseline-env-manifest.json` containing recorded SHA, tree fingerprint, Python version, and sorted installed distributions. Tree fingerprints include tracked-source extensions and exclude `.git`, virtual environments, caches, build output, generated databases, logs, and archives; recompute before and after setup and require equality. Never run `pip install -e` against source roots.

Use these exact local install targets: Mem0 repository root followed by `sentence-transformers>=5.2`; Graphiti repository root with `[kuzu,sentence-transformers]`; Hindsight `hindsight-api-slim[local-ml,embedded-db]` plus `hindsight-clients/python`; and MemPalace repository root. The setup script invokes `uv pip install --python {venv_python} {local_target}` for each target and never resolves a baseline package by its remote package name.

- [ ] **Step 4: Implement strict JSONL-RPC and process lifecycle**

```python
class JsonlRpcClient:
    async def call(self, method: str, params: dict[str, object], timeout: float = 300.0) -> dict[str, object]:
        request_id = self._ids.next()
        await self._write({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        response = await asyncio.wait_for(self._read(), timeout)
        if response.get("id") != request_id:
            raise BaselineProtocolError("JSONL-RPC response id mismatch")
        if "error" in response:
            raise BaselineRemoteError.from_payload(response["error"])
        return cast(dict[str, object], response["result"])
```

Capture stderr separately, redact before saving, terminate with SIGTERM and bounded wait, then SIGKILL only for a process started by this supervisor. Never kill by process name or port.

Apply the core 1/2/4-second transient retry schedule to health and retrieval. Do not retry an ingest after an ambiguous transport failure unless the public API accepts a deterministic idempotency key and confirms the prior record; otherwise mark the namespace unusable, reset the owned state, and replay the full conversation into a fresh namespace.

Start one loopback-only `OpenAIUsageProxy` per baseline that uses the work model. Accept only non-streaming `POST /v1/chat/completions` and `POST /v1/responses`, forward the body without semantic changes to the configured upstream, inject the upstream Authorization secret inside the proxy, preserve status/body/headers required by the SDK, and extract response usage, request ID, actual model, latency, and provider cost. Reject any other path or streaming request during preflight. Give each baseline the proxy base URL through its public model configuration. Redact request content/headers before telemetry and never cache responses.

- [ ] **Step 5: Run tests and create isolated environments**

Run: `uv run pytest tests/unit/baselines/test_source_identity.py tests/unit/baselines/test_rpc.py tests/unit/baselines/test_supervisor.py tests/unit/baselines/test_metering_proxy.py -v`

Expected: all tests pass.

Run: `uv run python scripts/setup_baseline_envs.py --config config/baselines.toml`

Expected: four import probes pass and the manifest contains four distinct environments without modifying source roots.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock config/baselines.toml src/ke_memory_demo/baselines scripts/setup_baseline_envs.py tests/unit/baselines .gitignore
git commit -m "build: isolate frozen baseline environments"
```

### Task 2: Shared Exchange Rendering and Baseline Contract Suite

**Files:**
- Create: `src/ke_memory_demo/baselines/rendering.py`
- Create: `src/ke_memory_demo/baselines/base.py`
- Create: `tests/contract/baselines/conftest.py`
- Create: `tests/contract/baselines/test_memory_system_contract.py`
- Create: `tests/unit/baselines/test_rendering.py`

**Interfaces:**
- Consumes: core `Exchange`, `Evidence`, `MemorySystem`, receipt models, and token counter.
- Produces: `render_exchange_text()`, `exchange_messages()`, `BaselineAdapterBase`, and a reusable `memory_system_contract(adapter_factory)`.

- [ ] **Step 1: Write failing render and contract tests**

```python
def test_text_render_preserves_roles_order_and_tool_events():
    rendered = render_exchange_text(exchange_with_tool())
    assert rendered.splitlines() == [
        "[USER]", "run it", "[TOOL_CALL]", '{"name":"run"}',
        "[TOOL_RESULT]", '{"ok":true}', "[ASSISTANT]", "done",
    ]


@pytest.mark.asyncio
async def test_contract_requires_fresh_scope_and_attributed_receipt(adapter_factory):
    adapter = adapter_factory()
    identity = await adapter.prepare(RunScope(run_id="r", conversation_id="c", system_id=adapter.system_id))
    receipt = await adapter.ingest(sample_exchange())
    assert identity.namespace
    assert receipt.source_exchange_id == sample_exchange().id
    assert receipt.system_record_ids
```

- [ ] **Step 2: Run tests and observe missing shared adapter code**

Run: `uv run pytest tests/unit/baselines/test_rendering.py tests/contract/baselines/test_memory_system_contract.py -v`

Expected: FAIL during import.

- [ ] **Step 3: Implement exact rendering and contract assertions**

`exchange_messages()` returns source-ordered OpenAI-style records for APIs accepting roles. `render_exchange_text()` emits the fixed labels above without adding summaries or IDs to semantic text. IDs travel only through metadata. The contract suite covers prepare isolation, sequential ingest receipts, readiness, retrieval under budget, source attribution or explicit `unattributed`, stats, reset, duplicate-ingest policy, and typed failure behavior.

- [ ] **Step 4: Run shared tests**

Run: `uv run pytest tests/unit/baselines/test_rendering.py tests/contract/baselines/test_memory_system_contract.py -v`

Expected: fake adapter passes every shared contract case.

- [ ] **Step 5: Commit**

```bash
git add src/ke_memory_demo/baselines/rendering.py src/ke_memory_demo/baselines/base.py tests/contract/baselines tests/unit/baselines/test_rendering.py
git commit -m "test: define baseline adapter contract"
```

### Task 3: Mem0 OSS Public Adapter

**Files:**
- Create: `baseline_bridges/common.py`
- Create: `baseline_bridges/mem0_bridge.py`
- Create: `src/ke_memory_demo/baselines/mem0.py`
- Create: `tests/unit/baselines/test_mem0_adapter.py`
- Create: `tests/contract/baselines/test_mem0_contract.py`
- Create: `tests/live/test_mem0_live.py`

**Interfaces:**
- Consumes: JSONL-RPC, rendering, settings, and core protocol.
- Produces: `Mem0Adapter` and a bridge that calls only `Memory.from_config`, `Memory.add`, and `Memory.search`.

- [ ] **Step 1: Write failing request/normalization tests**

```python
@pytest.mark.asyncio
async def test_mem0_ingest_uses_one_exchange_and_source_metadata(fake_mem0_bridge):
    adapter = Mem0Adapter(fake_mem0_bridge.client, fake_mem0_bridge.settings)
    await adapter.prepare(run_scope("mem0"))
    await adapter.ingest(sample_exchange())
    call = fake_mem0_bridge.last_call("ingest")
    assert [m["role"] for m in call["messages"]] == ["user", "assistant"]
    assert call["metadata"]["source_exchange_id"] == sample_exchange().id
```

- [ ] **Step 2: Run tests and verify missing adapter**

Run: `uv run pytest tests/unit/baselines/test_mem0_adapter.py tests/contract/baselines/test_mem0_contract.py -v`

Expected: FAIL during import.

- [ ] **Step 3: Implement the bridge using Mem0 public configuration**

```python
config = {
    "llm": {"provider": "openai", "config": {
        "model": work.model, "api_key": "local-metered",
        "openai_base_url": metering_proxy.base_url, "temperature": 0.0,
        "max_tokens": 4096, "is_reasoning_model": True, "reasoning_effort": "low",
    }},
    "vector_store": {"provider": "qdrant", "config": {
        "collection_name": namespace, "path": str(state_root / "qdrant"),
        "embedding_model_dims": 1024, "on_disk": True,
    }},
    "embedder": {"provider": "huggingface", "config": {
        "model": str(embedding.local_path), "embedding_dims": 1024,
        "model_kwargs": {"local_files_only": True, "trust_remote_code": True},
    }},
}
memory = Memory.from_config(config_dict=config)
```

Call `memory.add(messages, user_id=namespace, metadata=source_metadata, infer=True)` once per exchange and `memory.search(question, top_k=60, filters={"user_id": namespace}, threshold=0.0, explain=True)` for retrieval. Normalize `id`, `memory`/`text`, score, metadata, and receipt IDs. If the frozen public Hugging Face provider rejects the local Qwen path or dimension, use the upstream embedder configuration accepted by this SHA and record `embedding_condition="upstream-default"`; do not patch Mem0.

Implement reset with public `memory.delete_all(user_id=namespace)` followed by bridge shutdown. Never call global `memory.reset()` because it can affect other isolated scopes.

- [ ] **Step 4: Run unit and contract tests**

Run: `uv run pytest tests/unit/baselines/test_mem0_adapter.py tests/contract/baselines/test_mem0_contract.py -v`

Expected: all tests pass with the fake bridge.

- [ ] **Step 5: Run one opt-in live exchange**

Run: `uv run pytest tests/live/test_mem0_live.py -v -m live_baseline`

Expected: one ingest receipt, one nonempty public search response, and no source-tree changes.

- [ ] **Step 6: Commit**

```bash
git add baseline_bridges/common.py baseline_bridges/mem0_bridge.py src/ke_memory_demo/baselines/mem0.py tests/unit/baselines/test_mem0_adapter.py tests/contract/baselines/test_mem0_contract.py tests/live/test_mem0_live.py
git commit -m "feat: adapt Mem0 OSS public memory API"
```

### Task 4: Graphiti Public Adapter with Embedded Kuzu

**Files:**
- Create: `baseline_bridges/graphiti_bridge.py`
- Create: `baseline_bridges/qwen_graphiti_embedder.py`
- Create: `src/ke_memory_demo/baselines/graphiti.py`
- Create: `tests/unit/baselines/test_graphiti_adapter.py`
- Create: `tests/contract/baselines/test_graphiti_contract.py`
- Create: `tests/live/test_graphiti_live.py`

**Interfaces:**
- Consumes: bridge infrastructure and core protocol.
- Produces: `GraphitiAdapter`, public `Graphiti.add_episode/search` bridge, and a public `EmbedderClient` implementation backed by local Qwen.

- [ ] **Step 1: Write failing episode-order and evidence tests**

```python
@pytest.mark.asyncio
async def test_graphiti_uses_synthetic_order_only_reference_time(fake_graphiti_bridge):
    adapter = GraphitiAdapter(fake_graphiti_bridge.client, fake_graphiti_bridge.settings)
    await adapter.prepare(run_scope("graphiti"))
    await adapter.ingest(sample_exchange(global_ordinal=12))
    call = fake_graphiti_bridge.last_call("ingest")
    assert call["reference_time"] == "2000-01-01T00:00:12+00:00"
    assert call["source_description"] == "synthetic_order_only"
```

- [ ] **Step 2: Run tests and verify missing adapter**

Run: `uv run pytest tests/unit/baselines/test_graphiti_adapter.py tests/contract/baselines/test_graphiti_contract.py -v`

Expected: FAIL during import.

- [ ] **Step 3: Implement public Graphiti construction and Qwen embedder**

```python
driver = KuzuDriver(db=str(state_root / "graphiti.kuzu"), max_concurrent_queries=1)
llm = OpenAIClient(config=LLMConfig(
    api_key="local-metered", model=work.model, base_url=metering_proxy.base_url,
    temperature=0.0, max_tokens=work.max_output_tokens,
))
graphiti = Graphiti(graph_driver=driver, llm_client=llm, embedder=QwenGraphitiEmbedder(embedding))
```

`QwenGraphitiEmbedder` subclasses public `EmbedderClient` and implements both `create` and `create_batch` with 1024-dimensional normalized vectors. Ingest with `add_episode(name=exchange.id, episode_body=render_exchange_text(exchange), source_description="synthetic_order_only", reference_time=epoch + ordinal seconds, source=EpisodeType.message, group_id=namespace)`. Retrieve with `search(question, group_ids=[namespace], num_results=60)` and normalize public edge facts, UUIDs, validity fields, and episode/source IDs exposed by the returned objects.

Reset closes Graphiti through public `close()` and then lets the supervisor delete only the per-run Kuzu file it created. It never issues direct graph queries for cleanup or attribution.

- [ ] **Step 4: Run unit and contract tests**

Run: `uv run pytest tests/unit/baselines/test_graphiti_adapter.py tests/contract/baselines/test_graphiti_contract.py -v`

Expected: all tests pass; ingest calls are sequential and reference times strictly increase.

- [ ] **Step 5: Run one opt-in live exchange**

Run: `uv run pytest tests/live/test_graphiti_live.py -v -m live_baseline`

Expected: Kuzu state is created under ignored run state, search returns public `EntityEdge` data, and the bridge closes the driver.

- [ ] **Step 6: Commit**

```bash
git add baseline_bridges/graphiti_bridge.py baseline_bridges/qwen_graphiti_embedder.py src/ke_memory_demo/baselines/graphiti.py tests/unit/baselines/test_graphiti_adapter.py tests/contract/baselines/test_graphiti_contract.py tests/live/test_graphiti_live.py
git commit -m "feat: adapt Graphiti temporal graph API"
```

### Task 5: Hindsight Public HTTP Client Adapter

**Files:**
- Create: `src/ke_memory_demo/baselines/hindsight.py`
- Create: `src/ke_memory_demo/baselines/hindsight_service.py`
- Create: `tests/unit/baselines/test_hindsight_adapter.py`
- Create: `tests/contract/baselines/test_hindsight_contract.py`
- Create: `tests/live/test_hindsight_live.py`

**Interfaces:**
- Consumes: baseline settings, supervisor, rendering, and core protocol.
- Produces: `HindsightAdapter` using only `Hindsight.aget_version`, `aretain_batch`, and `arecall` plus public bank/reset APIs.

- [ ] **Step 1: Write failing one-item batch and recall-budget tests**

```python
@pytest.mark.asyncio
async def test_hindsight_uses_one_item_batch_with_document_id(fake_hindsight):
    adapter = HindsightAdapter(fake_hindsight.client, fake_hindsight.settings)
    await adapter.prepare(run_scope("hindsight"))
    await adapter.ingest(sample_exchange())
    call = fake_hindsight.last_call("aretain_batch")
    assert len(call["items"]) == 1
    assert call["items"][0]["document_id"] == sample_exchange().id
    assert call["retain_async"] is False
```

- [ ] **Step 2: Run tests and verify missing adapter**

Run: `uv run pytest tests/unit/baselines/test_hindsight_adapter.py tests/contract/baselines/test_hindsight_contract.py -v`

Expected: FAIL during import.

- [ ] **Step 3: Implement the public client mapping**

Construct `Hindsight(base_url=settings.base_url, api_key=settings.api_key, timeout=300.0)`. Use `bank_id=namespace`. Call `aretain_batch(bank_id, items=[{"content": render_exchange_text(exchange), "document_id": exchange.id, "metadata": source_metadata}], retain_async=False)`. Readiness requires successful return plus `aget_version`; do not inspect PostgreSQL. Recall with `arecall(bank_id, question, max_tokens=8192, budget="high", trace=True, include_chunks=True, max_chunk_tokens=8192, include_source_facts=True, max_source_facts_tokens=8192)`. Normalize public results, chunks, source facts, document IDs, scores, and trace usage; do not call `areflect`.

Reset uses public `adelete_bank(namespace)` and confirms the public response before stopping an owned service process.

- [ ] **Step 4: Run unit and contract tests**

Run: `uv run pytest tests/unit/baselines/test_hindsight_adapter.py tests/contract/baselines/test_hindsight_contract.py -v`

Expected: all tests pass and no reflect call is observed.

- [ ] **Step 5: Start the frozen self-hosted service and run one live exchange**

`HindsightService` must start `[Path(settings.python).with_name("hindsight-api"), "--host", "127.0.0.1", "--port", "8888"]`. Set child `HOME` to `var/baselines/hindsight/{run_id}/home` and set `HINDSIGHT_API_DATABASE_URL=pg0://{namespace}`, `HINDSIGHT_API_LLM_PROVIDER=openai`, `HINDSIGHT_API_LLM_API_KEY=local-metered`, `HINDSIGHT_API_LLM_MODEL=gpt-5.4`, `HINDSIGHT_API_LLM_BASE_URL` to the per-system metering proxy, `HINDSIGHT_API_LLM_TEMPERATURE=none`, `HINDSIGHT_API_EMBEDDINGS_PROVIDER=local`, `HINDSIGHT_API_EMBEDDINGS_LOCAL_MODEL` to the independent Qwen path, and `HINDSIGHT_API_EMBEDDINGS_LOCAL_TRUST_REMOTE_CODE=true`. Keep the frozen upstream reranker provider and record it in the adapter manifest. Wait for the public version endpoint, then run: `uv run pytest tests/live/test_hindsight_live.py -v -m live_baseline`.

Expected: version probe, synchronous retain, and recall succeed; service logs are redacted and saved as run telemetry.

- [ ] **Step 6: Commit**

```bash
git add src/ke_memory_demo/baselines/hindsight.py src/ke_memory_demo/baselines/hindsight_service.py tests/unit/baselines/test_hindsight_adapter.py tests/contract/baselines/test_hindsight_contract.py tests/live/test_hindsight_live.py
git commit -m "feat: adapt Hindsight retain and recall APIs"
```

### Task 6: MemPalace Public MCP Adapter

**Files:**
- Create: `src/ke_memory_demo/baselines/mcp_http.py`
- Create: `src/ke_memory_demo/baselines/mempalace.py`
- Create: `src/ke_memory_demo/baselines/mempalace_service.py`
- Create: `tests/unit/baselines/test_mcp_http.py`
- Create: `tests/unit/baselines/test_mempalace_adapter.py`
- Create: `tests/contract/baselines/test_mempalace_contract.py`
- Create: `tests/live/test_mempalace_live.py`

**Interfaces:**
- Consumes: HTTPX, supervisor, rendering, and core protocol.
- Produces: `McpHttpClient`, `MemPalaceService`, and `MemPalaceAdapter` calling only `mempalace_add_drawer` and `mempalace_search`.

- [ ] **Step 1: Write failing JSON-RPC and tool-argument tests**

```python
@pytest.mark.asyncio
async def test_mempalace_ingest_calls_public_add_drawer(fake_mcp):
    adapter = MemPalaceAdapter(fake_mcp.client, fake_mcp.settings)
    await adapter.prepare(run_scope("mempalace"))
    await adapter.ingest(sample_exchange(session_id="s1"))
    request = fake_mcp.last_tool_call()
    assert request["name"] == "mempalace_add_drawer"
    assert request["arguments"]["wing"] == adapter.namespace
    assert request["arguments"]["room"] == "s1"
    assert request["arguments"]["source_file"] == sample_exchange().id
```

- [ ] **Step 2: Run tests and verify missing adapter**

Run: `uv run pytest tests/unit/baselines/test_mcp_http.py tests/unit/baselines/test_mempalace_adapter.py tests/contract/baselines/test_mempalace_contract.py -v`

Expected: FAIL during import.

- [ ] **Step 3: Implement loopback MCP HTTP service and client**

Start the frozen console module with its isolated Python:

```python
run_palace_directory = Path("var/baselines/mempalace") / run_id / conversation_id
command = [
    str(settings.python), "-m", "mempalace.mcp_server",
    "--palace", str(run_palace_directory), "--transport", "http",
    "--host", "127.0.0.1", "--port", "18765",
]
```

The run palace directory is computed by code and never supplied through user text. Set a random bearer token in the child environment, send it only in Authorization headers, and redact it from telemetry. Wait on `/healthz`, then JSON-RPC `initialize` and `tools/list`; require both write and search tools.

- [ ] **Step 4: Implement public tool mapping**

Call `mempalace_add_drawer` with `wing=namespace`, `room=session_id`, verbatim rendered content, `source_file=exchange.id`, and `added_by="ke-memory-demo"`. Treat the returned logical/physical drawer IDs as the ingest receipt. Call `mempalace_search` with question, `wing=namespace`, limit 100, and configured max distance. Normalize returned drawer content, score/distance, source file/path, drawer ID, and matched-via fields.

Use the frozen MemPalace embedding/backend configuration exposed by its CLI and record it as `embedding_condition="upstream-public-config"`; do not import an internal collection to replace embeddings.

Reset stops the owned MCP service and deletes only its per-run palace directory. It does not query Chroma or another MemPalace backend directly.

- [ ] **Step 5: Run unit, contract, and opt-in live tests**

Run: `uv run pytest tests/unit/baselines/test_mcp_http.py tests/unit/baselines/test_mempalace_adapter.py tests/contract/baselines/test_mempalace_contract.py -v`

Expected: all tests pass.

Run: `uv run pytest tests/live/test_mempalace_live.py -v -m live_baseline`

Expected: health, initialize, add drawer, and search succeed over loopback HTTP; the service is terminated by its owning supervisor.

- [ ] **Step 6: Commit**

```bash
git add src/ke_memory_demo/baselines/mcp_http.py src/ke_memory_demo/baselines/mempalace.py src/ke_memory_demo/baselines/mempalace_service.py tests/unit/baselines/test_mcp_http.py tests/unit/baselines/test_mempalace_adapter.py tests/contract/baselines/test_mempalace_contract.py tests/live/test_mempalace_live.py
git commit -m "feat: adapt MemPalace MCP memory tools"
```

### Task 7: Baseline Registry, Sequential Ingestion, and Verification Gate

**Files:**
- Create: `src/ke_memory_demo/baselines/registry.py`
- Create: `src/ke_memory_demo/baselines/runner.py`
- Create: `tests/unit/baselines/test_registry.py`
- Create: `tests/integration/test_baseline_runner.py`
- Create: `tests/live/test_all_baselines_smoke.py`
- Modify: `src/ke_memory_demo/cli.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: all four adapters and core artifact/snapshot services.
- Produces: `BaselineRegistry`, `BaselineRunner.ingest_conversation()`, `BaselineRunner.retrieve_all()`, and CLI commands `baseline preflight`, `baseline ingest`, and `baseline smoke`.

- [ ] **Step 1: Write failing order, isolation, and incomplete-run tests**

```python
@pytest.mark.asyncio
async def test_runner_writes_each_system_in_exact_exchange_order(fake_registry):
    exchanges = [sample_exchange(global_ordinal=n) for n in range(3)]
    await BaselineRunner(fake_registry, artifact_store()).ingest_conversation(run_scope("all"), exchanges)
    for adapter in fake_registry.adapters:
        assert adapter.ingested_ordinals == [0, 1, 2]
        assert adapter.max_concurrent_ingests == 1


@pytest.mark.asyncio
async def test_failed_adapter_marks_run_incomplete_without_zero_score(fake_registry):
    fake_registry.adapters[1].fail_on_ingest(2)
    result = await BaselineRunner(fake_registry, artifact_store()).ingest_conversation(run_scope("all"), exchanges_fixture())
    assert result.status == "incomplete"
    assert result.failures[0].system_id == fake_registry.adapters[1].system_id
```

- [ ] **Step 2: Run tests and verify missing runner**

Run: `uv run pytest tests/unit/baselines/test_registry.py tests/integration/test_baseline_runner.py -v`

Expected: FAIL during import.

- [ ] **Step 3: Implement registry and sequential runner**

Load enabled systems from `config/baselines.toml`, create fresh namespaces, preflight every adapter before any BEAM write, ingest serially inside each conversation, persist every receipt immediately, call public readiness, and snapshot a baseline manifest containing source identity, configuration condition, environment manifest, counts, latency, usage, and failures. A resume may skip only an exchange with a verified successful receipt and an idempotent public system record ID.

- [ ] **Step 4: Run non-live baseline suite**

Run: `uv run pytest tests/unit/baselines tests/contract/baselines tests/integration/test_baseline_runner.py -v`

Expected: all tests pass; no live processes or network sockets are used.

- [ ] **Step 5: Run serial live smoke gate**

Run: `uv run ke-memory baseline preflight --config-root config && uv run pytest tests/live/test_all_baselines_smoke.py -v -m live_baseline --maxfail=1`

Expected: each system accepts one Exchange and returns at least one public retrieval result; all source roots remain unchanged.

- [ ] **Step 6: Run formatting, types, and forbidden-access scan**

Run: `uv run ruff format --check . && uv run ruff check . && uv run pyright && ! git grep -nE '/public/home/wwb/memory(/|$)|fusion-memory' -- ':!docs/superpowers/specs/*' ':!docs/superpowers/plans/*'`

Expected: every command exits 0 and the forbidden-access scan finds no runtime reference.

- [ ] **Step 7: Commit**

```bash
git add src/ke_memory_demo/baselines/registry.py src/ke_memory_demo/baselines/runner.py src/ke_memory_demo/cli.py tests/unit/baselines/test_registry.py tests/integration/test_baseline_runner.py tests/live/test_all_baselines_smoke.py README.md
git commit -m "feat: orchestrate frozen memory baselines"
```
