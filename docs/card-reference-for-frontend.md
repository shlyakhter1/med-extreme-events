# Playbook cards — reference for the front-end team

*As of 2026-09-20. Describes the six v1 cards as the API serves them, and the rules for
rendering them. Source of truth for the clinical wording is `docs/card-library.md`; the
machine-readable form is `cards/*.yaml`, validated against `cards/card.schema.json`.*

---

## 1. What a card is

A card is one reviewed clinical rule pairing an **extreme-event type** with a **condition +
medication or device class**, plus the actions to take, the patient-facing wording, and the
escalation triggers. Cards are content, not code: they are YAML files reviewed like
clinical documents.

The engine matches an event to cards, works out which facilities are in scope, sizes the
affected panel, and writes an **action item**. Action items are what you render.

```
event (NWS alert, FEMA declaration, smoke polygon)
   → counties
   → facilities in those counties
   → cards whose trigger matches the event
   → panel sized from aggregate data
   → one action item per (event, card, facility, role)
```

### Three rules that are not negotiable

1. **Render clinical text verbatim.** Never paraphrase, summarise, truncate mid-sentence,
   auto-translate, or "improve" anything in `actions[].text`, `message`, or
   `escalation[].signs`. This is reviewed clinical content. Truncation with an ellipsis for
   a list preview is fine as long as the full text is one interaction away.
2. **Always show `safety_message` when present.** It is the "don't stop your medication"
   line. It must not be collapsed behind a disclosure control.
3. **Never show a number without its provenance.** Every panel estimate carries `formula`,
   `inputs`, `caveats` and `sources`. A "how was this computed?" affordance is required
   wherever `panel.value` appears.

---

## 2. Why one item per facility, and not per patient

**This is the question we get most often, so it is worth stating plainly.**

The system runs in **Mode A: aggregate, no PHI**. There are no patient records in it at
all, real or synthetic. Nothing identifies a person, and nothing could.

So a card cannot be issued per patient — there are no patients to issue it to. Instead an
action item is scoped to a **facility**, and its `panel` is an *estimate* of how many
people at that facility fall in the card's population. The item means:

> "At this station, roughly this many veterans match this card during this window. Here is
> what to do, and here is exactly how that number was derived."

`scope_type` is `"facility"` today. It exists because in later modes it becomes
`"patient"`, at which point the same engine emits one item per person and `scope_id` holds
a patient id. The card content, evidence tier, escalation and safety line do not change
between modes — only the scope.

### Timing already differs between facilities

Two facilities holding the same card are not duplicates, and their timing is not the same.
The window comes from the **event** driving that facility, and each facility sits in
different counties under different alerts with different onsets. From the heat-dome replay,
the same card at the same moment:

| Station | Event | Window (UTC) |
| --- | --- | --- |
| `vha_663` Seattle | Excessive Heat Warning | 2021-06-18 20:00 → 2021-07-02 08:44 |
| `vha_648` Portland | Excessive Heat Warning | 2021-06-19 17:00 → 2021-06-30 03:15 |
| `vha_531` Boise | Excessive Heat Warning | 2021-06-21 18:00 → 2021-07-08 06:00 |

Across 11 stations firing that one card there were **7 distinct window starts and 9
distinct window ends**. Treat `window_start`/`window_end` as per-item, never per-card.

`window_start` is `event.onset − card.window_days.max`, which is why items appear up to
seven days before the weather does. That lead time is the entire point of the product.

### One item per station, not per clinic

Action items are issued only at facilities that own a catchment — the **183 stations**
(medical centers and health care centers) out of 1,400 facilities. Clinics inherit their
station's estimate for display but do not get their own items, because the same estimated
patients would otherwise be counted once per facility. Before this was fixed, 70 facilities
in one replay reported only 14 distinct panel values and the totals were inflated several
times over.

---

## 3. The six cards

Every card currently has `window_days` of **3–7 days** and `version` `1.0.0`.

| # | `card_id` | Title | Fires on | Acuity rank | Evidence |
| --- | --- | --- | --- | --- | --- |
| 6 | `outage-dialysis` | Hurricane/Power Outage × Dialysis-Dependent ESRD | hurricane, tropical storm, observed outage ≥ 10% of county customers | **0 (highest)** | strong |
| 3 | `hurricane-delivery-interruption` | Hurricane/Flood × Delivery Interruption: Clozapine, LAIs, Methadone | hurricane, tropical storm, storm surge, flood, flash flood, observed outage ≥ 25% | 1 | inferential |
| 5 | `outage-insulin` | Hurricane/Power Outage × Insulin-Dependent Diabetes | hurricane, tropical storm, observed outage ≥ 10% | 2 | strong |
| 1 | `heat-lithium` | Extreme Heat × Bipolar Disorder on Lithium | heat advisory/watch/warning, HeatRisk ≥ orange | 3 | strong |
| 2 | `heat-antipsychotics` | Extreme Heat × Schizophrenia on Antipsychotics | same heat triggers | 4 | strong |
| 4 | `heat-heart-failure` | Extreme Heat × Heart Failure on Diuretics / ACE-ARB-ARNI / Beta-blockers | same heat triggers | 5 | strong |

**Acuity rank drives ordering.** Lower is more urgent. Sort lists by `acuity_rank` first,
then by event severity, then by panel size. Dialysis outranks everything because a missed
session is life-threatening within days. Do not invent your own ordering.

### Card 1 — `heat-lithium`

Extreme Heat × Bipolar Disorder on Lithium · acuity `lithium` (rank 3) · evidence **strong**

- **Triggers:** Heat Advisory, Excessive/Extreme Heat Watch, Excessive/Extreme Heat
  Warning, HeatRisk ≥ orange.
- **Population:** bipolar disorder (ICD-10 F31) on lithium (ATC N05AN01).
- **Risk flags:** co-prescribed ACE/ARB, thiazide, NSAID; CKD; prior lithium toxicity;
  homeless or isolated.
- **Content:** 8 care-team actions (4 pre-event, 4 during), 3 patient sentences,
  2 escalation triggers (1 emergency), 4 sources.
- **Carbon:** lithium carbonate, 7–22 kg CO₂e per patient-year, confidence medium.
- **Hook:** VA Pharmacy Disaster Relief Plan.

### Card 2 — `heat-antipsychotics`

Extreme Heat × Schizophrenia on Antipsychotics · acuity `antipsychotic_heat` (rank 4) ·
evidence **strong**

- **Triggers:** same as Card 1.
- **Population:** schizophrenia (F20), schizoaffective (F25), antipsychotic-treated bipolar
  (F31), on any antipsychotic (ATC N05A).
- **Risk flags:** clozapine, olanzapine, chlorpromazine, adjunctive benztropine, two or
  more antipsychotics, homeless or isolated.
- **Content:** 8 care-team actions (3 pre, 5 during), 3 patient sentences, 2 escalation
  triggers (1 emergency), 5 sources, 5 evidence claims, 2 caveats.
- **Carbon:** clozapine 15–40, olanzapine 5–11, haloperidol 5–11 kg CO₂e per patient-year.
- **Hook:** Homeless PACT teams.
- **Note for the UI:** the patient text opens with "Your medicine is important — keep
  taking it." Do not let a layout truncate that sentence.

### Card 3 — `hurricane-delivery-interruption`

Hurricane/Flood × Delivery Interruption: Clozapine, LAIs, Methadone · acuity
`clozapine_lai_methadone` (rank 1) · evidence **inferential**

- **Triggers:** Hurricane Watch/Warning, Tropical Storm Watch/Warning, Storm Surge
  Watch/Warning, Flood Watch/Warning, Flash Flood Warning; or an observed power outage
  of ≥ 25% of county electric customers sustained over two consecutive polls.
- **Population:** schizophrenia (F20), schizoaffective (F25), opioid-related disorders
  (F11).
- **Three sub-panels**, each rendered as its own sized component under the card's panel:
  1. `clozapine` — clozapine patients (≈4% of VHA schizophrenia patients)
  2. `lai_antipsychotic` — LAI antipsychotic patients with injections due in the window
  3. `methadone_buprenorphine` — OUD patients on methadone or buprenorphine
- **Content:** 10 care-team actions (5 pre, 5 during), 3 patient sentences, **3 escalation
  triggers, all emergency**, 7 sources.
- **Carbon:** paliperidone LAI 2.4–7, methadone liquid 11–22, venlafaxine ER 5–13 kg
  CO₂e per patient-year.
- **Hooks:** Pharmacy Disaster Relief Plan, National Clozapine Coordinating Center, OTP
  coordination per SAMHSA, Clinical Contact Center, My HealtheVet.
- **This is the only `inferential` card.** Its evidence tier must be visible, because the
  disaster→clozapine-relapse pathway is inferred rather than directly documented.

### Card 4 — `heat-heart-failure`

Extreme Heat × Heart Failure on Diuretics / ACE-ARB-ARNI / Beta-blockers · acuity
`heart_failure` (rank 5) · evidence **strong**

- **Triggers:** same as Card 1.
- **Population:** heart failure (I50) on loop or thiazide diuretics, ACE inhibitors, ARBs,
  ARNI, or beta-blockers (ATC C03C, C03A, C09A, C09C, C09DX04, C07).
- **Risk flags:** ACE/ARB plus diuretic, prior AKI, prior hyponatremia.
- **Content:** 8 care-team actions (4 pre, 4 during), **6 patient sentences**, **6
  escalation triggers** (1 emergency, 5 using the templated response) — the longest
  escalation list, so plan for it in the layout.
- **Panel multiplier:** this is the only card whose panel is narrowed by a medication-class
  share (`hfref_ace_arb_arni_share`, 0.62).
- **Carbon:** furosemide 4–9, lisinopril 5–11, metoprolol ER 5–11 kg CO₂e per patient-year.

### Card 5 — `outage-insulin`

Hurricane/Power Outage × Insulin-Dependent Diabetes · acuity `insulin` (rank 2) · evidence
**strong**

- **Triggers:** Hurricane Watch/Warning, Tropical Storm Watch/Warning, **or an observed
  power outage** of ≥ 10% of county electric customers sustained over two consecutive
  polls — the first card with a non-weather trigger.
- **Population:** type 1 (E10) and insulin-treated type 2 (E11) diabetes, on insulin
  (A10A) or GLP-1 analogues (A10BJ); insulin pump as a device class.
- **Risk flags:** pump user, mail-order refrigerated supply.
- **Content:** 8 care-team actions, 6 patient sentences, 4 escalation triggers (2
  emergency), 5 sources.
- **Carbon:** insulin glargine 15–40 kg CO₂e per patient-year, confidence medium.
- **Largest panels in the set** — diabetes is ~25% of VA patients, so expect five-figure
  numbers at big stations and lay out accordingly.

### Card 6 — `outage-dialysis`

Hurricane/Power Outage × Dialysis-Dependent ESRD · acuity `dialysis` (**rank 0**) ·
evidence **strong**

- **Triggers:** Hurricane Watch/Warning, Tropical Storm Watch/Warning, or an observed
  outage of ≥ 10% of county customers sustained over two polls.
- **Population:** ESRD (N18.6) and dialysis dependence (Z99.2); device classes for
  in-center hemodialysis and home dialysis.
- **Risk flags:** home dialysis, emPOWER electricity-dependent.
- **Content:** 9 care-team actions (4 pre, 5 during), 6 patient sentences, 4 escalation
  triggers (2 emergency), 6 sources.
- **The only card with `safety.do_not_stop_medication: false`**, so `safety_message` is
  `null`. Dialysis is a therapy, not a medication, so the do-not-stop line does not apply.
  Handle the null.
- **The patient text contains a phone number** (KCER hotline, 1-866-901-3773). Make it
  tappable.
- **Carbon:** in-center hemodialysis **3,800–4,800 kg CO₂e per patient-year**, confidence
  high — roughly 300–500× any oral drug in the set. Expect this row to dominate any chart;
  do not put it on a shared linear axis with the pills.

---

## 4. API surface

Base URL is the app itself. Full interactive reference at `/docs`.

| Endpoint | Returns |
| --- | --- |
| `GET /cards` | All six card definitions (the reviewed content) |
| `GET /action-items?scenario=&at=&facility=&role=&card=&status=` | Compact rows for lists and maps |
| `GET /action-items/{id}` | One item in full, including card text and panel provenance |
| `POST /action-items/{id}/status` | Status transition, body `{"status": "acknowledged"}` |
| `GET /facilities/{id}/action-items?role=&at=&scenario=` | Full items for one facility |
| `GET /facilities` | Facilities as GeoJSON |
| `GET /facilities/{id}/panels[?card=]` | Panel estimates with provenance, without events |
| `GET /events?scenario=&at=&county=` · `GET /events/detail?key=` | Events |
| `GET /scenarios` | Replay scenarios with window and `peak_at` |
| `GET /carbon` | Carbon table, grouped under `by_card` |
| `GET /reference/counties` | County polygons for the map (5 MB, gzipped) |
| `GET /feeds` | Live feed freshness for the staleness banner |

**Omit `scenario` for live data; pass a scenario id for a replay.** Everything is UTC.
`at` accepts ISO-8601, a trailing `Z`, `datetime-local` minute precision, or a bare date.

### Compact row (lists, maps, boards)

```json
{
  "id": "nws:2021-KOTX-EH.W-0001|heat-lithium|vha_663|patient",
  "event_key": "nws:2021-KOTX-EH.W-0001",
  "event_name": "Excessive Heat Warning",
  "event_type": "heat",
  "event_severity": "Severe",
  "event_temporality": "imminent",
  "phase": "pre_event",
  "card_id": "heat-lithium",
  "card_title": "Extreme Heat × Bipolar Disorder on Lithium",
  "facility_id": "vha_663",
  "role": "patient",
  "status": "issued",
  "superseded_by": null,
  "acuity_rank": 3,
  "acuity_class": "lithium",
  "panel": 3323,
  "exposure": null,
  "rank_score": 3323.0,
  "window_start": "2021-06-18T20:00:00+00:00",
  "window_end": "2021-07-02T08:44:00+00:00"
}
```

In compact rows `panel` is a **rounded number**. In full items it is an object.

`exposure` is set only on power-outage items: the emPOWER count of electricity-dependent
Medicare beneficiaries in the station's catchment (a full `Estimate` object in full items).
It is a **measured Medicare proxy, not veteran-specific** — render it as a second line next
to `panel`, with that label, never in place of it. `rank_score` orders items within an
acuity class: panel size normally, `outage_pct × exposure` for outage items; the full item's
`rank_formula` says which.

### Full item

Adds `actions`, `message`, `escalation`, `safety_message`, `evidence_tier`, `sources`,
`card_version`, `scope_type`, `scope_id`, `created_at`, `acknowledged_at`, and the panel
object:

```json
{
  "actions": [{ "text": "Heat can push your lithium to a dangerous level.", "phase": "any" }],
  "message": "Heat can push your lithium to a dangerous level. Drink water steadily, ...",
  "escalation": [{
    "signs": "New/worsening tremor, nausea/vomiting, diarrhea, drowsiness, confusion, slurred speech, unsteadiness",
    "response": "urgent contact / same-day level / ED",
    "emergency": true
  }],
  "safety_message": "Don't stop your medication — contact your care team.",
  "panel": { "label": "...", "value": 3323.1, "unit": "veterans",
             "formula": "...", "inputs": {}, "caveats": [], "sources": [], "components": [] }
}
```

- `phase` is `pre_event`, `during_event` or `any`. Group care-team actions by phase; label
  `pre_event` as "Pre-event (3–7 days out)".
- `message` is the patient/caregiver sentences joined. It is `null` for `care_team`.
- `escalation[].response` is never null on an item — the profile's templated response is
  filled in. It *is* null in raw card definitions from `GET /cards`.
- `panel.components` nests: the card panel contains the condition panel, which contains the
  scoped population, which contains the veteran count. Render it as a tree in the
  provenance popover.

---

## 5. Roles

The data model carries three roles: `care_team`, `patient`, `caregiver`.

**The UI presents two audiences**: *care team*, and *patient & caregiver* combined. Show
the patient text, then the caregiver text beneath it when present.

**In v1 no card has caregiver wording, and the engine does not emit an item for a role a
card has no content for.** So `GET /action-items?role=caregiver` returns **zero rows**
today — that is correct, not a bug. Render a short note under the patient text rather than
an empty panel or an error. When caregiver wording is written, items start appearing with
no API change, so build the merge now.

`message` is `null` on `care_team` items; the care-team view uses `actions[]` grouped by
`phase`.

---

## 6. Status and lifecycle

```
issued → delivered → acknowledged → completed
   ↘         ↘            ↘
    expired / superseded (terminal)
```

- The server enforces transitions. An illegal one returns **409**; render the message.
- **`superseded`** means a stronger overlapping alert replaced this item — a watch upgraded
  to a warning. `superseded_by` holds the winning item id. Hide these by default; list
  endpoints already exclude them unless you pass `include_superseded=true`.
- **`expired`** means the window closed. Live items auto-expire; replay items never do,
  because their scenario time frame is fixed.
- Offer *Acknowledge* on `issued`/`delivered`, and *Mark completed* on `acknowledged`.
  Nothing else is user-triggerable.
- Unacknowledged items with `acuity_rank <= 1` are the outreach queue. Surface them.

---

## 7. Carbon panel

`GET /carbon` returns display-only, order-of-magnitude estimates per therapy, grouped by
card number under `by_card`. Each entry has `assumed_dose`, `kg_co2e_per_patient_year`,
`km_driven_equivalent_per_year`, `basis`, `confidence`, `citations`, and sometimes
`g_co2e_per_daily_dose`, `kg_co2e_per_session` or a `note`.

Rules:

- **Always render `ui_disclaimer`** with any carbon number. It ships in the same payload so
  you cannot render the numbers without it.
- **Never sum rows within a card.** The drugs on a card are alternatives a patient takes
  one of. Show each as its own scenario.
- **Always show the range**, never a midpoint. Ranges are honest bounds, and per-drug
  precision beyond one significant figure is not supported by the underlying evidence.
- Scale to the facility's panel if you want a total: `panel × kg_per_patient_year ÷ 1000`
  gives tonnes per year. Label it as an estimate scaled by an estimate.
- Carbon never affects triggering, acuity or clinical content. It is context only.

---

## 7a. Selections nest, so closing is layered

Playback selections stack: a card filter can contain a facility drill-down. Closing must
therefore go back one level, not all the way out. The detail panel carries a breadcrumb
(`All cards › <card> › <facility>`) where each earlier step links back to that level, an
explicit × close for the deepest level, and an Escape binding. Apply the same pattern in
any new view: an explicit close, a keyboard escape, and a visible trail back.

---

## 8. Edge cases to handle

| Case | What you get | What to do |
| --- | --- | --- |
| Card with no caregiver text (all of v1) | **No caregiver item at all** — `role=caregiver` returns zero rows | Show a note under the patient text; do not treat as an error |
| `care_team` item | `message` is `null` | Use `actions[]` grouped by `phase` |
| Dialysis card | `safety_message` is `null` | Omit the warning block |
| Clinic, not a station | No action items of its own | Link to its parent station; `panel.inputs.station_id` names it |
| Facility outside US county coverage | `county_fips` is null (Manila VA Clinic) | Excluded from matching; never shows items |
| Event with no matching card | Event exists, no items | Say so explicitly — this is a real answer, not an error |
| Stale live feed | `/feeds` marks `stale: true` after 6 h | Banner. **An empty board is never an all-clear** |
| Superseded item | `status: "superseded"`, `superseded_by` set | Hide by default; show the successor |
| Sub-panels (Card 3 only) | `panel.components` with `(sub-panel)` labels | Render as named components under the total |

---

## 9. Things that will change

- **Caregiver wording** is unwritten. When it lands, the combined panel fills in with no
  API change.
- **Mode B** switches `scope_type` to `patient` and `scope_id` to a patient id. Plan list
  and detail components so the scope is a parameter, not an assumption.
- **Clinical review is open** on the claim evidence tiers, the ICD-10/ATC code bindings,
  the heat-watch trigger, and the VHA-user share used to scale literature rates. See the
  top of `PROGRESS.md`. Nothing about the payload shape depends on those outcomes.
- **AirNow** air-quality events are not verified against a live key yet, so `air_pollution`
  events may not appear. No v1 card triggers on them.
