# VA Extreme-Event Playbook Cards — Card Library v1

*As of 2026-09-19*

## Overview

This library holds six playbook cards for the VA extreme-event decision-support demo: each card maps one (event type × condition + medication/device class) pair to facility-level actions, sized from aggregate data only — no patient-level PHI. Cards 1–3 cover serious mental illness; cards 4–6 cover cardiometabolic and device-dependent populations.

| # | Event | Condition × med/device class | Trigger |
| --- | --- | --- | --- |
| 1 | Extreme heat | Bipolar disorder on lithium | NWS Heat Advisory/Excessive Heat Warning; HeatRisk orange+ |
| 2 | Extreme heat | Schizophrenia on antipsychotics | Same as card 1 |
| 3 | Hurricane / flood | Clozapine, LAI antipsychotics, methadone (delivery interruption) | NWS hurricane/flood watch (~48 h; act at 3–7 days) |
| 4 | Extreme heat | Heart failure on diuretics / ACE-ARB-ARNI / beta-blockers | Same as card 1 |
| 5 | Hurricane / power outage | Insulin-dependent diabetes (cold chain + supply) | Hurricane watch or forecast outage |
| 6 | Hurricane / power outage | Dialysis-dependent ESRD (missed treatments) | Hurricane watch or forecast outage |

How a facility uses a card: an event feed (NWS alerts, HeatRisk, AirNow, OpenFEMA) fires for the facility's county → the card's population query sizes the affected panel from pharmacy/registry data → pre-event and during-event actions run against that panel. Each card ends with patient-facing language and escalation triggers.

## Card 1 — Extreme Heat × Bipolar Disorder on Lithium

**Population.** Patients with bipolar disorder (or other indication) on active lithium prescriptions; flag co-prescribed ACE inhibitors/ARBs, thiazides, NSAIDs, CKD, or prior toxicity. Denominator anchor: bipolar ≈ 3.0% of VHA enrollees.

**Mechanism.** Sweating and reduced fluid/salt intake deplete volume; the kidney reabsorbs lithium with sodium, pushing a narrow-therapeutic-index drug toward toxicity. The FDA label warns of decreased heat tolerance from protracted sweating.

**Magnitude.** FDA-labeled interaction. A 2025 BJPsych Open case: serum lithium 3.4 mEq/L with AKI after fever/vomiting/diarrhea on only 400 mg/day, requiring hemodialysis. NSAIDs raise mean minimum lithium ~15% and cut renal clearance ~20%; ACE inhibitors/ARBs also elevate levels.

**Pre-event (3–7 days out).**
- Generate the lithium roster; auto-message hydration and salt-consistency guidance.
- Review co-prescribed NSAIDs/diuretics/ACE-ARBs; counsel against new NSAIDs.
- Ensure a recent lithium level for higher-risk patients; confirm emergency-refill pathway and supply.
- Prioritize cooling-center access and a check-in contact for isolated or homeless patients.

**During event.** Low-threshold level checks for anyone with vomiting, diarrhea, fever, or reduced intake; steady fluids toward 2.5–3 L/day unless contraindicated; hold NSAIDs; clinician-directed dose changes only with level guidance — no self-adjustment.

**Patient-facing.** "Heat can push your lithium to a dangerous level. Drink water steadily, keep salt intake about the same, don't start ibuprofen or naproxen, and stay cool. If you get a stomach bug or fever, call us — you may need a quick blood test."

**Escalation.** New/worsening tremor, nausea/vomiting, diarrhea, drowsiness, confusion, slurred speech, unsteadiness → urgent contact / same-day level / ED. Inability to stay hydrated during heat.

**Sources.** CDC "Heat and Medications — Guidance for Clinicians" (2024); FDA lithium prescribing information; Ali & Dogar 2025 (BJPsych Open); NSAID/ACE-ARB lithium interaction pharmacology.

## Card 2 — Extreme Heat × Schizophrenia on Antipsychotics

**Population.** Patients with schizophrenia/schizoaffective disorder (and antipsychotic-treated bipolar) on any antipsychotic. Highest-risk flags: clozapine, olanzapine, chlorpromazine, adjunctive benztropine, ≥2 concurrent antipsychotics, homeless or socially isolated. Denominator anchor: schizophrenia ≈ 3.6% of VHA enrollees.

**Mechanism.** Antipsychotics impair central thermoregulation (hypothalamic dopamine blockade) and peripheral heat dissipation (anticholinergic reduction of sweating); anticholinergic burden is additive. Anosognosia and isolation reduce protective behavior.

**Magnitude.**
- 2003 European heat wave (Nordon et al. 2009): antipsychotics aOR 2.09 (1.89–2.35); any psychotropic +30%; dose-response by drug count (aOR 1.25 per additional drug).
- Bordeaux ED study (Martin-Latry et al.): anticholinergics OR 6.0 (1.8–19.6); antipsychotics OR 4.6 (1.9–11.2); anxiolytics OR 2.4 (1.3–4.4).
- 2021 BC heat dome (Chen et al. 2025): any antipsychotic OR 2.43 (1.52–4.01), driven by haloperidol/clozapine/zuclopenthixol; ≥2 antipsychotics OR 4.05 (2.41–6.98); people with schizophrenia ≈ 8% of deaths at ≈ 1% population prevalence.
- Shannon et al. 2025 (JAMA Netw Open, CA veterans): heat-mortality odds up 10–18%, larger among homeless veterans (up to 36% at the 97.5th percentile; interaction not statistically significant).

**Pre-event (3–7 days out).**
- Roster ranked by anticholinergic burden and polypharmacy; prioritize clozapine, multi-antipsychotic, and homeless/isolated patients.
- Arrange cooling-center placement, transportation, and daily check-ins for the highest-risk.
- Counsel hydration and light clothing. Instruct patients and staff NOT to stop antipsychotics — manage with cooling, not discontinuation.

**During event.** Active wellness checks on flagged patients; ensure cooling access; monitor for heat illness; coordinate with homeless PACT teams and shelters; low threshold for bringing high-risk patients into cooled clinical space.

**Patient-facing.** "Your medicine is important — keep taking it. But it can make it harder for your body to cool itself, so you may not feel how hot you are. Stay in air conditioning, drink water, and let us or a friend check on you daily during the heat."

**Escalation.** Hot/dry skin, no sweating, temperature ≥103°F, confusion, agitation, fainting, rapid pulse → heat-stroke emergency (911/ED). Any decompensation from missed cooling.

**Sources.** Nordon et al. 2009 (Am J Geriatr Psychiatry); Martin-Latry et al. (European Psychiatry); Chen et al. 2025 (Scientific Reports) and BCCDC/BCMJ report; CDC Heat and Medications guidance; Shannon et al. 2025 (JAMA Network Open).

## Card 3 — Hurricane/Flood × Delivery Interruption: Clozapine, LAIs, Methadone

**Population.** Three sub-panels: (a) clozapine patients (≈ 4% of VHA schizophrenia patients, as low as ≈ 1.3% in younger cohorts — small, highest acuity; identifiable via the VA National Clozapine Coordinating Center); (b) LAI antipsychotic patients with injections due in the event window; (c) OUD patients on methadone (daily OTP dispensing) or buprenorphine. Also flag short-half-life antidepressants (venlafaxine, paroxetine) and benzodiazepines.

**Mechanism.** Disasters close pharmacies, clinics, labs, and transport. Abrupt clozapine loss → cholinergic rebound, rebound psychosis within 24–48 h, catatonia, rarely seizure. Missed LAI → relapse as plasma levels fall. Missed methadone → withdrawal within a day. Short-half-life antidepressant/benzodiazepine gaps → discontinuation syndrome or withdrawal seizures.

**Magnitude.** LAI buffer after discontinuation: 50% relapse-free at ~2 mo (oral), ~6 mo (PP1M), ~13 mo (PP3M) (Morris et al.). Post-Katrina/Sandy OTP dose-verification failures and unsafe ED dosing documented. Puerto Rico post-Maria: most pharmacies closed; 84% of hospitals without generator power on day 6 (CDC MMWR). Caveat: no peer-reviewed report directly ties a named clozapine patient's relapse to Katrina/Maria access loss — the pathway is inferred from infrastructure collapse plus withdrawal-syndrome case reports.

**Regulatory currency.** FDA eliminated the clozapine REMS on June 13, 2025 — ANC lab access is no longer a legal barrier to dispensing. Priority shifts to drug-supply continuity plus clinically appropriate ANC monitoring per labeling.

**Pre-event (3–7 days out).**
- Activate the VA Pharmacy Disaster Relief Plan; push emergency refills (10-day supply at in-network retail for maintenance meds; controlled substances via VA) by phone/mail/My HealtheVet.
- Clozapine: ensure on-hand supply; dispense without gating on a current ANC (post-2025) while continuing monitoring.
- LAIs due soon: early re-injection or pre-event conversion.
- Coordinate with OTPs on pre-dispensed methadone take-homes and guest dosing per SAMHSA guidance.
- Front-load short-half-life antidepressants and benzodiazepines.

**During event.** Track flagged patients via the Clinical Contact Center; enable guest dosing and alternate-pharmacy fills; clozapine gaps >48 h → plan re-titration from 12.5 mg (ANC restart per labeling after ≥30-day gaps); substitute oral antipsychotic if an LAI cannot be given; treat withdrawal symptomatically.

**Patient-facing.** "Before the storm, get an emergency refill — some psychiatric medicines and methadone are dangerous to stop suddenly. If you can't reach your clinic or pharmacy, call the VA 24/7 line. On methadone? Ask your program about take-home doses now."

**Escalation.** Clozapine: return of hallucinations/paranoia, agitation, severe nausea/vomiting/sweating, fever, new confusion. Methadone: withdrawal signs. Antidepressant/benzodiazepine: severe dizziness, "brain zaps," or seizure. Any → urgent VA contact / ED.

**Sources.** FDA clozapine REMS elimination (June 13, 2025); clozapine withdrawal-syndrome case literature; Morris et al. (paliperidone relapse timing); SAMHSA OTP disaster take-home/guest-dosing guidance; post-Katrina/Sandy OTP studies; CDC MMWR Puerto Rico data; VA Pharmacy Disaster Relief Plan.

## Card 4 — Extreme Heat × Heart Failure on Diuretics / ACE-ARB-ARNI / Beta-blockers

**Population.** HF patients on ≥1 heat-sensitizing cardiovascular class: loop/thiazide diuretics, ACE inhibitors, ARBs, ARNIs, beta-blockers. Highest risk: ACE/ARB + diuretic combinations; prior AKI or hyponatremia. Denominator anchor: HF ≈ 5% of veterans in VA care (~510,000 VHA HF patients 2016–2020); ACE/ARB/ARNI and beta-blocker prescribing each ~60–64% in VA HFrEF cohorts.

**Mechanism.** Heat causes dehydration, vasodilation, and neurohormonal activation; diuretics deplete volume and blunt thirst, ACE/ARBs reduce thirst and blood pressure, beta-blockers reduce cutaneous vasodilation and sweating — together impairing heat dissipation and precipitating hypotension, electrolyte derangement, AKI, and HF decompensation (CDC guidance).

**Magnitude.** Layton et al. 2020 (Medicare ≥65): heatwaves raised heat-related hospitalization 21% (95% CI 7–38%) to 33% (95% CI 14–55%) across heat-sensitizing classes; loop diuretics specifically implicated in HF, dementia, and MI patients; effects additive, not synergistic. CDC: ACE/ARB + diuretic "may significantly increase risk of harm from heat exposure." Extreme heat above the 97th–99th temperature percentiles is linked to roughly a 10–15% rise in HF-related deaths.

**Pre-event (3–7 days out).**
- Run the HF + heat-sensitizing-drug query; flag ACE/ARB + diuretic combos and prior AKI/hyponatremia.
- Pharmacist/clinician review of a "hot-day" plan: pre-specified parameters for temporary diuretic adjustment and fluid intake — never abrupt discontinuation without a plan.
- Confirm daily weights, BP checks, and a named check-in contact.
- Verify home cooling and that no medications sit in hot locations (cars, above the fridge).

**During event.** Outreach calls/telehealth to the highest-risk cohort on HeatRisk orange/red/magenta days; reinforce the hot-day plan; watch orthostatic symptoms, weight change, urine output; expedite electrolyte/renal checks.

**Patient-facing.** "Hot weather plus your heart and blood-pressure medicines can make you dehydrated, dizzy, or hurt your kidneys. Stay cool. Follow the fluid plan we gave you — don't guess. Weigh yourself daily. Don't stop any medicine on your own. If you feel dizzy, very weak, confused, urinate much less, or gain weight fast, call us."

**Escalation.** Weight gain >2–3 lb/day or >5 lb/week; worsening dyspnea or swelling; BP drop with dizziness/fainting; reduced urine output or confusion; heat-exhaustion symptoms. Syncope, chest pain, or altered mental status → emergency.

**Sources.** CDC "Heat and Medications — Guidance for Clinicians"; Layton et al., PLOS One 2020; Setoguchi & Hennessy, Pharmacoepidemiol Drug Saf 2026; VA CHF prevalence (JAMA Network Open VA cohort).

## Card 5 — Hurricane/Power Outage × Insulin-Dependent Diabetes

**Population.** Diabetes patients on insulin (and other refrigeration- or supply-sensitive injectables, e.g., GLP-1 agonists), especially pump users and those on mail-order/refrigerated supply. Denominator anchor: diabetes ≈ 25% of VA patients — the largest at-risk pool in the library.

**Mechanism.** Insulin degrades with heat and freezing ("unopened insulin loses potency within months at 37°C"); outages break the cold chain while the disaster simultaneously interrupts pharmacy access, mail delivery, routine care, and diet — compounding loss of glycemic control.

**Magnitude.** FDA emergency thresholds: insulin in vials/cartridges may stay unrefrigerated at 59–86°F for up to 28 days; discard pump-reservoir insulin after 48 h or if exposed above 98.6°F; never use frozen insulin. Post-Katrina cohort (Fonseca et al., Diabetes Care 2009; n=1,795 across private, state, and VA systems): marked HbA1c deterioration concentrated in the safety-net system (7.7% → 8.3%, p<0.001), with less change among VA patients — continuity of supply buffers the harm.

**Pre-event (3–7 days out).**
- Query the insulin registry; push emergency refills toward a 7–14-day cushion before the storm/outage window.
- Confirm a cool-storage plan per patient: insulated cooler + ice packs (no direct contact/freezing), thermometer, the FDA 28-day/59–86°F rule.
- Pump users: explicit backup basal via pen/syringe plus the 48-hour reservoir rule.
- Provide glucometer + strips (not power-dependent), sick-day carbohydrate/hydration guidance, and FDA switching-in-emergency guidance.

**During event.** Keep insulin as cool as possible without freezing; when power returns, discard vials kept in extreme conditions and replace once properly stored insulin is available; monitor glucose more often; use alternative insulin only with FDA switching guidance and clinician contact where possible.

**Patient-facing.** "Your insulin can be ruined by heat or freezing. In an outage, keep it in a cooler with ice packs — but don't let it touch the ice. Most insulin is still OK at room temperature (up to 86°F) for 28 days. Never use insulin that was frozen or looks clumpy, cloudy when it should be clear, or discolored. If your pump stops, use your backup pen. Check your sugar often and don't skip insulin unless told to."

**Escalation.** Glucose persistently >300 mg/dL despite dosing; DKA symptoms (nausea/vomiting, deep rapid breathing, fruity breath, confusion, abdominal pain); severe hypoglycemia; no usable insulin and no pharmacy access. DKA or severe hypoglycemia → emergency.

**Sources.** FDA "Information Regarding Insulin Storage and Switching Between Products in an Emergency"; Fonseca et al., Diabetes Care 2009; Setoguchi & Hennessy 2026; VA diabetes prevalence (VA Office of Health Equity; Liu et al., Prev Chronic Dis); CDC/ADA diabetes disaster preparedness.

## Card 6 — Hurricane/Power Outage × Dialysis-Dependent ESRD

**Population.** ESRD patients on maintenance dialysis — in-center hemodialysis (VA-operated and VA-financed community units) and home dialysis (electricity/water-dependent). Denominator anchor: >52,000 veterans on dialysis; ~13,000 new kidney-failure cases/year; VA historically finances ~60% of these veterans' dialysis, mostly in community units. Cross-reference HHS emPOWER ZIP-level electricity-dependent counts.

**Mechanism.** Disasters cut transportation, power, and water, forcing missed sessions → fluid overload, hyperkalemia, and uremia that can be fatal.

**Magnitude.** Post-Katrina: ~44% of New Orleans HD patients missed ≥1 session, ~17% missed ≥3; missing ≥3 sessions carried adjusted OR 2.16 (95% CI 1.05–4.43) for hospitalization (Anderson et al., Kidney Int 2009). Post-Sandy (13,264 ESRD patients): ED visits, hospitalizations, and 30-day mortality all elevated; early dialysis before landfall was associated with lower adjusted odds of ED visits (OR 0.80), hospitalization (OR 0.79), and 30-day mortality (OR ~0.72) (Kelman/Lurie et al., AJKD 2015). VA precedent: essentially all Manhattan VA ESRD patients missed ≥1 treatment during Sandy; hemodialysis was re-established at Brooklyn VAMC once transport resumed.

**Pre-event (3–7 days out).**
- Pre-schedule early dialysis for all patients before projected landfall/outage — the single most evidence-backed intervention.
- Verify each patient's transportation plan and a backup/partner facility; confirm generator/water status and KCER/ESRD-network facility-status reporting.
- Distribute the CMS/KCER 3-day emergency renal diet (~2 cups fluid/day, strict potassium limits) and an emergency kit (med list + ≥3-day supply, dry weight, dialysis prescription, contacts).
- Home dialysis: confirm backup power/water and manual PD capability; flag to emPOWER/utility priority-restoration lists.

**During event.** Activate the KCER hotline / ESRD-network coordination; track against a missed-session list; arrange emergency dialysis or transfer (Brooklyn VAMC model); triage hyperkalemia/fluid overload; start the 3-day emergency diet immediately in a widespread disaster.

**Patient-facing.** "Missing dialysis in a disaster can be life-threatening. If a storm or outage is coming, get your dialysis EARLY — before it hits. Know a second center and how you'll get there. If you can't get treatment, start the 3-day emergency diet right away: about 2 cups of fluid a day and no high-potassium foods (bananas, oranges, potatoes, salt substitutes). Keep a 3-day supply of your medicines and your dialysis info with you. Call the KCER hotline (1-866-901-3773) or your center."

**Escalation.** Missed ≥1 scheduled session with no rescheduled slot; fluid overload (severe shortness of breath, can't lie flat, rapid weight gain/swelling); hyperkalemia (muscle weakness, palpitations, chest pain); confusion. Breathing difficulty, chest pain, or suspected hyperkalemia → emergency.

**Sources.** Anderson et al., Kidney International 2009; Kelman/Lurie et al., AJKD 2015; VA Sandy dialysis access study; CMS/KCER 3-Day Emergency Diet and facility preparedness; HHS emPOWER; VA Office of Health Equity ESRD data (2022).

## Cross-Cutting Caveats & Evidence Tiers

**Evidence tiers.** Strong (replicated epidemiology or regulatory labeling): antipsychotic-heat mortality, lithium-heat toxicity, dialysis missed-treatment outcomes, FDA insulin thresholds, Layton heat-hospitalization estimates. Mechanistically sound but inferential: the disaster-clozapine relapse pathway (no peer-reviewed case directly documents it). Weak/folklore — do not use: precise "levels rise X% per degree" claims, insulin shelf-life numbers beyond FDA figures, blog-sourced thresholds.

**Do not double-count.** Relative risks are not additive across cards; a homeless veteran on clozapine during a heat wave sits at the intersection of Cards 2, 3, and heat generally and warrants individualized priority. Cards are triage aids, not a substitute for clinical judgment.

**"Don't stop the medication" is a headline message** across antipsychotics, clozapine, lithium, methadone, and short-half-life antidepressants/benzodiazepines — abrupt discontinuation is often the larger acute danger than the event itself.

**Additive, not synergistic.** Layton 2020 found drug and heatwave effects largely additive; avoid quoting a multiplicative OR for any single drug.

**Currency checks before any real deployment.**
- Clozapine content reflects the post-June-2025 REMS-eliminated regime — re-verify.
- The CDC heat-and-medications page was archived in early 2025; citations reflect the June 2024 version — re-verify against the live page.
- Denominators are planning estimates (CDC PLACES model-based rates × VA enrollee counts, or literature multipliers), not counts.
- Subgroup findings in Shannon et al. 2025 (homelessness amplification) were not statistically significant, though effect sizes were large.

## Wave 2 Candidates & Sources

**Wave 2 cards (deferred, not weak).**
- Wildfire smoke × COPD/asthma on inhaled therapies: NY asthma ED visits rose 81.9% statewide on June 7, 2023 during Canadian smoke (CDC MMWR); deferred because levers (rescue inhalers, N95s, clean rooms, AQI messaging) overlap routine care.
- Consolidated electricity-dependent DME card (home oxygen, CPAP, home dialysis): HHS emPOWER counts >3 million Medicare beneficiaries with electricity-dependent DME claims at ZIP level; fold in with Card 6's power logic to avoid duplication.

**Key sources.**

| Source | Anchors |
| --- | --- |
| [CDC Heat and Medications — Guidance for Clinicians](https://restoredcdc.org/www.cdc.gov/heat-health/hcp/clinical-guidance/heat-and-medications-guidance-for-clinicians.html) | Cards 1, 2, 4 mechanisms (June 2024 version; archived) |
| Nordon et al. 2009, Am J Geriatr Psychiatry | 2003 heat wave psychotropic ORs |
| Martin-Latry et al., [European Psychiatry](https://www.sciencedirect.com/science/article/abs/pii/S0924933807013089) | Bordeaux ED anticholinergic/antipsychotic ORs |
| Chen et al. 2025, Scientific Reports | 2021 BC heat dome antipsychotic ORs |
| Shannon et al. 2025, JAMA Network Open (2545524) | CA veteran heat mortality; homelessness amplification |
| FDA clozapine REMS elimination (June 13, 2025) | Card 3 regulatory currency |
| [SAMHSA OTP disaster guidance](https://www.pew.org/en/research-and-analysis/articles/2025/02/25/how-states-can-ensure-addiction-treatment-access-during-natural-disasters) | Methadone take-homes, guest dosing |
| [Layton et al. 2020, PLOS One](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7728169/) | Heat × medication hospitalization 21–33% |
| [Fonseca et al. 2009, Diabetes Care](https://pubmed.ncbi.nlm.nih.gov/19542210/) | Post-Katrina HbA1c deterioration |
| [FDA insulin emergency storage/switching](https://www.fda.gov/drugs/emergency-preparedness-drugs/information-regarding-insulin-storage-and-switching-between-products-emergency) | 28-day / 59–86°F / 48-h pump thresholds |
| Anderson et al. 2009, Kidney Int | Katrina missed-dialysis OR 2.16 |
| [Kelman/Lurie et al. 2015, AJKD](https://www.sciencedirect.com/science/article/abs/pii/S0272638614010592) | Sandy early-dialysis protective ORs |
| [VA Pharmacy Disaster Relief Plan](https://www.va.gov/fayetteville-coastal-health-care/programs/pharmacy-disaster-relief-plan/) | Emergency 10-day retail refills |
| Setoguchi & Hennessy 2026, [Pharmacoepidemiol Drug Saf (PMC13427620)](https://pmc.ncbi.nlm.nih.gov/articles/PMC13427620/) | Framework: climate–medication commentary |
| [HHS emPOWER](https://empowerprogram.hhs.gov/about.html) | Electricity-dependent DME counts by ZIP |
| [CDC MMWR 72(34)](https://www.cdc.gov/mmwr/volumes/72/wr/mm7234a5.htm) | 2023 smoke asthma ED surge |
