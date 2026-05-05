# Live Commentator

`examples/live_commentator` is the most stateful example in the repo. It is not
just a Live API wrapper: it is an event-driven commentator that keeps speaking,
lets the user interrupt it, interrupts itself when video changes, asks the model
when to wait, and schedules the next comment so generated audio lands close to
real playback time.

## Source References

- Design docstring, constants, tools, prompts:
  `examples/live_commentator/commentator.py:16-88`,
  `examples/live_commentator/commentator.py:113-277`
- Event enum, timing formulas, state machine:
  `examples/live_commentator/commentator.py:280-558`
- Runtime loop and function-response injection:
  `examples/live_commentator/commentator.py:561-890`
- Factory pipeline:
  `examples/live_commentator/commentator.py:893-994`
- CLI entrypoint: `examples/live_commentator/commentator_cli.py:68-96`
- AI Studio server: `examples/live_commentator/commentator_ais.py:44-83`
- ADK adapter: `examples/live_commentator/commentator_adk/agent.py:50-53`
- AI Studio client streams:
  `examples/live_commentator/ais_app/index.tsx:77-105`,
  `examples/live_commentator/ais_app/index.tsx:153-181`,
  `examples/live_commentator/ais_app/index.tsx:194-304`
- Event detection engine: `genai_processors/core/event_detection.py:137-296`
- Live API adapter: `genai_processors/core/live_model.py:61-129`,
  `genai_processors/core/live_model.py:181-279`
- Audio pacing: `genai_processors/core/rate_limit_audio.py:37-178`
- Stream merge/dequeue: `genai_processors/streams.py:136-230`
- Function response constructor:
  `genai_processors/content_api.py:402-455`

## Entrypoints

- CLI: from `examples/live_commentator`, run `python3 commentator_cli.py`.
- WebSocket server: `python3 commentator_ais.py`, default port `8765`.
- ADK: from `examples/live_commentator`, run `adk web` and select
  `commentator_adk`.
- Factory: `commentator.create_live_commentator(api_key, chattiness=...,
  unsafe_string_list=...)`.

The CLI builds local device IO:

```text
VideoIn(camera|screen) + PyAudioIn(use_pcm_mimetype=True)
  -> create_live_commentator(...)
  -> PyAudioOut
```

The AI Studio app sends mic, camera, screen, reset, and chattiness messages over
WebSocket. The server creates the same processor pipeline and streams audio or
state parts back to the browser.

## Semantic Model

The commentator treats the world as four simultaneous streams:

- `realtime`: audio/video/text that should enter Gemini Live through realtime
  input methods. Device media must use this substream.
- default substream: regular client content sent as turn content to Gemini Live.
- `event_detection`: internal control events from the detector to the
  `LiveCommentator`; these are intentionally not sent to Live API.
- model output/control: audio inline-data, transcription substreams, function
  calls, function cancellations, `generation_complete`, `interrupted`, and
  `go_away` metadata emitted by `LiveProcessor`.

The example composes three semantic processors:

1. `EventDetection` observes image parts and injects start/stop/interrupt
   control parts.
2. `LiveCommentator` owns the conversation state machine and injects async
   function responses into the Live model.
3. `RateLimitAudio` converts fast model audio into realtime playback pacing and
   flushes buffered audio when an interrupt state part arrives.

## Core Data And Config Contracts

The live commentator does not use a custom dataclass as its main stream
contract. Its "typed state" is distributed across enums, metadata fields,
substream names, function-call ids, and timing records. For replication, these
contracts are more important than the exact prompts.

| Contract | Values / Shape | Semantic Role |
| --- | --- | --- |
| `EventTypes` | `yes`, `no`, `interruption` | Output vocabulary of the cheap visual detector. |
| `GenerationType` | `COMMENT`, `USER_REQUEST`, `EVENT_INTERRUPTION` | Why the current Live generation was requested. |
| `GenerationRequestInfo` | `generation_start_sec`, `generation_type`, `time_audio_start`, `ttft_sec`, `audio_duration` | Per-generation timing ledger used for scheduling. |
| `CommentatorStateMachine` | `state`, `generation_request_info`, `ttfts`, `id` | Deterministic owner of lifecycle, timing history, and active async tool id. |
| `start_commentating` function id | metadata `id` from model function call | Long-lived handle used to send future function responses. |
| `wait_for_user` function id | metadata `id` from model function call | Short-lived handle acknowledged silently to pause model output. |
| `interrupt_request` metadata | boolean on an `event_detection` part | Local request to ask Live for an interrupting comment. |
| `generation_complete` metadata | boolean model state part | Signal that all audio for a generation has arrived, even if playback is still ongoing. |
| `interrupted` metadata | boolean model state part | Signal used to flush or prepare audio interruption. |

Key constants define the system's operating envelope:

| Constant / Setting | Default | Effect |
| --- | --- | --- |
| `MODEL_LIVE` | `gemini-2.5-flash-native-audio-preview-12-2025` | Dialogue/audio model for the Live session. |
| `MODEL_DETECTION` | `gemini-2.5-flash-lite` | Cheap classifier for visual events. |
| `MEDIA_RESOLUTION` | `MEDIA_RESOLUTION_MEDIUM` | Image understanding quality for Live and detection models. |
| `RECEIVE_SAMPLE_RATE` | `24000` | Audio duration math and `RateLimitAudio` playback pacing. |
| `NO_DETECTION_SENSITIVITY` | `3` | Stop-commentating debounce threshold; strict comparison means four repeated stop labels. |
| `MAX_SILENCE_WAIT_FOR_USER_SEC` | `5` | Extra delay before resuming after `wait_for_user`. |
| `NO_COMMENT_DELAY_SEC` | `3` | Retry delay when chattiness blocks an autonomous comment. |
| `chattiness` | constructor argument, default `1.0` | Probability that a scheduled autonomous comment actually fires. |
| `unsafe_string_list` | constructor argument, default `None` | Optional transcription-level output guard. |

### Stage Ownership Matrix

| Concern | Owner | Why It Lives There |
| --- | --- | --- |
| Low-cost visual presence/change detection | `EventDetection` | Keeps the Live model from polling every frame with expensive dialogue context. |
| Dialogue style, user interaction, wait decisions | Gemini Live prompt and tools | The model needs conversational context to decide what to say or whether to pause. |
| Lifecycle and scheduling truth | `CommentatorStateMachine` | State transitions must be deterministic and inspectable. |
| Async tool protocol | `LiveCommentator` | It owns function-call ids and can inject function responses at precise times. |
| Realtime media transport | `LiveProcessor` | It maps processor parts to Live API transport methods. |
| Playback pacing and interrupt flush | `RateLimitAudio` | Audio timing should be independent from model generation speed. |
| Browser device capture and UI state | `ais_app/index.tsx` | Client owns devices, echo cancellation, reset/config messages, and visual transcript state. |

## Pipeline Diagram

```mermaid
flowchart LR
    subgraph Inputs
        Cam["camera/screen image parts\nsubstream=realtime"]
        Mic["mic PCM audio parts\nsubstream=realtime"]
        Text["terminal or UI text/config"]
    end

    Cam --> ED["EventDetection\ncheap turn model"]
    Mic --> ED
    Text --> ED

    ED -->|passes all original parts| LC["LiveCommentator\nstate machine"]
    ED -->|start/stop realtime text| LC
    ED -->|interrupt_request on event_detection| LC

    LC -->|external content + injected function responses| LP["LiveProcessor\nGemini Live API"]
    LP -->|audio, transcriptions, function calls,\nmetadata signals| LC

    LC --> RLA["RateLimitAudio(24000 Hz)"]
    RLA --> Out["speaker / browser audio\nplus state parts"]
```

Important directionality: `LiveCommentator` is both a consumer of `LiveProcessor`
output and a producer of extra input to it. It creates `input_queue`, merges the
external input stream with `streams.dequeue(input_queue)`, and passes that
merged stream into `LiveProcessor`.

```mermaid
sequenceDiagram
    participant External as External content stream
    participant Queue as input_queue
    participant Merge as streams.merge(stop_on_first=True)
    participant Live as LiveProcessor
    participant LC as LiveCommentator loop

    External->>Merge: realtime media / text / detector controls
    Queue->>Merge: function responses and corrective user turns
    Merge->>Live: unified input stream
    Live->>LC: audio, function calls, metadata
    LC->>Queue: start_commentating response
    LC->>Queue: wait_for_user silent response
    LC->>Queue: unsafe-output corrective user text
    LC-->>External: yielded model audio/state/control parts
```

`stop_on_first=True` means the merged input terminates when one of the merged
streams ends. In normal operation the internal queue does not end, so external
content controls session lifetime.

## Stage Semantics

### Stage 1: EventDetection

`EventDetection` is the perception sidecar. It consumes the same incoming media
stream as the Live model, but it only reasons over recent image parts. It emits
two kinds of output:

- the original stream, passed through unchanged;
- optional control parts derived from event transitions.

Its semantic job is not to write commentary. It reduces a moving visual context
to a small event alphabet:

```text
visual_window -> {yes, no, interruption}
```

This keeps visual event detection cheap, bounded, and debounced. The expensive
Live session receives the raw media and only gets extra textual/tool pressure
when the detector decides that the control state has changed.

### Stage 2: LiveCommentator

`LiveCommentator` is the orchestration controller. It wraps a `LiveProcessor`,
creates an internal `input_queue`, merges that queue with external content, and
then reacts to every Live output part. It is responsible for:

- turning model function calls into stored async tool handles;
- converting detector controls into function responses;
- converting user/model metadata into deterministic state transitions;
- deciding when the next autonomous comment should be scheduled;
- yielding local state markers that downstream audio pacing can understand.

This is the most reusable architectural idea in the example: the controller
does not generate language itself. It controls when and why the Live model is
allowed to generate.

### Stage 3: LiveProcessor

`LiveProcessor` is the transport adapter. It knows how processor parts map onto
the Live API:

```text
ProcessorPart envelope -> Live API method
Live server message -> ProcessorPart envelope
```

That boundary is intentionally kept generic. Similar repos can replace Gemini
Live with another realtime model adapter as long as the adapter preserves the
same semantic surface: realtime media, turn content, function calls, tool
responses, interruptions, generation completion, and audio output.

### Stage 4: RateLimitAudio

`RateLimitAudio` is the output pacer. It treats the model's emitted audio as a
buffered signal and releases it at natural playback speed. It also gives
`interrupted=True` state parts operational meaning by flushing queued audio.

Without this stage, a fast Live model can emit seconds of audio almost
immediately, which makes later interruptions arrive too late from the user's
perspective.

## Control-Loop Formula

The example is best modeled as a realtime feedback loop, not a single request
pipeline:

```text
observed_events_t =
  EventDetection(recent_realtime_images_t)

live_input_t =
  merge(external_realtime_content_t, injected_function_responses_t)

live_output_t =
  LiveProcessor(live_input_t)

controller_state_{t+1}, controller_outputs_t =
  LiveCommentatorStateMachine(live_output_t, observed_events_t, controller_state_t)

user_audio_t =
  RateLimitAudio(controller_outputs_t)
```

The detector and controller form a closed loop:

```text
visual change
  -> detector transition
  -> local control part
  -> state-machine action
  -> async function response
  -> Live model generation or interruption
  -> audio/state output
  -> playback pacing and possible flush
```

Autonomous commentary is probabilistic only at the scheduling gate:

```text
should_comment ~ Bernoulli(chattiness)
```

Everything else should be treated as deterministic state transition logic. That
split is useful when replicating this pattern: keep exploration style and
comment density configurable, but keep lifecycle, id management, audio flushing,
and routing deterministic.

## Event Detection Semantics

The detector keeps a deque of recent image parts with timestamps. For each model
call it sends alternating image and relative timestamp text parts:

```text
image_0, "00:00", image_1, "00:01", ..., image_n, "00:dt"
```

The classifier returns one enum value:

- `yes`: something worth commentating is present.
- `no`: no relevant presence/action.
- `interruption`: a new notable event should interrupt the current comment.

Transition validity is not "latest label wins". The engine computes:

```text
event_name = response_text.strip().lower()
current_transition = (last_transition.to_state, event_name)
```

Then it checks:

```text
valid_transition =
  (current_transition in output_dict or current_transition.from_state == START)
  and current_transition.to_state != current_transition.from_state

sensitivity_reached =
  current_transition not in sensitivity
  or transition_counter[current_transition] > sensitivity[current_transition]
```

The strict `>` matters. With `NO_DETECTION_SENSITIVITY = 3`, the stop transition
fires only after the fourth repeated `(yes, no)` classification. Treat that as
the implementation contract, even though the constant comment reads like "three
times".

Configured transitions:

| Transition | Emitted Part | Meaning |
| --- | --- | --- |
| `(*, yes)` | realtime user text `"start commentating"`, `turn_complete=True` | Ask Live model to start or resume commentator behavior. |
| `(yes, no)` | realtime user text `"stop commentating"`, `turn_complete=True` | Ask model to cancel/stop active commentating after sustained absence. |
| `(yes, interruption)` | empty user part on `event_detection`, `interrupt_request=True` | Internal signal to request an interrupting comment. |
| `(interruption, yes)` | `None` | Accept the transition but emit no extra part. |

Because `EventDetection` passes all input through before injecting control
parts, downstream processors continue receiving normal media even while
detection is running.

## Live API Input Semantics

`LiveProcessor` routes each input part by semantic envelope:

| Input Part | Live API Method | Effect |
| --- | --- | --- |
| `function_response` | `session.send_tool_response(...)` | Returns async tool output to the model. |
| `substream_name == "realtime"` and `audio_stream_end` | `send_realtime_input(audio_stream_end=True)` | Ends realtime audio stream. |
| `substream_name == "realtime"` and inline media | `send_realtime_input(media=...)` | Sends mic/camera/screen media. |
| `substream_name == "realtime"` and text | `send_realtime_input(text=...)` | Sends realtime text control such as start/stop. |
| default substream | `send_client_content(..., turn_complete=...)` | Sends turn-style content. |
| any other substream | passed through | Lets internal control parts reach `LiveCommentator`. |

`to_parts()` converts Live server messages back into `ProcessorPart`s:

- audio model parts become inline-data `ProcessorPart`s with role from
  `model_turn`.
- `input_transcription` and `output_transcription` become text parts on their
  named substreams.
- metadata such as `generation_complete`, `interrupted`, `usage_metadata`, and
  `go_away` becomes empty model parts with metadata.
- function calls become `ProcessorPart.from_function_call(...)` with metadata
  `id`.
- tool cancellations become tool-cancellation parts.

## State Machine

The state machine stores:

- `state`: current `State` enum.
- `id`: active `start_commentating` async function-call id.
- `generation_request_info`: timing data for the current model request.
- `ttfts`: history of observed time-to-first-audio values.

```mermaid
stateDiagram-v2
    [*] --> OFF

    OFF --> REQUESTING_COMMENT: TURN_ON / store id, then REQUEST_FROM_COMMENTATOR
    OFF --> OFF: other actions ignored

    REQUESTING_COMMENT --> TALKING: STREAM_MEDIA_PART
    TALKING --> REQUESTING_COMMENT: REQUEST_FROM_COMMENTATOR
    WAITING_FOR_USER --> REQUESTING_COMMENT: REQUEST_FROM_COMMENTATOR

    TALKING --> REQUESTING_INTERRUPTION: REQUEST_INTERRUPT
    WAITING_FOR_USER --> REQUESTING_INTERRUPTION: REQUEST_INTERRUPT
    REQUESTING_COMMENT --> REQUESTING_INTERRUPTION: REQUEST_INTERRUPT
    REQUESTING_INTERRUPTION --> INTERRUPTED_FROM_DETECTION: INTERRUPT
    INTERRUPTED_FROM_DETECTION --> TALKING: STREAM_MEDIA_PART

    TALKING --> USER_IS_TALKING: INTERRUPT
    REQUESTING_COMMENT --> USER_IS_TALKING: INTERRUPT
    REQUESTING_RESPONSE --> USER_IS_TALKING: INTERRUPT
    USER_IS_TALKING --> TALKING: STREAM_MEDIA_PART

    TALKING --> REQUESTING_RESPONSE: REQUEST_FROM_USER
    WAITING_FOR_USER --> REQUESTING_RESPONSE: REQUEST_FROM_USER
    REQUESTING_RESPONSE --> TALKING: STREAM_MEDIA_PART

    TALKING --> WAITING_FOR_USER: WAIT_FOR_USER
    REQUESTING_COMMENT --> WAITING_FOR_USER: WAIT_FOR_USER
    REQUESTING_RESPONSE --> WAITING_FOR_USER: WAIT_FOR_USER

    TALKING --> OFF: TURN_OFF
    WAITING_FOR_USER --> OFF: TURN_OFF
    REQUESTING_COMMENT --> OFF: TURN_OFF
    REQUESTING_RESPONSE --> OFF: TURN_OFF
    REQUESTING_INTERRUPTION --> OFF: TURN_OFF
    USER_IS_TALKING --> OFF: TURN_OFF
```

### State Meanings

| State | Semantic Meaning | Active Request Data |
| --- | --- | --- |
| `OFF` | Commentator is inactive. User can still speak to the Live model, but autonomous commentary is off. | Cleared on `TURN_OFF`. |
| `TALKING` | Steady state: model audio is being played, or the agent is otherwise active and ready to schedule. | May have request timing from the last generation. |
| `USER_IS_TALKING` | VAD/model interruption indicates user started speaking. The agent yields an `interrupted` state part to stop old audio. | `GenerationType.USER_REQUEST`; start time is artificially delayed by 2 seconds to approximate user utterance duration. |
| `REQUESTING_INTERRUPTION` | Detector found a notable event. The system has asked the model for an interrupting comment but keeps old audio until replacement audio arrives. | `GenerationType.EVENT_INTERRUPTION`. |
| `REQUESTING_COMMENT` | Scheduler has requested the next autonomous comment. | `GenerationType.COMMENT`. |
| `REQUESTING_RESPONSE` | User-originated input should produce a response. | `GenerationType.USER_REQUEST`. |
| `INTERRUPTED_FROM_DETECTION` | Model confirmed interruption from detector. The next audio part will flush old audio, then play replacement audio. | Event-interruption request remains active until audio arrives. |
| `WAITING_FOR_USER` | Model called `wait_for_user`; client silently acknowledges and waits for user response or visual change. | Existing audio can finish; next schedule includes silence timeout. |

## Runtime Dispatch Matrix

`LiveCommentator.call()` processes every output part from `LiveProcessor` in a
priority order. This order is part of the behavior.

| Incoming Part | Guard | State Action | Output / Injection |
| --- | --- | --- | --- |
| `substream_name == "unsafe_regex"` | unsafe filter enabled | `REQUEST_FROM_USER` | Inject corrective realtime user text; do not yield unsafe part. |
| function call `start_commentating` | state is `OFF` | `TURN_ON` | Store function id; model may continue because tool is non-blocking. |
| function call `start_commentating` | state is not `OFF` | none | Inject empty silent response to reject duplicate active tool call. |
| function call `wait_for_user` | state is not `OFF` | `WAIT_FOR_USER` | Inject empty silent response; schedule resume after timeout. |
| metadata `start_of_user_turn` | any | `REQUEST_FROM_USER` | Consumed as state signal. |
| tool cancellation matching active id | any | `TURN_OFF` | Cancel scheduled comment task. |
| metadata `generation_complete` | state not `OFF` | no state update | Yield completion state part; schedule next comment or wait timeout. |
| metadata `interrupted` | any | `INTERRUPT` | For user interrupt, yield immediate `interrupted` state part. For detector interrupt, wait for replacement audio. |
| metadata `interrupt_request` | eligible states | `REQUEST_INTERRUPT` | Inject `start_commentating` response with `scheduling=INTERRUPT`. |
| metadata `go_away` | any | none | Cancel scheduled task and end processor. |
| inline audio/media output | any | `STREAM_MEDIA_PART` | If detector interruption is ready, yield `interrupted` before this audio; then yield audio. |
| any other part | any | none | Yield unchanged. |

### Controller Decision Rules

In implementation terms, the controller reduces mixed Live output into action
decisions:

```text
if unsafe_regex:
  action = REQUEST_FROM_USER
  inject corrective realtime text

elif function_call.name == "start_commentating" and state == OFF:
  action = TURN_ON
  store function_call.id

elif function_call.name == "start_commentating" and state != OFF:
  inject SILENT empty response for duplicate id

elif function_call.name == "wait_for_user" and state != OFF:
  action = WAIT_FOR_USER
  inject SILENT empty response
  schedule resume at tentative_trigger_time + MAX_SILENCE_WAIT_FOR_USER_SEC

elif metadata.start_of_user_turn:
  action = REQUEST_FROM_USER

elif tool_cancellation == active_commentator_id:
  action = TURN_OFF

elif metadata.generation_complete and state != OFF:
  yield generation_complete state marker
  schedule next comment from tentative_trigger_time

elif metadata.interrupted:
  action = INTERRUPT
  if state == USER_IS_TALKING:
    yield interrupted state immediately

elif metadata.interrupt_request:
  action = REQUEST_INTERRUPT
  inject start_commentating response with scheduling=INTERRUPT

elif metadata.go_away:
  cancel scheduled comment task
  end processor

elif inline_audio:
  if state == INTERRUPTED_FROM_DETECTION:
    yield interrupted state before replacement audio
  action = STREAM_MEDIA_PART
```

This priority order is part of the semantic contract. For example, unsafe
transcription controls are consumed before function calls, and detector
interrupts are converted to `REQUEST_INTERRUPT` before the next audio blob can
move the state back to `TALKING`.

## Async Tool Semantics

The Live model receives two non-blocking function declarations:

- `start_commentating`: model-facing handle for an ongoing commentator task.
  The client stores the function-call id and later sends function responses into
  the same call id to schedule more comments.
- `wait_for_user`: model-facing signal that it wants silence while the user
  answers or performs a visual action.

Function responses are created with `ProcessorPart.from_function_response(...)`.
The key scheduling modes used here are:

- `WHEN_IDLE`: add response and trigger generation when current model output is
  idle. Used for ordinary continuation.
- `INTERRUPT`: ask Gemini to interrupt current generation and regenerate with
  fresh event context. Used after `interrupt_request`.
- `SILENT`: acknowledge/cancel a tool call without triggering generation. Used
  for duplicate `start_commentating` calls and `wait_for_user` acknowledgments.

## Concurrency And Ordering

There are multiple asynchronous lanes, and their ordering rules explain most of
the example's subtle behavior.

| Lane | Producer | Consumer | Ordering Rule |
| --- | --- | --- | --- |
| External realtime media | CLI/browser device streams | `EventDetection`, then `LiveProcessor` | Passes through immediately; detector work does not block media forwarding. |
| Detector control parts | `EventDetection` backend result | `LiveCommentator` | Arrive after model classification latency; they refer to a recent visual window, not necessarily the latest frame. |
| Internal function responses | `LiveCommentator.input_queue` | `LiveProcessor` | Merged with external content; response timing is controlled by queued inserts and scheduling mode. |
| Live model output | Live API session | `LiveCommentator` | Audio, metadata, function calls, and cancellations are handled in controller priority order. |
| Scheduled comments | `asyncio` task from `_schedule_comment` | `input_queue` | Only one scheduled task is intended to be active; new completion/interrupt/wait signals cancel and replace it. |
| Rate-limited audio | `RateLimitAudio` queues | speaker/browser | Audio preserves playback pace; interrupt state parts flush queued audio. |

Important consequences:

- A detector interruption is causally related to an earlier image window. The
  Live model still receives newer realtime media before and after that control
  signal.
- The internal queue can inject tool responses while camera/mic data continues
  streaming. This is how the controller asks the Live model to comment without
  stopping device input.
- `generation_complete` means "the model has sent all audio for this
  generation", not "the user has heard all audio". Scheduling therefore uses
  measured audio duration to approximate the playback boundary.
- `wait_for_user` cancels the normal follow-up schedule and replaces it with a
  silence-timeout schedule. A later `generation_complete` or interruption can
  replace that task again.
- Duplicate `start_commentating` calls are acknowledged silently because only
  one long-lived commentator tool id can own the autonomous loop.

## Timing Formulas

All timing math assumes 16-bit PCM audio. One sample is 2 bytes.

Audio duration:

```text
audio_duration_sec(audio_bytes, sample_rate) =
  len(audio_bytes) / (2 * sample_rate)
```

For this example:

```text
sample_rate = RECEIVE_SAMPLE_RATE = 24000
audio_duration_sec = len(audio_bytes) / 48000
```

Time to first audio:

```text
ttft_sec = time_audio_start - generation_start_sec
```

`time_audio_start` is captured when the first model audio blob arrives for a
request. `generation_start_sec` is set when `REQUEST_FROM_COMMENTATOR`,
`REQUEST_INTERRUPT`, or `REQUEST_FROM_USER` starts a generation. For user
interrupts, `generation_start_sec` is shifted by `+2` seconds to approximate the
fact that the user is still speaking when the interrupt signal first arrives.

Predicted TTFT:

```text
if len(ttfts) == 0:
  predicted_ttft = 0.0
else:
  predicted_ttft = max(0.4, mean(ttfts) - std(ttfts))
```

This is intentionally optimistic. It asks for the next comment slightly before
the current audio finishes so the first audio of the next generation can arrive
near the playback boundary. The `0.4` lower bound avoids assuming impossible
near-zero model latency once historical measurements exist.

Tentative next trigger:

```text
tentative_trigger_time =
  time_audio_start
  + max(5.0, audio_duration)
  - predicted_ttft
```

The `max(5.0, audio_duration)` term guarantees a minimum conversational pause
window even when the model emitted no audio or very short audio, especially in
`WAITING_FOR_USER`.

Wait-for-user resume:

```text
resume_time =
  tentative_trigger_time + MAX_SILENCE_WAIT_FOR_USER_SEC
```

With the default constant:

```text
MAX_SILENCE_WAIT_FOR_USER_SEC = 5
```

Chattiness scheduling:

```text
if chattiness < 1e-6:
  do not schedule autonomous comments

after at_time:
  draw u ~ Uniform(0, 1)
  if u < chattiness:
    request next comment
  else:
    sleep NO_COMMENT_DELAY_SEC and retry
```

For `0 < chattiness <= 1`, the expected number of attempts is approximately
`1 / chattiness`, and the expected extra delay after `at_time` is approximately:

```text
((1 - chattiness) / chattiness) * NO_COMMENT_DELAY_SEC
```

The default retry delay is:

```text
NO_COMMENT_DELAY_SEC = 3
```

## Interruption Semantics

There are two interrupt paths, and they deliberately flush audio at different
times.

### User Interrupt

```mermaid
sequenceDiagram
    participant User
    participant Live as Gemini Live VAD
    participant LC as LiveCommentator
    participant RLA as RateLimitAudio

    User->>Live: starts speaking over audio
    Live->>LC: metadata interrupted=True
    LC->>LC: update(INTERRUPT) -> USER_IS_TALKING
    LC->>RLA: empty state part metadata interrupted=True
    RLA->>RLA: flush queued audio
    Live->>LC: later model response audio
    LC->>RLA: new audio
```

User speech should stop playback immediately, because the user is now driving
the turn.

### Detector Interrupt

```mermaid
sequenceDiagram
    participant ED as EventDetection
    participant LC as LiveCommentator
    participant Live as Gemini Live
    participant RLA as RateLimitAudio

    ED->>LC: interrupt_request=True on event_detection
    LC->>LC: update(REQUEST_INTERRUPT) -> REQUESTING_INTERRUPTION
    LC->>Live: function response scheduling=INTERRUPT
    Live->>LC: metadata interrupted=True
    LC->>LC: update(INTERRUPT) -> INTERRUPTED_FROM_DETECTION
    Note over LC,RLA: old audio is not flushed yet
    Live->>LC: first replacement audio blob
    LC->>RLA: interrupted=True state part
    RLA->>RLA: flush old queued audio
    LC->>RLA: replacement audio blob
```

Detector interrupts wait until replacement audio is ready. This avoids awkward
silence between "stop old comment" and "start new event comment".

## Audio Rate Limiting

Gemini can stream audio faster than realtime. `RateLimitAudio` enforces playback
pacing and bounded interrupt latency.

Chunk splitting:

```text
MAX_AUDIO_PART_SEC = 0.05
chunk_target_bytes = int(MAX_AUDIO_PART_SEC * sample_rate * 2)
num_chunks = ceil(len(audio_data) / chunk_target_bytes)
```

At 24 kHz:

```text
chunk_target_bytes = int(0.05 * 24000 * 2) = 2400 bytes
```

Playback schedule:

```text
start_playing_time = max(now - 0.05, start_playing_time)
sleep_sec = max(0, start_playing_time - now)
yield audio_part
start_playing_time += audio_duration(audio_part)
```

The `0.05` second buffer keeps audio from being clipped. On an `interrupted`
state part, `RateLimitAudio` flushes the audio queue before yielding the
interrupt state downstream.

## Data Lifecycle

```mermaid
flowchart TD
    A["Browser/CLI captures media"] --> B["ProcessorPart\nrole=user\nsubstream=realtime"]
    B --> C["EventDetection stores recent images\nand passes original parts"]
    C --> D["LiveProcessor sends realtime media\nto Gemini Live"]
    C --> E["Detector model classifies image window"]
    E --> F{"event transition?"}
    F -->|start/stop| G["realtime text control\nturn_complete=True"]
    F -->|interrupt| H["event_detection control\ninterrupt_request=True"]
    G --> D
    H --> I["LiveCommentator state machine"]
    D --> J["Gemini Live output\nfunction calls, metadata, audio"]
    J --> I
    I --> K{"state signal?"}
    K -->|function response| D
    K -->|audio/state output| L["RateLimitAudio"]
    L --> M["speaker/browser/transcript UI"]
```

The important semantic move is that a `ProcessorPart` can be data or control
depending on its envelope:

- inline audio/image bytes are media data.
- text with `turn_complete=True` is a prompt/control turn.
- `substream_name="event_detection"` is local routing control.
- function-call/function-response parts are tool protocol messages.
- empty text parts with metadata are state markers.

## Prompt Contract

`PROMPT_PARTS` instruct the model to:

- act as a commentator/interviewer/coach, not a passive assistant;
- address people in the video as "you" because they can hear it;
- keep comments short, usually one or two sentences;
- answer user interruptions first, then resume commentary;
- call `wait_for_user` when it asks a question or instructs the user to do
  something and should stay silent;
- interrupt stale commentary when the current image/audio changes materially.

The detector prompt is narrower. It does not generate user-facing text; it only
classifies camera/screen state into `yes`, `no`, or `interruption`.

## Unsafe Output Loop

If `unsafe_string_list` is configured, the constructor chains a
`text.MatchProcessor` onto the Live processor:

```text
output_transcription -> MatchProcessor -> unsafe_regex
```

The match processor watches model output transcription, not raw audio. When a
match appears, `LiveCommentator`:

1. updates state with `REQUEST_FROM_USER`;
2. injects a corrective realtime user message using `START_AGAIN_MSG`;
3. includes the forbidden expressions in the message;
4. suppresses the unsafe regex control part from downstream output.

This is a local sanity mechanism, not a full safety system.

## AI Studio Client Semantics

The browser client sends:

- mic audio chunks as inline data with `substream_name="realtime"`;
- camera/screen image chunks as inline data with `substream_name="realtime"`;
- reset command as `mimetype="application/x-command"`;
- chattiness config as `mimetype="application/x-config"` with metadata.

The browser receives:

- `audio/*`: decoded and written into an audio output stream;
- `text/*`: appended to transcript;
- `application/x-state` with `generation_complete` or `interrupted`: clears the
  transcript shortly after the current visible turn.

## Failure Modes And Gotchas

- Realtime device media must be on `substream_name="realtime"`; default-substream
  media is sent as client content, not realtime input.
- Non-default, non-realtime substreams are passed through by `LiveProcessor`.
  This is why `event_detection` control parts can reach `LiveCommentator`.
- Detector output is asynchronous. Control parts may not appear immediately
  after the image that triggered them.
- `NO_DETECTION_SENSITIVITY = 3` uses strict `>` semantics, so sustained stop
  takes four repeated `(yes, no)` classifications.
- Detector interrupts do not flush audio immediately; they flush when
  replacement audio arrives.
- User interrupts flush immediately.
- `chattiness=0` disables autonomous scheduled follow-up comments, but user
  input and detector-driven start/interrupt behavior can still flow through the
  Live model.
- CLI users should wear headphones; browser/AI Studio relies on browser echo
  cancellation to avoid the model interrupting itself.

## Error And Drift Notes

These are the details future implementations should either preserve
deliberately or clean up before productionizing the pattern:

- `NO_DETECTION_SENSITIVITY = 3` is checked with strict `>`, so it requires
  four repeated `(yes, no)` classifications. This is a debounce contract, not a
  simple count comment.
- `LiveCommentator.__init__` creates `self.ttfts`, but the active TTFT history
  used by `predict_next_ttft()` lives on `CommentatorStateMachine.ttfts`. If
  extracting this controller, keep only one timing history owner.
- `RateLimitAudio` code uses `MAX_AUDIO_PART_SEC = 0.05`; its docstring still
  mentions 200 ms sub-parts. The executable behavior is 50 ms chunks.
- The detector interruption part must stay off the `realtime` substream. The
  `event_detection` substream is what prevents a local control marker from
  being sent to the Live model as user content before the controller handles it.
- Tool-call ids are protocol state. Losing `self._commentator.id` means the
  controller can no longer send follow-up `start_commentating` responses.
- The unsafe-output loop is transcription-based. If output transcription is
  disabled or delayed, unsafe audio could already have entered the audio queue.
- `generation_complete` scheduling assumes the controller has received enough
  audio blobs to estimate playback duration. Text-only or no-audio responses
  fall back to the 5 second minimum duration.
- `streams.merge(stop_on_first=True)` means external stream shutdown should end
  the Live session. If a host keeps the external stream open forever, it also
  needs explicit reset or cancellation handling.

## Replication Blueprint

For another repo or another live agent, preserve the same ownership boundaries
even if the domain is not a video commentator.

Recommended generic shape:

```text
DeviceOrRealtimeInput
  -> PerceptionClassifier
  -> ControllerStateMachine
  -> RealtimeModelAdapter
  -> OutputPacer
  -> ClientOutput
```

Recommended controller contracts:

```text
PerceptionEvent = PRESENCE | ABSENCE | INTERRUPTING_CHANGE | domain-specific events

ControllerState =
  OFF
  ACTIVE
  USER_IS_DRIVING
  REQUESTING_AUTONOMOUS_OUTPUT
  REQUESTING_EVENT_INTERRUPT
  WAITING_FOR_USER

GenerationRequestInfo =
  request_start_time
  request_reason
  first_output_time
  time_to_first_output
  emitted_output_duration
```

Implementation checklist:

1. Put perception classification in a cheap side processor.
2. Encode perception changes as explicit state/control parts, not ad hoc strings
   hidden inside model output.
3. Keep the realtime model as the dialogue/speech generator, not the lifecycle
   owner.
4. Put scheduling and lifecycle truth in a deterministic state machine.
5. Preserve a stable async-tool or session-control handle for future injected
   responses.
6. Use separate routing lanes for realtime input, local controls,
   transcription/status, and model-visible text.
7. Represent timing with measured output facts: request start, first output,
   emitted duration, and historical latency.
8. Flush output differently for user interrupts versus perception-driven
   interrupts. User interrupts should cut immediately; perception interrupts
   can wait until replacement output is ready.
9. Keep probabilistic personality/density knobs, such as `chattiness`, outside
   the state-machine transition table.
10. Treat client echo cancellation, reset, and config messages as part of the
    product contract, not merely UI details.

The semantic formula to copy is:

```text
domain_observation
  -> small classified event
  -> explicit control part
  -> deterministic transition
  -> model/session command
  -> paced output
```

That formula also works outside realtime media. For example:

- API monitoring agent:
  `metrics/logs -> incident classifier -> state machine -> model summary -> notification pacer`.
- Code-review companion:
  `file diffs -> risk classifier -> state machine -> model explanation -> UI/status stream`.
- Robotics coach:
  `sensor/video frames -> motion event classifier -> state machine -> Live instruction -> audio pacing`.

## Test Strategy For Similar Agents

Minimum tests for a production-grade replica:

- state-machine transition table for every `(state, action)` pair that should
  matter;
- detector transition debounce, especially the strict `>` sensitivity behavior;
- function-call id lifecycle: first `start_commentating`, duplicate call,
  cancellation, and lost-id behavior;
- `wait_for_user` scheduling: silent response, timeout resume, cancellation on
  interrupt or new completion;
- user interrupt flush: `interrupted=True` state part must clear queued audio
  immediately;
- detector interrupt flush: old audio should continue until first replacement
  audio arrives;
- TTFT prediction and trigger-time calculations with no history, short audio,
  long audio, and no-audio generations;
- substream routing: `realtime` reaches Live API, `event_detection` reaches only
  the controller, reserved/status substreams bypass model-visible content;
- unsafe-output loop behavior with matching and non-matching transcription
  parts;
- client integration reset/config paths for browser and CLI entrypoints.

## Extension Ideas

- Replace the enum-only detector with a structured event object carrying
  `event_type`, `confidence`, `description`, and `source_timestamp`.
- Persist a short rolling event and generation trace so reconnecting clients can
  resume state without starting from `OFF`.
- Add metrics for detector latency, TTFT, interruption latency, audio queue
  depth, duplicate tool calls, and chattiness skip count.
- Add a validation processor that rejects malformed local control parts before
  they reach the controller.
- Split user-facing state parts from internal control parts so clients can show
  richer state without exposing tool protocol details.
- Make chattiness deterministic under test by injecting a random source into
  `_schedule_comment`.
