"""ZIP → county crosswalk and facility attribution."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from xevents.geography import CountyIndex, ZipCountyCrosswalk, attribute_facilities
from xevents.geography.zip_county import DEFAULT_PATH
from xevents.providers.va_facilities import from_geojson, parse_page

SAMPLE = Path(__file__).parent / "fixtures" / "facilities" / "v1_page_sample.json"
REAL_FACILITIES = Path(__file__).parents[1] / "fixtures" / "reference" / "facilities.geojson"


@pytest.fixture(scope="module")
def crosswalk() -> ZipCountyCrosswalk:
    return ZipCountyCrosswalk.load(DEFAULT_PATH)


@pytest.fixture(scope="module")
def counties() -> CountyIndex:
    return CountyIndex.load()


def test_county_index_is_national_including_territories(counties: CountyIndex) -> None:
    assert len(counties) > 3_230  # 3,235 incl. PR, GU, AS, MP, VI


@pytest.mark.parametrize(
    ("lon", "lat", "geoid", "name"),
    [
        (-122.68344, 45.49707, "41051", "Multnomah"),  # Portland VAMC
        (-79.95898403, 40.44711478, "42003", "Allegheny"),  # Pittsburgh VAMC (unique ZIP 15240)
        (-77.47035097, 37.49792643, "51760", "Richmond"),  # Richmond VAMC (unique ZIP 23249)
        (144.84826191, 13.57214716, "66010", "Guam"),  # territory
        (-66.1, 18.4, "72127", "San Juan"),  # Puerto Rico
    ],
)
def test_point_in_polygon_known_points(
    counties: CountyIndex, lon: float, lat: float, geoid: str, name: str
) -> None:
    hit = counties.lookup(lon, lat)
    assert hit is not None
    assert (hit.geoid, hit.name) == (geoid, name)


def test_point_outside_us_is_none(counties: CountyIndex) -> None:
    assert counties.lookup(120.99139, 14.54408) is None  # Manila VA Clinic
    assert counties.lookup(0.0, 0.0) is None


def test_crosswalk_fixture_is_national(crosswalk: ZipCountyCrosswalk) -> None:
    assert len(crosswalk) > 30_000


@pytest.mark.parametrize(
    ("zip5", "county"),
    [("97239", "41051"), ("98108", "53033"), ("33912", "12071"), ("10001", "36061")],
)
def test_known_zip_lookups(crosswalk: ZipCountyCrosswalk, zip5: str, county: str) -> None:
    match = crosswalk.lookup(zip5)
    assert match is not None
    assert match.county_fips == county
    assert 0 < match.share <= 1.0


def test_multi_county_zip_is_assigned_by_dominant_share(crosswalk: ZipCountyCrosswalk) -> None:
    # 33912 (Fort Myers) straddles Lee County only; find any ZIP with share < 1 to prove
    # dominance logic ran, and check it still yields exactly one county.
    partial = next(m for z in ("77494", "30188", "89052", "20105") if (m := crosswalk.lookup(z)))
    assert partial.share < 1.0
    assert len(partial.county_fips) == 5


def test_unknown_or_missing_zip(crosswalk: ZipCountyCrosswalk) -> None:
    assert crosswalk.lookup(None) is None
    assert crosswalk.lookup("00000") is None


def test_zip_only_attribution_of_sample_facilities(crosswalk: ZipCountyCrosswalk) -> None:
    facilities = parse_page(json.loads(SAMPLE.read_text(encoding="utf-8")))
    report = attribute_facilities(facilities, crosswalk)  # no county index → ZIP fallback only
    by_id = {f.id: f for f in report.facilities}
    assert by_id["vha_648"].county_fips == "41051"  # Multnomah, OR
    assert by_id["vha_663"].county_fips == "53033"  # King, WA
    assert by_id["vha_516GC"].county_fips == "12071"  # Lee, FL
    source = by_id["vha_648"].county_source
    assert source is not None and "zip 97239" in source
    assert report.unresolved_county == ["vha_999ZZ"]
    assert report.unresolved_visn == []
    assert not report.all_resolved
    assert report.by_method == {"zip_crosswalk": 3}


def test_point_in_polygon_attribution_resolves_no_zip_sample(
    crosswalk: ZipCountyCrosswalk, counties: CountyIndex
) -> None:
    facilities = parse_page(json.loads(SAMPLE.read_text(encoding="utf-8")))
    report = attribute_facilities(facilities, crosswalk, counties)
    by_id = {f.id: f for f in report.facilities}
    assert report.all_resolved
    nowhere = by_id["vha_999ZZ"].county_fips
    assert nowhere is not None and nowhere.startswith("20")  # (40.0, -100.0) is in Kansas
    source = by_id["vha_648"].county_source
    assert source is not None and source.startswith("point-in-polygon")
    assert report.by_method == {"point_in_polygon": 4}


@pytest.mark.skipif(not REAL_FACILITIES.exists(), reason="run `make reference` first")
def test_m1_done_when_every_health_facility_resolves(
    crosswalk: ZipCountyCrosswalk, counties: CountyIndex
) -> None:
    """M1 'done when': every health facility resolves to a county and VISN.

    The one accepted exception is the Manila VA Clinic (Philippines), which has no US county.
    """
    facilities = from_geojson(json.loads(REAL_FACILITIES.read_text(encoding="utf-8")))
    assert len(facilities) > 1_000
    report = attribute_facilities(facilities, crosswalk, counties)
    assert report.unresolved_visn == []
    assert report.unresolved_county == ["vha_358"]
    assert report.by_method.get("point_in_polygon", 0) >= len(facilities) - 5
