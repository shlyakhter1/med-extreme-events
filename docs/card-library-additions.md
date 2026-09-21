# Card Library Additions — Cards 7, 8 and Card 6 Addendum

*As of 2026-09-21. Drafted to the cards 1–6 standard; same review discipline applies before transcription to YAML (M9). Clinical strings below are the verbatim source of truth.*

## Card 7 — Extreme Cold / Winter Storm × Cardiovascular & Respiratory Disease

**Triggers.** NWS (post-Oct-2024 taxonomy; provider normalizes legacy names): Extreme Cold Warning, Extreme Cold Watch, Cold Weather Advisory, Winter Storm Warning, Winter Storm Watch, Ice Storm Warning, Blizzard Warning. Temporality: watches → forecast; warnings/advisories → imminent. Participates in the cold×outage co-occurrence boost.

**Population.** Patients with cardiovascular disease (ischemic heart disease, heart failure, hypertension, prior stroke) or chronic respiratory disease (COPD, asthma); risk-amplifier flags: age ≥65, homeless or unstably housed, home-oxygen or electricity-dependent DME, prior MI/stroke, outdoor workers. Denominator anchors: CHD/COPD/asthma county rates from CDC PLACES × catchment veteran counts (existing M3 machinery); CHF ≈ 5% of VHA enrollees.

**Mechanism.** Cold exposure causes peripheral vasoconstriction, raising blood pressure and cardiac workload, and shifts hemostatic factors toward thrombosis — precipitating MI and stroke; cold, dry air triggers bronchoconstriction and worsens COPD/asthma, and winter respiratory infections compound it. Storm conditions add hypothermia risk (especially with power loss) and carbon-monoxide poisoning from improvised indoor heating (generators, grills, vehicles).

**Evidence (tiered).**
- [strong] Cold is responsible for far more temperature-attributable mortality than heat: in the 74-million-death multi-country analysis, ~7.3% of deaths were attributable to cold vs ~0.4% to heat (Gasparrini et al., Lancet 2015).
- [strong] Winter Storm Uri (Feb 2021, TX): 246 storm-related deaths in the state's final tally, the majority from hypothermia; a concurrent surge of carbon-monoxide poisonings produced over a thousand ED visits (Texas DSHS final report 2021; CDC/MMWR and Texas DSHS CO surveillance).
- [strong] Cold spells are associated with increased MI and cardiovascular mortality; risk rises as temperature falls, with effects lagged over days (cold-weather cardiovascular epidemiology; AHA guidance on cold exposure and cardiac events).
- [expert_guidance] CDC/NWS extreme-cold guidance: indoor heating safety (CO), layered clothing, limiting exertion (esp. snow shoveling for cardiac patients), checking on isolated adults.
- [caveat] Medication-specific cold interactions are weakly evidenced compared with heat; do not present drug-level cold claims beyond expert guidance (beta-blocker/peripheral-circulation notes are expert_guidance at most).

**Pre-event (care team).**
- Generate rosters: cardiovascular and respiratory panels, flagging home-oxygen/DME, homeless, and age ≥65 patients.
- Verify heating adequacy and a warm-place plan for flagged patients; coordinate with homeless PACT teams and warming centers; arrange transportation.
- Counsel against strenuous cold exertion (snow shoveling) for cardiac patients; review inhaler supply and cold-air pre-medication plans for asthma/COPD per their action plans.
- Push CO-safety messaging: never run generators, grills, or vehicles indoors or in garages; check smoke/CO detectors.
- Confirm emergency refills and oxygen backup (ties to Card 6 DME sub-panel when outages threaten).

**During event (care team).** Wellness checks on flagged patients (isolation + cold is the lethal combination); monitor for hypothermia and CO-poisoning presentations; low threshold to relocate patients in unheated homes; if outages co-occur, the boost elevates these items — treat as the compounded emergency it is.

**Patient-facing.** "Cold weather is hard on your heart and lungs. Stay warm and dry, dress in layers, and avoid heavy outdoor work like shoveling snow. Cover your nose and mouth with a scarf so you breathe warmer air. Never use a generator, grill, or your car to heat your home — the fumes can kill without warning. If your heat goes out, go somewhere warm and tell us. Keep taking your medicines."

**Escalation.** Chest pain or pressure, one-sided weakness or trouble speaking (stroke signs) → 911. Severe shortness of breath or blue lips → 911. Confusion, intense shivering or shivering that stops, slurred speech (hypothermia) → 911 and rewarm. Headache/dizziness/nausea in a heated space (possible CO) → fresh air immediately and call. No heat at home during an Extreme Cold Warning → call the care team same-day.

**Sources.** Gasparrini et al., Lancet 2015 (mortality attributable to cold vs heat, 384 locations); Texas DSHS Winter Storm Uri mortality report (2021); CDC carbon monoxide poisoning surveillance, Feb 2021 Texas; CDC extreme-cold clinical and public guidance; AHA cold-weather cardiovascular guidance; NWS SCN23-44 (cold-product taxonomy, Oct 2024).

## Card 8 — Wildfire Smoke × COPD / Asthma on Inhaled Therapies

**Triggers.** AirNow AQI ≥ 101 (USG) for the sensitive-population tier; AQI ≥ 151 escalates severity; HMS smoke density Medium/Heavy over the county (observed). Temporality: AirNow forecast → forecast; observations and HMS → observed. Window: smoke events develop over 1–3 days; forecast AQI gives the pre-event window.

**Population.** Patients with asthma (ICD-10 J45) or COPD (J44) on inhaled therapies — SABA rescue inhalers (albuterol), ICS and ICS/LABA controllers; secondary flags: cardiovascular disease, diabetes (EPA at-risk groups), outdoor workers, homeless. Denominators: PLACES county asthma/COPD rates × catchment veteran counts.

**Mechanism.** Wildfire smoke's principal hazard is fine particulate matter (PM2.5), which penetrates deep into the airways and bloodstream, triggering bronchoconstriction, airway inflammation, and exacerbations in asthma/COPD, and cardiovascular events in susceptible patients (EPA/CDC wildfire-smoke guidance).

**Evidence (tiered).**
- [strong] During the June 2023 Canadian-wildfire smoke event, New York State asthma-associated ED visits rose 81.9% statewide on the peak day (June 7), from a baseline mean of ~81 to 147 visits (CDC MMWR 72(34), 2023); CDC's national analysis found asthma ED visits 17% above expected across 19 smoke days.
- [strong] July 14–20, 2026 Canadian-wildfire smoke episode: more than 100 million people in the US under air-quality alerts from Milwaukee to Washington DC; daily-average PM2.5 near 200 µg/m³ in the Baltimore–DC area on July 17 prompting Code Purple alerts; hourly AQI above 200 across Upper Midwest/Great Lakes monitors July 16–17, co-occurring with a central-US heat dome (NBC News data desk; NASA SVS 5665; Clarity open-sensor network; CNN) — the replay-fixture event.
- [expert_guidance] EPA/CDC wildfire smoke guides: stay indoors with windows closed and AC on recirculate, HEPA/clean-room use, N95 respirators when outdoor exposure is unavoidable, pre-check rescue-inhaler supply, follow the written asthma/COPD action plan.

**Pre-event (care team).**
- Generate the asthma/COPD roster; auto-message the smoke-forecast alert with action-plan reminders.
- Verify rescue-inhaler supply (push refills for anyone low); confirm controller adherence.
- Distribute clean-air guidance: HEPA purifier or DIY box-fan filter, AC on recirculate, windows closed; N95s for unavoidable outdoor time.
- Flag outdoor workers and homeless patients for respite/clean-air-shelter coordination; reschedule outdoor appointments and pulmonary rehab.

**During event (care team).** Monitor AQI by facility ZIP; telehealth-first for respiratory complaints; low threshold for early exacerbation treatment per action plans; track ED-surge signal locally.

**Patient-facing.** "Wildfire smoke can set off your asthma or COPD even indoors. Stay inside with windows closed and the AC on recirculate; use an air purifier if you have one. Keep your rescue inhaler with you and make sure it isn't empty — call us now if you need a refill. If you must go out, an N95 mask helps; cloth masks don't. Follow your action plan, and don't wait to treat early symptoms."

**Escalation.** Using the rescue inhaler more often than your action plan allows, or it isn't helping → call same-day. Severe shortness of breath, can't speak full sentences, chest tightness not relieved by the inhaler, or blue lips → 911/ED. Any cardiac symptoms (chest pain, palpitations) during smoke days → urgent contact.

**Sources.** CDC MMWR 72(34) 2023 (NY asthma ED surge); CDC national smoke-day asthma analysis 2023; EPA "Wildfire Smoke: A Guide for Public Health Officials" and AirNow Fire & Smoke guidance; July 2026 event documentation — NBC News (rcna588051), NASA Scientific Visualization Studio #5665, Clarity.io sensor report, CNN (2026/07/17); NOAA HMS product documentation.

## Card 6 addendum — `electricity_dependent_dme` sub-panel (transcribed in M8)

**Sub-panel population.** Veterans dependent on electricity-powered durable medical equipment at home: oxygen concentrators, ventilators, CPAP/BiPAP, home-dialysis equipment, electric wheelchairs, enteral-feeding pumps. Denominator: emPOWER county/ZIP counts (measured Medicare proxy — label as such).

**Pre-event additions (care team).** Confirm backup power (battery/generator) and supplier contact for each flagged patient; register eligible patients with utility medical-baseline/priority-restoration programs; identify the nearest powered facility or shelter accepting medical equipment; for oxygen users, confirm backup cylinders and conserving devices.

**Patient-facing addition.** "If your medical equipment needs electricity, plan for an outage now: know your backup battery time, keep supplier and utility numbers handy, and know where you'd go if power stays out. If you use oxygen, ask us about backup cylinders. If your equipment stops and you can't restore power, call us or 911 — don't wait."

**Escalation addition.** Equipment on backup power with less than 4 hours remaining and no restoration estimate → call now for relocation. Oxygen interruption with breathlessness → 911.

**Sources.** HHS emPOWER Program documentation (DME categories, REST service); existing Card 6 sources (KCER/CMS) for dialysis overlap.
