# Runtime Flow

Processor calls are lazy async streams. Calling a processor returns a `ProcessorStream`; work happens as the stream is consumed, gathered, or awaited.

## Source References

- `genai_processors/processor.py:87-108` normalizes sync or async content into `ProcessorPart` objects.
- `genai_processors/processor.py:149-178` wraps a `Processor` call in a `ProcessorStream` and creates trace context.
- `genai_processors/processor.py:187-258` implements processor invocation, including input normalization, trace IO, and context creation when missing.
- `genai_processors/processor.py:372-405` normalizes a `PartProcessor` input and applies `match()` before `call()`.
- `genai_processors/content_api.py:815-836` executes a stream via `.gather()` or `await stream`.
- `genai_processors/processor.py:520-557` implements `apply_async` and `apply_sync` by lifting to a processor and gathering.
- `genai_processors/streams.py:266-268` gathers any async iterable into a list.

## Flow

1. Caller invokes `processor(content)`.
2. `Processor.__call__` returns `ProcessorStream(self._call_impl(...))`.
3. When consumed, `_call_impl` wraps non-stream inputs with `_normalize_part_stream`.
4. If no processor context exists, `_call_impl` opens `context()` and uses a queue so generator yields and task-group cancellation stay connected.
5. `Processor.call(content_stream)` yields raw `ProcessorPartTypes`.
6. `_normalize_part_stream` converts yielded raw values into `ProcessorPart`.
7. The returned `ProcessorStream` can be iterated, gathered into `ProcessorContent`, reduced to text, or awaited for side effects.

For a `PartProcessor`, the flow is narrower:

1. Caller invokes `part_processor(part)`.
2. `PartProcessor.__call__` coerces raw input to `ProcessorPart`.
3. `_call_impl` returns the input unchanged if `match(part)` is false.
4. Otherwise `call(part)` yields zero or more parts, normalized through `_normalize_part_stream`.

## Invariants

- Invocation is separate from execution. A returned `ProcessorStream` may do no work until consumed.
- `Processor.call()` receives a `ProcessorStream`, not a list.
- `PartProcessor.call()` receives exactly one `ProcessorPart`.
- `PartProcessor.match(part) == False` means pass-through in normal chains/apply; parallel composition has extra fallback/drop semantics.
- Use `await processor(input).gather()` when all output is needed; use streaming iteration only when arrival order matters.
- Non-`ProcessorPart` outputs are allowed only if they are valid `ProcessorPartTypes`; otherwise normalization raises a producer-tagged `ValueError`.

## Read Next

- `.llms/reference/concepts/content-model.md`
- `.llms/reference/concepts/processors-and-composition.md`
- `.llms/reference/architecture/async-context-and-taskgroups.md`
