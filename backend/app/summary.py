from __future__ import annotations

import re

from opentelemetry import trace

from .config import Settings
from .llm import DeepSeekClient, LLMUnavailableError
from .schemas import TranscriptSummaryResponse


def summarize_transcript(transcript: str) -> TranscriptSummaryResponse:
    complaint_match = re.search(
        r"(?:patient|chief complaint|reports?)\s*[:\-]?\s*(.+?)(?=\n|\.|$)",
        transcript,
        flags=re.IGNORECASE,
    )
    diagnosis_match = re.search(
        r"diagnosis\s*[:\-]\s*(.+?)(?=\n|\.|$)",
        transcript,
        flags=re.IGNORECASE,
    )
    medication_match = re.search(
        r"(?:medication|prescribed|prescription)\s*[:\-]\s*(.+?)(?=\n|\.|$)",
        transcript,
        flags=re.IGNORECASE,
    )
    instructions_match = re.search(
        r"(?:doctor instructions|advised|instructed)\s*[:\-]?\s*(.+?)(?=\n|\.|$)",
        transcript,
        flags=re.IGNORECASE,
    )

    return TranscriptSummaryResponse(
        chief_complaint=_clean(complaint_match.group(1) if complaint_match else ""),
        diagnosis=_clean(diagnosis_match.group(1) if diagnosis_match else ""),
        medication=_clean(medication_match.group(1) if medication_match else ""),
        doctor_instructions=_clean(
            instructions_match.group(1) if instructions_match else ""
        ),
    )


class SummaryService:
    def __init__(self, settings: Settings, tracer: trace.Tracer | None = None):
        self.settings = settings
        self.tracer = tracer or trace.get_tracer("clinicpilot-ai")

    def summarize(self, transcript: str) -> TranscriptSummaryResponse:
        if self.settings.llm_mode == "mock":
            return summarize_transcript(transcript)

        try:
            return DeepSeekClient(self.settings, tracer=self.tracer).summarize(
                transcript
            )
        except LLMUnavailableError:
            if not self.settings.llm_fallback_to_mock:
                raise
            trace.get_current_span().add_event("deepseek.summary.fallback")
            return summarize_transcript(transcript)


def _clean(value: str) -> str:
    return value.strip().strip("\"' ")
