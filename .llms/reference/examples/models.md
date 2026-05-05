# Example Model Selector

## Source References

- `examples/models.py`
- `examples/chat.py`
- `examples/realtime_simple_cli.py`
- `examples/smart_model.py`
- `genai_processors/core/genai_model.py`
- `genai_processors/core/ollama_model.py`
- `genai_processors/core/transformers_model.py`
- `genai_processors/contrib/langchain_model.py`

## Entrypoint

- Imported helper, not a standalone CLI.
- Main API: `turn_based_model(system_instruction, tools=None,
  disable_automatic_function_calling=False)`.
- Flags: `--model_type=gemini|ollama|langchain|transformers`,
  `--model_name`, `--api_service_address`.

## Pipeline / Data Flow

- Converts `system_instruction` into model-specific config.
- Gemini path creates `genai_model.GenaiModel` with Google Search as default
  tool unless `tools` is supplied.
- Ollama path creates `ollama_model.OllamaModel`.
- LangChain path wraps `langchain_google_genai.ChatGoogleGenerativeAI` in
  `LangChainModel`.
- Transformers path creates `transformers_model.TransformersModel`.
- Gemini `--model_name=critic:<name>` wraps the base model in
  `smart_model.CriticReviser`.
- Gemini `--model_name=research:<name>` returns `smart_model.Researcher`.

## Dependencies / Env

- Requires `GOOGLE_API_KEY` at module import time.
- LangChain mode requires `langchain_google_genai`.
- Transformers and Ollama modes require their respective runtime dependencies.

## Demonstrated Processor Contracts

- Model adapters are all returned as `processor.Processor`.
- Backend selection is hidden behind a common turn-based processor contract.
- Tool declarations can be callables, Gemini `Tool`s, or MCP sessions depending
  on backend support.

## Dispatch Matrix

| `--model_type` | Returned Processor | Tool Handling | Notes |
| --- | --- | --- | --- |
| `gemini` | `GenaiModel` or smart wrapper | Gemini tools / disabled auto mode as requested | Supports `critic:` and `research:` prefixes. |
| `ollama` | `OllamaModel` | provider-compatible function declarations | Local service dependency. |
| `langchain` | `LangChainModel` | limited by wrapped LangChain chat model | Converts text/image parts only. |
| `transformers` | `TransformersModel` | local transformer adapter | Dependency/runtime heavy. |

Semantic formula:

```text
turn_based_model(flags, config) -> Processor[ProcessorStream -> ProcessorStream]
```

Examples should depend on the returned processor contract, not concrete provider
classes. Provider-specific setup belongs in this selector.

## Gotchas

- This helper is intentionally example-only and flag-driven.
- `GOOGLE_API_KEY` is read even if selecting non-Gemini modes.
- Default Gemini config uses `api_version='v1alpha'` and includes server-side
  tool invocation parts.
- `--api_service_address` is defined but not used by current paths.
