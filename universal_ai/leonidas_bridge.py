"""Optional composition adapter around existing Leonidas pipelines.

No changes to Leonidas's default behavior or websocket contract are required.
A future rollout can opt into this adapter in PipelineRegistry after E2E checks.
"""

from genai_processors import processor

from universal_ai.contracts import ConversationNeeds
from universal_ai.contracts import ProviderCapabilities
from universal_ai.streaming import compose_conversation


def leonidas_capabilities(pipeline_id: str) -> ProviderCapabilities:
  """Map current Leonidas pipeline IDs to explicit generic capabilities."""
  if pipeline_id == 'gemini_live':
    return ProviderCapabilities(
        provider_id='leonidas/gemini_live',
        input_modalities=frozenset({'audio', 'text', 'image'}),
        output_modalities=frozenset({'audio', 'text'}),
        barge_in=True,
        native_audio=True,
    )
  if pipeline_id == 'cascade_local':
    return ProviderCapabilities(
        provider_id='leonidas/cascade_local',
        input_modalities=frozenset({'audio', 'text'}),
        output_modalities=frozenset({'audio', 'text'}),
        barge_in=True,
    )
  raise ValueError(f'Unknown Leonidas pipeline: {pipeline_id}')


def wrap_leonidas_pipeline(
    backend: processor.Processor,
    pipeline_id: str,
    requirements: ConversationNeeds,
) -> processor.Processor:
  """Add generic realtime vision policy to an already configured pipeline."""
  return compose_conversation(
      backend, leonidas_capabilities(pipeline_id), requirements
  )
