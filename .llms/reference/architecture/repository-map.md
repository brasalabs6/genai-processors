# Repository Map

This map is for LLM navigation. Prefer the files below before widening a search.

## Core Runtime

- `genai_processors/content_api.py`: content wrappers, coercion, MIME helpers, text/image reducers, GenAI conversion.
- `genai_processors/processor.py`: processor interfaces, decorators, composition operators, chain/parallel internals, cache wrappers, sources.
- `genai_processors/map_processor.py`: concurrent execution engine for part functions over streams and trees.
- `genai_processors/streams.py`: async stream utilities: split, concat, merge, enqueue/dequeue, gather.
- `genai_processors/context.py`: contextvars, cancellable task group, `create_task`, reserved-substream table.
- `genai_processors/switch.py`: stream and part routing by cases.

## Public Entry Points

- `genai_processors/__init__.py:27-50` re-exports the common API.
- `llms.txt:1-32` gives high-level guidance for coding agents.
- `documentation/docs/` contains human-facing guides; use source files for contract-level details.
- `examples/` shows application assembly and core usage.

## Built-In Processors

- `genai_processors/core/genai_model.py`: GenAI model stream processor.
- `genai_processors/core/live_model.py`, `core/realtime.py`: realtime/live streaming contracts.
- `genai_processors/core/function_calling.py`: tool/function-call processors.
- `genai_processors/core/text.py`: terminal IO, text extraction, regex/window-style processors.
- `genai_processors/core/audio.py`, `core/audio_io.py`, `core/video.py`: multimodal processors.
- `genai_processors/core/pdf.py`, `core/filesystem.py`, `core/web.py`, `core/github.py`, `core/drive.py`: IO and document ingestion.
- `genai_processors/contrib/`: optional integrations such as LangChain and OpenRouter.

## Test Anchors

- `genai_processors/tests/content_api_test.py`: coercion, serialization, reducers.
- `genai_processors/tests/processor_test.py`: chain, parallel, match, reserved-substream, cache behavior.
- `genai_processors/tests/map_processor_test.py`: concurrent tree execution behavior.
- `genai_processors/tests/streams_test.py`: stream utilities.
- `genai_processors/tests/switch_test.py`: routing and ordering behavior.
- `genai_processors/tests/context_test.py`: task group and cancellation behavior.

## Source References

- `genai_processors/processor.py:42-57` aliases context constants and stream helpers into the processor module.
- `genai_processors/processor.py:560-667` provides decorators and top-level composition constructors.
- `genai_processors/processor.py:898-970` fuses processor chains and lifts part processors.
- `genai_processors/map_processor.py:98-194` exposes map/chain/parallel part-function constructors.
- `genai_processors/streams.py:27-111` provides split/concat behavior; `genai_processors/streams.py:136-230` provides merge and queues.
- `genai_processors/switch.py:34-227` is the routing module.

## Invariants

- Start with `content_api.py`, `processor.py`, `context.py`, `streams.py`, `map_processor.py`, and `switch.py` for framework behavior.
- Use tests as contract evidence when behavior involves concurrency, order, or reserved streams.
- Avoid changing core composition semantics from a built-in processor file; composition contracts live in `processor.py` and `map_processor.py`.
- Public import availability is controlled by `__init__.py`; internal helpers may be intentionally omitted.

## Read Next

- `.llms/reference/architecture/runtime-flow.md`
- `.llms/reference/concepts/processors-and-composition.md`
- `.llms/reference/concepts/substreams-and-routing.md`
