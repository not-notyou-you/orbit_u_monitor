# api/schemas_monitor.py
"""Model request Tahap 3: hidromet, alert, kejadian bencana, wilayah, laporan (INTERFACE.md §4.4–4.9).

Respons berupa dict/list biasa (kolom VIEW apa adanya); request divalidasi di
sini supaya kesalahan input menjadi 422 sebelum menyentuh database.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Severity = Literal["INFO", "WARNING", "CRITICAL"]
Comparator = Literal[">=", ">", "<=", "<"]
InfoSource = Literal["GMLS", "BPBD_LEBAK", "BNPB_DIBI", "MEDIA", "LAINNYA"]


class AcknowledgeRequest(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class AlertRuleCreate(BaseModel):
    rule_code: str = Field(pattern=r"^[A-Z0-9_]{3,40}$")
    disaster_type_code: str
    band_code: str
    comparator: Comparator = ">="
    threshold_value: float | None = None
    severity: Severity
    reference_source: str = Field(min_length=2, max_length=150)
    is_active: bool = True


class AlertRuleUpdate(BaseModel):
    comparator: Comparator | None = None
    threshold_value: float | None = None
    severity: Severity | None = None
    reference_source: str | None = Field(default=None, min_length=2, max_length=150)
    is_active: bool | None = None


class LatLon(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class DisasterCreate(BaseModel):
    disaster_type_code: str
    region_id: int
    village_name: str | None = Field(default=None, max_length=100)
    location: LatLon | None = None
    event_date: date
    event_end_date: date | None = None
    description: str = Field(min_length=10, max_length=4000)
    impact_summary: str | None = Field(default=None, max_length=500)
    info_source: InfoSource
    source_reference: str | None = None
    is_verified: bool = False

    @field_validator("event_end_date")
    @classmethod
    def _end_after_start(cls, v, info):
        start = info.data.get("event_date")
        if v is not None and start is not None and v < start:
            raise ValueError("event_end_date must not be before event_date")
        return v


class DisasterUpdate(BaseModel):
    disaster_type_code: str | None = None
    region_id: int | None = None
    village_name: str | None = Field(default=None, max_length=100)
    location: LatLon | None = None
    event_date: date | None = None
    event_end_date: date | None = None
    description: str | None = Field(default=None, min_length=10, max_length=4000)
    impact_summary: str | None = Field(default=None, max_length=500)
    info_source: InfoSource | None = None
    source_reference: str | None = None
    is_verified: bool | None = None


class DisasterTypeCreate(BaseModel):
    type_code: str = Field(pattern=r"^[A-Z0-9_]{3,30}$")
    type_name: str = Field(min_length=2, max_length=100)
    category: str = Field(default="HIDROMETEOROLOGI", max_length=30)
    indicator_bands: str | None = Field(default=None, max_length=100)
    is_active: bool = True


class DisasterTypeUpdate(BaseModel):
    type_name: str | None = Field(default=None, min_length=2, max_length=100)
    category: str | None = Field(default=None, max_length=30)
    indicator_bands: str | None = Field(default=None, max_length=100)
    is_active: bool | None = None


class RegionAoiUpdate(BaseModel):
    in_aoi: bool


class UnionRoiCreate(BaseModel):
    region_ids: list[int] = Field(min_length=1, max_length=50)
    name: str = Field(min_length=2, max_length=100)
    region_code: str | None = Field(default=None, pattern=r"^[A-Z0-9_]{2,20}$")


class ReportRegenerateRequest(BaseModel):
    report_code: Literal["HYDROMET_WEEKLY", "HYDROMET_MONTHLY", "DATAHEALTH_WEEKLY", "DATAHEALTH_MONTHLY"]
    period_start: date
