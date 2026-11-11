# Universal AI — Conversation Runtime v0.1

This first implementation intentionally **reuses the existing Leonidas app**.
Leonidas already owns production-like browser capture, Gemini Live, the local
Parakeet/Groq/XTTS cascade, session cancellation, playback pacing, and WebSocket
transport. The new `universal_ai` package adds reusable, provider-neutral
contracts and multi-source stream policies **without replacing those parts**.

## Run the existing conversation app

From the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev,contrib]'
cd leonidas/webui && npm ci && npm run build && cd ../..
GOOGLE_API_KEY='your-key' .venv/bin/python -m leonidas
```

Open `http://127.0.0.1:8000`. Credentials stay on the server. Follow
`leonidas/README.md` for the optional local cascade environment and hardware
requirements. This path is unchanged by the Universal AI v0.1 proposal.

## Verify the new architecture without credentials

```bash
.venv/bin/python -m examples.universal_conversation.demo
.venv/bin/python -m unittest discover -s universal_ai/tests -p '*_test.py'
```

The demo composes two independently scheduled input streams with a fake
`Processor` backend and prints source-stamped replies. It tests orchestration,
not quality of transcription, natural conversation, model latency or audio.

## Wrap a Leonidas backend (opt-in integration)

```python
from universal_ai.contracts import ConversationNeeds
from universal_ai.leonidas_bridge import wrap_leonidas_pipeline

backend = registry.create(agent_config)  # existing Leonidas registry
requirements = ConversationNeeds(
    input_modalities=frozenset({'audio', 'text', 'image'}),
    output_modalities=frozenset({'audio'}),
    require_barge_in=True,
)
conversation = wrap_leonidas_pipeline(
    backend, agent_config.pipeline_id, requirements
)
```

`wrap_leonidas_pipeline` is **not enabled in Leonidas by default**. In particular,
requesting `image` against `cascade_local` raises `CapabilityError` rather than
silently losing visual input. Enabling the bridge in the live app requires
explicit rollout tests of interruption and playback. Do not replace or double
apply the existing `RateLimitAudio` stage.

Architecture, feature roadmap, contracts and security limits:
[`docs/architecture/universal-ai.md`](../../docs/architecture/universal-ai.md).
