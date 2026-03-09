"""Abstract profile contract for COSMIN assistant capability metadata."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping

from cosmin_assistant.models.enums import ProfileType
from cosmin_assistant.profiles.constants import (
    CosminBoxKey,
    CosminReviewStepKey,
    MeasurementPropertyKey,
    ProfileCapabilityStatus,
    TableTemplateKey,
)

_NON_PROM_ADAPTED_STEPS: tuple[CosminReviewStepKey, ...] = (
    CosminReviewStepKey.STEP_5_MODIFIED_GRADE,
    CosminReviewStepKey.STEP_6_TABLE_BUILDING,
    CosminReviewStepKey.STEP_7_INTERPRETATION_AND_RECOMMENDATION,
)


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
    def measurement_property_capabilities(
        self,
    ) -> Mapping[MeasurementPropertyKey, ProfileCapabilityStatus]:
        """Capability map for measurement properties."""

    @property
    @abstractmethod
    def cosmin_box_capabilities(self) -> Mapping[CosminBoxKey, ProfileCapabilityStatus]:
        """Capability map for COSMIN RoB boxes."""

    @property
    @abstractmethod
    def review_step_capabilities(self) -> Mapping[CosminReviewStepKey, ProfileCapabilityStatus]:
        """Capability map for ordered COSMIN review steps."""

    @property
    @abstractmethod
    def rule_capabilities(self) -> Mapping[str, ProfileCapabilityStatus]:
        """Capability map for deterministic rule identifiers."""

    @property
    def common_required_extraction_fields(self) -> tuple[str, ...]:
        """Cross-profile required extraction fields."""

        return (
            "study_design",
            "target_population",
            "sample_size",
            "instrument_name",
            "instrument_version",
            "subscale",
            "language",
            "country",
        )

    @property
    @abstractmethod
    def profile_specific_required_extraction_fields(self) -> tuple[str, ...]:
        """Profile-specific extraction fields that extend common requirements."""

    @property
    @abstractmethod
    def reviewer_required_decisions(self) -> tuple[str, ...]:
        """Reviewer decisions required for non-deterministic judgment areas."""

    @property
    @abstractmethod
    def reviewer_questions(self) -> tuple[str, ...]:
        """Reviewer-facing questions used for profile-specific adjudication."""

    @property
    @abstractmethod
    def unsupported_auto_scoring_areas(self) -> tuple[str, ...]:
        """Auto-scoring areas intentionally unsupported by this profile."""

    @property
    @abstractmethod
    def adaptation_points(self) -> tuple[str, ...]:
        """Explicit adaptation notes and known limits for this profile."""

    @property
    @abstractmethod
    def table_column_availability(self) -> Mapping[TableTemplateKey, tuple[str, ...]]:
        """Profile-specific table column availability by template."""

    @property
    def applicable_measurement_properties(self) -> tuple[MeasurementPropertyKey, ...]:
        """Measurement properties this profile can represent."""

        return tuple(
            key
            for key, status in self.measurement_property_capabilities.items()
            if status is not ProfileCapabilityStatus.UNSUPPORTED
        )

    @property
    def applicable_cosmin_boxes(self) -> tuple[CosminBoxKey, ...]:
        """COSMIN boxes this profile can evaluate."""

        return tuple(
            key
            for key, status in self.cosmin_box_capabilities.items()
            if status is not ProfileCapabilityStatus.UNSUPPORTED
        )

    @property
    def required_extraction_fields(self) -> tuple[str, ...]:
        """Extraction fields required before downstream assessments."""

        specific_fields = self.profile_specific_required_extraction_fields
        return self._merge_unique(self.common_required_extraction_fields + specific_fields)

    @property
    def deterministic_rules_available(self) -> tuple[str, ...]:
        """Deterministic rule identifiers usable for this profile."""

        return tuple(
            rule_id
            for rule_id, status in self.rule_capabilities.items()
            if status in (ProfileCapabilityStatus.REUSED, ProfileCapabilityStatus.ADAPTED)
        )

    def supports_measurement_property(self, property_key: MeasurementPropertyKey) -> bool:
        """Return true when this profile supports a measurement property."""

        status = self.measurement_property_status(property_key)
        return status is not ProfileCapabilityStatus.UNSUPPORTED

    def supports_cosmin_box(self, box_key: CosminBoxKey) -> bool:
        """Return true when this profile supports a COSMIN RoB box."""

        return self.cosmin_box_status(box_key) is not ProfileCapabilityStatus.UNSUPPORTED

    def requires_field(self, field_name: str) -> bool:
        """Return true when an extraction field is required by this profile."""

        return field_name in self.required_extraction_fields

    def has_deterministic_rule(self, rule_id: str) -> bool:
        """Return true when a rule ID is available for deterministic use."""

        status = self.rule_status(rule_id)
        return status in (ProfileCapabilityStatus.REUSED, ProfileCapabilityStatus.ADAPTED)

    def requires_reviewer_decision(self, decision_key: str) -> bool:
        """Return true when a reviewer decision key is required."""

        return decision_key in self.reviewer_required_decisions

    def supports_auto_scoring_area(self, area_key: str) -> bool:
        """Return true when an auto-scoring area is not explicitly unsupported."""

        return area_key not in self.unsupported_auto_scoring_areas

    def require_supported_auto_scoring_area(self, area_key: str) -> None:
        """Raise a clear error when an unsupported auto-scoring area is requested."""

        if not self.supports_auto_scoring_area(area_key):
            msg = (
                f"auto-scoring area '{area_key}' is unsupported for profile "
                f"'{self.profile_type.value}'"
            )
            raise NotImplementedError(msg)

    def require_deterministic_rule(self, rule_id: str) -> None:
        """Raise a clear error when a deterministic rule is unavailable."""

        if not self.has_deterministic_rule(rule_id):
            status = self.rule_status(rule_id).value
            msg = (
                f"deterministic rule '{rule_id}' is unavailable for profile "
                f"'{self.profile_type.value}' (status={status})"
            )
            raise NotImplementedError(msg)

    def measurement_property_status(
        self,
        property_key: MeasurementPropertyKey,
    ) -> ProfileCapabilityStatus:
        """Return declared capability status for one measurement property."""

        return self.measurement_property_capabilities[property_key]

    def cosmin_box_status(self, box_key: CosminBoxKey) -> ProfileCapabilityStatus:
        """Return declared capability status for one COSMIN box."""

        return self.cosmin_box_capabilities[box_key]

    def review_step_status(self, step_key: CosminReviewStepKey) -> ProfileCapabilityStatus:
        """Return declared capability status for one review step."""

        return self.review_step_capabilities[step_key]

    def rule_status(self, rule_id: str) -> ProfileCapabilityStatus:
        """Return declared capability status for one rule identifier."""

        return self.rule_capabilities.get(rule_id, ProfileCapabilityStatus.UNSUPPORTED)

    def available_table_columns(self, template_key: TableTemplateKey | str) -> tuple[str, ...]:
        """Return available table columns for a template key."""

        return self.table_column_availability.get(TableTemplateKey(template_key), ())

    def to_metadata(self) -> dict[str, object]:
        """Serialize profile capabilities into JSON-friendly metadata."""

        return {
            "profile_type": self.profile_type.value,
            "applicable_measurement_properties": [
                value.value for value in self.applicable_measurement_properties
            ],
            "applicable_cosmin_boxes": [value.value for value in self.applicable_cosmin_boxes],
            "common_required_extraction_fields": list(self.common_required_extraction_fields),
            "profile_specific_required_extraction_fields": list(
                self.profile_specific_required_extraction_fields
            ),
            "required_extraction_fields": list(self.required_extraction_fields),
            "deterministic_rules_available": list(self.deterministic_rules_available),
            "reviewer_required_decisions": list(self.reviewer_required_decisions),
            "reviewer_questions": list(self.reviewer_questions),
            "unsupported_auto_scoring_areas": list(self.unsupported_auto_scoring_areas),
            "adaptation_points": list(self.adaptation_points),
            "measurement_property_capabilities": {
                key.value: status.value
                for key, status in self.measurement_property_capabilities.items()
            },
            "cosmin_box_capabilities": {
                key.value: status.value for key, status in self.cosmin_box_capabilities.items()
            },
            "review_step_capabilities": {
                key.value: status.value for key, status in self.review_step_capabilities.items()
            },
            "rule_capabilities": {
                rule_id: status.value for rule_id, status in self.rule_capabilities.items()
            },
            "table_column_availability": {
                key.value: list(columns) for key, columns in self.table_column_availability.items()
            },
        }

    def _validate_contract(self) -> None:
        self._validate_unique(self.required_extraction_fields, "required_extraction_fields")
        self._validate_unique(
            self.deterministic_rules_available,
            "deterministic_rules_available",
        )
        self._validate_unique(
            self.reviewer_required_decisions,
            "reviewer_required_decisions",
        )
        self._validate_unique(self.reviewer_questions, "reviewer_questions")
        self._validate_unique(
            self.unsupported_auto_scoring_areas,
            "unsupported_auto_scoring_areas",
        )
        self._validate_unique(self.adaptation_points, "adaptation_points")

        if set(self.measurement_property_capabilities) != set(MeasurementPropertyKey):
            msg = "measurement_property_capabilities must explicitly declare all property keys"
            raise ValueError(msg)
        if set(self.cosmin_box_capabilities) != set(CosminBoxKey):
            msg = "cosmin_box_capabilities must explicitly declare all COSMIN box keys"
            raise ValueError(msg)
        if set(self.review_step_capabilities) != set(CosminReviewStepKey):
            msg = "review_step_capabilities must explicitly declare all review steps"
            raise ValueError(msg)
        if set(self.table_column_availability) != set(TableTemplateKey):
            msg = "table_column_availability must declare template_5/template_7/template_8"
            raise ValueError(msg)

        for template_key, columns in self.table_column_availability.items():
            if not columns:
                msg = f"table_column_availability[{template_key.value}] must not be empty"
                raise ValueError(msg)
            self._validate_unique(
                columns,
                f"table_column_availability[{template_key.value}]",
            )

        if self.profile_type is not ProfileType.PROM:
            if not self.unsupported_auto_scoring_areas:
                msg = "non-PROM profiles must explicitly declare unsupported auto-scoring areas"
                raise ValueError(msg)
            if not self.adaptation_points:
                msg = "non-PROM profiles must explicitly declare adaptation points"
                raise ValueError(msg)
            if not self.profile_specific_required_extraction_fields:
                msg = "non-PROM profiles must declare profile-specific extraction fields"
                raise ValueError(msg)

            for step_key in _NON_PROM_ADAPTED_STEPS:
                step_status = self.review_step_status(step_key)
                if step_status not in (
                    ProfileCapabilityStatus.ADAPTED,
                    ProfileCapabilityStatus.REVIEWER_REQUIRED,
                ):
                    msg = (
                        f"non-PROM profile '{self.profile_type.value}' must mark "
                        f"{step_key.value} as adapted or reviewer_required"
                    )
                    raise ValueError(msg)

    @staticmethod
    def _validate_unique(values: Iterable[object], field_name: str) -> None:
        values_list = list(values)
        if len(values_list) != len(set(values_list)):
            msg = f"{field_name} contains duplicate values"
            raise ValueError(msg)

    @staticmethod
    def _merge_unique(values: tuple[str, ...]) -> tuple[str, ...]:
        merged: list[str] = []
        seen: set[str] = set()
        for value in values:
            if value not in seen:
                merged.append(value)
                seen.add(value)
        return tuple(merged)
