"""One execution path for fact-only speaking-axis modules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .accuracy import AccuracyModule
from .coherence import CoherenceModule
from .evidence.models import EvidenceBundle
from .range import RangeExtractor


DEFAULT_FACT_MODULES = frozenset({"fluency", "range"})
SUPPORTED_FACT_MODULES = frozenset({"fluency", "range", "accuracy", "coherence"})
INTERACTIVE_FACT_MODULES = SUPPORTED_FACT_MODULES


@dataclass(frozen=True)
class FactModuleRun:
    """Selected fact packets, reusable by every entry point."""

    active_modules: frozenset[str]
    packets: Mapping[str, dict[str, Any]]

    def merge_objective_data(self, base_data: Mapping[str, Any]) -> dict[str, Any]:
        return {**base_data, **self.packets}

    def add_packets_to_roleplay_input(self, base_input: Mapping[str, Any]) -> dict[str, Any]:
        return {**base_input, **self.packets}


def run_fact_modules(
    evidence: EvidenceBundle,
    *,
    selected_modules: Iterable[str] | None = None,
    range_extractor: RangeExtractor | None = None,
) -> FactModuleRun:
    """Collect selected packets from one already-built EvidenceBundle."""

    active_modules = normalize_fact_modules(selected_modules)
    packets: dict[str, dict[str, Any]] = {}
    if "range" in active_modules:
        active_range_extractor = range_extractor or RangeExtractor.default()
        analyze_evidence = getattr(type(active_range_extractor), "analyze_linguistic_evidence", None)
        packets["range_data"] = (
            analyze_evidence(active_range_extractor, evidence.linguistic)
            if callable(analyze_evidence)
            else active_range_extractor.analyze(evidence.speech.raw_transcript_hiragana)
        )
    if "accuracy" in active_modules:
        packets["accuracy_data"] = AccuracyModule().collect(evidence).to_dict()
    if "coherence" in active_modules:
        packets["coherence_data"] = CoherenceModule().collect(evidence).to_dict()
    return FactModuleRun(active_modules=active_modules, packets=packets)


def normalize_fact_modules(selected_modules: Iterable[str] | None) -> frozenset[str]:
    modules = DEFAULT_FACT_MODULES if selected_modules is None else frozenset(selected_modules)
    unknown = modules - SUPPORTED_FACT_MODULES
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ValueError(f"unsupported fact module(s): {names}")
    return modules
