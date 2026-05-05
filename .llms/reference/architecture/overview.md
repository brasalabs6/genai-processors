# Architecture Overview

GenAI Processors is an async streaming composition library. The smallest runtime value is a `ProcessorPart`; parts move through `ProcessorStream`s; `Processor`s transform whole streams; `PartProcessor`s transform one part into zero or more parts and can be lifted to stream processors for concurrent execution.

## Source References

- `genai_processors/__init__.py:27-50` exports the public surface: `ProcessorPart`, `ProcessorContent`, `Processor`, `PartProcessor`, composition helpers, and stream helpers.
- `genai_processors/content_api.py:39-68` defines `ProcessorPart` as content plus role, substream, MIME type, and metadata.
- `genai_processors/content_api.py:695-820` defines `ContentStream`, the async adapter around parts with `.text()` and `.gather()` reducers.
- `genai_processors/content_api.py:841-980` defines `ProcessorContent`, the static multi-part container and coercion point.
- `genai_processors/processor.py:149-283` defines `Processor`: stream-in, stream-out, implement `call`, invoke through `__call__`.
- `genai_processors/processor.py:372-430` defines `PartProcessor`: part-in, stream-out, implement `call`, invoke through `__call__`.
- `genai_processors/context.py:25-53` stores the current processor task group and reserved substreams in context variables.
- `genai_processors/switch.py:34-142` routes streams by first matching case; `genai_processors/switch.py:145-227` routes single parts with `PartSwitch`.

## Model

Use this stack when reading or changing code:

1. Content enters as broad `ProcessorContentTypes` or `ProcessorPartTypes`.
2. Boundaries normalize content to `ProcessorPart`.
3. A `Processor` consumes an async stream of parts and yields an async stream of parts.
4. A `PartProcessor` consumes one normalized part and yields zero or more parts.
5. Composition helpers lift part processors into stream processors and schedule concurrent work.
6. `context.context()` provides task-group ownership and the reserved-substream table.
7. Reserved substreams are out-of-band lanes: they bypass downstream processors and are yielded promptly.

## Invariants

- Do not call `Processor.call()` or `PartProcessor.call()` directly. Use `p(content)` or `part_processor(part)` so normalization, tracing, context handling, and match behavior run.
- Do not assume processor output is text. Preserve `ProcessorPart` until a boundary truly needs `.text()`, `.as_text()`, or `.gather()`.
- Do not treat substreams as separate Python iterables. A substream is metadata on each `ProcessorPart`.
- A stream processor may reorder output across concurrent branches, but each branch preserves its own local order.
- Reserved substreams are control/data lanes, not model-input lanes; chain and parallel composition capture them before handing parts to the next processor.

## Read Next

- `.llms/reference/concepts/content-model.md`
- `.llms/reference/concepts/processors-and-composition.md`
- `.llms/reference/concepts/substreams-and-routing.md`
- `.llms/reference/architecture/async-context-and-taskgroups.md`
