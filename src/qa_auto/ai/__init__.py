"""Local-first AI analysis and QA intelligence module."""

from qa_auto.ai.assertion_generator import (
    AssertionGenerationResult,
    AssertionSuggestion,
    generate_heuristic_assertions,
    suggest_assertions,
)
from qa_auto.ai.coverage_analyst import (
    CoverageIntelligenceResult,
    RouteCoverage,
    analyze_corpus_coverage,
)
from qa_auto.ai.failure_analyst import (
    FailureAnalysisResult,
    FailureCategory,
    analyze_execution_failure,
    analyze_failure_heuristics,
)
from qa_auto.ai.models import AnalysisResult, Annotation, Message
from qa_auto.ai.provider import (
    NullProvider,
    OllamaProvider,
    OpenAICompatProvider,
    Provider,
    get_provider,
)
from qa_auto.ai.selectors import (
    SelectorAnalysis,
    SelectorAuditReport,
    audit_testcase_selectors,
    evaluate_selector,
)
from qa_auto.ai.variations import (
    GeneratedVariation,
    VariationMutation,
    generate_heuristic_variations,
    generate_smart_variations,
)

__all__ = [
    "AnalysisResult",
    "Annotation",
    "AssertionGenerationResult",
    "AssertionSuggestion",
    "CoverageIntelligenceResult",
    "FailureAnalysisResult",
    "FailureCategory",
    "GeneratedVariation",
    "Message",
    "NullProvider",
    "OllamaProvider",
    "OpenAICompatProvider",
    "Provider",
    "RouteCoverage",
    "SelectorAnalysis",
    "SelectorAuditReport",
    "VariationMutation",
    "analyze_corpus_coverage",
    "analyze_execution_failure",
    "analyze_failure_heuristics",
    "audit_testcase_selectors",
    "evaluate_selector",
    "generate_heuristic_assertions",
    "generate_heuristic_variations",
    "generate_smart_variations",
    "get_provider",
    "suggest_assertions",
]
