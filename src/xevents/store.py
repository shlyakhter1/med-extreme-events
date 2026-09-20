"""Persistence: SQLAlchemy tables + a small repository API.

``DATABASE_URL`` selects PostgreSQL (docker compose) or the SQLite fallback
(``sqlite:///xevents.db``). M1 persists facilities; events and action items (with the
status machine) arrive in M2/M4.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, Float, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from xevents.models import Facility, OperatingStatusCode

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
