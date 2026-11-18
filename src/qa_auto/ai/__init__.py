"""Local-first AI analysis and provider module."""

from qa_auto.ai.models import AnalysisResult, Annotation, Message
from qa_auto.ai.provider import (
    NullProvider,
    OllamaProvider,
    OpenAICompatProvider,
    Provider,
    get_provider,
)

__all__ = [
    "AnalysisResult",
    "Annotation",
    "Message",
    "NullProvider",
    "OllamaProvider",
    "OpenAICompatProvider",
    "Provider",
    "get_provider",
]
