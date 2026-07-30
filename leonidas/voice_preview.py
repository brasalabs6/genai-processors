"""Bounded Gemini Live voice previews isolated from the active session."""

import asyncio
import io
import wave

from google import genai
from google.genai import types

from leonidas import capabilities


class GeminiVoicePreview:
  """Produces a short WAV using an ephemeral provider session."""

  def __init__(self, api_key: str, *, timeout: float = 15.0):
    self._client = genai.Client(api_key=api_key)
    self._timeout = timeout
    self._lock = asyncio.Lock()

  async def preview(self, model_id: str, voice_name: str, text: str) -> bytes:
    capabilities.resolve_model(model_id)
    if voice_name not in capabilities.VOICES:
      raise ValueError('Unsupported voice')
    sample = text.strip()[:240]
    if not sample:
      raise ValueError('Preview text must not be empty')
    if self._lock.locked():
      raise RuntimeError('A voice preview is already running')
    async with self._lock:
      pcm = await asyncio.wait_for(
          self._generate(model_id, voice_name, sample),
          timeout=self._timeout,
      )
    return self._wav(pcm)

  async def _generate(self, model_id: str, voice_name: str, text: str) -> bytes:
    config = types.LiveConnectConfig(
        response_modalities=['AUDIO'],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name=voice_name
                )
            )
        ),
    )
    chunks = bytearray()
    async with self._client.aio.live.connect(
        model=model_id, config=config
    ) as session:
      await session.send_client_content(
          turns=types.Content(role='user', parts=[types.Part(text=text)]),
          turn_complete=True,
      )
      async for response in session.receive():
        server_content = response.server_content
        if server_content and server_content.model_turn:
          for part in server_content.model_turn.parts or []:
            if part.inline_data and part.inline_data.data:
              chunks.extend(part.inline_data.data)
              if len(chunks) >= 24000 * 2 * 10:
                return bytes(chunks[: 24000 * 2 * 10])
        if server_content and server_content.turn_complete:
          break
    if not chunks:
      raise RuntimeError('The provider returned no preview audio')
    return bytes(chunks)

  @staticmethod
  def _wav(pcm: bytes) -> bytes:
    output = io.BytesIO()
    with wave.open(output, 'wb') as wav_file:
      wav_file.setnchannels(1)
      wav_file.setsampwidth(2)
      wav_file.setframerate(24000)
      wav_file.writeframes(pcm)
    return output.getvalue()
