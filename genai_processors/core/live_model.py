# Copyright 2026 DeepMind Technologies Limited. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

"""Wraps the Gemini Live API into a Processor.

The list of available models can be found at
https://ai.google.dev/gemini-api/docs/models
Note that only Live models will work with the LiveProcessor.

## Example usage

```py
p = LiveProcessor(
    api_key=API_KEY,
    model_name="gemini-2.0-flash-live-001",
)
```

Given a stream of content, you can use the processor to generate
a stream of content as follows:

```py
async for part in p(['hello', 'world']):
  # Do something with part
```

The Live Processor processor only considers parts with the substream name
"realtime" as input (sent to real-time methods), or with the default substream
name (sent to content generate method).
"""

import asyncio
from collections.abc import AsyncIterable
import enum
import re
import time
from typing import Iterable, Optional
from absl import logging
from genai_processors import content_api
from genai_processors import processor
from google.genai import client
from google.genai import live
from google.genai import types as genai_types


PartTypes = content_api.ProcessorPartTypes
ProcessorPart = content_api.ProcessorPart
ProcessorPartTypes = content_api.ProcessorPartTypes


class DefaultInputTransport(enum.StrEnum):
  """Transport used for parts received on the default substream."""

  CLIENT_CONTENT = 'client_content'
  REALTIME_INPUT = 'realtime_input'


class RealtimeMediaTransport(enum.StrEnum):
  """Wire field used for realtime audio and video blobs."""

  MEDIA = 'media'
  TYPED = 'typed'


def to_parts(
    msg: genai_types.LiveServerMessage,
) -> Iterable[content_api.ProcessorPart]:
  """Converts a LiveServerMessage to a stream of ProcessorParts."""
  if msg.server_content:
    metadata = msg.server_content.to_json_dict()
    if 'model_turn' in metadata:
      del metadata['model_turn']
    if msg.server_content.model_turn:
      for part in msg.server_content.model_turn.parts:
        yield content_api.ProcessorPart(
            value=part,
            role=msg.server_content.model_turn.role,
        )
    for k, v in metadata.items():
      value = ''
      if k in ('input_transcription', 'output_transcription'):
        if 'text' in v:
          value = v['text']
        yield content_api.ProcessorPart(
            value=value,
            role='model',
            substream_name=k,
        )
      else:
        yield content_api.ProcessorPart(
            value='',
            role='model',
            metadata={k: v},
        )
  if msg.tool_call:
    function_calls = msg.tool_call.function_calls
    for function_call in function_calls:
      yield content_api.ProcessorPart.from_function_call(
          name=function_call.name,
          args=function_call.args,
          role='model',
          metadata={'id': function_call.id},
      )
  if msg.tool_call_cancellation and msg.tool_call_cancellation.ids:
    for function_call_id in msg.tool_call_cancellation.ids:
      yield content_api.ProcessorPart.from_tool_cancellation(
          function_call_id=function_call_id,
      )
  if msg.usage_metadata:
    yield content_api.ProcessorPart(
        value='',
        role='model',
        metadata={'usage_metadata': msg.usage_metadata.to_json_dict()},
    )

  if msg.go_away:
    yield content_api.ProcessorPart(
        value='',
        role='model',
        metadata={'go_away': msg.go_away.to_json_dict()},
    )

  if msg.session_resumption_update:
    yield content_api.ProcessorPart(
        value='',
        role='model',
        metadata={
            'session_resumption_update': (
                msg.session_resumption_update.to_json_dict()
            )
        },
    )


class LiveProcessor(processor.Processor):
  """Gemini Live API Processor to generate realtime content.

  The realtime content captured via mic and camera should be passed to the
  processor with the `realtime` substream name. The default substream is used
  for standard content input.

  An image sent on the default substream will be processed by the model as an
  ad-hoc user input, not as a realtime input captured from realtime devices.
  This lets the user send an image to the model and ask a question about it,
  for example "What is this?", independently of the video stream being sent to
  the model on the `realtime` substream.
  """

  def __init__(
      self,
      api_key: str,
      model_name: str,
      realtime_config: Optional[genai_types.LiveConnectConfigOrDict] = None,
      debug_config: client.DebugConfig | None = None,
      http_options: (
          genai_types.HttpOptions | genai_types.HttpOptionsDict | None
      ) = None,
      default_input_transport: DefaultInputTransport = (
          DefaultInputTransport.CLIENT_CONTENT
      ),
      realtime_media_transport: RealtimeMediaTransport = (
          RealtimeMediaTransport.MEDIA
      ),
  ):
    """Initializes the Live Processor.

    Args:
      api_key: The [API key](https://ai.google.dev/gemini-api/docs/api-key) to
        use for authentication. Applies to the Gemini Developer API only.
      model_name: The name of the model to use. See
        https://ai.google.dev/gemini-api/docs/models for a list of available
          models. Only use models with a `-live-` suffix.
      realtime_config: The configuration for generating realtime content.
      debug_config: Config settings that control network behavior of the client.
        This is typically used when running test code.
      http_options: Http options to use for the client. These options will be
        applied to all requests made by the client. Example usage: `client =
        genai.Client(http_options=types.HttpOptions(api_version='v1'))`.
      default_input_transport: Transport used for parts without a substream
        name. The default preserves the turn-based `send_client_content`
        behavior. `REALTIME_INPUT` is intended for Live models that require
        text and media context through `send_realtime_input`.
      realtime_media_transport: Wire representation for realtime blobs.
        `MEDIA` preserves the legacy `media` field. `TYPED` sends PCM through
        `audio` and image frames through `video`.

    Returns:
      A `Processor` that calls the Genai API in a realtime (aka live) fashion.
    """
    self._client = client.Client(
        api_key=api_key,
        debug_config=debug_config,
        http_options=http_options,
    )
    self._model_name = model_name
    self._realtime_config = realtime_config
    self._default_input_transport = default_input_transport
    self._realtime_media_transport = realtime_media_transport

  async def _send_realtime_media(
      self,
      session: live.AsyncSession,
      media_blob: genai_types.Blob,
  ) -> None:
    """Sends one realtime blob using the configured wire representation."""
    if self._realtime_media_transport == RealtimeMediaTransport.MEDIA:
      await session.send_realtime_input(media=media_blob)
    elif content_api.is_audio(media_blob.mime_type):
      await session.send_realtime_input(audio=media_blob)
    elif content_api.is_image(media_blob.mime_type):
      await session.send_realtime_input(video=media_blob)
    else:
      raise ValueError(
          'Typed realtime input only supports audio or image media.'
      )

  async def call(
      self, content: processor.ProcessorStream
  ) -> AsyncIterable[ProcessorPartTypes]:

    output_queue = asyncio.Queue[Optional[ProcessorPart]](maxsize=1_000)

    async with self._client.aio.live.connect(
        model=self._model_name,
        config=self._realtime_config,
    ) as session:

      async def consume_content():
        async for chunk_part in content:
          if chunk_part.part.function_response:
            logging.debug(
                '%s - Live Processor: sending tool response: %s',
                time.perf_counter(),
                chunk_part,
            )
            await session.send_tool_response(
                function_responses=chunk_part.part.function_response
            )
          elif (
              chunk_part.substream_name == 'realtime'
              and chunk_part.get_metadata('audio_stream_end')
          ):
            logging.debug(
                '%s - Live Processor: sending realtime audio_stream_end',
                time.perf_counter(),
            )
            await session.send_realtime_input(audio_stream_end=True)
          elif (
              chunk_part.substream_name == 'realtime'
              and chunk_part.part.inline_data
          ):
            await self._send_realtime_media(
                session, chunk_part.part.inline_data
            )
          elif chunk_part.substream_name == 'realtime' and content_api.is_text(
              chunk_part.mimetype
          ):
            logging.debug(
                '%s - Live Processor: sending realtime input: %s',
                time.perf_counter(),
                chunk_part.text,
            )
            await session.send_realtime_input(text=chunk_part.text)
          elif not chunk_part.substream_name:
            # Default substream.
            if (
                self._default_input_transport
                == DefaultInputTransport.REALTIME_INPUT
            ):
              if content_api.is_text(chunk_part.mimetype):
                logging.debug(
                    '%s - Live Processor: sending default realtime text',
                    time.perf_counter(),
                )
                await session.send_realtime_input(text=chunk_part.text)
              elif chunk_part.part.inline_data:
                await self._send_realtime_media(
                    session, chunk_part.part.inline_data
                )
              else:
                raise ValueError(
                    'Default realtime input only supports text or inline media.'
                )
            else:
              logging.debug(
                  '%s - Live Processor: sending client content: %s',
                  time.perf_counter(),
                  chunk_part.part,
              )
              turn_complete = chunk_part.get_metadata('turn_complete')
              await session.send_client_content(
                  turns=genai_types.Content(
                      parts=[chunk_part.part], role=chunk_part.role
                  ),
                  turn_complete=(
                      True if turn_complete is None else turn_complete
                  ),
              )
          else:
            logging.debug(
                '%s - Live Processor: part passed through: %s',
                time.perf_counter(),
                chunk_part,
            )
            await output_queue.put(chunk_part)
        await output_queue.put(None)

      async def produce_content():
        try:
          while True:
            async for response in session.receive():
              if not (
                  response.server_content
                  and response.server_content.model_turn
                  and response.server_content.model_turn.parts
                  and response.server_content.model_turn.parts[0].inline_data
              ):
                logging.debug(
                    '%s - Live Processor Response: %s',
                    time.perf_counter(),
                    # Remove the None values from the response.
                    re.sub(r'(,\s)?[^\(\s]+=None,?\s?', '', str(response)),
                )
              for part in to_parts(response):
                await output_queue.put(part)
            # Allow `yield` if session.receive() does not return anything.
            await asyncio.sleep(0)
        finally:
          await output_queue.put(None)

      consume_content_task = processor.create_task(consume_content())
      produce_content_task = processor.create_task(produce_content())

      while chunk := await output_queue.get():
        yield chunk

      consume_content_task.cancel()
      produce_content_task.cancel()
