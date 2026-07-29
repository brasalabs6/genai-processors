# AGENTS.md

## Repository Scope and Maturity

This file applies to the entire repository unless a more local `AGENTS.md`
overrides it.

This repository is a production-facing Python library published as
`genai-processors`. Preserve public APIs, content contracts, processor
composition semantics, environment contracts, and externally consumed behavior
unless a breaking change and migration are explicitly requested.

The repository is a fork of the Google Gemini project and may diverge from its
upstream. Do not assume upstream ownership, access, or compatibility beyond what
can be verified in this workspace.

Before using or modifying the library, read:

1. `llms.txt`
2. `README.md`
3. `pyproject.toml`
4. The relevant guide under `documentation/docs/`
5. The implementation and tests for the processors being changed

For live-agent work, also read:

- `documentation/docs/concepts/realtime.md`
- `documentation/docs/development/websocket-server.md`
- `examples/live_commentator/README.md`
- `examples/live_commentator/commentator.py`
- `genai_processors/core/live_model.py`
- `genai_processors/core/realtime.py`

## Architecture and Core Contracts

GenAI Processors is an asynchronous, streaming, multimodal pipeline library.
Its model-independent contract is more important than any provider SDK.

### Content model

- `genai_processors/content_api.py` owns `ProcessorPart`,
  `ProcessorContent`, and `ContentStream`.
- A `ProcessorPart` wraps a Google GenAI `Part` and adds `role`, `mimetype`,
  `substream_name`, and `metadata`.
- Preserve multimodal parts as long as possible. Do not reduce a stream to text
  unless the next boundary is intentionally text-only.
- Check a part's modality with helpers such as `content_api.is_text`,
  `content_api.is_audio`, and `content_api.is_image` before using
  modality-specific accessors.
- Use `await processor(input).gather()` for finite output collection and
  `.text()` only when text narrowing is intended.

### Processor model

- `genai_processors/processor.py` owns `Processor`, `PartProcessor`, stream
  normalization, tracing integration, and composition.
- Implement stream processors by subclassing `Processor` and defining
  `async call(content)`. Yield `ProcessorPartTypes`; let the library normalize
  accepted values.
- `a + b` is a sequential pipeline.
- `a // b` is parallel fan-out with concatenated outputs.
- Composition must preserve backpressure, cancellation, and reserved
  substreams. Do not replace asynchronous streams with eager lists in live
  paths.
- Use `processor.create_task` for library-managed tasks so tracing and context
  behavior are retained.

### Substreams and control metadata

Substreams and metadata are runtime contracts, not incidental fields.

- `realtime`: device audio, camera frames, screen frames, and realtime text.
- Default substream (`''`): regular turn-based content.
- `input_transcription`: STT output used by the turn-based realtime loop.
- `output_transcription`: model audio transcription.
- Reserved debug/status substreams bypass ordinary chained processors.
- Important control metadata includes `turn_complete`, `audio_stream_end`,
  `generation_complete`, `interrupted`, `interrupt_request`, `go_away`,
  `health_check`, and session-resumption data.

When adding a new provider or UI, translate provider-specific events at the
adapter boundary and keep these internal semantic contracts stable.

## Repository Map

- `genai_processors/`: public package and foundational contracts.
- `genai_processors/core/`: maintained general-purpose processors, including
  Gemini, Ollama, Transformers, realtime orchestration, audio/video, VAD, STT,
  TTS, event detection, function calling, and windowing.
- `genai_processors/contrib/`: optional community integrations whose
  dependencies must remain outside the base dependency set when practical.
- `genai_processors/dev/`: development serving, tracing, and diagnostics.
- `genai_processors/tests/`: core unit and behavior tests.
- `examples/`: executable reference applications; example-only selectors are
  not public backend abstractions.
- `documentation/docs/`: user and architecture documentation.
- `notebooks/`: learning material, not the canonical runtime implementation.
- `.github/workflows/`: CI and documentation deployment.

Add reusable processors to `core` only when they are truly general and their
dependency cost is appropriate. Follow `CONTRIBUTING.md` for optional or
community processors under `contrib`.

## Live and Realtime Architectures

There are two intentionally different live paths:

1. `core.live_model.LiveProcessor` wraps the Gemini Live API. The server owns
   conversation state, native audio generation, VAD, realtime multimodal input,
   and Live tool-call semantics.
2. `core.realtime.LiveProcessor` wraps any finite, turn-based `Processor` in a
   client-side conversation loop. It owns a rolling prompt, turn triggers,
   cancellation, and interruption.

Do not hide this distinction behind a model-name conditional. Select a runtime
by explicit capabilities.

### Live Commentator

`examples/live_commentator/commentator.py` composes:

```text
device/browser stream
  -> EventDetection(turn-based vision model)
  -> LiveCommentator(state machine + Gemini Live session)
  -> RateLimitAudio(24 kHz)
  -> browser or local speaker
```

The event detector passes all input through while asynchronously classifying
recent frames. Its transition outputs start commentary, stop commentary, or
request an interruption.

`LiveCommentator` owns commentary state, timing, chattiness, interruption
coordination, wait-for-user behavior, and time-to-first-audio estimates. Gemini
Live currently owns native VAD, audio generation, conversation state, and
non-blocking `start_commentating` / `wait_for_user` tool-call behavior.

`RateLimitAudio` is required for useful barge-in behavior: generated audio must
not be queued far ahead of what the user has heard.

The browser path is:

```text
Vite + TypeScript standalone app
  <-> JSON ProcessorPart messages over ws://localhost:8765
  <-> genai_processors.dev.live_server
  <-> per-connection Processor instance
```

The browser supplies echo cancellation, microphone/camera/screen capture,
base64 media transport, PCM playback, and transcript display. The backend must
keep provider credentials server-side.

## Planned Conversational Screen Agent

The intended evolution is a conversational agent that sees the user's screen,
listens, and speaks in real time. Until implementation is explicitly requested,
do not change model constants, provider behavior, prompts, or the current
commentator runtime.

Keep the future design split into these responsibilities:

- **Objective/persona**: a typed configuration that owns system instructions,
  interaction style, proactivity, language, and tool policy. Changing the
  agent's purpose must not require editing transport or provider adapters.
- **Conversation runtime**: owns turns, history, cancellation, barge-in,
  silence/wait policy, and proactive visual-event triggers.
- **Vision policy**: selects or summarizes screen frames. Do not retain every
  frame in the rolling prompt; `core.realtime.LiveProcessor` currently
  re-tokenizes retained images on every turn.
- **STT adapter**: emits final/interim transcription plus
  `speech_events.StartOfSpeech` and `speech_events.EndOfSpeech`. A future Groq
  Whisper adapter must conform to this contract.
- **LLM adapter**: a turn-based `Processor` selected independently from STT and
  TTS. Existing candidates include Gemini, Ollama, Transformers, LangChain, and
  OpenRouter integrations.
- **TTS adapter**: consumes model text incrementally where supported and emits
  correctly labelled PCM/audio parts. A local TTS implementation must declare
  sample rate, channels, sample width, voice, language, cancellation behavior,
  and thread/process execution for blocking inference. CUDA-backed engines such
  as XTTS must remain optional and must also expose a CPU-safe configuration.
- **Local acceleration**: diarization, Parakeet, and XTTS may share a CUDA
  runtime, but each integration must declare VRAM expectations, device
  selection, CPU fallback, model download/cache behavior, and compatible
  PyTorch/CUDA versions. Never make the base library require a CUDA wheel.
- **Playback pacing**: `RateLimitAudio` followed by an interruption-aware
  browser or local audio sink.
- **Composition root**: validates provider configuration and constructs one of
  the supported pipelines. Provider-specific SDK objects must not leak into the
  state machine or WebSocket protocol.

The two expected compositions are:

```text
Native Live:
browser media -> event policy -> Gemini Live adapter -> RateLimitAudio

Cascaded fallback:
browser PCM -> VAD/endpointing -> Groq Whisper STT
            -> turn-based realtime conversation -> selected LLM
            -> local TTS -> RateLimitAudio
browser screen frames -> vision policy ----------------------^
```

The cascaded path cannot depend on Gemini's non-blocking Live tool calls.
Scheduling the next utterance, waiting for the user, and proactive interruption
must be explicit runtime state transitions. Model tool calls may request
actions, but they must not be the only mechanism keeping the conversation
alive.

Select backends using a capability description, including:

- accepted input modalities;
- streaming output support;
- native audio input/output;
- native VAD and interruption signals;
- tool-calling behavior;
- vision support;
- context and image-retention limits;
- sample format and rate;
- cancellation guarantees.

Reject invalid combinations during configuration. Do not silently downgrade
vision, interruption, or tool behavior.

### Web UI requirements

Evolve the WebSocket envelope around `ProcessorPart` rather than creating a
provider-specific frontend protocol. Any protocol change is cross-boundary and
requires backend and TypeScript contract tests.

A functional UI should eventually provide:

- explicit connection, capture, listening, thinking, speaking, interrupted,
  and error states;
- microphone, camera, and screen controls;
- text input and transcript/history rendering;
- backend/model/voice/objective configuration without exposing secrets;
- reconnect backoff and an intentional session reset flow;
- immediate audio-buffer flush on `interrupted`;
- browser echo cancellation and a clear headphone fallback;
- bounded frame rate/resolution and WebSocket payload size handling;
- actionable permission and device errors;
- secure `wss://` and origin/auth controls before non-local deployment.

The current `live_server` binds to localhost, creates a processor per
connection, uses JSON/base64 messages, and limits messages to 2 MiB. Treat those
details as current contracts until deliberately migrated.

## Testing and Validation

Behavior changes require Red-Green-Refactor:

1. Add the smallest real failing behavior or regression test.
2. Run it and confirm the expected failure.
3. Implement the minimal robust change.
4. Run the targeted test until green.
5. Run the broader relevant suite and refactor only while green.

Tests live beside their ownership area:

- core tests: `genai_processors/tests/*_test.py`
- contrib tests: `genai_processors/contrib/tests/*_test.py`
- cross-boundary WebSocket behavior: `live_server_test.py` plus frontend tests
  when the frontend is changed

Mock external, costly, or nondeterministic provider boundaries, but keep
complete real schemas in mocks. For provider adapters, add contract tests for
part conversion, event translation, cancellation, errors, and audio formats.
Use opt-in live smoke tests for credentials and network access; never make CI
depend on real paid APIs.

Standard setup and validation:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev,contrib]'
.venv/bin/python -m pytest
.venv/bin/python -m flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
.venv/bin/python -m pyink --check genai_processors examples
```

Prefer a targeted test during development, for example:

```bash
.venv/bin/python -m pytest genai_processors/tests/realtime_test.py
```

If optional system dependencies prevent a full suite, run the largest relevant
subset and report exactly what was skipped and why.

## Style and Implementation Rules

- Support Python 3.11 through 3.13 unless project metadata changes.
- Follow Google-style Python formatted by Pyink: 80 columns and 2-space
  indentation.
- Keep control flow explicit and asynchronous cancellation visible.
- Bound queues and retained media in long-running pipelines.
- Clean up tasks, network sessions, device streams, and model resources on
  cancellation, reset, disconnect, and error.
- Do not add blocking model, audio, or image work to the event loop; isolate it
  in a thread, process, or asynchronous client as appropriate.
- Do not add dependencies when an existing dependency or a small local adapter
  is sufficient. Provider-specific and local-model dependencies should normally
  be optional.
- Do not manually edit generated artifacts or lockfiles.
- Keep examples thin; reusable provider logic belongs in an owned package
  module with tests.

## Security, Privacy, and Operations

- Never commit API keys, OAuth tokens, `.env` files, captured audio, screenshots,
  camera frames, transcripts containing private data, or trace files with user
  content.
- Read credentials from environment variables or an approved secret store.
  Never send provider credentials to the browser.
- Do not print credential values. Live smoke tests may report only provider,
  model, success/failure, latency, and non-sensitive response metadata.
- Treat screen, camera, microphone, and transcripts as sensitive user data.
  Capture only with explicit UI state, minimize retention, and make recording or
  tracing opt-in.
- The local WebSocket server has no production authentication or origin policy.
  Do not expose it beyond localhost without designing those boundaries.

## Documentation and Reporting

Update documentation when changing public processors, content/substream
contracts, supported models, setup, WebSocket messages, or examples.

After every change, report:

- what changed and why;
- affected files and contracts;
- exact commands run;
- tests and live smokes performed;
- validations not run and why;
- known uncertainty or incomplete work;
- downstream or frontend coordination required.
