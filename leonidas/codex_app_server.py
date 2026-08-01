"""Server-side adapter for the experimental Codex app-server realtime API.

The adapter intentionally owns the JSONL/RPC boundary.  Browser code receives
normal ``ProcessorPart`` values and never receives Codex request ids,
credentials, or approval RPCs.
"""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Awaitable, Callable
import json
import logging
from typing import Any

from genai_processors import content_api
from genai_processors import processor

from leonidas import capabilities


CODEX_WEBRTC_OFFER_MIMETYPE = 'application/x-codex-webrtc-offer'
CODEX_WEBRTC_ANSWER_MIMETYPE = 'application/x-codex-webrtc-answer'


class CodexProtocolError(RuntimeError):
  """The app-server returned an invalid or rejected protocol operation."""

  public_message = True

  def __init__(self, message: str):
    normalized = message.strip()
    lowered = normalized.lower()
    if 'voice session access denied' in lowered or (
        '403 forbidden' in lowered and 'realtime' in lowered
    ):
      normalized = (
          'Codex realtime voice access denied by the upstream service; '
          'verify that this Codex account has realtime voice entitlement.'
      )
    else:
      for marker in (', url:', ', cf-ray:', ', request id:'):
        normalized = normalized.split(marker, maxsplit=1)[0]
    super().__init__(normalized or 'Codex realtime protocol error')


SendLine = Callable[[str], Awaitable[None]]
ReceiveLine = Callable[[], Awaitable[str | None]]


class JsonlRpcClient:
  """Small multiplexed JSONL client with explicit server-request handling."""

  def __init__(self, send_line: SendLine, receive_line: ReceiveLine):
    self._send_line = send_line
    self._receive_line = receive_line
    self._next_id = 0
    self._pending: dict[int, asyncio.Future[Any]] = {}
    self._notifications: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    self._reader_task: asyncio.Task[None] | None = None
    self._closed = False

  async def start(self) -> None:
    if self._reader_task is not None:
      return
    self._reader_task = asyncio.create_task(
        self._reader(), name='leonidas-codex-jsonl-reader'
    )

  async def _reader(self) -> None:
    try:
      while True:
        line = await self._receive_line()
        if line is None:
          raise CodexProtocolError('Codex app-server closed its JSONL stream')
        try:
          message = json.loads(line)
        except json.JSONDecodeError as exc:
          raise CodexProtocolError(
              'Codex app-server sent invalid JSON'
          ) from exc
        if not isinstance(message, dict):
          raise CodexProtocolError('Codex app-server sent a non-object message')
        message_id = message.get('id')
        if isinstance(message_id, int) and message_id in self._pending:
          pending = self._pending.pop(message_id)
          error = message.get('error')
          if isinstance(error, dict):
            pending.set_exception(
                CodexProtocolError(str(error.get('message', 'RPC error')))
            )
          else:
            pending.set_result(message.get('result'))
        elif 'method' in message and 'id' in message:
          # Approval/input requests cannot be ignored: leaving one unresolved
          # can deadlock the Codex thread.  Leonidas does not authorize tools.
          await self._send_line(
              json.dumps(
                  {
                      'id': message['id'],
                      'error': {
                          'code': -32601,
                          'message': (
                              'Leonidas does not support server requests'
                          ),
                      },
                  },
                  separators=(',', ':'),
              )
          )
          raise CodexProtocolError(
              f"Unsupported server request: {message.get('method')}"
          )
        else:
          await self._notifications.put(message)
    except asyncio.CancelledError:
      raise
    except Exception as exc:
      if not isinstance(exc, CodexProtocolError):
        exc = CodexProtocolError(str(exc))
      for pending in self._pending.values():
        if not pending.done():
          pending.set_exception(exc)
      self._pending.clear()

  async def notify(
      self, method: str, params: dict[str, Any] | None = None
  ) -> None:
    await self._send_line(
        json.dumps(
            {'method': method, 'params': params or {}},
            separators=(',', ':'),
        )
    )

  async def request(self, method: str, params: dict[str, Any]) -> Any:
    if self._closed:
      raise CodexProtocolError('Codex app-server client is closed')
    await self.start()
    self._next_id += 1
    request_id = self._next_id
    loop = asyncio.get_running_loop()
    pending = loop.create_future()
    self._pending[request_id] = pending
    try:
      await self._send_line(
          json.dumps(
              {'id': request_id, 'method': method, 'params': params},
              separators=(',', ':'),
          )
      )
      return await pending
    except BaseException:
      self._pending.pop(request_id, None)
      raise

  async def next_notification(self) -> dict[str, Any]:
    await self.start()
    return await self._notifications.get()

  async def close(self) -> None:
    self._closed = True
    for pending in self._pending.values():
      if not pending.done():
        pending.set_exception(CodexProtocolError('Client closed'))
    self._pending.clear()
    if self._reader_task is not None:
      self._reader_task.cancel()
      await asyncio.gather(self._reader_task, return_exceptions=True)
      self._reader_task = None


class CodexRealtimeClient:
  """Lifecycle and media methods confirmed by the installed app-server schema."""

  def __init__(self, rpc: JsonlRpcClient, *, audio_mimetype: str):
    if not audio_mimetype.startswith('audio/'):
      raise ValueError('audio_mimetype must be an audio MIME type')
    self._rpc = rpc
    self._audio_mimetype = audio_mimetype
    self._thread_id: str | None = None
    self._started = False

  async def request(self, method: str, params: dict[str, Any]) -> Any:
    """Expose a constrained server-side request seam for diagnostics/tests."""
    return await self._rpc.request(method, params)

  async def initialize(self, *, client_name: str, client_version: str) -> Any:
    result = await self._rpc.request(
        'initialize',
        {
            'clientInfo': {
                'name': client_name,
                'title': 'Leonidas',
                'version': client_version,
            },
            'capabilities': {'experimentalApi': True},
        },
    )
    await self._rpc.notify('initialized')
    return result

  async def start_realtime(
      self,
      *,
      objective: str,
      model: str | None = None,
      voice: str | None = None,
      version: str = 'v3',
      sdp_offer: str | None = None,
  ) -> str | None:
    if sdp_offer is not None:
      if not sdp_offer.strip():
        raise ValueError('sdp_offer must not be empty')
      if version not in {'v1', 'v3'}:
        raise ValueError('Codex WebRTC realtime requires version v1 or v3')
    result = await self._rpc.request(
        'thread/start',
        {
            'ephemeral': True,
            'approvalPolicy': 'never',
            'sandbox': 'read-only',
            'baseInstructions': objective,
        },
    )
    try:
      self._thread_id = str(result['thread']['id'])
    except (KeyError, TypeError) as exc:
      raise CodexProtocolError('thread/start returned no thread id') from exc
    params: dict[str, Any] = {
        'threadId': self._thread_id,
        'outputModality': 'audio',
        'prompt': objective,
        'version': version,
        'includeStartupContext': True,
    }
    if sdp_offer is None:
      params['transport'] = {'type': 'websocket'}
    else:
      params['transport'] = {'type': 'webrtc', 'sdp': sdp_offer}
    if model:
      params['model'] = model
    if voice:
      params['voice'] = voice
    await self._rpc.request('thread/realtime/start', params)
    remote_sdp: str | None = None
    while True:
      notification = await self._rpc.next_notification()
      if notification.get('method') == 'thread/realtime/sdp':
        candidate = notification.get('params', {}).get('sdp')
        if isinstance(candidate, str):
          remote_sdp = candidate
        continue
      if notification.get('method') == 'thread/realtime/started':
        self._started = True
        return remote_sdp
      if notification.get('method') == 'thread/realtime/error':
        raise CodexProtocolError(
            str(notification.get('params', {}).get('message', 'realtime error'))
        )

  async def append_text(self, text: str) -> None:
    if not self._thread_id or not self._started:
      raise CodexProtocolError('Codex realtime session is not started')
    await self._rpc.request(
        'thread/realtime/appendText',
        {'threadId': self._thread_id, 'text': text},
    )

  async def append_audio(
      self, data: bytes, *, sample_rate: int, num_channels: int
  ) -> None:
    if not self._thread_id or not self._started:
      raise CodexProtocolError('Codex realtime session is not started')
    await self._rpc.request(
        'thread/realtime/appendAudio',
        {
            'threadId': self._thread_id,
            'audio': {
                'data': base64.b64encode(data).decode('ascii'),
                'sampleRate': sample_rate,
                'numChannels': num_channels,
                'samplesPerChannel': len(data) // (2 * num_channels),
            },
        },
    )

  async def stop_realtime(self) -> None:
    if self._thread_id is not None:
      await self._rpc.request(
          'thread/realtime/stop', {'threadId': self._thread_id}
      )
    self._started = False

  async def close(self) -> None:
    await self._rpc.close()


class CodexTurnClient:
  """Text-turn app-server client usable with either Codex login mode."""

  def __init__(self, rpc: JsonlRpcClient):
    self._rpc = rpc
    self._thread_id: str | None = None

  async def initialize(self, *, client_name: str, client_version: str) -> Any:
    result = await self._rpc.request(
        'initialize',
        {
            'clientInfo': {
                'name': client_name,
                'title': 'Leonidas',
                'version': client_version,
            },
            'capabilities': {'experimentalApi': True},
        },
    )
    await self._rpc.notify('initialized')
    return result

  async def start_thread(self, objective: str) -> None:
    result = await self._rpc.request(
        'thread/start',
        {
            'ephemeral': True,
            'approvalPolicy': 'never',
            'sandbox': 'read-only',
            'baseInstructions': objective,
        },
    )
    try:
      self._thread_id = str(result['thread']['id'])
    except (KeyError, TypeError) as exc:
      raise CodexProtocolError('thread/start returned no thread id') from exc

  async def respond(self, text: str, *, model: str | None = None) -> str:
    if not self._thread_id:
      raise CodexProtocolError('Codex text thread is not started')
    params: dict[str, Any] = {
        'threadId': self._thread_id,
        'input': [{'type': 'text', 'text': text}],
    }
    if model:
      params['model'] = model
    result = await self._rpc.request('turn/start', params)
    try:
      turn_id = str(result['turn']['id'])
    except (KeyError, TypeError) as exc:
      raise CodexProtocolError('turn/start returned no turn id') from exc
    chunks: list[str] = []
    while True:
      notification = await self._rpc.next_notification()
      params = notification.get('params') or {}
      notification_turn_id = params.get('turnId') or (
          params.get('turn') or {}
      ).get('id')
      if notification_turn_id != turn_id:
        continue
      if notification.get('method') == 'item/agentMessage/delta':
        chunks.append(str(params.get('delta', '')))
      elif notification.get('method') == 'turn/completed':
        return ''.join(chunks)

  async def close(self) -> None:
    await self._rpc.close()


def notification_parts(
    message: dict[str, Any],
    *,
    audio_mimetype: str = 'audio/pcm;rate=24000',
    include_audio: bool = True,
) -> list[content_api.ProcessorPart]:
  """Translate confirmed realtime notifications into internal content parts."""
  method = message.get('method')
  params = message.get('params') or {}
  if method == 'thread/realtime/outputAudio/delta' and include_audio:
    audio = params.get('audio') or {}
    try:
      data = base64.b64decode(str(audio['data']), validate=True)
      sample_rate = int(audio['sampleRate'])
      num_channels = int(audio['numChannels'])
    except (KeyError, TypeError, ValueError) as exc:
      raise CodexProtocolError(
          'Invalid Codex output audio notification'
      ) from exc
    return [
        content_api.ProcessorPart(
            data,
            mimetype=audio_mimetype,
            substream_name='realtime',
            role='model',
            metadata={
                'sample_rate': sample_rate,
                'num_channels': num_channels,
                'codex_realtime': True,
            },
        )
    ]
  if method == 'thread/realtime/transcript/done':
    text = str(params.get('text', ''))
    if not text:
      return []
    return [
        content_api.ProcessorPart(
            text,
            role=str(params.get('role', 'model')),
            substream_name='output_transcription',
            metadata={'is_final': True, 'codex_realtime': True},
        )
    ]
  return []


class CodexRealtimeProcessor(processor.Processor):
  """A Processor facade for a persistent Codex realtime client."""

  def __init__(
      self,
      client: CodexRealtimeClient | None = None,
      *,
      objective: str,
      model: str | None = None,
      voice: str | None = None,
      version: str = 'v3',
      client_factory: (
          Callable[
              [],
              Awaitable[
                  tuple[CodexRealtimeClient, Callable[[], Awaitable[None]]]
              ],
          ]
          | None
      ) = None,
  ):
    super().__init__()
    self._client = client
    self._objective = objective
    self._model = model
    self._voice = voice
    self._version = version
    self._client_factory = client_factory

  async def call(self, content: Any):
    cleanup: Callable[[], Awaitable[None]] | None = None
    if self._client is None:
      if self._client_factory is None:
        raise CodexProtocolError('Codex client factory is not configured')
      self._client, cleanup = await self._client_factory()
    started = False
    input_task: asyncio.Task[Any] | None = None
    event_task: asyncio.Task[Any] | None = None
    input_iterator = aiter(content)
    try:
      first_part: content_api.ProcessorPart | None = None
      try:
        first_part = await anext(input_iterator)
      except StopAsyncIteration:
        pass
      sdp_offer: str | None = None
      if (
          first_part is not None
          and first_part.mimetype == CODEX_WEBRTC_OFFER_MIMETYPE
      ):
        sdp_offer = first_part.part.text
        if not isinstance(sdp_offer, str) or not sdp_offer:
          raise CodexProtocolError('Codex WebRTC SDP offer is empty')
        if (
            self._voice
            and self._voice not in capabilities.CODEX_WEBRTC_V1_VOICES
        ):
          raise CodexProtocolError(
              f'Codex WebRTC v1 does not support voice {self._voice!r}; '
              'choose a compatible Codex voice'
          )
      remote_sdp = await self._client.start_realtime(
          objective=self._objective,
          model=self._model,
          voice=self._voice,
          version=(
              'v3'
              if sdp_offer is not None and self._version == 'v3'
              else 'v1'
              if sdp_offer is not None
              else self._version
          ),
          sdp_offer=sdp_offer,
      )
      if remote_sdp is not None:
        yield content_api.ProcessorPart(
            remote_sdp,
            mimetype=CODEX_WEBRTC_ANSWER_MIMETYPE,
            role='model',
            substream_name='realtime',
            metadata={'codex_webrtc_answer': True},
        )
      started = True
      if first_part is not None and sdp_offer is None:
        await self._append_input(first_part)
      input_task = asyncio.create_task(anext(input_iterator))
      event_task = asyncio.create_task(self._client._rpc.next_notification())
      while True:
        done, _ = await asyncio.wait(
            (input_task, event_task), return_when=asyncio.FIRST_COMPLETED
        )
        if input_task in done:
          try:
            part = input_task.result()
          except StopAsyncIteration:
            break
          await self._append_input(part)
          input_task = asyncio.create_task(anext(input_iterator))
        if event_task in done:
          message = event_task.result()
          for output in notification_parts(
              message, include_audio=sdp_offer is None
          ):
            yield output
          event_task = asyncio.create_task(
              self._client._rpc.next_notification()
          )
    finally:
      tasks = [task for task in (input_task, event_task) if task is not None]
      for task in tasks:
        task.cancel()
      await asyncio.gather(*tasks, return_exceptions=True)
      try:
        if started:
          await self._client.stop_realtime()
      finally:
        if cleanup is not None:
          await cleanup()

  async def _append_input(self, part: content_api.ProcessorPart) -> None:
    if part.mimetype == CODEX_WEBRTC_OFFER_MIMETYPE:
      raise CodexProtocolError('Codex WebRTC offer must be the first input')
    if content_api.is_text(part.mimetype) and part.text.strip():
      await self._client.append_text(part.text.strip())
    elif content_api.is_audio(part.mimetype) and part.bytes:
      sample_rate = int(part.get_metadata('sample_rate') or 16000)
      channels = int(part.get_metadata('num_channels') or 1)
      await self._client.append_audio(
          part.bytes, sample_rate=sample_rate, num_channels=channels
      )


class _TestingServer:

  def __init__(
      self, incoming: asyncio.Queue[str], outgoing: asyncio.Queue[str]
  ):
    self._incoming = incoming
    self._outgoing = outgoing

  async def next_request(self) -> dict[str, Any]:
    while True:
      message = json.loads(await self._incoming.get())
      if 'id' in message:
        return message

  async def respond(self, request: dict[str, Any], result: Any) -> None:
    await self._outgoing.put(
        json.dumps({'id': request['id'], 'result': result})
    )

  async def notify(self, method: str, params: dict[str, Any]) -> None:
    await self._outgoing.put(json.dumps({'method': method, 'params': params}))

  async def request_from_server(
      self, method: str, params: dict[str, Any]
  ) -> None:
    await self._outgoing.put(
        json.dumps({'id': 9001, 'method': method, 'params': params})
    )


def testing_rpc_pair() -> tuple[JsonlRpcClient, list[str], _TestingServer]:
  incoming: asyncio.Queue[str] = asyncio.Queue()
  outgoing: asyncio.Queue[str] = asyncio.Queue()
  sent: list[str] = []

  async def send(line: str) -> None:
    sent.append(line)
    await incoming.put(line)

  async def receive() -> str:
    return await outgoing.get()

  rpc = JsonlRpcClient(send, receive)
  return rpc, sent, _TestingServer(incoming, outgoing)


def testing_pair() -> tuple[CodexRealtimeClient, list[str], _TestingServer]:
  rpc, sent, server = testing_rpc_pair()
  return (
      CodexRealtimeClient(rpc, audio_mimetype='audio/pcm;rate=24000'),
      sent,
      server,
  )
