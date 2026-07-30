"""Declarative provider capabilities for Leonidas pipelines."""

import dataclasses
from typing import Any


MODEL_LIVE_2_5 = 'gemini-2.5-flash-native-audio-preview-12-2025'
MODEL_LIVE_3_1 = 'gemini-3.1-flash-live-preview'
DEFAULT_MODEL = MODEL_LIVE_2_5
PIPELINE_GEMINI = 'gemini_live'
PIPELINE_CASCADE = 'cascade_local'
PARAKEET_V3_MODEL = 'nvidia/parakeet-tdt-0.6b-v3'
GROQ_GPT_OSS_20B = 'openai/gpt-oss-20b'
GROQ_GPT_OSS_120B = 'openai/gpt-oss-120b'
XTTS_V2_MODEL = 'tts_models/multilingual/multi-dataset/xtts_v2'
CASCADE_VOICES = ('leonidas',)

VOICES = (
    'Zephyr',
    'Puck',
    'Charon',
    'Kore',
    'Fenrir',
    'Leda',
    'Orus',
    'Aoede',
    'Callirrhoe',
    'Autonoe',
    'Enceladus',
    'Iapetus',
    'Umbriel',
    'Algieba',
    'Despina',
    'Erinome',
    'Algenib',
    'Rasalgethi',
    'Laomedeia',
    'Achernar',
    'Alnilam',
    'Schedar',
    'Gacrux',
    'Pulcherrima',
    'Achird',
    'Zubenelgenubi',
    'Vindemiatrix',
    'Sadachbia',
    'Sadaltager',
    'Sulafat',
)


@dataclasses.dataclass(frozen=True)
class ModelCapability:
  """Capabilities needed to construct one Gemini Live profile."""

  model_id: str
  label: str
  default_input_transport: str
  realtime_media_transport: str
  function_call_mode: str
  thinking_field: str

  def to_public_dict(self) -> dict[str, Any]:
    return {
        'id': self.model_id,
        'label': self.label,
        'pipeline_id': 'gemini_live',
        'input_modalities': ['audio', 'image', 'text'],
        'output_modalities': ['audio', 'transcription'],
        'native_audio': True,
        'vision': True,
        'voices': True,
        'vad': True,
        'thinking_field': self.thinking_field,
        'function_call_mode': self.function_call_mode,
    }


_MODELS = {
    MODEL_LIVE_2_5: ModelCapability(
        model_id=MODEL_LIVE_2_5,
        label='Gemini 2.5 Flash Native Audio',
        default_input_transport='client_content',
        realtime_media_transport='media',
        function_call_mode='async_scheduled',
        thinking_field='thinking_budget',
    ),
    MODEL_LIVE_3_1: ModelCapability(
        model_id=MODEL_LIVE_3_1,
        label='Gemini 3.1 Flash Live Preview',
        default_input_transport='realtime_input',
        realtime_media_transport='typed',
        function_call_mode='synchronous',
        thinking_field='thinking_level',
    ),
}


def resolve_model(model_id: str) -> ModelCapability:
  """Returns an allowlisted model profile."""
  try:
    return _MODELS[model_id]
  except KeyError as exc:
    raise ValueError(f'Unsupported live model: {model_id!r}.') from exc


def public_capabilities() -> dict[str, Any]:
  """Returns the browser-safe capability document."""
  return {
      'schema_version': 1,
      'pipelines': [
          {
              'id': PIPELINE_GEMINI,
              'label': 'Gemini Live',
              'implemented': True,
              'vision': True,
              'models': [model.to_public_dict() for model in _MODELS.values()],
          },
          {
              'id': PIPELINE_CASCADE,
              'label': 'Local + Groq',
              'implemented': True,
              'vision': False,
              'input_modalities': ['audio', 'text'],
              'output_modalities': ['audio', 'text', 'transcription'],
              'stt_models': [PARAKEET_V3_MODEL],
              'llm_models': [GROQ_GPT_OSS_20B, GROQ_GPT_OSS_120B],
              'tts_models': [XTTS_V2_MODEL],
              'voices': list(CASCADE_VOICES),
              'reasoning_efforts': ['low', 'medium', 'high'],
              'devices': ['auto', 'cuda', 'cpu'],
          },
      ],
      'voices': list(VOICES),
      'presets': ['low_latency', 'balanced', 'quality'],
      'limits': {
          'objective_characters': [1, 12000],
          'frame_interval_ms': [250, 10000],
          'frame_width': [160, 1920],
          'frame_height': [120, 1080],
          'jpeg_quality': [0.3, 0.95],
          'temperature': [0.0, 2.0],
      },
  }
