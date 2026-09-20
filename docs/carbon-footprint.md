# Medication Carbon-Footprint Table — Demo Display Data v1

*As of 2026-09-20. Estimates for UI display in the VA extreme-event demo. These are order-of-magnitude planning figures, not product-specific LCAs.*

## Methods (read before using the numbers)

**Approach.** For each medication in the six playbook cards, we estimate cradle-to-pharmacy greenhouse-gas emissions per assumed daily dose and per patient-year, assuming API (active pharmaceutical ingredient) production in China/India with formulation, packaging, and transport to the US. Three estimation bases are used and labeled per row:

1. **Measured/hybrid-LCA anchor** — Piffoux et al. 2024 (J. Cleaner Production) computed cradle-to-pharmacy footprints for 12,316 oral medicines via hybrid LCA (API + excipients + packaging + transport + manufacturing + corporate overhead). Key anchors: generic paracetamol 1,000 mg tablet ≈ 48 g CO2e/pill (387.8 g/box of 8); generic ramipril 10 mg ≈ 25 g CO2e/pill (740.7 g/box of 30); oral treatments average 14.1 kg CO2e/month across the pharmacopeia (heavily skewed by expensive drugs). Central lesson: for cheap small-molecule generics, **excipients + packaging + manufacturing overhead dominate; API mass is a minor driver**, and footprint correlates with price more than mass. Cheap generic pills land at roughly **10–50 g CO2e per pill** full cradle-to-pharmacy.
2. **API process estimate** — Parvatker et al. 2019 (ACS Sustain. Chem. Eng.): cradle-to-gate API factors for 20 drugs span **11–3,000 kg CO2e per kg API**, correlated with synthesis-step count. Used for API-mass sanity checks (matters only for high-mass APIs like lithium carbonate and clozapine).
3. **Formulation analogues** — oral liquid ≈ 4× tablet and IV/glass-vial ≈ 8–16× tablet per Davies et al. (1 g paracetamol: 38 g tablet, 151 g oral liquid, 310–628 g IV); insulin pens from manufacturer-disclosed figures (Novo Nordisk: disposable-pen users ≈ 15 kg CO2e/patient-year; reusable ≈ 8.2 kg/yr; France OD→OW pen analysis consistent at ~0.7 kg CO2e/pen); in-center hemodialysis from published LCAs (Sehgal et al. 2022, JASN: **58.9 kg CO2e/treatment** across 15 US facilities, 3-fold facility variation, range in literature 24.5–65.1 kg/session; per-patient-year 3.8 t (Connor, UK) to 4.8 t (Melbourne AJKD 2025); travel + energy + consumables dominate).

**China/India manufacturing adjustment.** Process energy (electricity + steam) drives most API cradle-to-gate emissions. Grid intensity ≈ 0.56–0.60 kg CO2/kWh (China) and ≈ 0.71 (India) vs ≈ 0.21–0.25 (EU) and ≈ 0.37 (US) (Ember Global Electricity Review, annual — verify current year). We therefore apply **×1.2–1.5 to the API portion** of European-baseline process estimates (basis 2 only). Piffoux-anchored numbers (basis 1) already reflect real globalized supply chains including Asian API production — no further adjustment. Net effect on totals is small because API is a minor share for small-mass orals.

**Everyday equivalent.** km driven in a typical US passenger car at 0.25 kg CO2e/km (EPA ~400 g CO2/mile).

**Dose assumptions are parameters, not facts** — they live in `data/carbon.yaml` (`assumed_dose`) so the demo can display and adjust them per event/card.

## Main table

| Card | Drug / therapy | Assumed dose | API g/pt-yr | Basis | Est. g CO2e / daily dose | Est. kg CO2e / patient-year | ≈ km driven / yr | Confidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Lithium carbonate | 900 mg/day PO | 329 | Analogue: Piffoux high-API-mass generic (paracetamol anchor) + Li2CO3 industrial LCA for API; ×1.2–1.5 CN/IN on API | 20–60 | 7–22 | 30–90 | Medium |
| 2 | Clozapine | 350 mg/day PO | 128 | Analogue: Parvatker class-median API (multi-step synthesis, ×1.2–1.5 CN/IN) + Piffoux per-pill overhead | 50–110 | 15–40 | 60–160 | Low–Med |
| 2 | Olanzapine | 15 mg/day PO | 5.5 | Analogue: Piffoux cheap-generic pill (packaging-dominated) | 15–30 | 5–11 | 20–45 | Medium |
| 2 | Haloperidol | 10 mg/day PO | 3.7 | Analogue: Piffoux cheap-generic pill | 15–30 | 5–11 | 20–45 | Medium |
| 3 | Paliperidone palmitate LAI | 156 mg IM/month | 1.9 | Analogue: sterile prefilled-syringe injectable via Davies IV-vs-oral ratios | 200–600 per injection (÷30 ≈ 7–20/day) | 2.4–7 | 10–30 | Low |
| 3 | Methadone (oral liquid) | 90 mg/day | 33 | Analogue: Davies oral-liquid ≈ 4× tablet; bottle + daily unit-dose packaging | 30–60 | 11–22 (drug only)¹ | 45–90¹ | Low |
| 3 | Venlafaxine ER | 150 mg/day PO | 55 | Analogue: Piffoux cheap-generic capsule | 15–35 | 5–13 | 20–50 | Medium |
| 4 | Furosemide | 40 mg/day PO | 14.6 | Analogue: Piffoux cheap-generic pill | 10–25 | 4–9 | 15–35 | Medium |
| 4 | Lisinopril | 20 mg/day PO | 7.3 | **Measured analogue**: Piffoux ramipril 10 mg = 24.7 g/pill (same class, same scale) | 15–30 | 5–11 | 20–45 | Med–High |
| 4 | Metoprolol succinate ER | 100 mg/day PO | 36.5 | Analogue: Piffoux cheap-generic ER tablet | 15–30 | 5–11 | 20–45 | Medium |
| 5 | Insulin glargine (pens; vial similar order) | ~40 U/day SC | ~0.5 (protein) | Manufacturer-disclosed pen footprints (~0.7 kg CO2e/pen; 15 kg/pt-yr at ~22 pens) scaled to 40 U/day ≈ 49 × 3 mL pens/yr; cold-chain freight adds a minor increment (home refrigeration excluded) | 40–110 | 15–40 | 60–160 | Medium |
| 6 | In-center hemodialysis (therapy, not a drug) | 3 sessions/week | n/a | **Measured LCAs**: 58.9 kg/session (US, 15 facilities); literature 24.5–65.1/session; 3.8–4.8 t/pt-yr | 57–59 kg **per session** | 3,800–4,800 | 15,000–19,000 | High |

¹ Methadone drug footprint is dwarfed by **daily OTP dispensing travel**: a 10 km round trip × ~300 trips/yr ≈ 750 kg CO2e/yr — the same travel-dominance pattern as in-center dialysis. Display this note with the row; take-home dosing (the Card 3 disaster action) is also the low-carbon option.

## Reading the table (for the UI)

- Oral small-molecule generics cluster at **5–15 kg CO2e/patient-year** — the differences between them are within estimation error; do not rank them against each other.
- The carbon story of this card set is **insulin/clozapine ≈ 2–4× a generic pill; dialysis ≈ 300–500× everything else**, driven by sessions, travel, and consumables — mirroring where the clinical acuity already is.
- Delivery model beats molecule: daily dispensing (methadone) and thrice-weekly in-center treatment (dialysis) carry travel footprints larger than any drug's manufacture. This aligns with Setoguchi & Hennessy's upstream framing (e.g., their MDI-inhaler and IV-vs-oral examples).

## Caveats

- **No product-specific LCA exists for most of these drugs.** Rows marked analogue are class-median or formulation-ratio estimates; ranges are honest but wide. Do not present per-drug precision beyond one significant figure.
- Manufacturer figures (insulin pens) have undisclosed scope; treat as indicative. Sanofi reports 100% renewable electricity in its insulin manufacturing (2024 LCA), which would lower glargine specifically.
- Hybrid-LCA anchors are French-market cradle-to-pharmacy; US distribution differs modestly.
- The ×1.2–1.5 CN/IN multiplier applies to the API portion only and is grid-intensity-based; verify current Ember figures before publication.
- Numbers will change with: renewable-energy adoption in API plants, pen recycling/reusable pens (−40%), home vs in-center dialysis (−41% to −59% per Melbourne LCA), and take-home methadone.
- **UI disclaimer (one line):** "Carbon estimates are order-of-magnitude, derived from published pharmaceutical LCAs and analogues — for awareness, never for clinical decisions."

## References

1. Piffoux M, Le Tellier A, Taillemite Z, et al. Carbon footprint of oral medicines using hybrid life cycle assessment. *J Cleaner Production* 2024. https://www.sciencedirect.com/science/article/pii/S0959652624030257
2. Parvatker AG, Tunceroglu H, Sherman JD, et al. Cradle-to-Gate Greenhouse Gas Emissions for Twenty Anesthetic Active Pharmaceutical Ingredients. *ACS Sustain Chem Eng* 2019;7:6580–91. https://pubs.acs.org/doi/10.1021/acssuschemeng.8b05473
3. Davies et al. (paracetamol formulation LCA: 38 g tablet / 151 g liquid / 310–628 g IV per 1 g dose), as summarized in *Kidney Int* eco-prescription review 2026 (https://www.sciencedirect.com/science/article/pii/S0085253826002279) and PMC12268954.
4. Sehgal AR, et al. Sources of Variation in the Carbon Footprint of Hemodialysis Treatment. *JASN* 2022 (58.9 kg CO2e/treatment). https://pubmed.ncbi.nlm.nih.gov/35654600/
5. Connor A, et al. The carbon footprints of home and in-center maintenance hemodialysis in the UK. 2011 (3.8 t CO2e/pt-yr in-center). https://pubmed.ncbi.nlm.nih.gov/21231998/
6. Barraclough KA, et al. Carbon Emissions From Different Dialysis Modalities: A Life Cycle Assessment. *AJKD* 2025 (in-center 4,814 kg/pt-yr; home HD −41%, CAPD −59%). https://www.ajkd.org/article/S0272-6386(25)00920-5/fulltext
7. Novo Nordisk carbon data via Sustainable Healthcare Coalition SusQI report (disposable pens ≈ 15 kg CO2e/pt-yr; durable ≈ 8.2 kg/yr): https://production.networks.sustainablehealthcare.org.uk/sites/default/files/2023-10/Diabetes%20-%20SusQI%20Project%20Report_0.pdf ; ISPOR Europe 2024 France OD→OW pen analysis: https://www.ispor.org/heor-resources/presentations-database/presentation/euro2024-4014/145501
8. NHS Devon sustainable diabetes care guideline (reusable pens −40% footprint): https://www.royaldevon.nhs.uk/media/wapfftc5/rd-e-diabetes-sustainable-diabetes-care-pens-and-cgm.pdf
9. Taillemite Z, et al. Carbon Footprint of Antibody-Based Drugs and Biologics Using Hybrid LCA. *Clin Pharmacol Ther* 2026 (oral treatments 14.1 kg CO2e/month mean context). https://pubmed.ncbi.nlm.nih.gov/42092334/
10. Setoguchi S, Hennessy S. Climate Change and Medications. *Pharmacoepidemiol Drug Saf* 2026 (upstream framing). https://pmc.ncbi.nlm.nih.gov/articles/PMC13427620/
11. Grid intensities: Ember Global Electricity Review (annual); US EPA typical passenger vehicle ≈ 400 g CO2/mile.
