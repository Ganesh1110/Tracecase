"""Requirements engineering and test generation package (Phase 9.1)."""

from tracecase.requirements.evidence import (
    EvidenceCatalog,
    ObservedEvidenceRecord,
    extract_evidence_catalog,
)
from tracecase.requirements.generator import (
    generate_journey_from_requirements,
    generate_journey_from_requirements_sync,
)
from tracecase.requirements.matcher import (
    IntentMatchResult,
    match_intent_to_evidence,
)
from tracecase.requirements.models import (
    AcceptanceCriterion,
    RequirementFormat,
    RequirementSpec,
    TestIntent,
    ValidationStatus,
)
from tracecase.requirements.parsers import (
    detect_requirement_format,
    parse_acceptance_criteria,
    parse_gherkin,
    parse_natural_language,
    parse_openapi,
    parse_requirement,
    parse_user_story,
)

__all__ = [
    "AcceptanceCriterion",
    "EvidenceCatalog",
    "IntentMatchResult",
    "ObservedEvidenceRecord",
    "RequirementFormat",
    "RequirementSpec",
    "TestIntent",
    "ValidationStatus",
    "detect_requirement_format",
    "extract_evidence_catalog",
    "generate_journey_from_requirements",
    "generate_journey_from_requirements_sync",
    "match_intent_to_evidence",
    "parse_acceptance_criteria",
    "parse_gherkin",
    "parse_natural_language",
    "parse_openapi",
    "parse_requirement",
    "parse_user_story",
]
