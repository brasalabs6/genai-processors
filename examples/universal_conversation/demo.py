"""Offline multi-source smoke test for Universal AI / GenAI Processors.

Run: python -m examples.universal_conversation.demo
No API key, microphone, camera or network access is needed.
"""

import asyncio

from genai_processors import content_api
from genai_processors import processor

from universal_ai.contracts import ConversationNeeds
from universal_ai.contracts import ProviderCapabilities
from universal_ai.streaming import run_conversation


class OfflineEchoBackend(processor.Processor):
  """A fake provider proving real Processor composition works offline."""

  async def call(self, content):
    async for part in content:
      if content_api.is_text(part.mimetype):
        yield content_api.ProcessorPart(
            f'echo: {part.text}',
            role='model',
            metadata={'ua_source': part.get_metadata('ua_source')},
        )


async def text_source():
  for message in ('Olá!', 'Como vai?'):
    await asyncio.sleep(0)
    yield content_api.ProcessorPart(message, role='user')


async def status_source():
  for message in ('status: camera available', 'status: user listening'):
    await asyncio.sleep(0)
    yield content_api.ProcessorPart(message, role='user')


async def main():
  capabilities = ProviderCapabilities(
      provider_id='offline_echo',
      input_modalities=frozenset({'text'}),
      output_modalities=frozenset({'text'}),
  )
  async for event in run_conversation(
      OfflineEchoBackend(),
      capabilities,
      ConversationNeeds(),
      {'terminal': text_source(), 'events': status_source()},
  ):
    print(event.text, f'(origem={event.get_metadata("ua_source")})')


if __name__ == '__main__':
  asyncio.run(main())
