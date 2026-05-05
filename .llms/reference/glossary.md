# Glossary

Concise terms for LLM agents. Prefer these names over invented abstractions.

## Source References

- Core package exports: `genai_processors/__init__.py:22-50`
- Content primitives and helpers: `genai_processors/content_api.py:39-1226`
- Processor primitives and composition: `genai_processors/processor.py:110-1649`
- Stream helpers: `genai_processors/streams.py:27-265`
- Context and reserved substreams: `genai_processors/context.py:25-158`

## Core Terms

- `ProcessorPart`: one content item. It wraps a Google GenAI `Part` and adds
  role, substream, MIME type, and metadata. Source:
  `genai_processors/content_api.py`.
- `ProcessorContent`: a collection-like wrapper that normalizes accepted input
  content into parts. Source: `genai_processors/content_api.py`.
- `ProcessorPartTypes`: accepted single-part inputs, including existing
  `ProcessorPart` values and plain supported payloads such as strings. Source:
  `genai_processors/content_api.py`.
- `ProcessorContentTypes`: accepted multi-part inputs for processor calls.
  `llms.txt` says to pass these directly instead of over-wrapping.
- `ProcessorStream`: async stream returned by a processor call. It carries the
  underlying async iterable plus optional trace state. Source:
  `genai_processors/processor.py`.
- `Processor`: class abstraction for a stream-to-stream transformation.
  Implement `call`; invoke via `__call__`. Source:
  `genai_processors/processor.py`.
- `PartProcessor`: per-part transformation that can run concurrently over a
  stream. It may define `match(part)` to skip unsupported parts. Source:
  `genai_processors/processor.py`.
- `ProcessorFn`: async generator function matching the processor protocol.
  Source: `genai_processors/processor.py`.
- `PartProcessorFn`: async generator function for one input part. Source:
  `genai_processors/processor.py`.
- `part_processor_function`: decorator that wraps a `PartProcessorFn` as a
  `PartProcessor`; optionally accepts `match_fn`. Source:
  `genai_processors/processor.py`.

## Content And Stream Terms

- `mimetype`: MIME type attached to a part. Empty underlying MIME is treated as
  text. Non-text `.text` access raises `ValueError`. Sources:
  `genai_processors/content_api.py`, `llms.txt`.
- `role`: optional content producer label. Gemini model roles must be `user` or
  `model`, but the library leaves semantics to callers. Source:
  `genai_processors/content_api.py`.
- `substream_name`: logical stream name within a part stream. Empty string is
  the default stream. Source: `genai_processors/content_api.py`.
- `metadata`: arbitrary per-part key-value data. Source:
  `genai_processors/content_api.py`.
- `gather()`: convenience method on content streams used by `llms.txt` as the
  preferred way to execute and collect processor output.
- `stream_content`: exported helper for normalizing content streams. Source:
  `genai_processors/__init__.py`, `genai_processors/streams.py`.
- `split`: duplicates one async stream into multiple streams; use copy mode
  when downstream processors mutate parts. Source: `genai_processors/streams.py`.
- `concat`: consumes streams concurrently and yields each stream's output in
  argument order. Source: `genai_processors/streams.py`.
- `merge`: interleaves multiple streams by availability and preserves order only
  within each source stream. Source: `genai_processors/streams.py`.

## Composition Terms

- `+`: processor chaining operator. Source: `genai_processors/processor.py`.
- `//`: parallel operator for `PartProcessor` composition. Source:
  `genai_processors/processor.py`.
- `chain([...])`: sequence composition helper; converts all-part-processor
  chains to a `Processor`. Source: `genai_processors/processor.py`.
- `parallel([...])`: creates a parallel `PartProcessor`. Source:
  `genai_processors/processor.py`.
- `parallel_concat([...])`: runs processors in parallel and concatenates their
  outputs. Source: `genai_processors/processor.py`.
- `key_prefix`: cache/key collision prefix, usually class name unless arguments
  change output. Source: `genai_processors/processor.py`.
- `trace_name`: shorter human-readable trace label. Source:
  `genai_processors/processor.py`.

## Semantic Categories

Use these categories when reading or writing docs:

| Category | Carrier | Typical Meaning |
| --- | --- | --- |
| Content | text, bytes, image, file, dataclass part | Model-visible or user-visible data. |
| Routing | `substream_name` | Selects a lane such as realtime, status, debug, UI, error. |
| State | empty part + metadata | Signals events like turn completion, interruption, usage, go-away. |
| Tool protocol | function call/response part | Represents model tool invocation and local result. |
| Provenance | metadata fields | Tracks source filename, model name, usage, capture time. |

Rule of thumb:

```text
value changes what is said
substream changes where it goes
metadata changes how it is interpreted
```

## Common Misreads

- A text part on a named substream is not automatically prompt text.
- Empty text is not necessarily meaningless; metadata may carry the whole
  signal.
- `.text` is safe only for text-like MIME types.
- `ProcessorContent` normalizes inputs; it does not imply the stream has been
  executed.
- `gather()` is an execution choice that trades streaming behavior for full
  collection.
