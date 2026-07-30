"""ProcessorPart WebSocket transport owned by Leonidas."""

import json
import time
from typing import Any

from genai_processors import content_api
from genai_processors.dev.live_server import clean_encoder
from websockets.asyncio.server import ServerConnection
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

from leonidas import runtime
from leonidas import telemetry


def local_origins(web_port: int) -> tuple[str | None, ...]:
  """Returns browser origins permitted for production and Vite development."""
  return (
      None,
      f'http://127.0.0.1:{web_port}',
      f'http://localhost:{web_port}',
      'http://127.0.0.1:5173',
      'http://localhost:5173',
  )


def _state_part(
    state: dict[str, Any], sequence: int
) -> content_api.ProcessorPart:
  metadata = dict(state)
  metadata.update(
      {
          'sequence': sequence,
          'timestamp': time.time(),
          'session_id': state.get('session_id'),
      }
  )
  return content_api.ProcessorPart(
      '', mimetype='application/x-state', metadata=metadata
  )


def _decode(message: str | bytes) -> content_api.ProcessorPart:
  if isinstance(message, bytes):
    message = message.decode('utf-8')
  payload = json.loads(message)
  if 'part' not in payload:
    payload['part'] = {'text': ''}
  part = content_api.ProcessorPart.from_dict(data=payload)
  if content_api.is_audio(part.mimetype) or content_api.is_image(part.mimetype):
    part.role = 'user'
    part.substream_name = 'realtime'
  elif content_api.is_text(part.mimetype):
    part.role = 'user'
    part.metadata['turn_complete'] = True
  return part


async def run(
    manager: runtime.SessionManager,
    metrics: telemetry.MetricsStore,
    *,
    host: str = '127.0.0.1',
    port: int = 8765,
    allowed_origins: tuple[str | None, ...] | None = None,
) -> None:
  """Serves the single-owner media channel until cancelled."""
  if host != '127.0.0.1':
    raise ValueError('Leonidas v1 only binds to 127.0.0.1')

  async def handler(websocket: ServerConnection) -> None:
    if websocket.request.path.split('?', maxsplit=1)[0] != '/api/v1/live':
      await websocket.close(1008, 'Unknown WebSocket path')
      return
    sequence = 0
    latency = telemetry.LatencyTracker(metrics)

    async def send_part(part: content_api.ProcessorPart) -> None:
      nonlocal sequence
      if content_api.is_audio(part.mimetype):
        metrics.increment('audio_chunks_sent')
        latency.mark_output_audio()
      if part.get_metadata('interrupted'):
        sequence += 1
        part = _state_part(
            {**manager.snapshot(), 'agent_state': 'interrupted'}, sequence
        )
      await websocket.send(
          json.dumps(part.to_dict(mode='python'), default=clean_encoder)
      )

    async def send_state(state: dict[str, Any]) -> None:
      nonlocal sequence
      sequence += 1
      await send_part(_state_part(state, sequence))

    try:
      await manager.attach_media(send_part)
    except runtime.MediaAlreadyConnectedError:
      await websocket.close(1008, 'Another media client owns the session')
      return
    manager.add_state_listener(send_state)
    await send_state(manager.snapshot())
    try:
      async for message in websocket:
        try:
          part = _decode(message)
        except (ValueError, TypeError, json.JSONDecodeError):
          await websocket.close(1007, 'Invalid ProcessorPart')
          return
        if part.mimetype == 'application/x-client-metric':
          name = str(part.metadata.get('name', 'client_metric'))
          value = float(part.metadata.get('value', 0))
          metrics.observe(name, value)
        elif part.mimetype == 'application/x-mic-off':
          latency.mark_input()
          await manager.send(
              content_api.ProcessorPart(
                  '',
                  role='user',
                  substream_name='realtime',
                  metadata={'audio_stream_end': True},
              )
          )
        else:
          if content_api.is_audio(part.mimetype) or content_api.is_text(
              part.mimetype
          ):
            latency.mark_input()
          await manager.send(part)
    except ConnectionClosed:
      pass
    finally:
      manager.remove_state_listener(send_state)
      await manager.detach_media()

  async with serve(
      handler,
      host,
      port,
      origins=allowed_origins or local_origins(8000),
      max_size=2 * 1024 * 1024,
      compression=None,
  ):
    await __import__('asyncio').Future()
