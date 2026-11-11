"""Provider-agnostic conversational runtime primitives for GenAI Processors.

This package is additive: it does not replace the genai_processors API or the
Leonidas application. See docs/architecture/universal-ai.md.
"""

from universal_ai.contracts import CapabilityError
from universal_ai.contracts import ConversationNeeds
from universal_ai.contracts import ProviderCapabilities
from universal_ai.contracts import SourceSettings
from universal_ai.ingress import BoundedIngress

__all__ = [
    'BoundedIngress',
    'CapabilityError',
    'ConversationNeeds',
    'ProviderCapabilities',
    'SourceSettings',
]
