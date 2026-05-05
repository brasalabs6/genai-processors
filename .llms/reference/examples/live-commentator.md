# Live Commentator

## Source References

- `examples/live_commentator/commentator.py`
- `examples/live_commentator/commentator_cli.py`
- `examples/live_commentator/commentator_ais.py`
- `examples/live_commentator/commentator_adk/agent.py`
- `examples/live_commentator/ais_app/index.tsx`
- `examples/live_commentator/README.md`
- `genai_processors/core/event_detection.py`
- `genai_processors/core/live_model.py`
- `genai_processors/core/rate_limit_audio.py`

## Entrypoint

- CLI: from `examples/live_commentator`, run `python3 commentator_cli.py`.
- WebSocket server: `python3 commentator_ais.py`.
- ADK: from `examples/live_commentator`, run `adk web` and select
  `commentator_adk`.
- Factory: `commentator.create_live_commentator(api_key, chattiness=...,
  unsafe_string_list=...)`.

## Pipeline / Data Flow

- CLI input is `video.VideoIn(...) + audio_io.PyAudioIn(...,
  use_pcm_mimetype=True)`.
- `create_live_commentator` builds a detection Gemini model that classifies
  frames into `DETECTION`, `NO_DETECTION`, or `INTERRUPTION`.
- `event_detection.EventDetection` maps state transitions to realtime user
  parts: start commentating, stop commentating, or interrupt request.
- `live_model.LiveProcessor` connects to native-audio Live API with async
  `start_commentating` and `wait_for_user` function declarations.
- `LiveCommentator` manages a state machine around user speech, scheduled
  comments, event interruptions, waits, function cancellation, and unsafe text.
- `rate_limit_audio.RateLimitAudio(RECEIVE_SAMPLE_RATE)` slows model audio to
  realtime playback pace.
- CLI appends `audio_io.PyAudioOut`; AI Studio app sends/receives media through
  WebSocket.

## Dependencies / Env

- Requires `GOOGLE_API_KEY`.
- CLI requires `pyaudio`.
- Default WebSocket port: `8765`.
- Live model: `gemini-2.5-flash-native-audio-preview-12-2025`.
- Detection model: `gemini-2.5-flash-lite`.
- Live API uses `api_version='v1alpha'`.

## Demonstrated Processor Contracts

- Event detector output can inject control parts with metadata such as
  `turn_complete` or `interrupt_request`.
- Async function-call responses use `will_continue` and scheduling values such
  as `WHEN_IDLE`, `INTERRUPT`, and `SILENT`.
- A processor may merge the external content stream with an internal queue using
  `streams.merge`.
- Interruption and generation-complete metadata are yielded as state parts for
  downstream audio/UI behavior.

## Gotchas

- Device input parts must use substream `realtime` for the live model path.
- Browser echo cancellation is assumed for AI Studio; CLI users should wear
  headphones.
- `chattiness` controls probability of scheduling follow-up comments; zero
  effectively disables autonomous commentating.
- Unsafe string filtering watches output transcription and injects a corrective
  user turn before continuing.
