"""Profile capability system for PROM and adapted non-PROM workflows."""

from cosmin_assistant.profiles.activity_monitor import ActivityMonitorProfile
from cosmin_assistant.profiles.base import BaseProfile
from cosmin_assistant.profiles.constants import CosminBoxKey, MeasurementPropertyKey
from cosmin_assistant.profiles.pbom import PbomProfile
from cosmin_assistant.profiles.prom import PromProfile
from cosmin_assistant.profiles.registry import get_profile, list_profiles

__all__ = [
    "ActivityMonitorProfile",
    "BaseProfile",
    "CosminBoxKey",
    "MeasurementPropertyKey",
    "PbomProfile",
    "PromProfile",
    "get_profile",
    "list_profiles",
]
