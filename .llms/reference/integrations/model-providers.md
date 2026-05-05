# Model Providers

Use model processors as ordinary `Processor`s: they consume `ProcessorPart`
streams and yield model output parts. Turn-based providers buffer their input
before making one request; they do not keep conversation state, so callers must
pass the full history for multi-turn context.

## Source References

- Gemini metadata, turn model, and image preprocessing:
  `genai_processors/core/genai_model.py:86-322`
- Gemini Live adapter: `genai_processors/core/live_model.py:61-241`
- Client-side realtime wrapper: `genai_processors/core/realtime.py:58-360`
- Ollama model adapter: `genai_processors/core/ollama_model.py:53-301`
- Transformers adapter: `genai_processors/core/transformers_model.py:41-360`
- OpenRouter contrib adapter:
  `genai_processors/contrib/openrouter_model.py:81-360`
- LangChain contrib adapter:
  `genai_processors/contrib/langchain_model.py:42-140`
- Provider tests: `genai_processors/tests/genai_model_test.py:45-260`,
  `genai_processors/tests/live_model_test.py:1-260`,
  `genai_processors/tests/realtime_test.py:1-187`,
  `genai_processors/contrib/tests/openrouter_model_test.py:37-220`,
  `genai_processors/contrib/tests/langchain_model_test.py:32-160`

## Gemini GenAI

`genai_processors.core.genai_model.GenaiModel` wraps
`client.aio.models.generate_content_stream`. Configure it with `api_key`,
`model_name`, optional `GenerateContentConfig`, `debug_config`, `http_options`,
and `stream_json`.

- Input is gathered, converted with `content_api.to_genai_contents`, then sent
  to the GenAI API.
- Streamed candidate parts are wrapped as `ProcessorPart`s with model role and
  metadata from `genai_response_to_metadata`: create time, response ID, model
  version, prompt feedback, usage metadata, automatic function-calling history,
  and parsed output.
- Streaming requests retry GenAI `APIError`s for HTTP 408, 429, 500, 502, 503,
  and 504. Retry count comes from `http_options.retry_options.attempts` or
  defaults to 5.
- If `generate_content_config.response_schema` is set and `stream_json=False`,
  output is piped through `StructuredOutputParser`; set `stream_json=True` to
  receive raw JSON text chunks.
- `ImagePreprocess` uploads image parts through the File API and yields file
  handles; use it before `GenaiModel` to avoid re-uploading/tokenizing images
  in repeated calls.

## Gemini Live API

`genai_processors.core.live_model.LiveProcessor` is the Gemini Live API
adapter. It opens `client.aio.live.connect(model, config)` and runs concurrent
send/receive loops.

- Parts on substream `realtime` are sent with `send_realtime_input`.
  Inline-data parts become media, text parts become realtime text, and parts
  with metadata `audio_stream_end` send the Live audio end signal.
- Default-substream parts are sent with `send_client_content`; metadata
  `turn_complete` controls the Live `turn_complete` flag.
- Function responses are routed with `send_tool_response`.
- Server messages are converted back into `ProcessorPart`s, including model
  turn parts, transcription substreams, tool calls, tool cancellations, usage,
  go-away, and session resumption metadata.
- Unknown non-default substreams pass through unchanged.

## Client-Side Realtime Wrapper

`genai_processors.core.realtime.LiveProcessor` converts any turn-based
processor into a realtime-style bidirectional processor. It keeps a rolling
prompt, pre-processes pending context, and triggers model turns on explicit
end-of-turn parts or speech events.

- `turn_processor` handles one finite prompt; outputs are added back to the
  rolling prompt unless they are reserved substreams.
- `duration_prompt_sec` bounds rolling prompt history; `None` keeps all
  history.
- `AudioTriggerMode.FINAL_TRANSCRIPTION` triggers after final speech
  transcription; `END_OF_SPEECH` triggers earlier for audio-capable models.
- Start-of-speech cancels current output; end-of-speech or end-of-turn starts a
  new generation.
- Each completed model turn emits an empty model part with
  `metadata={"turn_complete": True}`.

## Ollama

`genai_processors.core.ollama_model.OllamaModel` calls a local Ollama
`/api/chat` endpoint.

- Defaults to `http://127.0.0.1:11434`; use `host` to override.
- Accepts `system_instruction`, sampling options, stop sequences,
  `keep_alive`, response schemas, JSON schema, and tools.
- Converts `model` role to Ollama `assistant`, function calls to `tool_calls`,
  function responses to `tool` messages, text to `content`, and images to
  base64 `images`.
- Supports streamed text, streamed tool calls, and image outputs.
- Uses JSON/schema `format` for constrained output; with `response_schema` and
  `stream_json=False`, output is parsed by `StructuredOutputParser`.

## Transformers

`genai_processors.core.transformers_model.TransformersModel` wraps Hugging Face
`AutoProcessor` and `AutoModelForCausalLM`.

- Buffers messages, applies the model chat template, and generates in a worker
  thread with a streamer that pushes `ProcessorPart`s back to asyncio.
- Supports text input, system instructions, sampling options, stop sequences,
  max output tokens, and tool declarations.
- Function calls/responses are mapped to common chat-template structures.
- Image input currently raises `ValueError("Images are not supported yet.")`.
- `tool_response_format` controls whether tool responses are rendered as a
  string or dict for the chat template.

## OpenRouter

`genai_processors.contrib.openrouter_model.OpenRouterModel` streams
OpenRouter `/chat/completions` responses.

- Converts text, images, function calls, and function responses to OpenAI-like
  chat messages.
- Sends `stream=True`; parses SSE `data:` lines until `[DONE]`.
- Supports OpenRouter sampling/provider options, fallback models, transforms,
  tool declarations, tool choice, and JSON response schema conversion.
- Text deltas become model-role `ProcessorPart`s with usage/model metadata when
  present.
- Streaming function-call deltas are accumulated and emitted as one function
  call part at finish.
- HTTP errors include parsed OpenRouter error details when possible.

## LangChain

`genai_processors.contrib.langchain_model.LangChainModel` wraps a LangChain
`BaseChatModel`.

- Prepends optional system instruction, converts parts to LangChain human,
  system, or AI messages, and streams `model.astream`.
- Supports text and image input; images become data URL `image_url` content.
- Output is text-only; non-string streamed output raises
  `NotImplementedError`.
- GenAI-level tool translation and structured/constrained decoding are not
  implemented in this adapter.
