# Replay Scenario Catalog

*As of 2026-09-21. Scenarios the system can (or could) replay. Status: `built` = fixture exists; `this_iteration` = built in M10; `cataloged` = feasible, sources identified, not yet built; `partial` = some layers unavailable. EAGLE-I outage data exists only from 2014 onward; pre-2014 events can never carry a real outage layer.*

| Scenario | Dates / Region | Hazards exercised | Cards | Fixture sources | Status |
| --- | --- | --- | --- | --- | --- |
| PNW Heat Dome | Jun 25–Jul 1 2021, WA/OR | Extreme heat | 1, 2, 4 | IEM CAP archive | **built** |
| Hurricane Ian | Sep 23–30 2022, FL | Hurricane → observed outage (supersede path) | 3, 5, 6 | IEM CAP + ORNL EAGLE-I 2022 FL | **built → upgraded (M10)** |
| Canadian smoke NYC | Jun 6–8 2023, NY/Northeast | Wildfire smoke / AQI | 8 | HMS + AirNow archive | **built** (card lands M9) |
| **Winter Storm Uri** | Feb 10–20 2021, TX | Extreme cold + largest US outage in EAGLE-I record + cold×outage boost; legacy CAP names test | 7 + 3/5/6 | IEM CAP (legacy Wind Chill products) + ORNL EAGLE-I 2021 TX | **this_iteration (headline golden test)** |
| **Canadian smoke, July 2026** | Jul 14–20 2026, Upper Midwest/Great Lakes → Northeast | Wildfire smoke (PM2.5 ~200 µg/m³ Baltimore–DC Jul 17; AQI >200 Midwest; >100M under alerts) + concurrent central-US heat dome | 8 (+1/2/4 heat narrative) | HMS + AirNow (post-migration endpoints; AQS fallback) + IEM CAP heat alerts | **this_iteration** |
| Hurricane Ida | Aug 26–Sep 2 2021, LA (+ Northeast flooding) | Hurricane + near-total New Orleans outage + post-landfall heat-during-outage | 3, 5, 6 + boost showcase | IEM CAP + ORNL EAGLE-I 2021 LA | cataloged |
| Hurricane Helene | Sep 24–30 2024, FL/GA/NC | Hurricane + Appalachian outage + IV-fluid supply-chain narrative (Baxter plant) | 3, 5, 6 | IEM CAP + ORNL EAGLE-I 2024 | cataloged |
| Winter Storm Elliott | Dec 21–26 2022, Central/East | Extreme cold, grid stress, holiday travel | 7 | IEM CAP + EAGLE-I 2022 | cataloged |
| CA PSPS event | Oct 26–Nov 1 2019, N. CA | *Planned/forecast* outage (temporality=forecast showcase) | 5, 6 pre-event | CPUC PSPS rollup + EAGLE-I 2019 | cataloged (PSPS machine-readable data partner-gated; rollup is coarse) |
| 2023 Canadian smoke, Midwest wave | Jun 27–29 2023, Chicago/Detroit | Wildfire smoke, second wave | 8 | HMS + AirNow archive | cataloged |
| Hurricane Sandy | Oct 2012, NY/NJ | Hurricane, dialysis-history anchor (Card 6 evidence base) | 3, 5, 6 | IEM CAP only | **partial — no EAGLE-I layer (pre-2014); narrative/backtest use only** |
| Hurricane Maria | Sep 2017, PR | Hurricane, pharmacy/power collapse (Card 3 evidence base) | 3, 5, 6 | Limited: PR utility data poor in EAGLE-I early years | partial |
| July 2024 Houston derecho + Beryl | May & Jul 2024, TX | Wind-driven mass outages in extreme heat | 5, 6 + boost | IEM CAP + EAGLE-I 2024 | cataloged |

## Fixture conventions (unchanged)
Each built scenario directory holds raw source files, a `README` with retrieval dates and URLs, and a `build.py` that reconstructs the fixture — rebuildable, never hand-edited. Every event record carries `temporality` (v2 requirement). Golden tests assert the exact expected action-item set per scenario.

## Selection guidance for future additions
Prefer events that (a) exercise an untested code path (a new temporality, a new provider, a supersede pair), (b) anchor a card's own evidence base (Sandy for dialysis, Maria for pharmacy collapse), or (c) demonstrate compounding. Post-2014 events with county-scale impact are fixture-complete; pre-2014 events are narrative-only.
