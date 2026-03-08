"""Profile registry utilities."""

from __future__ import annotations

from cosmin_assistant.models.enums import ProfileType
from cosmin_assistant.profiles.activity_monitor import ActivityMonitorProfile
from cosmin_assistant.profiles.base import BaseProfile
from cosmin_assistant.profiles.pbom import PbomProfile
from cosmin_assistant.profiles.prom import PromProfile


def get_profile(profile_type: ProfileType | str) -> BaseProfile:
    """Instantiate and return a profile object by type."""

    match ProfileType(profile_type):
        case ProfileType.PROM:
            return PromProfile()
        case ProfileType.PBOM:
            return PbomProfile()
        case ProfileType.ACTIVITY_MEASURE:
            return ActivityMonitorProfile()


def list_profiles() -> tuple[BaseProfile, ...]:
    """Return all supported profiles in stable order."""

    return (PromProfile(), PbomProfile(), ActivityMonitorProfile())
