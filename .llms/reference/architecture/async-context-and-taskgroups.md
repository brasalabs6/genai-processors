# Async Context And TaskGroups

`genai_processors.context` owns two runtime contracts: spawned tasks should join the current processor task group, and reserved substreams should be visible to composition code through context variables.

## Source References

- `genai_processors/context.py:25-53` declares context variables for the current task group and reserved substreams.
- `genai_processors/context.py:66-128` defines `CancellableContextTaskGroup`, task tracking, contextvar setup/reset, exception flattening, and cancellation.
- `genai_processors/context.py:130-147` exposes `context()`, `task_group()`, `get_reserved_substreams()`, and `is_reserved_substream()`.
- `genai_processors/context.py:150-174` implements `create_task`; it uses the current task group when present and keeps references to background tasks when absent.
- `genai_processors/context.py:180-189` cancels context tasks when a wrapper coroutine is cancelled.
- `genai_processors/processor.py:199-251` explains why processor invocation uses a queue inside a task group when no context exists.
- `genai_processors/map_processor.py:207-243`, `genai_processors/map_processor.py:259-317`, and `genai_processors/map_processor.py:340-383` eagerly schedule part-function work through `context.create_task`.
- `genai_processors/streams.py:27-78` notes `split()` should be used with processor context for error propagation.

## Contract

Use `processor.context()` or `context.context()` around manual async orchestration. Inside that context, `processor.create_task()` and `context.create_task()` attach work to the active `CancellableContextTaskGroup`; outside it, tasks are created with `asyncio.create_task` and retained in a module-level set until done.

The same context carries the reserved-substream set. By default, `debug`, `status`, and `ui` are reserved. Passing `reserved_substreams=[...]` replaces the reserved set for that context.

## Invariants

- Use `context.create_task` or the alias `processor.create_task` for framework tasks so failures and cancellation propagate through the active task group.
- Do not use a raw `asyncio.create_task` inside processors unless escaping processor cancellation is intentional.
- Do not keep async generators open across unrelated contexts; context reset can see `GeneratorExit` from a different context.
- Reserved-substream membership is prefix-based: `part.substream_name.startswith(prefix)`.
- A custom `reserved_substreams` argument replaces the current reserved set for that context, it does not append to the default set.
- Composition helpers rely on the context task group; missing context is patched at processor invocation boundaries, but explicit context is clearer for manual stream utilities.

## Read Next

- `.llms/reference/architecture/runtime-flow.md`
- `.llms/reference/concepts/substreams-and-routing.md`
- `.llms/reference/concepts/processors-and-composition.md`
