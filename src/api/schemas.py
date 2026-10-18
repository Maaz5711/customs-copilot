"""Request shapes. Strict: unknown fields are refused, every string has a length cap, numbers have ranges."""
from __future__ import annotations

import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

ISO_DATE = r"^\d{4}-\d{2}-\d{2}$"
KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,79}$")       # answer ids look like "claim.fifth_schedule_rules:123" or "goods.origin_country"
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

Short = Annotated[str, Field(max_length=500)]


def clean(s: str) -> str:
    """Drop control characters and surrounding blanks. The text is still treated as data by the agent, never as instructions."""
    return _CTRL.sub("", s).strip()


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AskIn(Strict):
    question: str = Field(min_length=2, max_length=1500)
    date: str | None = Field(default=None, pattern=ISO_DATE)

    _q = field_validator("question")(lambda v: clean(v))


class AnswerIn(Strict):
    thread_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    answers: dict[str, Short] = Field(default_factory=dict, max_length=20)
    reply: str | None = Field(default=None, max_length=1500)

    @field_validator("answers")
    @classmethod
    def _keys(cls, v):
        for k in v:
            if not KEY.match(k):
                raise ValueError("bad answer id")
        return {k: clean(x) for k, x in v.items()}


class LookupIn(Strict):
    query: str = Field(min_length=1, max_length=120)
    date: str | None = Field(default=None, pattern=ISO_DATE)
    chapter: str | None = Field(default=None, pattern=r"^\d{1,2}$")
    cd_pct: str | None = Field(default=None, pattern=r"^\d{1,3}(\.\d{1,2})?$")
    k: int = Field(default=10, ge=1, le=25)

    _q = field_validator("query")(lambda v: clean(v))


FactValue = str | bool | int | float | None


class BillIn(Strict):
    code: str = Field(pattern=r"^\d{4}(\.?\d{2}(\.?\d{2})?)?$")
    value_pkr: float = Field(gt=0, le=1e13)
    date: str | None = Field(default=None, pattern=ISO_DATE)
    importer: dict[str, FactValue] = Field(default_factory=dict, max_length=20)
    goods: dict[str, FactValue] = Field(default_factory=dict, max_length=20)
    quantity: float | None = Field(default=None, ge=0, le=1e12)
    unit: str | None = Field(default=None, max_length=20)
    claimed_rules: list[Annotated[str, Field(max_length=80)]] = Field(default_factory=list, max_length=10)

    @field_validator("importer", "goods")
    @classmethod
    def _facts(cls, v):
        for k, x in v.items():
            if not KEY.match(k):
                raise ValueError("bad field name")
            if isinstance(x, str) and len(x) > 200:
                raise ValueError("value too long")
        return v


class FeedbackIn(Strict):
    thread_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    helpful: bool
    code: str | None = Field(default=None, pattern=r"^\d{8}$")           # the line the user says is right
    note: str | None = Field(default=None, max_length=500)
    consent_to_store_note: bool = False                                    # nothing free-text is kept unless this is true
