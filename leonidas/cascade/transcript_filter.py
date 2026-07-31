"""Conservative post-STT validation for short Portuguese microphone turns."""

import re
import unicodedata


_SHORT_ENGLISH_ARTIFACTS = frozenset(
    {
        'yeah',
        'yep',
        'you',
        'me',
        'mm',
        'mmm',
        'mm hmm',
        'uh huh',
        'okay',
        'okey',
    }
)
_WORD_RE = re.compile(r"[^a-z0-9' ]+")


def _canonical(text: str) -> str:
  normalized = unicodedata.normalize('NFKD', text).encode(
      'ascii', errors='ignore'
  ).decode('ascii')
  return ' '.join(_WORD_RE.sub(' ', normalized.lower()).split())


def is_probable_short_artifact(
    text: str,
    *,
    audio_duration_seconds: float,
    language: str,
) -> bool:
  """Rejects only evidenced, very short cross-language hallucinations.

  Valid Portuguese acknowledgements such as ``sim``, ``não`` and ``aham`` are
  intentionally not filtered. Longer utterances are always preserved, even if
  they contain one of the listed English words.
  """
  if language != 'pt' or audio_duration_seconds > 1.1:
    return False
  return _canonical(text) in _SHORT_ENGLISH_ARTIFACTS
