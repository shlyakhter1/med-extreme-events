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

from sqlalchemy import (
    JSON,
    DateTime,
    Engine,
    Float,
    String,
    Text,
    create_engine,
    event,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from xevents.engine import rank_key
from xevents.geography.catchment import CatchmentAssignment, StationAssignment
from xevents.models import (
    ALLOWED_TRANSITIONS,
    ActionItem,
    ActionItemStatus,
    Event,
    Facility,
    OperatingStatusCode,
)

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
    engine = create_engine(url, future=True)
    if engine.dialect.name == "sqlite":
        # WAL lets the web process keep reading while the live refresher writes, and the
        # busy timeout makes a colliding writer wait instead of failing.
        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn: Any, _record: Any) -> None:
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA busy_timeout=10000")
            cur.close()

    return engine


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
    temporality: Mapped[str] = mapped_column(String(16), index=True)
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
            "temporality": self.temporality,
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
            temporality=e.temporality.value,
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
    live_only: bool = False,
) -> list[Event]:
    """``scenario=None`` means no scenario filter; ``live_only=True`` keeps only live rows
    (scenario NULL) so live pages never deserialize the replay fixtures."""
    stmt = select(EventRow).order_by(EventRow.onset, EventRow.event_key)
    if scenario is not None:
        stmt = stmt.where(EventRow.scenario == scenario)
    elif live_only:
        stmt = stmt.where(EventRow.scenario.is_(None))
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


def feed_status(engine: Engine) -> list[dict[str, Any]]:
    """Per source: live (scenario-less) event count and last ingestion time."""
    from sqlalchemy import func

    stmt = (
        select(EventRow.source, func.count(), func.max(EventRow.ingested_at))
        .where(EventRow.scenario.is_(None))
        .group_by(EventRow.source)
        .order_by(EventRow.source)
    )
    with Session(engine) as s:
        rows = s.execute(stmt).all()
    return [
        {
            "source": src,
            "events": int(n),
            "last_ingested_at": _aware(last).isoformat() if last else None,
        }
        for src, n, last in rows
    ]


def get_event(engine: Engine, event_key: str) -> Event | None:
    with Session(engine) as s:
        row = s.get(EventRow, event_key)
        return row.to_model() if row else None


def delete_scenario_events(engine: Engine, scenario: str) -> int:
    with session_scope(engine) as s:
        rows = list(s.scalars(select(EventRow).where(EventRow.scenario == scenario)))
        for row in rows:
            s.delete(row)
    return len(rows)


# --------------------------------------------------------------------------- catchments


class CatchmentRow(Base):
    __tablename__ = "county_catchment"

    county_fips: Mapped[str] = mapped_column(String(5), primary_key=True)
    facility_id: Mapped[str] = mapped_column(String(32), index=True)
    distance_km: Mapped[float] = mapped_column(Float)


def replace_catchments(engine: Engine, assignments: list[CatchmentAssignment]) -> int:
    with session_scope(engine) as s:
        for row in s.scalars(select(CatchmentRow)):
            s.delete(row)
        s.flush()
        for a in assignments:
            s.add(
                CatchmentRow(
                    county_fips=a.county_fips, facility_id=a.facility_id, distance_km=a.distance_km
                )
            )
    return len(assignments)


def catchment_map(engine: Engine) -> dict[str, list[str]]:
    """facility id → sorted county FIPS list."""
    out: dict[str, list[str]] = {}
    with Session(engine) as s:
        for row in s.scalars(select(CatchmentRow).order_by(CatchmentRow.county_fips)):
            out.setdefault(row.facility_id, []).append(row.county_fips)
    return out


class FacilityStationRow(Base):
    __tablename__ = "facility_station"

    facility_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    station_id: Mapped[str] = mapped_column(String(32), index=True)
    method: Mapped[str] = mapped_column(String(32))


def replace_stations(engine: Engine, assignments: list[StationAssignment]) -> int:
    with session_scope(engine) as s:
        for row in s.scalars(select(FacilityStationRow)):
            s.delete(row)
        s.flush()
        for a in assignments:
            s.add(
                FacilityStationRow(
                    facility_id=a.facility_id, station_id=a.station_id, method=a.method
                )
            )
    return len(assignments)


def station_map(engine: Engine) -> dict[str, tuple[str, str]]:
    """facility id → (station id, method)."""
    with Session(engine) as s:
        rows = s.scalars(select(FacilityStationRow))
        return {r.facility_id: (r.station_id, r.method) for r in rows}


# --------------------------------------------------------------------------- action items


class ActionItemRow(Base):
    __tablename__ = "action_items"

    id: Mapped[str] = mapped_column(String(512), primary_key=True)
    event_key: Mapped[str] = mapped_column(String(256), index=True)
    card_id: Mapped[str] = mapped_column(String(64), index=True)
    scope_id: Mapped[str] = mapped_column(String(32), index=True)
    role: Mapped[str] = mapped_column(String(16))
    event_type: Mapped[str] = mapped_column(String(32), index=True)
    event_severity: Mapped[str] = mapped_column(String(16))
    acuity_rank: Mapped[int] = mapped_column(index=True)
    panel_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    rank_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    superseded_by: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # progress (delivered/acknowledged) parked while a stronger alert supersedes this item,
    # restored when that alert goes away
    status_before_superseded: Mapped[str | None] = mapped_column(String(16), nullable=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    scenario: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)

    def to_model(self) -> ActionItem:
        data = dict(self.payload)
        data.update(
            status=self.status,
            superseded_by=self.superseded_by,
            created_at=_aware(self.created_at),
            acknowledged_at=_aware(self.acknowledged_at) if self.acknowledged_at else None,
        )
        return ActionItem.model_validate(data)

    @classmethod
    def from_model(cls, item: ActionItem) -> ActionItemRow:
        return cls(
            id=item.id,
            event_key=item.event_key,
            card_id=item.card_id,
            scope_id=item.scope_id,
            role=item.role.value,
            event_type=item.event_type.value,
            event_severity=item.event_severity.value,
            acuity_rank=item.acuity_rank,
            panel_value=item.panel.value if item.panel else None,
            rank_score=item.rank_score,
            status=item.status.value,
            superseded_by=item.superseded_by,
            window_start=item.window_start,
            window_end=item.window_end,
            scenario=item.scenario,
            created_at=item.created_at,
            acknowledged_at=item.acknowledged_at,
            payload=item.model_dump(mode="json"),
        )


class TransitionError(ValueError):
    pass


# Payload keys the store owns (status machine, timestamps); everything else is engine content
# and any change to it is a real update.
_STORE_OWNED = {"status", "superseded_by", "created_at", "acknowledged_at"}


def _content(payload: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in payload.items() if k not in _STORE_OWNED}


def upsert_action_items(engine: Engine, items: list[ActionItem]) -> dict[str, int]:
    """Insert new items; refresh content of existing ones by natural key while keeping any
    status progress (delivered/acknowledged/completed) — except that engine-computed
    supersession always applies. Progress parked by a supersession is restored when the
    stronger alert goes away. Returns counts."""
    counts = {"inserted": 0, "updated": 0, "unchanged": 0}
    with session_scope(engine) as s:
        for item in items:
            existing = s.get(ActionItemRow, item.id)
            if existing is None:
                s.add(ActionItemRow.from_model(item))
                counts["inserted"] += 1
                continue
            current = ActionItemStatus(existing.status)
            new_status = current
            parked = existing.status_before_superseded
            if item.status is ActionItemStatus.SUPERSEDED and current not in (
                ActionItemStatus.COMPLETED,
                ActionItemStatus.EXPIRED,
                ActionItemStatus.SUPERSEDED,
            ):
                new_status = ActionItemStatus.SUPERSEDED
                parked = current.value
            elif (
                current is ActionItemStatus.SUPERSEDED
                and item.status is not ActionItemStatus.SUPERSEDED
            ):
                # the stronger alert went away: pick up where the team left off
                new_status = ActionItemStatus(parked or ActionItemStatus.ISSUED.value)
                parked = None
            fresh = ActionItemRow.from_model(item)
            changed = (
                _content(existing.payload) != _content(fresh.payload)
                or new_status is not current
                or existing.superseded_by != item.superseded_by
            )
            if not changed:
                counts["unchanged"] += 1
                continue
            payload = dict(fresh.payload)
            payload["created_at"] = existing.payload.get("created_at", payload["created_at"])
            existing.payload = payload
            existing.window_start = item.window_start
            existing.window_end = item.window_end
            existing.panel_value = fresh.panel_value
            existing.rank_score = fresh.rank_score
            existing.acuity_rank = item.acuity_rank
            existing.event_severity = item.event_severity.value
            existing.status = new_status.value
            existing.status_before_superseded = parked
            existing.superseded_by = (
                item.superseded_by if new_status is ActionItemStatus.SUPERSEDED else None
            )
            if new_status in (ActionItemStatus.ISSUED, ActionItemStatus.DELIVERED):
                existing.acknowledged_at = None  # parked (superseded) rows keep it for restore
            counts["updated"] += 1
    return counts


def transition_action_item(
    engine: Engine, item_id: str, new_status: ActionItemStatus
) -> ActionItem:
    with session_scope(engine) as s:
        row = s.get(ActionItemRow, item_id)
        if row is None:
            raise KeyError(item_id)
        current = ActionItemStatus(row.status)
        if new_status not in ALLOWED_TRANSITIONS[current]:
            raise TransitionError(f"{current.value} → {new_status.value} is not allowed")
        row.status = new_status.value
        if new_status is ActionItemStatus.ACKNOWLEDGED:
            row.acknowledged_at = datetime.now(UTC)
        s.flush()
        return row.to_model()


def expire_action_items(engine: Engine, now: datetime) -> int:
    """Auto-expire open *live* items whose window has ended (replay items never expire)."""
    n = 0
    with session_scope(engine) as s:
        stmt = select(ActionItemRow).where(
            ActionItemRow.window_end < now,
            ActionItemRow.status.in_(
                [
                    st.value
                    for st in (
                        ActionItemStatus.ISSUED,
                        ActionItemStatus.DELIVERED,
                        ActionItemStatus.ACKNOWLEDGED,
                    )
                ]
            ),
            ActionItemRow.scenario.is_(None),  # replay items keep their scenario time frame
        )
        for row in s.scalars(stmt):
            row.status = ActionItemStatus.EXPIRED.value
            n += 1
    return n


def list_action_items(
    engine: Engine,
    *,
    scenario: str | None = None,
    facility_id: str | None = None,
    role: str | None = None,
    card_id: str | None = None,
    status: str | None = None,
    active_at: datetime | None = None,
    include_superseded: bool = False,
    live_only: bool = False,
) -> list[ActionItem]:
    stmt = select(ActionItemRow)
    if scenario is not None:
        stmt = stmt.where(ActionItemRow.scenario == scenario)
    elif live_only:
        stmt = stmt.where(ActionItemRow.scenario.is_(None))
    if facility_id:
        stmt = stmt.where(ActionItemRow.scope_id == facility_id)
    if role:
        stmt = stmt.where(ActionItemRow.role == role)
    if card_id:
        stmt = stmt.where(ActionItemRow.card_id == card_id)
    if status:
        stmt = stmt.where(ActionItemRow.status == status)
    elif not include_superseded:
        stmt = stmt.where(ActionItemRow.status != ActionItemStatus.SUPERSEDED.value)
    if active_at is not None:
        stmt = stmt.where(
            ActionItemRow.window_start <= active_at, ActionItemRow.window_end >= active_at
        )
    with Session(engine) as s:
        items = [row.to_model() for row in s.scalars(stmt)]
    return sorted(items, key=rank_key)  # the engine's order: acuity, severity, score, id


def get_action_item(engine: Engine, item_id: str) -> ActionItem | None:
    with Session(engine) as s:
        row = s.get(ActionItemRow, item_id)
        return row.to_model() if row else None


def delete_scenario_action_items(engine: Engine, scenario: str) -> int:
    with session_scope(engine) as s:
        rows = list(s.scalars(select(ActionItemRow).where(ActionItemRow.scenario == scenario)))
        for row in rows:
            s.delete(row)
    return len(rows)
