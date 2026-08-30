"""Versioned local control API independent from the media transport."""

import dataclasses
import json
from pathlib import PurePosixPath
import uuid
from typing import Any, Callable, Mapping, Protocol
from urllib import parse

from leonidas import capabilities
from leonidas import config
from leonidas import log_store
from leonidas import runtime
from leonidas import telemetry


class VoicePreview(Protocol):

  async def preview(
      self,
      model_id: str,
      voice_name: str,
      text: str,
      *,
      device: str = 'auto',
  ) -> bytes:
    ...


@dataclasses.dataclass(frozen=True)
class ApiResponse:
  status: int
  body: str | bytes
  content_type: str = 'application/json; charset=utf-8'
  headers: Mapping[str, str] = dataclasses.field(default_factory=dict)


def _json_response(
    data: Any = None,
    *,
    status: int = 200,
    error: dict[str, Any] | None = None,
) -> ApiResponse:
  return ApiResponse(
      status,
      json.dumps(
          {
              'data': data,
              'error': error,
              'request_id': uuid.uuid4().hex,
          },
          ensure_ascii=False,
      ),
  )


def _error(status: int, code: str, message: str) -> ApiResponse:
  return _json_response(
      status=status,
      error={'code': code, 'message': message, 'details': None},
  )


class ControlApi:
  """Pure route dispatcher used by the threaded HTTP adapter."""

  def __init__(
      self,
      *,
      config_store: config.ConfigStore,
      session: runtime.SessionManager,
      metrics: telemetry.MetricsStore,
      logs: log_store.LogStore,
      voice_preview: VoicePreview,
      resources: Callable[[], dict[str, Any]] | None = None,
  ):
    self._config = config_store
    self._session = session
    self._metrics = metrics
    self._logs = logs
    self._voice_preview = voice_preview
    self._resources = resources or (
        lambda: {
            'schema_version': 1,
            'overall_state': 'unloaded',
            'components': [],
        }
    )

  def _reset_metrics_for_new_session(self) -> None:
    state = self._session.snapshot().get('state')
    if state not in (
        runtime.SessionState.STARTING.value,
        runtime.SessionState.RUNNING.value,
        runtime.SessionState.STOPPING.value,
    ):
      self._metrics.reset_session()

  async def dispatch(
      self,
      method: str,
      raw_path: str,
      body: Mapping[str, Any] | None = None,
  ) -> ApiResponse:
    parsed = parse.urlsplit(raw_path)
    path = parsed.path.rstrip('/') or '/'
    body = body or {}
    try:
      if method == 'GET' and path == '/api/v1/capabilities':
        return _json_response(capabilities.public_capabilities())
      if method == 'GET' and path == '/api/v1/config':
        return _json_response(self._config.snapshot().to_dict())
      if method == 'PUT' and path == '/api/v1/config/draft':
        snapshot = self._config.update_draft(
            body.get('updates', {}),
            expected_revision=int(body['expected_revision']),
        )
        return _json_response(snapshot.to_dict())
      if method == 'POST' and path == '/api/v1/config/apply':
        if self._session.snapshot().get('state') in (
            runtime.SessionState.STARTING.value,
            runtime.SessionState.RUNNING.value,
        ):
          self._metrics.reset_session()
        return _json_response(await self._session.apply_config())
      if method == 'GET' and path == '/api/v1/session':
        return _json_response(self._session.snapshot())
      if method == 'POST' and path == '/api/v1/session/start':
        self._reset_metrics_for_new_session()
        snapshot = await self._session.start()
        return _json_response(
            snapshot, status=202 if snapshot.get('state') == 'starting' else 200
        )
      if method == 'POST' and path == '/api/v1/session/stop':
        return _json_response(await self._session.stop())
      if method == 'GET' and path == '/api/v1/metrics':
        return _json_response(self._metrics.snapshot())
      if method == 'GET' and path == '/api/v1/resources':
        return _json_response(self._resources())
      if method == 'GET' and path == '/api/v1/logs':
        return _json_response({'files': self._logs.list_files()})
      if method == 'GET' and path.startswith('/api/v1/logs/'):
        log_id = parse.unquote(path.removeprefix('/api/v1/logs/'))
        if not log_id or len(PurePosixPath(log_id).parts) != 1:
          raise log_store.InvalidLogIdError('Invalid log id')
        query = parse.parse_qs(parsed.query)
        cursor = int(query.get('cursor', ['0'])[0])
        limit = int(query.get('limit', ['500'])[0])
        return _json_response(
            self._logs.read(log_id, cursor=cursor, limit=limit)
        )
      if method == 'POST' and path == '/api/v1/voices/preview':
        model_id = str(body.get('model_id', ''))
        voice_name = str(body.get('voice_name', ''))
        local_preview = model_id in (
            capabilities.GROQ_GPT_OSS_20B,
            capabilities.GROQ_GPT_OSS_120B,
        )
        if local_preview:
          supported_voices = capabilities.CASCADE_VOICES
          if self._session.snapshot().get('state') in (
              runtime.SessionState.STARTING.value,
              runtime.SessionState.RUNNING.value,
              runtime.SessionState.STOPPING.value,
          ):
            return _error(
                409,
                'session_busy',
                'Stop the local session before generating a voice preview',
            )
        else:
          capabilities.resolve_model(model_id)
          supported_voices = capabilities.VOICES
        if voice_name not in supported_voices:
          raise config.ConfigValidationError('voice_name is not supported')
        draft = self._config.snapshot().draft
        device = draft.cascade.device if local_preview else 'auto'
        audio = await self._voice_preview.preview(
            model_id,
            voice_name,
            str(body.get('text', 'Olá, eu sou Leonidas. Como posso ajudar?')),
            device=device,
        )
        return ApiResponse(
            200,
            audio,
            content_type='audio/wav',
            headers={'Cache-Control': 'no-store'},
        )
      return _error(404, 'not_found', 'Endpoint not found')
    except KeyError:
      return _error(422, 'invalid_request', 'A required field is missing')
    except config.RevisionConflictError as exc:
      return _error(409, 'revision_conflict', str(exc))
    except runtime.MediaNotConnectedError as exc:
      return _error(409, 'media_not_connected', str(exc))
    except runtime.MediaAlreadyConnectedError as exc:
      return _error(409, 'media_already_connected', str(exc))
    except log_store.InvalidLogIdError as exc:
      return _error(404, 'invalid_log_id', str(exc))
    except (config.ConfigValidationError, TypeError, ValueError) as exc:
      return _error(422, 'invalid_configuration', str(exc))
    except RuntimeError:
      return _error(
          503,
          'runtime_unavailable',
          'The selected runtime dependency is unavailable',
      )
    except TimeoutError:
      return _error(504, 'provider_timeout', 'The provider did not respond')
