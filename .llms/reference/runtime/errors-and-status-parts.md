# Errors And Status Parts

Errors, status, debug, and UI messages are represented as ordinary
`ProcessorPart`s with reserved substream names or exception MIME types. This
lets pipelines carry operational state without sending those parts through
model prompts or downstream processors that should ignore them.

## Source References

- Reserved substream constants and context: `genai_processors/context.py:25-158`
- Status/debug helpers and reserved capture:
  `genai_processors/processor.py:510-515`,
  `genai_processors/processor.py:973-1073`
- Exception-to-part wrapper: `genai_processors/processor.py:1453-1521`
- Exception MIME and end-of-turn helpers:
  `genai_processors/mime_types.py:1-120`,
  `genai_processors/content_api.py:987-1044`
- Function-calling error handling:
  `genai_processors/core/function_calling.py:402-620`
- Trace error recording: `genai_processors/dev/trace.py:36-240`

## Reserved Substreams

Default reserved substreams are:

- `debug`: debug information embedded in the conversation timeline.
- `status`: one-line task progress or recoverable failure messages.
- `ui`: parts intended to bypass model processing and go directly to the user.

Any substream whose name starts with a reserved prefix is also reserved.
`context.context(reserved_substreams=...)` can replace the reserved set for the
current async context.

## Capture Contract

When processors are chained, reserved substream parts are captured and yielded
immediately instead of being passed to the next processor. This applies to both
processor chains and part-processor chains.

- Use `processor.debug(content, **kwargs)` to create a debug part.
- Use `processor.status(content, **kwargs)` to create a status part.
- Use reserved substreams for out-of-band progress, logs, UI events, and
  partial failures that should not affect model context unless explicitly
  reintroduced.

## Exception Parts

Decorate processor or part-processor `call` methods with
`processor.yield_exceptions_as_parts` to convert thrown exceptions into status
parts instead of failing the pipeline.

The generated part has:

- `mimetype="text/x-exception"`.
- `substream_name="status"`.
- text formatted as an unexpected-error message.
- metadata `original_exception` and `exception_type`.

Use `mime_types.is_exception(part.mimetype)` to detect exception parts instead
of relying on exact text formatting.

## Cache Interaction

Cache hashing returns `None` for inputs containing exception parts, making them
uncacheable. Cache wrappers also skip storing outputs that contain
`text/x-exception`. Failed or partial operations should therefore not poison
future cache hits.

## Function-Calling Errors

Function-calling failures are encoded as function responses with `is_error=True`.
This stores the error under the function response's `error` field.

Common cases:

- Unknown tool name: emits an error response listing available tools.
- Tool exception: emits an error response containing the failed invocation.
- MCP `isError` result: raises `McpToolError`, which the function-calling loop
  converts into an error function response.
- `cancel_fc` can emit an error response when requested IDs are missing.

## End Of Turn And Completion Status

End-of-turn is an empty user `ProcessorPart` with metadata
`{"turn_complete": True}`. `content_api.is_end_of_turn(part)` detects it.

- `ProcessorPart.end_of_turn()` creates the user signal.
- Realtime wrappers and function-calling loops use it to schedule or delimit
  model turns.
- `realtime.LiveProcessor` emits an empty model part with
  `metadata={"turn_complete": True}` after each generated turn.
- OpenRouter emits an empty model part with `finish_reason` and
  `turn_complete=True` at stream finish.

## Trace Errors

Tracing records uncaught exceptions separately from status exception parts.
When a traced processor raises, the trace stores a formatted traceback in
`trace.error` and adds an error event. Cancellation is recorded as
`cancelled=True`, not as a normal error.
