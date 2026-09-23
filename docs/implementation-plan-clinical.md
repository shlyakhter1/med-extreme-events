# Implementation Plan — Clinical Review Adoption (M11–M12)

*As of 2026-09-23. Implements the clinical-evidence audit. The two documents in this bundle —
`docs/card-library.md` (all 8 cards + Card 6 DME sub-panel) and `docs/medical-references.md` —
are the new sources of truth and REPLACE the current `docs/card-library.md`,
`docs/card-library-additions.md`, and `docs/medical-references.md`. Card YAML is re-transcribed
from the new library by the maintainer; Claude Code's job is everything around that. One
milestone per session; `make lint test` green and a PROGRESS.md entry at the end of each.*

## Direct answer: what changes beyond text?

**Triggers: nothing.** The audit confirmed the trigger design (AQI 101/151, the SCN 23-44
cold taxonomy, outage thresholds); no `event_triggers` or `TriggerConditions` change is
needed.

**Beyond text, five real items:** (1) source-id migration so the loader and the
references-index test pass; (2) a shared-sentence consistency test enforcing the cross-card
rules; (3) handling for the one action that doesn't fit the current phase model (Card 1's
post-heat-event level check); (4) provenance labeling of planning-estimate denominators in
the UI; (5) test/golden/doc-generation fallout. All are small; none touches the engine's
matching logic.

## M11 — Adopt the reviewed library: docs, ids, YAML validation

Touch: `docs/card-library.md` (replace), `docs/card-library-additions.md` (delete — its
content now lives in the unified library; fix inbound links from guide pages and
requirements-v2), `docs/medical-references.md` (replace), `cards/*.yaml` (validate the
maintainer's re-transcription), `src/xevents/cards.py` tests, `docs/card-reference-for-frontend.md`.

1. **Source-id migration.** The card YAML and the references index must use the new id set
   (medical-references.md §1). Renames and splits:
   - `kelman-lurie-2015` → `kelman-2015` + `lurie-2015` (two papers, distinct claims)
   - `va-sandy-dialysis-study` → `lukowsky-2019`
   - `martin-latry` → `martin-latry-2007`; `katrina-sandy-otp-studies` → `maxwell-2009`,
     `mcclure-2014`, `griffin-2018`; `samhsa-otp-disaster-guidance` → `samhsa-42cfr8-2024`;
     `cms-kcer-emergency-diet` → `nkf-emergency-diet` + `ipro-khares`;
     `lithium-interaction-pharmacology` → `finley-1995` + `nsaid-class-labeling`;
     `fda-clozapine-rems-elimination` → `fda-clozapine-rems-2025` + `clozapine-pi`;
     `clozapine-withdrawal-literature` → `shiovitz-1996`; `morris-paliperidone` →
     `weiden-2017`; `cdc-mmwr-72-34-2023` → `meek-2023`;
     `cdc-smoke-day-asthma-2023` → `cdc-smoke-asthma-2023`
   - New ids: `alahmad-2023`, `heat-thermoregulation-meta-2024`, `bccdc-bcmj-2023`,
     `hf-daily-weight-education`, `ada-sick-day`, `cdc-co-guidance`, `aha-snow-shoveling`,
     `respiratory-action-plans`
   - Removed ids (must appear nowhere): `cdc-co-texas-2021` (unverifiable — its content is
     now covered by `texas-dshs-uri-2021`), `ali-dogar-2025`, `cdc-mmwr-puerto-rico`
     (unverified figure removed from Card 3), `anderson-2009` stays. `setoguchi-hennessy-2026`
     remains ONLY on Card 5 (mechanism claims) and in the carbon table — it must no longer
     appear in Card 4.
   - Add a temporary `tests/` assertion listing removed ids and failing if any card cites
     one (delete the assertion after one green release).
2. **Claim-level bindings.** After the maintainer re-transcribes YAML: verify every claim's
   `tier` and `source_ids` match the library exactly (tiers are now clinically assigned, no
   longer placeholders — remove the "engineering placeholders" caveat from PROGRESS/docs);
   verify no quantitative claim cites a pending-status source (loader-level check: add
   `status: pending` support to the references index parser or keep a hand-maintained
   pending-id list in the test).
3. **Verbatim patient-text test** re-baselined against the new library, including the
   `[SHARED]` markers, which are library markup — they must NOT appear in YAML strings or
   rendered UI text (strip rule documented in the library header; test that no rendered
   string contains "[SHARED]").
4. **Version bumps** on all 8 cards (minor for 2/5/7/8, major for 1/3/4/6 whose patient
   text changed materially); `number` unchanged; regenerate `card.schema.json` only if the
   maintainer's YAML surfaces schema gaps (none expected).
5. **Regenerate** `docs/card-reference-for-frontend.md` and the medical-references §2
   card-by-card table from the cards (the existing test that every cited id exists in the
   index must pass against the new index).

*Done when:* loader green on the re-transcribed YAML; no removed id cited; verbatim tests
re-baselined; references-index test green; guide links resolve.

## M12 — Consistency guards, phase handling, provenance polish

Touch: `tests/` (new consistency tests), `src/xevents/engine.py` (only if option B below is
chosen), `profiles/va.yaml`, web templates (provenance popover, hotline text).

1. **Shared-sentence tests** (the contradiction guards from medical-references.md §3):
   - Fluid-limit sentence: byte-identical in the patient text of Cards 1, 4, 6.
   - CO sentence: byte-identical in Cards 5, 6, 7, 8.
   - Card 8 contains the cleaner-air/cooling-center escape hatch.
   - Card 7 contains the insulin-freeze line; Card 1 patient text contains no
     liters-per-day figure; no patient-facing string on any card contains "stop your" +
     medication phrasing (crude but effective regression net for constraint 5).
2. **Post-event action (Card 1's "repeat level within a week").** The engine derives
   `pre_event`/`during_event` from temporality; there is no post-event phase. Decide:
   - **A (recommended, no engine change):** keep it as text inside the during-event
     care-team block, as the library currently words it ("After the event: …"). Ship this.
   - **B (backlog):** add `post_event` to the Phase enum, emitted when an event expires
     (event end + configurable window in `profiles/va.yaml`), schema bump + engine
     derivation + one golden assertion. Write it up as a backlog entry in requirements; do
     not build now.
3. **Planning-estimate provenance.** Denominators sourced from the VA planning anchors
   (medical-references.md §1, `va-*-prevalence`) must render with a "planning estimate"
   label in the provenance popover, distinct from PLACES×VetPop modeled estimates and from
   emPOWER measured counts. Copy change + one template test; no data change.
4. **Hotline rendering.** Card 6 patient text now carries two numbers (KHARES + legacy
   KCER); confirm the UI renders both as tappable tel: links; add a `# TODO(2026-Q4)` note
   in the card YAML comments to drop the legacy number once confirmed retired.
5. **Contested-findings display.** The two contested items (medical-references.md §4) live
   in card `caveats`; confirm caveats render in the card detail view (they exist in the
   schema — verify the template shows them; add if the retired-pages cleanup dropped it).
6. **Golden tests.** Patient strings appear in golden files for the three scenarios —
   regenerate goldens after M11 YAML lands and hand-diff: the ONLY changes must be text,
   versions, and source ids; any trigger/matching diff is a bug (triggers are unchanged by
   design).

*Done when:* consistency tests green and demonstrably failing when a shared sentence is
perturbed (mutation-check in the test itself); goldens regenerated with text-only diffs;
provenance labels visible; `make demo` green from empty.

## Out of scope, tracked

- `actions.caregiver` remains empty on all cards — still a content-authoring task for a
  clinical reviewer, unchanged by this audit.
- The verification queue (medical-references.md §5) is reviewer work, not code: pending
  sources block no current claim.
- Dynamic card generation and the System KG evaluation are separate legs of the review, not
  part of M11–M12.
