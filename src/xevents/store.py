"""Persistence: SQLAlchemy tables + a small repository API.

``DATABASE_URL`` selects PostgreSQL (docker compose) or the SQLite fallback
(``sqlite:///xevents.db``). M1 persists facilities; events and action items (with the
status machine) arrive in M2/M4.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Engine, Float, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from xevents.models import Event, Facility, OperatingStatusCode

DEFAULT_DATABASE_URL = "sqlite:///xevents.db"


class Base(DeclarativeBase):
    pass


class FacilityRow(Base):
    __tablename__ = "facilities"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    facility_type: Mapped[str] = mapped_column(String(64))
    classification: Mapped[str | None] = mapped_column(Text, nullable=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    zip5: Mapped[str | None] = mapped_column(String(5), nullable=True)
    city: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    visn: Mapped[str | None] = mapped_column(String(2), nullable=True, index=True)
    health_care_system: Mapped[str | None] = mapped_column(Text, nullable=True)
    operating_status: Mapped[str] = mapped_column(String(32))
    operating_status_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    county_fips: Mapped[str | None] = mapped_column(String(5), nullable=True, index=True)
    county_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    market: Mapped[str | None] = mapped_column(Text, nullable=True)

    def to_model(self) -> Facility:
        return Facility(
            id=self.id,
            name=self.name,
            facility_type=self.facility_type,
            classification=self.classification,
            lat=self.lat,
            lon=self.lon,
            zip5=self.zip5,
            city=self.city,
            state=self.state,
            visn=self.visn,
            health_care_system=self.health_care_system,
            operating_status=OperatingStatusCode(self.operating_status),
            operating_status_info=self.operating_status_info,
            county_fips=self.county_fips,
            county_source=self.county_source,
            market=self.market,
        )

    @classmethod
    def from_model(cls, f: Facility) -> FacilityRow:
        data = f.model_dump(mode="json")
        return cls(**data)


def make_engine(database_url: str | None = None) -> Engine:
    url = database_url or os.environ.get("DATABASE_URL") or DEFAULT_DATABASE_URL
    return create_engine(url, future=True)


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    with Session(engine) as session, session.begin():
        yield session


def upsert_facilities(engine: Engine, facilities: list[Facility]) -> int:
    """Insert or replace by facility id. Returns the number written."""
    with session_scope(engine) as s:
        for f in facilities:
            s.merge(FacilityRow.from_model(f))
    return len(facilities)


def list_facilities(
    engine: Engine,
    *,
    state: str | None = None,
    visn: str | None = None,
    county_fips: str | None = None,
) -> list[Facility]:
    stmt = select(FacilityRow).order_by(FacilityRow.id)
    if state:
        stmt = stmt.where(FacilityRow.state == state.upper())
    if visn:
        stmt = stmt.where(FacilityRow.visn == visn)
    if county_fips:
        stmt = stmt.where(FacilityRow.county_fips == county_fips)
    with Session(engine) as s:
        return [row.to_model() for row in s.scalars(stmt)]


def get_facility(engine: Engine, facility_id: str) -> Facility | None:
    with Session(engine) as s:
        row = s.get(FacilityRow, facility_id)
        return row.to_model() if row else None


# --------------------------------------------------------------------------- events


class EventRow(Base):
    """Normalized event store (append/upsert by natural key ``source:source_id``)."""

    __tablename__ = "events"

    event_key: Mapped[str] = mapped_column(String(256), primary_key=True)
    source: Mapped[str] = mapped_column(String(16), index=True)
    source_id: Mapped[str] = mapped_column(Text)
    event_type: Mapped[str] = mapped_column(String(32), index=True)
    event_name: Mapped[str] = mapped_column(Text)
    headline: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(String(16))
    urgency: Mapped[str] = mapped_column(String(16))
    certainty: Mapped[str] = mapped_column(String(16))
    onset: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    expires: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    sent: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    county_fips: Mapped[list[str]] = mapped_column(JSON)
    geography: Mapped[dict[str, Any]] = mapped_column(JSON)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON)
    scenario: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    raw_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    def to_model(self) -> Event:
        data = {
            "source": self.source,
            "source_id": self.source_id,
            "event_type": self.event_type,
            "event_name": self.event_name,
            "headline": self.headline,
            "severity": self.severity,
            "urgency": self.urgency,
            "certainty": self.certainty,
            "onset": _aware(self.onset),
            "expires": _aware(self.expires),
            "sent": _aware(self.sent) if self.sent else None,
            "geography": self.geography,
            "metrics": self.metrics,
            "scenario": self.scenario,
            "raw_ref": self.raw_ref,
        }
        return Event.model_validate(data)

    @classmethod
    def from_model(cls, e: Event, ingested_at: datetime) -> EventRow:
        return cls(
            event_key=e.event_key,
            source=e.source.value,
            source_id=e.source_id,
            event_type=e.event_type.value,
            event_name=e.event_name,
            headline=e.headline,
            severity=e.severity.value,
            urgency=e.urgency.value,
            certainty=e.certainty.value,
            onset=e.onset,
            expires=e.expires,
            sent=e.sent,
            county_fips=list(e.geography.county_fips),
            geography=e.geography.model_dump(mode="json"),
            metrics=dict(e.metrics),
            scenario=e.scenario,
            raw_ref=e.raw_ref,
            ingested_at=ingested_at,
        )


def _aware(dt: datetime) -> datetime:
    """SQLite drops tzinfo; everything we store is UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def upsert_events(engine: Engine, events: list[Event]) -> int:
    now = datetime.now(UTC)
    with session_scope(engine) as s:
        for e in events:
            s.merge(EventRow.from_model(e, now))
    return len(events)


def list_events(
    engine: Engine,
    *,
    scenario: str | None = None,
    source: str | None = None,
    event_type: str | None = None,
    active_at: datetime | None = None,
    county_fips: str | None = None,
) -> list[Event]:
    stmt = select(EventRow).order_by(EventRow.onset, EventRow.event_key)
    if scenario is not None:
        stmt = stmt.where(EventRow.scenario == scenario)
    if source:
        stmt = stmt.where(EventRow.source == source)
    if event_type:
        stmt = stmt.where(EventRow.event_type == event_type)
    if active_at is not None:
        stmt = stmt.where(EventRow.onset <= active_at, EventRow.expires >= active_at)
    with Session(engine) as s:
        events = [row.to_model() for row in s.scalars(stmt)]
    if county_fips:
        events = [e for e in events if county_fips in e.geography.county_fips]
    return events


def delete_scenario_events(engine: Engine, scenario: str) -> int:
    with session_scope(engine) as s:
        rows = list(s.scalars(select(EventRow).where(EventRow.scenario == scenario)))
        for row in rows:
            s.delete(row)
    return len(rows)
