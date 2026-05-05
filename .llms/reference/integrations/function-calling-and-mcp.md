# Function Calling And MCP

`genai_processors.core.function_calling.FunctionCalling` is the tool-use loop.
It wraps a model processor, intercepts model-emitted function calls, executes
matching Python or MCP tools, injects function responses back into the prompt,
and repeats until no more work is scheduled or the call limit is reached.

## Source References

- Function-call part constructors and helpers:
  `genai_processors/content_api.py:402-430`
- FunctionCalling runtime:
  `genai_processors/core/function_calling.py:202-660`
- MCP adapters: `genai_processors/mcp.py:48-151`
- Tool declaration utilities: `genai_processors/tool_utils.py:1-162`
- Function-calling tests:
  `genai_processors/tests/function_calling_test.py:101-760`,
  `genai_processors/tests/mcp_test.py:1-220`,
  `genai_processors/tests/tool_utils_test.py:1-136`

## Model Contract

- The model must emit `ProcessorPart`s whose underlying GenAI `Part` contains
  `function_call`.
- Tool results are represented as `ProcessorPart.from_function_response(...)`.
- The model adapter is responsible for formatting/parsing tool parts for its
  provider. For Gemini, pass the same tools to the model config and to
  `FunctionCalling`, and disable SDK automatic function calling to avoid
  duplicate calls.
- Function-call traffic is tagged with the configured substream, default
  `function_call`.
- Function calls already carrying a substream are treated as already handled.

## Constructor

Use:

```python
FunctionCalling(
    model,
    is_bidi_model=False,
    substream_name="function_call",
    pre_processor=None,
    fns=[tool_fn],
    max_function_calls=None,
)
```

- `model` may be turn-based or bidi/realtime.
- `is_bidi_model=False` wraps the model into a bidi-style loop internally.
- `pre_processor` runs over original input, function responses, and model
  output from previous iterations before each model call.
- `fns` may contain Python callables and MCP client sessions.
- Default `max_function_calls` is 5 for turn-based models and unbounded for
  bidi models.

## Tool Execution

Tools must have JSON-serializable arguments. Return values may be
JSON-serializable values, `ProcessorPart`s, `ProcessorContent`, or explicit
function-response parts.

- Sync tool + turn-based model: run in a worker thread and block the next model
  turn until complete.
- Async function or async generator: returns an immediate silent
  `"Running in background."` function response with a function-call ID, then
  streams later responses back into the loop.
- Sync tool + bidi model: treated like async so the realtime model is not
  blocked.
- Async generators emit streaming function responses. The wrapper sets
  `will_continue=True` until the generator finishes, then emits an empty final
  response with `will_continue=False`.
- Unknown tools and tool exceptions become error function responses instead of
  uncaught exceptions.

## Scheduling

Function responses may use GenAI `FunctionResponseScheduling`.

- `SILENT`: add to the prompt without triggering model output.
- `WHEN_IDLE`: trigger after the current model output finishes.
- Other scheduling, including interrupt-style behavior, requests an immediate
  model turn by injecting end-of-turn.

The loop tracks whether the model is outputting, how many function calls are
running, and whether another model call is scheduled.

## Cancellation And Listing

`cancel_fc(function_ids)` and `list_fc()` are interface functions to expose to
models. In bidi mode, `FunctionCalling` installs real implementations.

- `list_fc` returns a function response describing running background calls.
- `cancel_fc` cancels matching tool tasks and returns an error response when
  requested IDs are missing.
- A model can also emit tool-cancellation parts; `ProcessorPart` exposes
  `tool_cancellation` for function responses named `tool_cancellation`.

## MCP

`genai_processors.mcp` converts MCP tools into Python callables usable by
`FunctionCalling`.

- Pass a GenAI MCP client session in `fns`; initialization runs lazily on the
  first processor call.
- Each MCP tool becomes an async callable named after the MCP tool and with the
  MCP description as its docstring.
- `create_mcp_tool(session, tool)` calls `session.call_tool(tool.name, kwargs)`.
- MCP tool errors raise `McpToolError`; `FunctionCalling` catches it and emits
  an error function response.
- MCP `TextContent`, `ImageContent`, `AudioContent`, embedded resources, and
  resource links are converted into `ProcessorPart`s, then wrapped in one
  function response.

## Tool Declarations

`genai_processors.tool_utils` turns Python callables and GenAI `Tool`s into
provider payloads.

- `to_function_declarations` uses GenAI SDK schema inference and docstring
  parsing to populate declaration descriptions and parameter descriptions.
- `function_declaration_to_json` emits an OpenAI/Ollama-style function tool
  JSON object.
- Server-side Gemini tools such as retrieval, Google Search, Maps, URL context,
  code execution, and computer use are rejected for non-Gemini providers unless
  explicitly allow-listed.
