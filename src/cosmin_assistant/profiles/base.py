"""Abstract profile contract for COSMIN assistant capability metadata."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable

from cosmin_assistant.models.enums import ProfileType
from cosmin_assistant.profiles.constants import CosminBoxKey, MeasurementPropertyKey


class BaseProfile(ABC):
    """Abstract profile metadata contract used to drive extraction and scoring.

    Profiles are declarative. They do not execute scoring logic; they expose
    capability and limitation metadata for downstream deterministic stages.
    """

    def __init__(self) -> None:
        self._validate_contract()

    @property
    @abstractmethod
    def profile_type(self) -> ProfileType:
        """Profile type identifier."""

    @property
    @abstractmethod
    def applicable_measurement_properties(self) -> tuple[MeasurementPropertyKey, ...]:
        """Measurement properties this profile can represent."""

    @property
    @abstractmethod
    def applicable_cosmin_boxes(self) -> tuple[CosminBoxKey, ...]:
        """COSMIN boxes this profile can evaluate."""

    @property
    @abstractmethod
    def required_extraction_fields(self) -> tuple[str, ...]:
        """Extraction fields required before downstream assessments."""

    @property
    @abstractmethod
    def deterministic_rules_available(self) -> tuple[str, ...]:
        """Deterministic rule identifiers usable for this profile."""

    @property
    @abstractmethod
    def reviewer_required_decisions(self) -> tuple[str, ...]:
        """Reviewer decisions required for non-deterministic judgment areas."""

    @property
    @abstractmethod
    def unsupported_auto_scoring_areas(self) -> tuple[str, ...]:
        """Auto-scoring areas intentionally unsupported by this profile."""

    @property
    @abstractmethod
    def adaptation_points(self) -> tuple[str, ...]:
        """Explicit adaptation notes and known limits for this profile."""

    def supports_measurement_property(self, property_key: MeasurementPropertyKey) -> bool:
        """Return true when this profile supports a measurement property."""

        return property_key in self.applicable_measurement_properties

    def supports_cosmin_box(self, box_key: CosminBoxKey) -> bool:
        """Return true when this profile supports a COSMIN RoB box."""

        return box_key in self.applicable_cosmin_boxes

    def requires_field(self, field_name: str) -> bool:
        """Return true when an extraction field is required by this profile."""

        return field_name in self.required_extraction_fields

    def has_deterministic_rule(self, rule_id: str) -> bool:
        """Return true when a rule ID is available for deterministic use."""

        return rule_id in self.deterministic_rules_available

    def requires_reviewer_decision(self, decision_key: str) -> bool:
        """Return true when a reviewer decision key is required."""

        return decision_key in self.reviewer_required_decisions

    def supports_auto_scoring_area(self, area_key: str) -> bool:
        """Return true when an auto-scoring area is not explicitly unsupported."""

        return area_key not in self.unsupported_auto_scoring_areas

    def to_metadata(self) -> dict[str, object]:
        """Serialize profile capabilities into JSON-friendly metadata."""

        return {
            "profile_type": self.profile_type.value,
            "applicable_measurement_properties": [
                value.value for value in self.applicable_measurement_properties
            ],
            "applicable_cosmin_boxes": [value.value for value in self.applicable_cosmin_boxes],
            "required_extraction_fields": list(self.required_extraction_fields),
            "deterministic_rules_available": list(self.deterministic_rules_available),
            "reviewer_required_decisions": list(self.reviewer_required_decisions),
            "unsupported_auto_scoring_areas": list(self.unsupported_auto_scoring_areas),
            "adaptation_points": list(self.adaptation_points),
        }

    def _validate_contract(self) -> None:
        self._validate_unique(
            self.applicable_measurement_properties,
            "applicable_measurement_properties",
        )
        self._validate_unique(self.applicable_cosmin_boxes, "applicable_cosmin_boxes")
        self._validate_unique(self.required_extraction_fields, "required_extraction_fields")
        self._validate_unique(
            self.deterministic_rules_available,
            "deterministic_rules_available",
        )
        self._validate_unique(
            self.reviewer_required_decisions,
            "reviewer_required_decisions",
        )
        self._validate_unique(
            self.unsupported_auto_scoring_areas,
            "unsupported_auto_scoring_areas",
        )
        self._validate_unique(self.adaptation_points, "adaptation_points")

        if self.profile_type is not ProfileType.PROM:
            if not self.unsupported_auto_scoring_areas:
                msg = "non-PROM profiles must explicitly declare unsupported auto-scoring areas"
                raise ValueError(msg)
            if not self.adaptation_points:
                msg = "non-PROM profiles must explicitly declare adaptation points"
                raise ValueError(msg)

    @staticmethod
    def _validate_unique(values: Iterable[object], field_name: str) -> None:
        values_list = list(values)
        if len(values_list) != len(set(values_list)):
            msg = f"{field_name} contains duplicate values"
            raise ValueError(msg)
