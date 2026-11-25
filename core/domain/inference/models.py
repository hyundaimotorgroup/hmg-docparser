from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal
from pydantic import BaseModel, ConfigDict, StrictInt, StrictStr, model_validator


@dataclass(slots=True)
class OCRTextLineDTO:
    text: str
    score: float | None = None


@dataclass(slots=True)
class OCRResultDTO:
    lines: list[OCRTextLineDTO] = field(default_factory=list)
    average_score: float | None = None


class ReasoningConfig(BaseModel):
    """Provider independent, immutable intent; null means normal default resolution."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    mode: Literal["provider_default", "disabled", "effort", "budget", "adaptive"]
    effort: StrictStr | None = None
    budget_tokens: StrictInt | None = None

    @model_validator(mode="after")
    def valid_mode(self):
        if self.mode == "effort" and self.effort is None:
            raise ValueError("effort mode requires effort")
        if self.mode == "budget" and (
            self.budget_tokens is None or self.budget_tokens < 1
        ):
            raise ValueError("budget mode requires positive budget_tokens")
        if self.mode != "budget" and self.budget_tokens is not None:
            raise ValueError("budget_tokens is only valid for budget mode")
        if self.mode not in {"effort", "adaptive"} and self.effort is not None:
            raise ValueError("effort is only valid for effort/adaptive mode")
        if self.effort is not None:
            import re

            if not re.fullmatch(r"[a-z][a-z0-9_\-]{0,31}", self.effort):
                raise ValueError("effort must be a short lowercase identifier")
        return self
