# Playbook Card Library — Cards 1–8

*As of 2026-09-23. The source of truth for all card content. `cards/*.yaml` is
transcribed from this document; patient-facing sentences are verbatim and enforced by test.
Every quantitative claim carries an evidence tier (strong | inferential | expert_guidance)
and cites a source id from [`medical-references.md`](medical-references.md). Sentences marked
**[SHARED]** appear verbatim on every card listed in
[`medical-references.md`](medical-references.md) §3 and are test-enforced. No card ever
advises stopping or changing a medication.*

*Transcription rule: **[SHARED]** and the bracketed `[tier | source ids]` claim markers are
library markup, not card text. They are stripped when a sentence is copied into YAML (the
marker and the single space after it are removed), and markdown emphasis (`*lose*`) is
transcribed as plain text. No YAML string or rendered page ever contains "[SHARED]".*


## Status: pending clinician sign-off

This revision is an **AI-drafted evidence review** (Claude, 2026-09-23): claims were checked
against the literature and wording was proposed, but no clinician has approved it yet. The
cards are live in the demo with this text. A clinician should review this file end to end,
plus [`medical-references.md`](medical-references.md) §1 (source status), §3 (shared
sentences), §4 (contested findings) and §5 (verification queue), and decide the open
questions below. Each card is easiest to read as rendered at `/card-library/<card-id>`.

**Open questions for clinician sign-off**

1. **Card 6 mechanism.** This library gives Card 6 no mechanism paragraph, and the card
   format requires one. The YAML keeps the previous version's sentence: "Disasters cut
   transportation, power, and water, forcing missed sessions → fluid overload,
   hyperkalemia, and uremia that can be fatal." Approve it, or supply a replacement.
2. **Card 4 panel figures.** Card 4's panel is narrowed by a VA HFrEF ACE/ARB/ARNI share of
   0.62 (reported range ~60–64%), and the demo checks totals against ~510,000 VHA
   heart-failure patients (2016–2020). Both come from the previous library and are not
   restated here. Confirm them with a source, or say what to use instead.
3. **Card-level evidence tiers.** Tiers are assigned per claim; each card's overall tier was
   left as before. Card 3 is still `inferential` although most of its claims are now
   `strong` (the clozapine-withdrawal mechanism remains `inferential`). Confirm or reassign
   the overall tier for each card.
4. **Caregiver text.** No card has caregiver-addressed wording; caregivers currently see the
   patient text. Decide whether caregiver versions are needed, and supply them if so.
5. **Pending sources.** Ten sources are marked `pending` in medical-references §1:
   nsaid-class-labeling, fda-lithium-label, shannon-2025, shiovitz-1996,
   hf-daily-weight-education, ada-sick-day, cdc-co-guidance, aha-snow-shoveling,
   epa-wildfire-smoke-guide and respiratory-action-plans. So are the four VA prevalence
   anchors (va-chf/diabetes/smi/esrd-prevalence) used for panel sizing. Two more are partly
   verified: chen-2025 (polypharmacy OR) and weiden-2017 (primary DOI). No figure rests on a
   pending source alone. Verify them in the §5 order, or approve launching while they are
   pending.
6. **Coastal-flood and wind triggers (added 2026-09-25).** Card 3 now also fires on Coastal
   Flood Watch/Warning and Flash Flood Watch; Cards 5 and 6 fire on High Wind Watch/Warning
   and Extreme Wind Warning as a forecast of power loss. No card text changed. The pre-event
   actions and patient text were written for hurricanes ("if a storm or outage is coming");
   confirm they fit a nor'easter or wind event, or supply wind-specific wording.

---

## Card 1 — Extreme Heat × Bipolar Disorder on Lithium

**Triggers.** NWS: Extreme Heat Warning, Excessive Heat Warning (legacy), Heat Advisory,
Extreme Heat Watch. Lead window: 2–5 days (forecast/watch), 0–2 days (warning/advisory).

**Population.** Patients with bipolar disorder on lithium therapy. Risk amplifiers: age ≥65,
concurrent diuretic, ACE inhibitor, ARB, or NSAID; unstable housing; no air conditioning.
Panel sizing uses the VA bipolar planning estimate (~3.0% of enrollees — planning anchor,
not clinical text).

**Mechanism.** [strong | finley-1995] The kidney handles lithium like sodium: dehydration
and sodium loss increase lithium reabsorption, so heat-driven volume loss pushes levels
toward toxicity. Lithium has a narrow therapeutic window; relatively minor concentration
increases can cause serious adverse effects. [expert_guidance | fda-lithium-label —
pending verification] Labeling warns of decreased tolerance during protracted sweating.

**Drug interactions.** [strong | finley-1995, nsaid-class-labeling] NSAIDs raise lithium
levels (labeling studies: roughly 15% higher minimum levels and 20% lower clearance;
individual reports higher) and ACE inhibitors/ARBs impair lithium elimination, with effects
that can emerge over weeks. Thiazide diuretics reduce lithium clearance.

**Pre-event (care team).**
- Generate the lithium roster; flag co-prescriptions (NSAID, ACE-I/ARB, thiazide), age ≥65,
  housing instability, no-AC status.
- Prescriber reviews interacting medications; plan level checks for the highest-risk
  patients during the event window.
- Confirm cooling access (home AC, cooling-center map, transportation); outreach to flagged
  patients before day 1 of the event.
- Confirm refills; patients should not run short during the event.

**During event (care team).** Low-threshold lithium level and renal panel for anyone with
vomiting, diarrhea, fever, reduced intake, or new neurological symptoms (tremor, unsteady
gait, confusion, slurred speech). Dose changes only by a clinician, guided by a level.
**After the event:** repeat the level within about a week for patients who were symptomatic
or who take ACE inhibitors, ARBs, or thiazides.

**Patient-facing.** "Heat can push your lithium to a dangerous level. Drink regularly
through the day so you don't get thirsty or dizzy, and keep your salt intake about the same
as usual. [SHARED] If a doctor has given you a fluid limit — for your heart or your kidneys —
keep to that limit and call us so we can make a heat plan that is safe for you. Don't start
ibuprofen or naproxen — ask us what to use for pain instead. Stay in the coolest place you
can. If you get a stomach bug, a fever, bad shakiness, or feel confused, call us — you may
need a quick blood test. Don't stop or change your lithium on your own."

**Escalation.** Coarse tremor, repeated vomiting or diarrhea, unsteady walking, slurred
speech, or confusion → same-day level and clinical review; severe symptoms → 911. No
cooling available at home during a warning → same-day cooling-center placement.

**Caveats.** The lithium label's 2,500–3,000 mL/day fluid figure describes the initial
stabilization period; it is not quoted to patients and never overrides a prescribed fluid
restriction (see medical-references.md §3.1).

**Sources.** finley-1995; nsaid-class-labeling; fda-lithium-label; cdc-heat-medications-2024.

---

## Card 2 — Extreme Heat × Schizophrenia on Antipsychotics

**Triggers.** Same as Card 1.

**Population.** Patients with schizophrenia or schizoaffective disorder on antipsychotics;
heightened flags for anticholinergic co-prescriptions (e.g., benztropine), clozapine,
antipsychotic polypharmacy, age ≥65, unstable housing, no AC. Panel sizing uses the VA
schizophrenia planning estimate (~3.6% — planning anchor).

**Mechanism.** [inferential | heat-thermoregulation-meta-2024, cdc-heat-medications-2024]
Antipsychotics — especially those with anticholinergic effects — are thought to impair heat
regulation and sweating; direct human physiological evidence is limited, but the
association with heat-related hospitalization and death is consistent. Illness factors
(symptoms, isolation, reduced risk perception) independently reduce protective behavior.

**Magnitude.** [strong | nordon-2009] In the 2003 French heatwave, antipsychotic use in
older people was associated with heat-related death: adjusted OR 2.09 (95% CI 1.89–2.35),
with a dose-response trend of 1.25 per additional psychotropic. [strong | martin-latry-2007]
In Bordeaux (August 2003; 56 admissions, mean age 83), heat-related hospitalization was
associated with anticholinergics (OR 6.0, 1.8–19.6), antipsychotics (OR 4.6, 1.9–11.2), and
anxiolytics (OR 2.4, 1.3–4.4). [strong | chen-2025, bccdc-bcmj-2023] In the 2021 BC heat
dome, any antipsychotic dispensation was associated with extreme-heat-event mortality among
people with schizophrenia (OR 2.43, 1.52–4.01); people with schizophrenia were ~8% of
heat-dome deaths against ~1% population prevalence. [inferential | chen-2025 — polypharmacy
figure pending full-text verification] Multiple concurrent antipsychotics carried higher
risk.

**Pre-event (care team).**
- Generate the antipsychotic roster; flag anticholinergic burden, clozapine, polypharmacy,
  age ≥65, housing instability, no-AC.
- Proactive outreach with heat-plan check: cooling access, water, buddy contact; coordinate
  homeless-program (HPACT) outreach for unstably housed patients.
- Do not reduce or hold antipsychotics for heat; prescriber reviews anticholinergic
  co-medications where clinically appropriate. [expert_guidance | bccdc-bcmj-2023]

**During event (care team).** Wellness checks on flagged patients; treat any fever or
altered mental status as an emergency evaluation, not phone triage. Fever in a clozapine
patient requires clinician review (clozapine has independent fever causes, including
early-treatment myocarditis).

**Patient-facing.** "Your medicine helps you stay well — keep taking it, even in a heat
wave. But heat is harder on your body with these medicines. Stay in the coolest place you
can, drink water regularly, and check in with someone every day when it's very hot. If you
feel very hot, confused, dizzy, or stop sweating, that's an emergency — call 911. Your skin
being hot and red, with a pounding heartbeat, is an emergency even if you are still
sweating."

**Escalation.** Temperature ≥103°F, hot red skin (dry or damp), confusion, or collapse →
911. Heat stroke, neuroleptic malignant syndrome, and anticholinergic toxicity can look
alike (high temperature, confusion, rigidity, fast pulse); all are emergencies — call 911
and tell responders which medicines the patient takes. No cooling available → same-day
cooling placement.

**Caveats.** The physiological mechanism is contested (medical-references.md §4); the card
rests on the epidemiology. Never present antipsychotics as a reason to pause treatment in
heat.

**Sources.** nordon-2009; martin-latry-2007; chen-2025; bccdc-bcmj-2023;
heat-thermoregulation-meta-2024; cdc-heat-medications-2024.

---

## Card 3 — Hurricane / Flood × Delivery Interruption: Clozapine, LAIs, Methadone

**Triggers.** NWS: Hurricane Watch/Warning, Tropical Storm Watch/Warning, Storm Surge
Watch/Warning, Flood Watch/Warning, Flash Flood Watch/Warning, Coastal Flood Watch/Warning
(nor'easters and other non-tropical coastal storms); observed power outage ≥25% of county
customers (sustained). Advisory-level products (Coastal Flood Advisory, Flood Advisory) do
not trigger. Lead window: 3–7 days (watch), 1–3 days (warning).

**Population.** Patients on medications whose supply chain or dosing site can be
interrupted: clozapine; long-acting injectable antipsychotics (LAIs); methadone via opioid
treatment programs (OTPs); buprenorphine. Clozapine planning anchor: ~4% of VHA
schizophrenia patients.

**Mechanism / stakes.** [inferential | shiovitz-1996 — timing pending verification] Abrupt
clozapine discontinuation risks cholinergic rebound and rapid-onset rebound psychosis;
withdrawal catatonia is reported. [strong | weiden-2017] After stopping paliperidone, 50% of
patients remained relapse-free for roughly 2 months (oral), 6 months (1-month LAI), and 13
months (3-month LAI) — LAIs buy time, but interruption clocks differ by product. Missed
methadone dosing risks withdrawal and return to illicit use.

**Magnitude.** [strong | maxwell-2009] After Katrina, Texas programs recorded 567
hurricane-related treatment admissions of evacuees. [strong | mcclure-2014] After Sandy,
more than 75% of patients at 112 NYC substance-use treatment programs had treatment
interruptions. [strong | griffin-2018] VA precedent: the Manhattan VAMC OTP closed for 5
months; emergency guest dosing was arranged for about 100 veterans.

**Pre-event (care team).**
- Clozapine roster: confirm supply through the event window +7 days; emergency fills per the
  VA Pharmacy Disaster Relief Plan at any VA pharmacy.
- LAI roster: patients due during the event window get their injection early where the label
  allows, or a documented bridge plan; follow each product's missed-dose/re-initiation
  table.
- OTP: review each patient's take-home eligibility under 42 CFR Part 8 (2024) and dispense
  the maximum clinically appropriate supply before landfall; arrange guest-dosing agreements;
  confirm naloxone on hand and safe-storage counseling. [strong | samhsa-42cfr8-2024]
- Buprenorphine patients: confirm prescription fills (retail pharmacies make it a more
  resilient bridge for eligible patients).

**During event (care team).** Track pharmacy/OTP operational status; activate guest dosing;
clozapine interruptions ≥2 days: do not resume the prior dose — restart at 12.5 mg once or
twice daily and re-titrate per labeling; off 30+ days: ANC monitoring as a new patient.
[strong | clozapine-pi, fda-clozapine-rems-2025] Dispensing no longer requires ANC reporting
(REMS removed June 13, 2025); prescribers continue ANC monitoring per labeling.

**Patient-facing.** "Before the storm, make sure you have enough of your medicine — some
psychiatric medicines and methadone are dangerous to stop suddenly. If you take clozapine
and miss it for 2 days or more, don't restart your usual dose — call us first; restarting
has to be done gradually. If you get a long-acting injection, ask us now whether you should
get it early. On methadone? Ask your program today about take-home doses, and keep naloxone
with you. If you can't reach your clinic or pharmacy, any VA pharmacy can help with an
emergency fill — or call the VA 24/7 line."

**Escalation.** Clozapine missed ≥2 days → prescriber contact before any restart. LAI
overdue past its product window → same-week injection or oral bridge. Missed methadone
dosing day → same-day guest-dosing referral; withdrawal symptoms → urgent contact.

**Caveats.** The relapse-timing figures describe discontinuation cohorts, not missed-dose
windows; product labels govern late-dose handling. Take-home limits are clinical-judgment
ceilings (7 doses days 1–14; 14 from day 15; 28 from day 31), not entitlements.

**Sources.** fda-clozapine-rems-2025; clozapine-pi; shiovitz-1996; weiden-2017;
maxwell-2009; mcclure-2014; griffin-2018; samhsa-42cfr8-2024;
va-pharmacy-disaster-relief-plan.

---

## Card 4 — Extreme Heat × Heart Failure on Diuretics / ACE-ARB-ARNI / Beta-blockers

**Triggers.** Same as Card 1.

**Population.** Patients with heart failure on loop or thiazide diuretics, ACE
inhibitors/ARBs/ARNI, or beta-blockers. Risk amplifiers: age ≥65, CKD, unstable housing, no
AC. Panel sizing uses the VA CHF planning estimate (~5% — planning anchor).

**Mechanism.** [strong | cdc-heat-medications-2024] Diuretics deplete volume and
electrolytes in heat; ACE inhibitors and ARBs can blunt thirst; beta-blockers limit the
cardiac-output response to heat stress — CDC guidance flags the ACE/ARB + diuretic
combination as one that may significantly increase heat risk.

**Magnitude.** [strong | layton-2020] Among older Medicare beneficiaries with chronic
conditions, common cardiovascular medications were associated with 21% (7–38%) to 33%
(14–55%) increases in heat-related hospitalization during heatwaves; drug and heatwave
effects were largely additive. [strong | alahmad-2023] In a 27-country study, heat above the
99th temperature percentile was associated with higher heart-failure mortality than the
minimum-mortality temperature, and hot days above the 97.5th percentile accounted for about
2.6 excess deaths per 1,000 heart-failure deaths — the highest excess-death proportion among
cardiovascular causes. [inferential | shannon-2025 — figures pending verification] Among
California veterans with cardiometabolic disease, social factors (notably homelessness)
amplified extreme-heat mortality risk.

**Pre-event (care team).**
- Generate the HF roster with medication classes; flag ACE/ARB + diuretic combinations,
  CKD, age ≥65, housing instability, no-AC.
- Where the HF clinician judges it appropriate, pre-specify an individualized hot-day plan
  (weights, symptoms, when to call about diuretic dosing). There is no guideline rule for
  reducing diuretics in heat; adjustments are clinician-directed only.
- Confirm daily-weight capability (scale at home) and cooling access.

**During event (care team).** Daily-weight and symptom telemonitoring for the flagged
panel; same-day electrolyte/renal checks for dizziness, cramps, palpitations, or oliguria;
clinician-directed diuretic adjustments only.

**Patient-facing.** "Hot days are hard on your heart. Weigh yourself every morning. Call us
if you gain more than 2–3 pounds in a day or 5 pounds in a week — and also if you *lose*
more than 2–3 pounds in a day or feel dizzy, because in the heat that can mean dehydration.
[SHARED] If a doctor has given you a fluid limit — for your heart or your kidneys — keep to
that limit and call us so we can make a heat plan that is safe for you. Stay in the coolest
place you can, and keep taking your medicines as prescribed — call us before changing
anything."

**Escalation.** Weight gain >2–3 lb/day or >5 lb/week, or weight loss >2–3 lb/day with
dizziness or low urine output → same-day call. Chest pain, severe breathlessness, syncope →
911. No cooling at home during a warning → same-day cooling placement.

**Caveats.** Daily-weight thresholds follow standard HF patient education
(hf-daily-weight-education, URL pending). The fluid-limit sentence is shared verbatim with
Cards 1 and 6.

**Sources.** alahmad-2023; layton-2020; cdc-heat-medications-2024;
hf-daily-weight-education; shannon-2025.

---

## Card 5 — Hurricane / Power Outage × Insulin-Dependent Diabetes

**Triggers.** Hurricane/tropical products as Card 3; NWS High Wind Watch/Warning and
Extreme Wind Warning (forecast outage risk, so the panel is prepared before the power goes
out); observed power outage ≥10% of county customers (sustained 2 polls). Wind Advisory does
not trigger. Lead window: 3–7 days (watch) to landfall/outage.

**Population.** Insulin-dependent patients (type 1 and insulin-treated type 2), with flags
for pump/CGM users and refrigeration-dependent storage. Panel sizing uses the VA diabetes
planning estimate (~25% — planning anchor).

**Mechanism.** [strong | setoguchi-hennessy-2026] Unopened insulin loses potency within
months at 37 °C, and power outages during extreme weather can compromise insulin
effectiveness in emergencies. [strong | fda-insulin-emergency] FDA emergency guidance sets
the storage rules quoted below.

**Magnitude.** [strong | fonseca-2009] After Katrina (n = 1,795), mean A1C rose from 7.7%
to 8.3% among safety-net patients over the following year, while VA patients — with intact
records and pharmacy continuity — showed no significant deterioration: system continuity
buffers disaster impact.

**Pre-event (care team).**
- Insulin roster with storage method and pump/CGM flags; confirm ≥14-day supply plus backup
  pens for pump users, with written basal-bolus backup dosing.
- Push the cold-chain plan: cooler + ice packs guidance, and the FDA storage rules below.
- Confirm glucose meter, strips, and ketone strips on hand.

**During event (care team).** Outreach to pump users in outage counties within 24 h;
telehealth-first for hyperglycemia; emergency fills per the VA Pharmacy Disaster Relief
Plan.

**Patient-facing.** "Your insulin can be ruined by heat or by freezing. If the power goes
out, keep it in a cooler with ice packs — but don't let it touch the ice. Most insulin is
OK out of the fridge (up to 86°F) for about 28 days — check your insulin's label, because
some types last less. Never use insulin that was frozen, or that looks clumpy, discolored,
or cloudy when it should be clear. If your pump stops working, switch to your backup pens
the way we showed you; insulin in a pump should be replaced after 48 hours without power or
cooling. Check your sugar more often. If it's over 240 or you feel sick, check ketones. If
your sugar stays over 300, or you have moderate or large ketones, call us right away.
[SHARED] Never use a generator, grill, camp stove, or charcoal indoors or in a garage —
even with the door open. Keep generators outside and away from windows. Use a
battery-powered CO alarm. Don't skip your insulin unless a clinician tells you to."

**Escalation.** Glucose persistently >300 mg/dL despite dosing, moderate/large ketones,
vomiting, or drowsiness → urgent contact / ED (DKA risk). Insulin supply compromised with
no replacement → same-day pharmacy solution. CGM readings that don't match symptoms →
confirm by fingerstick.

**Caveats.** The 28-day/86 °F rule is the FDA emergency guidance for vials and cartridges;
in-use times differ by product (some pens 10–14 days; some basal analogues longer) — hence
"check your insulin's label." Heat and direct sun can also affect pump tubing and CGM
accuracy.

**Sources.** fda-insulin-emergency; setoguchi-hennessy-2026; fonseca-2009; ada-sick-day.

---

## Card 6 — Hurricane / Power Outage × Dialysis-Dependent ESRD

**Triggers.** Hurricane/tropical products as Card 3; wind products as Card 5; observed power
outage ≥10% of county customers (sustained 2 polls). Lead window: 3–7 days to
landfall/outage.

**Population.** In-center hemodialysis patients (highest acuity), plus home hemodialysis
and peritoneal dialysis patients (power/water dependent). Panel sizing uses the VA ESRD
planning anchor (>52,000 veterans on dialysis — planning anchor).

**Magnitude.** [strong | anderson-2009] After Katrina (n = 386), 44% of hemodialysis
patients missed at least one session and ~17% missed three or more; missing ≥3 sessions was
associated with hospitalization (adjusted OR 2.16, 1.05–4.43). [strong | kelman-2015] After
Sandy, ED visits, hospitalizations, and 30-day mortality were elevated among dialysis
patients. [strong | lurie-2015] Receiving dialysis early, before landfall, was associated
with lower odds of ED visits (OR 0.80, 0.67–0.96) and hospitalization (OR 0.79, 0.66–0.94)
among 13,836 patients; the 30-day mortality result was borderline (adjusted OR 0.72,
0.52–0.997; P = 0.048). [strong | lukowsky-2019] VA precedent: the Manhattan VAMC dialysis
unit closed from Oct 28, 2012 to mid-March 2013; the median gap between sessions was 5 days,
and the Brooklyn campus absorbed most displaced care.

**Pre-event (care team).**
- Pre-schedule early dialysis for the full panel before projected landfall/outage
  (observational evidence of fewer ED visits and hospitalizations).
- Confirm each patient's backup facility assignment and transportation plan.
- Push the 3-day emergency renal diet plan; confirm patients have the supplies for it.
- Home HD/PD patients: confirm backup power/water plan and a fallback in-center slot.

**During event (care team).** Track facility operational status; re-route to backup units;
prioritize patients approaching 3 missed sessions; document session gaps.

**Patient-facing.** "If a storm or outage is coming, your dialysis center may move your
treatment earlier — please go, even if the day changes; getting dialysis before the storm
protects you. If you can't reach your center, call your backup center, or the national
kidney emergency line (KHARES: 866-446-3507; older KCER number: 1-866-901-3773). If you
must wait for dialysis, follow your 3-day emergency diet: very little fluid (about 2 cups a
day), and avoid high-potassium and high-salt foods. [SHARED] If a doctor has given you a
fluid limit — for your heart or your kidneys — keep to that limit and call us so we can
make a heat plan that is safe for you. [SHARED] Never use a generator, grill, camp stove,
or charcoal indoors or in a garage — even with the door open. Keep generators outside and
away from windows. Use a battery-powered CO alarm."

**Escalation.** About to miss a 2nd session → same-day placement search. Missed ≥3
sessions, or breathlessness, chest pain, confusion, or severe weakness (hyperkalemia/fluid
overload) → ED, tell them the last dialysis date.

**Caveats.** Early-dialysis evidence is observational; the survival signal is borderline
(medical-references.md §4). The emergency-diet fluid figure applies only while dialysis is
delayed.

### Card 6 sub-panel — Electricity-Dependent DME

**Population.** Patients dependent on electricity-powered equipment at home: oxygen
concentrators, ventilators, CPAP/BiPAP, home-dialysis equipment, electric wheelchairs,
enteral pumps. Denominator: emPOWER county/ZIP counts — a measured Medicare proxy (>4.6M
at-risk beneficiaries nationally, >3M with electricity-dependent DME), always labeled as
such, never a veteran count. [strong | hhs-empower]

**Pre-event additions.** Confirm backup power (battery hours, generator) and supplier
contacts; register eligible patients with utility medical-baseline/priority-restoration
programs; identify the nearest powered facility or medical shelter; oxygen users: confirm
backup cylinders and conserving devices.

**Patient-facing.** "If your medical equipment needs electricity, plan for an outage now:
know how long your backup battery lasts, keep your supplier's and utility's numbers handy,
and know where you would go if the power stays out. If you use oxygen, ask us about backup
cylinders. If your equipment stops and you can't restore power, call us or 911 — don't
wait."

**Escalation.** Backup power under 4 hours with no restoration estimate → call now for
relocation. Oxygen interruption with breathlessness → 911.

**Sources.** anderson-2009; kelman-2015; lurie-2015; lukowsky-2019; nkf-emergency-diet;
ipro-khares; hhs-empower.

---

## Card 7 — Extreme Cold / Winter Storm × Cardiovascular & Respiratory Disease

**Triggers.** NWS (current taxonomy per SCN 23-44; the provider normalizes legacy names):
Extreme Cold Warning, Extreme Cold Watch, Cold Weather Advisory, Winter Storm
Warning/Watch, Ice Storm Warning, Blizzard Warning. Participates in the cold×outage
co-occurrence boost.

**Population.** Patients with cardiovascular disease (ischemic heart disease, heart
failure, hypertension, prior stroke) or chronic respiratory disease (COPD, asthma). Risk
amplifiers: age ≥65, homeless or unstably housed, home-oxygen or electricity-dependent DME,
insulin users (freeze risk), outdoor workers.

**Mechanism.** [strong | gasparrini-2015 context] Cold drives peripheral vasoconstriction,
raising blood pressure and cardiac workload, and shifts hemostatic factors toward
thrombosis — precipitating MI and stroke; cold, dry air triggers bronchospasm and worsens
COPD/asthma. Storm conditions add hypothermia risk and carbon-monoxide poisoning from
improvised indoor heating.

**Magnitude.** [strong | gasparrini-2015] Across 384 locations in 13 countries, 7.29% of
deaths were attributable to cold versus 0.42% to heat — with most of the cold burden from
moderate cold, so risk is not confined to record-breaking days. [strong |
texas-dshs-uri-2021] Winter Storm Uri (Texas, Feb 2021): 246 storm-related deaths; 161
(65.4%) from cold exposure, 158 of them hypothermia; 19 from carbon-monoxide poisoning.

**Pre-event (care team).**
- Rosters: cardiovascular and respiratory panels, flagging home-oxygen/DME, homeless, age
  ≥65, and insulin users.
- Verify heating adequacy and a warm-place plan; coordinate homeless-program outreach and
  warming centers with transportation.
- Counsel cardiac patients against strenuous cold exertion (snow shoveling); review inhaler
  supply and cold-air plans for asthma/COPD patients. [expert_guidance | aha-snow-shoveling,
  cdc-co-guidance — URLs pending]
- Push CO-safety messaging; confirm oxygen backup where outages threaten (Card 6 DME
  sub-panel).

**During event (care team).** Wellness checks on flagged patients — isolation plus cold is
the lethal combination; monitor for hypothermia and CO presentations; low threshold to
relocate patients in unheated homes; when outages co-occur, the engine boost elevates these
items — treat as a compounded emergency.

**Patient-facing.** "Cold weather is hard on your heart and lungs. Stay warm and dry, dress
in layers, and avoid heavy outdoor work like shoveling snow — it strains the heart; take
breaks or get help. Cover your nose and mouth with a scarf so you breathe warmer air, and
keep your rescue inhaler with you. [SHARED] Never use a generator, grill, camp stove, or
charcoal indoors or in a garage — even with the door open. Keep generators outside and away
from windows. Use a battery-powered CO alarm. If you use insulin, don't let it freeze — an
unheated home or car can freeze it, and frozen insulin must be thrown away. If your heat
goes out, go somewhere warm and tell us. Keep taking your medicines."

**Escalation.** Chest pain or pressure; one-sided weakness or trouble speaking → 911.
Severe shortness of breath or blue lips → 911. Confusion, intense shivering or shivering
that stops, slurred speech (hypothermia) → 911 and rewarm. Headache, dizziness, or nausea
indoors while heating with fuel (possible CO) → fresh air immediately and call. No heat at
home during an Extreme Cold Warning → same-day call.

**Caveats.** Medication-specific cold interactions are weakly evidenced compared with heat;
the only drug-level line is the insulin freeze rule (fda-insulin-emergency). Cardiovascular
cold-risk framing beyond the epidemiology is expert guidance.

**Sources.** gasparrini-2015; texas-dshs-uri-2021; nws-scn23-44; cdc-co-guidance;
aha-snow-shoveling; fda-insulin-emergency.

---

## Card 8 — Wildfire Smoke × COPD / Asthma on Inhaled Therapies

**Triggers.** AirNow AQI ≥101 (Unhealthy for Sensitive Groups); AQI ≥151 (Unhealthy)
escalates severity; NOAA HMS smoke density Medium/Heavy over the county (observed).

**Population.** Patients with asthma or COPD on inhaled therapies — SABA rescue inhalers,
ICS and ICS/LABA controllers; secondary flags: cardiovascular disease, diabetes, outdoor
workers, homeless.

**Mechanism.** [expert_guidance | epa-wildfire-smoke-guide] Wildfire smoke's principal
hazard is PM2.5, which penetrates deep into the airways, triggering bronchoconstriction,
airway inflammation, and exacerbations in asthma/COPD, and cardiovascular events in
susceptible patients.

**Magnitude.** [strong | meek-2023] During the June 2023 smoke event, asthma-associated ED
visits in New York State (excluding NYC; 134 EDs) rose 81.9% on June 7 versus the June 1–5
mean. [strong | cdc-smoke-asthma-2023] Nationally, asthma ED visits were 17% above expected
across the 19 smoke days (AQI ≥101) of April–August 2023.

**Pre-event (care team).**
- Asthma/COPD roster; auto-message the smoke-forecast alert with action-plan reminders.
- Verify rescue-inhaler supply (push refills for anyone low); confirm controller adherence.
- Distribute clean-air guidance (below); flag outdoor workers and homeless patients for
  respite/clean-air-shelter coordination; reschedule outdoor appointments and pulmonary
  rehab.

**During event (care team).** Monitor AQI by facility ZIP; telehealth-first for respiratory
complaints; low threshold for early exacerbation treatment per the patient's written action
plan; watch the local ED-surge signal.

**Patient-facing.** "Wildfire smoke can set off your asthma or COPD even indoors. When the
air quality index is over 100, limit your time outside; over 150, stay inside if you can.
Keep windows closed and run the AC on recirculate, with the best filter it takes. A
well-fitted N95 helps if you must go out — cloth and surgical masks don't block smoke. A
box fan with a MERV-13 filter taped to it can help as a temporary fix; don't leave it
running unattended. Keep your rescue inhaler with you and make sure it isn't empty — call
us now if you need a refill. Follow your asthma or COPD action plan, and don't wait to
treat early symptoms. If the power is out: [SHARED] Never use a generator, grill, camp
stove, or charcoal indoors or in a garage — even with the door open. Keep generators
outside and away from windows. Use a battery-powered CO alarm. If it gets too hot inside,
go to a cleaner-air or cooling center."

**Escalation.** Rescue inhaler needed more often than the action plan allows, or not
helping → same-day call. Severe shortness of breath, can't speak full sentences, chest
tightness unrelieved by the inhaler, or blue lips → 911/ED. Chest pain or palpitations on
smoke days → urgent contact.

**Caveats.** The 81.9% figure is New York State excluding NYC. DIY box-fan filtration is an
EPA-described temporary option, not an endorsement. The keep-windows-closed advice carries
the overheating escape hatch (medical-references.md §3.3).

**Sources.** meek-2023; cdc-smoke-asthma-2023; epa-wildfire-smoke-guide; noaa-hms;
respiratory-action-plans.
