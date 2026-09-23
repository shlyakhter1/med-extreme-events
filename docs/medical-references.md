# Medical references

*As of 2026-09-23. An index of the literature behind the playbook cards, plus background
references read for the project. It is a reading list, not clinical content: nothing here is
shown to patients or care teams.*

**What this document is not.** The reviewed sources of truth for card wording and evidence
are [`card-library.md`](card-library.md) (Cards 1–6) and
[`card-library-additions.md`](card-library-additions.md) (Cards 7, 8 and the Card 6
addendum). The cards cite sources by id in `cards/*.yaml`. To make a reference *support a
card*, add it to the card library through clinical review first, then transcribe it into the
card's `sources` and the claims' `source_ids` (the loader rejects unknown ids). Listing a
paper here changes nothing the system says.

Medication carbon references are kept separately, in
[`carbon-footprint.md`](carbon-footprint.md) §References.

## 1. Key references

### Setoguchi & Hennessy 2026 — Climate change and medications

> Setoguchi S, Hennessy S. Climate Change and Medications: Implications for Clinical
> Practice, Healthcare Sustainability, and Pharmacoepidemiology. *Pharmacoepidemiology and
> Drug Safety* 2026;35(8):e70437. doi:[10.1002/pds.70437](https://doi.org/10.1002/pds.70437).
> PMCID [PMC13427620](https://pmc.ncbi.nlm.nih.gov/articles/PMC13427620/). Published
> 31 July 2026.

- **Type:** commentary (a framework, not a primary study). Card id:
  `setoguchi-hennessy-2026`; carbon table id: `setoguchi2026`.
- **Framework:** two directions. *Downstream*, climate harms medications (stability, access,
  and how drugs interact with heat). *Upstream*, medications contribute to climate change
  (pharmaceutical emissions, inhalers, formulation choices).

**What it says that bears on the cards** (quoted from the full text, checked 2026-09-23):

| Point | Quote | Relevant to |
| --- | --- | --- |
| Insulin loses potency with heat, and outages threaten it | "unopened insulin loses potency within months at 37°C." "Power outages during extreme weather can therefore compromise insulin effectiveness during emergencies." | Card 5 (insulin × outage) |
| Heat-sensitizing drug classes | "diuretics and angiotensin‐converting enzyme inhibitors may blunt thirst sensation, and selective serotonin reuptake inhibitors and anticholinergics impair sweating" | Card 4 (heart failure), Card 2 (antipsychotics, anticholinergic burden) |
| Mail-order storage | Non-refrigerated drugs should be stored at 15–30 °C, "yet delivery trucks can reach 65°C" | Card 3 (delivery interruption), Card 5 |
| Supply chains | Hurricane Helene flooded the Baxter plant that makes about 60 % of US IV fluids | Card 3 (hurricane) |
| Preparedness | "Hospital systems and pharmacy networks should maintain backup power and emergency‐stock protocols"; "patient‐specific risk stratification for drug unavailability must consider age, chronic disease burden, and social support" | Cards 3, 5, 6; panel sizing |
| Inhaler carbon | Metered-dose inhaler propellants have "global warming potentials of 1430 to 3220 times greater than CO₂"; dry powder and soft mist inhalers have 10–37 times lower carbon intensity | Card 8 carbon panel only |
| Pharmacists | Pharmacists can "flag heat‐sensitizing combinations at medication reconciliation" | Care-team actions on Cards 1, 2, 4 |

**Where it is cited today:** the `sources` of Cards 4 and 5, the source table in
[`card-library.md`](card-library.md) ("Framework: climate–medication commentary"), and the
carbon table ([`carbon.yaml`](carbon.yaml), [`carbon-footprint.md`](carbon-footprint.md)
ref. 10) for the upstream framing.

**Citation check — open for clinical review.**

- **Card 4 attributes a claim to this paper that the paper does not make.** In
  `cards/04-heat-heart-failure.yaml`, the claim "Extreme heat above the 97th–99th
  temperature percentiles is linked to roughly a 10–15% rise in HF-related deaths" cites
  only `setoguchi-hennessy-2026`. The commentary has no heart-failure mortality figures or
  temperature percentiles. In `card-library.md` the same sentence carries no citation, so
  the link was added when the card was transcribed. A reviewer should find the claim's
  real source, or drop it.
- **Card 5 lists the paper as a source, but none of its claims cites it.** The insulin
  potency and outage sentences above would support a claim on that card.
- **It does not support deprescribing advice to patients.** The paper recommends
  clinician-led deprescribing of unnecessary drugs. This project never advises stopping or
  changing a medication (CLAUDE.md, constraint 5), so that recommendation stays out of card
  text.

## 2. Sources cited by each card

Generated from the `sources` lists in `cards/*.yaml` (42 distinct sources). The claim-level
tiers and `source_ids` in the YAML are engineering placeholders awaiting clinical review
(see `PROGRESS.md`). A test checks that every source id in the cards appears here.

### Card 1 — `heat-lithium`

*Extreme Heat × Bipolar Disorder on Lithium*

| Source id | Citation | Also cited by |
| --- | --- | --- |
| `cdc-heat-medications-2024` | [CDC "Heat and Medications — Guidance for Clinicians" (2024)](https://restoredcdc.org/www.cdc.gov/heat-health/hcp/clinical-guidance/heat-and-medications-guidance-for-clinicians.html) — June 2024 version; page archived early 2025. | Card 2, Card 4 |
| `fda-lithium-label` | FDA lithium prescribing information | — |
| `ali-dogar-2025` | Ali & Dogar 2025 (BJPsych Open) | — |
| `lithium-interaction-pharmacology` | NSAID/ACE-ARB lithium interaction pharmacology | — |

### Card 2 — `heat-antipsychotics`

*Extreme Heat × Schizophrenia on Antipsychotics*

| Source id | Citation | Also cited by |
| --- | --- | --- |
| `nordon-2009` | Nordon et al. 2009 (Am J Geriatr Psychiatry) | — |
| `martin-latry` | [Martin-Latry et al. (European Psychiatry)](https://www.sciencedirect.com/science/article/abs/pii/S0924933807013089) | — |
| `chen-2025` | Chen et al. 2025 (Scientific Reports) and BCCDC/BCMJ report | — |
| `cdc-heat-medications-2024` | [CDC "Heat and Medications — Guidance for Clinicians" (2024)](https://restoredcdc.org/www.cdc.gov/heat-health/hcp/clinical-guidance/heat-and-medications-guidance-for-clinicians.html) | Card 1, Card 4 |
| `shannon-2025` | Shannon et al. 2025 (JAMA Network Open, 2545524) | — |

### Card 3 — `hurricane-delivery-interruption`

*Hurricane/Flood × Delivery Interruption: Clozapine, LAIs, Methadone*

| Source id | Citation | Also cited by |
| --- | --- | --- |
| `fda-clozapine-rems-elimination` | FDA clozapine REMS elimination (June 13, 2025) | — |
| `clozapine-withdrawal-literature` | Clozapine withdrawal-syndrome case literature | — |
| `morris-paliperidone` | Morris et al. (paliperidone relapse timing) | — |
| `samhsa-otp-disaster-guidance` | [SAMHSA OTP disaster take-home/guest-dosing guidance](https://www.pew.org/en/research-and-analysis/articles/2025/02/25/how-states-can-ensure-addiction-treatment-access-during-natural-disasters) | — |
| `katrina-sandy-otp-studies` | Post-Katrina/Sandy OTP studies | — |
| `cdc-mmwr-puerto-rico` | CDC MMWR Puerto Rico data | — |
| `va-pharmacy-disaster-relief-plan` | [VA Pharmacy Disaster Relief Plan](https://www.va.gov/fayetteville-coastal-health-care/programs/pharmacy-disaster-relief-plan/) | — |

### Card 4 — `heat-heart-failure`

*Extreme Heat × Heart Failure on Diuretics / ACE-ARB-ARNI / Beta-blockers*

| Source id | Citation | Also cited by |
| --- | --- | --- |
| `cdc-heat-medications-2024` | [CDC "Heat and Medications — Guidance for Clinicians" (2024)](https://restoredcdc.org/www.cdc.gov/heat-health/hcp/clinical-guidance/heat-and-medications-guidance-for-clinicians.html) | Card 1, Card 2 |
| `layton-2020` | [Layton et al., PLOS One 2020](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7728169/) | — |
| `setoguchi-hennessy-2026` | [Setoguchi & Hennessy, Pharmacoepidemiol Drug Saf 2026](https://pmc.ncbi.nlm.nih.gov/articles/PMC13427620/) | Card 5 |
| `va-chf-prevalence` | VA CHF prevalence (JAMA Network Open VA cohort) | — |

### Card 5 — `outage-insulin`

*Hurricane/Power Outage × Insulin-Dependent Diabetes*

| Source id | Citation | Also cited by |
| --- | --- | --- |
| `fda-insulin-emergency` | [FDA "Information Regarding Insulin Storage and Switching Between Products in an Emergency"](https://www.fda.gov/drugs/emergency-preparedness-drugs/information-regarding-insulin-storage-and-switching-between-products-emergency) | — |
| `fonseca-2009` | [Fonseca et al., Diabetes Care 2009](https://pubmed.ncbi.nlm.nih.gov/19542210/) | — |
| `setoguchi-hennessy-2026` | [Setoguchi & Hennessy 2026](https://pmc.ncbi.nlm.nih.gov/articles/PMC13427620/) | Card 4 |
| `va-diabetes-prevalence` | VA diabetes prevalence (VA Office of Health Equity; Liu et al., Prev Chronic Dis) | — |
| `cdc-ada-diabetes-disaster` | CDC/ADA diabetes disaster preparedness | — |

### Card 6 — `outage-dialysis`

*Hurricane/Power Outage × Dialysis-Dependent ESRD*

| Source id | Citation | Also cited by |
| --- | --- | --- |
| `anderson-2009` | Anderson et al., Kidney International 2009 | — |
| `kelman-lurie-2015` | [Kelman/Lurie et al., AJKD 2015](https://www.sciencedirect.com/science/article/abs/pii/S0272638614010592) | — |
| `va-sandy-dialysis-study` | VA Sandy dialysis access study | — |
| `cms-kcer-emergency-diet` | CMS/KCER 3-Day Emergency Diet and facility preparedness | — |
| `hhs-empower` | [HHS emPOWER Program documentation (DME categories, REST service)](https://empowerprogram.hhs.gov/about.html) — Electricity-dependent DME sub-panel per docs/card-library-additions.md (Card 6 addendum). | — |
| `va-ohe-esrd-2022` | VA Office of Health Equity ESRD data (2022) | — |

### Card 7 — `cold-cardio-respiratory`

*Extreme Cold / Winter Storm × Cardiovascular & Respiratory Disease*

| Source id | Citation | Also cited by |
| --- | --- | --- |
| `gasparrini-2015` | Gasparrini et al., Lancet 2015 (mortality attributable to cold vs heat, 384 locations) | — |
| `texas-dshs-uri-2021` | Texas DSHS Winter Storm Uri mortality report (2021) | — |
| `cdc-co-texas-2021` | CDC carbon monoxide poisoning surveillance, Feb 2021 Texas | — |
| `cdc-extreme-cold` | CDC extreme-cold clinical and public guidance | — |
| `aha-cold-weather` | AHA cold-weather cardiovascular guidance | — |
| `nws-scn23-44` | NWS SCN23-44 (cold-product taxonomy, Oct 2024) — Source of the current product names listed in event_triggers. | — |

### Card 8 — `smoke-copd-asthma`

*Wildfire Smoke × COPD / Asthma on Inhaled Therapies*

| Source id | Citation | Also cited by |
| --- | --- | --- |
| `cdc-mmwr-72-34-2023` | CDC MMWR 72(34) 2023 (NY asthma ED surge) | — |
| `cdc-smoke-day-asthma-2023` | CDC national smoke-day asthma analysis 2023 | — |
| `epa-wildfire-smoke-guide` | EPA "Wildfire Smoke: A Guide for Public Health Officials" and AirNow Fire & Smoke guidance | — |
| `nbc-2026-smoke` | NBC News data desk, July 2026 Canadian-wildfire smoke episode (rcna588051) | — |
| `nasa-svs-5665` | NASA Scientific Visualization Studio | — |
| `clarity-2026` | Clarity.io open-sensor network report, July 2026 | — |
| `cnn-2026-07-17` | CNN, 2026/07/17 | — |
| `noaa-hms` | NOAA HMS product documentation — Smoke-density trigger basis. | — |

## 3. Other reference lists in the repo

- [`card-library.md`](card-library.md) §Wave 2 Candidates & Sources: the sources table
  with a one-line note of what each supports, and candidate cards not yet built.
- [`carbon-footprint.md`](carbon-footprint.md): medication and treatment life-cycle carbon.
- [`guide/data-sources.md`](guide/data-sources.md): the data behind events and panels
  (VetPop, CDC PLACES, emPOWER, EAGLE-I and the rest), with retrieval dates.
