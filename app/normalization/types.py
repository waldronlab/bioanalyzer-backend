"""Shared types for ontology-aligned field normalization."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NormalizedTerm:
    """Label, ontology ID, extraction status, and mapping confidence."""

    label: str
    ontology_id: str
    status: str
    mapping_confidence: float
    raw: str = ""

    @classmethod
    def absent(cls) -> NormalizedTerm:
        return cls(label="", ontology_id="", status="ABSENT", mapping_confidence=0.0)
