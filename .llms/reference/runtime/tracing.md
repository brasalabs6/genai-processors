# Tracing

Tracing records processor execution as a hierarchy of timestamped events:
inputs, outputs, sub-processor calls, errors, cancellations, and multimodal
parts. The trace format is incubating and not guaranteed stable.

## Source References

- Trace interface and excluded modules: `genai_processors/dev/trace.py:36-240`
- File trace event model and backend:
  `genai_processors/dev/trace_file.py:107-236`
- Processor trace integration: `genai_processors/processor.py:149-283`
- Trace tests: `genai_processors/tests/trace_file_test.py:117-260`
- Published tracing guide: `documentation/docs/development/tracing.md:1-150`

## Activation

Run a pipeline inside an async `Trace` context, usually
`trace_file.SyncFileTrace(trace_dir=..., name=...)`. `Processor.__call__` and
`PartProcessor` wrappers create sub-traces automatically when a trace is active.
No changes are needed in ordinary processor implementations.

## Trace Interface

Subclass `genai_processors.dev.trace.Trace` to implement another backend.
Required operations:

- `add_input(part)`: record an input part.
- `add_output(part)`: record an output part.
- `add_sub_trace(name, relation)`: create and attach a nested trace.
- `add_error(error_message)`: record processor failure.
- `cancel()`: mark cancellation and optionally trim incomplete events.
- `_finalize()`: flush/store the trace when the context exits.

`Trace` stores `name`, optional `processor_description`, `trace_id`,
`start_time`, `end_time`, `error`, `cancelled`, and `is_sub_trace`.

## Parent And Sub-Trace Rules

- `create_sub_trace(processor_name, parent_trace)` uses an explicit parent from
  the input stream when present; otherwise it uses the current trace context.
- Relation is `call` for a processor called under a root trace and `chain` when
  the input stream already carries a trace.
- Sub-traces are marked `is_sub_trace=True`.
- Modules in `EXCLUDED_TRACE_MODULES` do not create their own traces, but their
  children can still be traced. Defaults include `genai_processors.debug` and
  `genai_processors.map_processor`.

## File Trace Backend

`trace_file.SyncFileTrace` collects events in memory and writes JSON and HTML
files on finalize when `trace_dir` is set.

- Output filenames are `{name}_{trace_id}.json` and `.html`.
- `TraceEvent` may hold an input/output part hash, a nested sub-trace relation,
  or an error message.
- Root traces keep a deduplicated `parts_store`; events reference parts by
  hash.
- Part dictionaries are serialized with bytes base64-encoded for JSON/HTML.
- `metadata["capture_time"]` is dropped before hashing.
- Images are resized to `image_size` by default `(200, 200)`; set `None` to
  keep original image bytes.
- `max_size_bytes` causes later part content to be omitted after the size limit
  is exceeded while retaining metadata and envelope fields.
- `SyncFileTrace.load(path)` loads a saved JSON trace.

## Error And Cancellation Recording

- On non-cancellation exceptions, `Trace.__aexit__` stores the formatted
  traceback in `trace.error` and adds an error event before finalization.
- On `asyncio.CancelledError`, traces are marked `cancelled`.
- File traces cancel their worker task; if no output was produced, they clear
  incomplete events.
- Finalization is shielded from cancellation so traces can still be saved.

## Trace Names

Processors expose `trace_name`, usually the class name or wrapper name.
Composed chains and parallel part processors build combined names while
excluding modules registered as trace-noise. Override `trace_name` for shorter
human-readable labels in trace viewers.
