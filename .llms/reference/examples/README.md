# Examples Reference

LLM-facing map of example entrypoints and processor contracts. Use these pages
to locate runnable examples and copy pipeline patterns without tutorial prose.

## Source References

- Examples overview: `examples/README.md:1-51`
- CLI composition baseline: `examples/chat.py:41-199`,
  `examples/live_simple_cli.py:79-132`,
  `examples/realtime_simple_cli.py:81-166`
- Complex examples: `examples/research/agent.py:51-129`,
  `examples/live_commentator/commentator.py:280-930`,
  `examples/live_illustrator/illustrator.py:102-346`,
  `examples/widgets/widgets.py:55-197`
- Shared contracts: `genai_processors/processor.py:149-1649`,
  `genai_processors/content_api.py:39-1226`

## Pages

- [chat.md](chat.md): turn-by-turn CLI chat with URL/PDF fetch and optional MCP tools.
- [live-simple-cli.md](live-simple-cli.md): direct Gemini Live API audio/video CLI.
- [realtime-simple-cli.md](realtime-simple-cli.md): realtime audio conversation built from STT, turn model, TTS.
- [speech-to-text-cli.md](speech-to-text-cli.md): mic input into `SpeechToText`.
- [text-to-speech-cli.md](text-to-speech-cli.md): terminal text into `TextToSpeech` and audio output.
- [trip-request-cli.md](trip-request-cli.md): Gemini structured trip extraction plus itinerary generation.
- [trip-request-cli-ollama.md](trip-request-cli-ollama.md): local Ollama variant of trip extraction/generation.
- [trip-request-adk.md](trip-request-adk.md): ADK wrapper around the trip request processor.
- [vad-cli.md](vad-cli.md): VAD endpointing before a turn-based Gemini model.
- [mcp-server.md](mcp-server.md): demo/local/remote MCP client session helpers.
- [pdf-cli.md](pdf-cli.md): PDF bytes into `PDFExtract`.
- [models.md](models.md): flag-driven model selector used by examples.
- [smart-model.md](smart-model.md): critic/reviser and recursive researcher processors.
- [research.md](research.md): modular research agent using structured topic parts.
- [widgets.md](widgets.md): AI Studio dynamic widgets with async tool output.
- [live-commentator.md](live-commentator.md): event-driven audio/video commentator.
- [live-illustrator.md](live-illustrator.md): live narration-to-illustration processor.

## Cross-Cutting Contracts

- `processor.Processor` consumes a `ProcessorStream` and yields
  `ProcessorPartTypes`; compose stages with `+`.
- `processor.PartProcessor` handles matching individual `ProcessorPart`s and is
  naturally useful for fan-out over structured parts.
- `processor.part_processor_function`, `processor.processor_function`, and
  `processor.create_filter` are the compact stateless forms used in examples.
- `content_api.ProcessorPart` carries content, `mimetype`, `role`,
  `substream_name`, and metadata. Dataclass parts use
  `ProcessorPart.from_dataclass()` and `part.get_dataclass(T)`.
- Reserved/control substreams and metadata drive realtime behavior; do not treat
  all text parts as model-visible prompt text.

## Source Roots

- Runnable examples: `examples/`
- AI Studio applets: `examples/*/ais_app/`
- Core processors: `genai_processors/core/`
- Development server/tracing: `genai_processors/dev/`
