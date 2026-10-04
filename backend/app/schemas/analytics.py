"""Analytics contracts: counts and confidence have explicit populations."""

from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import (
    CultivarCount, CultivarRipeness, HourlyCount, RipenessDistribution, ScanTrend,
)
from app.schemas.timestamps import Timestamp


class SourceOption(BaseModel):
    key: str
    name: str


class SourceCount(SourceOption):
    count: int


class RipenessConfidence(BaseModel):
    ripeness: str
    avgConfidence: float | None
    count: int


class OperatorPerformance(BaseModel):
    operator_id: UUID
    name: str
    username: str
    total_scans: int
    avg_confidence: float | None
    confidence_sample_count: int
    flagged_scans: int
    flag_rate: float
    overridden_scans: int


class OperatorPerformanceList(BaseModel):
    items: list[OperatorPerformance]
    total_operators: int


class AnalyticsSummary(BaseModel):
    generated_at: Timestamp
    business_date: date
    next_refresh_at: Timestamp
    timezone: str = "Asia/Manila"
    range_start: Timestamp | None
    range_end: Timestamp
    trend_start: date
    trend_end: date
    confidence_threshold: float
    total_scans: int
    classification_count: int
    incomplete_count: int
    confidence_sample_count: int
    avg_confidence: float | None
    most_common_cultivar: str
    low_confidence_count: int
    low_confidence_rate: float | None
    at_risk_count: int
    current_stock_count: int
    risk_unknown_count: int
    human_verified_accuracy: float | None = None
    verified_scan_count: int = 0
    metric_definitions: dict[str, str]
    source_options: list[SourceOption]
    ripeness_distribution: list[RipenessDistribution]
    cultivar_counts: list[CultivarCount]
    scan_trend: list[ScanTrend]
    cultivar_ripeness: list[CultivarRipeness]
    ripeness_confidence: list[RipenessConfidence]
    scans_by_source: list[SourceCount]
    hourly_distribution: list[HourlyCount]
    operator_performance: list[OperatorPerformance] = Field(default_factory=list)
