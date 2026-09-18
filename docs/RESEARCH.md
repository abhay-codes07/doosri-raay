# Existing solutions and design rationale — research report (16 Sep 2026)

Scope: consumer scam protection for Indian families, with focus on digital arrest and elderly victims. Five research passes: government infrastructure, digital-arrest mechanics (25 cases), intervention-effectiveness evidence (50 studies/reports), startups and hackathon prior art, big-tech products. Items marked [unverified] rest on snippets or prior knowledge.

---

## 1. Headline verdict

The stack "AI listens to the call → detects digital arrest → red warning → alert family → freeze UPI → one-tap 1930" is a **common pattern among 2026 Indian hackathon submissions**. GitHub repos created since 1 Jan 2025: "scam detection" 3,355; "UPI fraud" 1,620; "digital arrest" 159. Named prior art whose READMEs describe some or all of this stack: Kavach (IIC 3.0), Rakshak (BunnieX 2026), SwarVed (SIH 2026, MHA track), VaaniRakshak, CallGuard, HearTrust, ScamShieldAI (ET Hackathon); see `docs/PRIOR_ART.md` for what each README states. Two platform facts, not judgements about those projects, are why we do not build on this stack: Android restricts third-party in-call audio, and in-the-wild voice-clone detection benchmarks are weak (section 2).

The evidence says the *victim-side detector* is the wrong frame:
- 82% of Singapore scam losses are self-authorised transfers (SPF 2025); the UK APP-fraud category (£450.7m, 2024) is entirely victim-authorised.
- Warning habituation sets in by the second exposure (Anderson, CHI 2015); a third of users click through SSL warnings (Akhawe & Felt, USENIX 2013).
- Across 25 documented Indian digital-arrest cases (2025–26), **every save came from an outsider**: a bank manager (Pune ₹14L, Nalgonda ₹18L, Lucknow ₹1.5cr), a relative (Bhopal daughter + lawyer friend; Moradabad daughter after the victim's phone died; Indore family filed missing-person), or police (Rajkot 112 call). Self-terminated cases ended only after the victim read a newspaper (Alwar 165 days, Nerul 6 weeks).
- Victims' own words: "questioning authority felt more dangerous than obeying it"; "we felt almost hypnotised" (HT Lucknow, Jan 2026).

**Therefore: build the outsider.** The guardian (adult child) is the primary user. The parent's job is one covert tap. The agent supplies the second opinion the scam is designed to remove, and then runs recovery end to end.

---

## 2. Competitive landscape

| Product | What it actually does | Family link | Works mid-scam? | Post-fraud | Gap for us |
|---|---|---|---|---|---|
| Truecaller / Truecaller Family (₹249/mo, ₹1,489/yr) | Crowd number reputation + "AI caller ID"; Family plan alerts child about suspicious *calls* to parents; 11 Indian languages | Yes (calls only) | Pre-answer only | No | Digital arrest uses WhatsApp/Skype video from fresh numbers; no transaction or isolation signal |
| Google Android fake-call detection (Jun 2026) | Verifies a call claiming to be a *saved contact* via encrypted RCS handshake; both sides need Phone by Google; on by default; Android 12+ | No | Only for spoofed-contact calls | No | Does nothing for "I am CBI" calls or WhatsApp video; does not judge content |
| Google Messages scam detection / Play Protect | On-device Gemini Nano on SMS from non-contacts [unverified for Hindi] | No | Text only | No | Not calls, not video, not family |
| PhonePe Protect / GPay + DoT FRI | Declines UPI payments to "Very High" risk numbers; ₹5,043cr prevented (Aug 2026) | No | Only flagged payees | No | Digital-arrest money goes by RTGS/NEFT to fresh company mule accounts, not flagged UPI IDs |
| NPCI UPI Circle | Family delegates a sub-account (₹5k/txn, ₹15k/month) | Yes (wrong direction) | No | No | Gates the *delegated* account, not the elder's own; limits far below scam amounts |
| RBI Apr 2026 discussion paper | 1-hour hold >₹10k; 70+ must nominate trusted person for >₹50k; kill switch | Proposed | Proposed | — | **Not in force**; industry pushback. We can build the trusted-person layer now, bank-independent |
| Sanchar Saathi / Chakshu | Report fraud numbers; screenshot mandatory; 30-day window; no outcome feedback; 2.5cr downloads | No | No | Report only | Experts: "tools used only after the crime" |
| 1930 / NCRP / CFCFRMS | Golden-hour freeze; 3.24cr calls in 2025; Mumbai hold rate 25.68%; form needs OTP login, ID upload, 200-char narrative, 12-digit UTR | No | No | Report only | HM Amit Shah (Jun 2026): "complicated reporting process, language barriers" |
| Money Restoration Module (mrm-ncrp.mha.gov.in, Aug 2026) | Refund of frozen funds; needs 14-digit ack, PAN, bank details, indemnity bond; FIR if >₹50k in one account | No | No | Refund | Nationally ₹10,700cr frozen vs ₹323cr refunded; no guide exists |
| ScamDekho / ScamRadar / scamchecker.app | Paste a link/message/screenshot → score | No | No | Links to 1930 | Requires the panicked elder to paste; nobody does that under a video "arrest" |
| Emoha / Khyaal / Samarth (elder-care) | Emergency helpline, community, Digi-Gold | Medical only | No | No | Zero scam features; 5M+ seniors on Khyaal = distribution with no incumbent |
| EverSafe / Carefull / Greenlight Family Shield (US) | Transaction-anomaly monitoring across accounts; trusted advocates get alerts; $1M insurance | Yes | No | Yes (care team) | US-only, Plaid-dependent; no Indian equivalent (Account Aggregator unused for elder fraud) |
| UK 159 / Monzo Call Status / Banking Protocol | Unspoofable "is this really my bank" channel; branch staff call police (£61.3m prevented 2024 [unverified]) | No | Yes | — | No Indian equivalent to verify "is this really CBI/SBI" mid-call |
| Singapore ScamShield + Project A.S.T.R.O. + CPF Trusted Contact | Police SMS-blast suspected victims (S$267.5m averted; "many victims unaware until the SMS"); CPF trusted contact gets notification copies, no account power; 1,266 in-person interventions | Yes (notification-only) | Yes (outreach) | Yes | The proven model; nothing like it exists in India for families |
| Hiya / Resemble / Reality Defender / Pindrop | Deepfake voice detection: browser ext, API, or enterprise call centres | No | Not on phone calls | No | In-the-wild AUC drops ~48%; cross-language near chance (XMAD-Bench 2025). Route around, don't detect |
| Kavach / Rakshak / SwarVed (hackathons) | Per their READMEs: in-call transcription + LLM verdict, on-screen warning, family alert, transaction pause, 1930 link; Kavach's README describes a PASS→CAUTION→PAUSE→KILL ladder and a "family verification challenge" | Yes | Per READMEs, during the call | Evidence pack / 1930 link | Closest prior art. Ours differs on: covert SOS, outsider escalation, recovery pipeline, deployed product |

---

## 3. What nobody does (gaps with evidence)

1. **A covert channel for a watched victim.** Scammers demand camera on, "do not leave the room", phone charged; the Moradabad victim hid his phone in his pocket at the bank. Every competitor shows a visible red overlay the scammer sees and the victim is ordered to ignore. No product has a disguised, silent SOS.
2. **Isolation-signature detection without listening to the call.** Signals the family can see: missed daily check-in, phone continuously busy for hours, unanswered guardian calls, unusual bank-branch visits, FD/gold-loan activity. SC direction #13 (4 Aug 2026) even asks DoT to examine time limits on video calls. Nobody operationalises the family as sensor.
3. **Pre-consented secrecy override.** Victims cannot decide to break "confidentiality" under duress. FINRA data: adoption jumps when a forced yes/no is asked at onboarding (42% named a trusted contact; 81% of the rest were never asked). CPF's notification-only trusted contact is the production precedent. No Indian product has a family pact.
4. **"Ask the person" verification.** Google verifies only spoofed *contact* calls, and only if both sides run Phone by Google. Nobody auto-pings the son when a caller says "your son is in trouble", or gives the parent a one-tap way to hear the official line and alert a guardian when a caller claims to be CBI/ED/TRAI. Vembu (Sep 2026): families need "verbal passwords". SOUPS 2025: older adults already rely on trusted relationships to detect scams.
5. **Recovery case management.** All competitors stop at "report". The real pipeline is 1930 → 14-digit ack (starts 329) → NCRP within 24h (exact field constraints) → e-Zero FIR threshold by state (Haryana/Rajasthan ₹1L, Punjab ₹5L) → MRM refund request (PAN, ≤₹50k-per-account rule, indemnity bond) → Chakshu within 30 days → bank ombudsman → guard against fake "MHA refund" SMS. No peer-reviewed AI reporting assistant exists (OpenAlex sweep), so novelty here is an honest claim.
6. **Vernacular voice-first UX for the 60+ user.** Every checker requires pasting text. Hackathon "Hindi-first" projects ship Streamlit desktop UIs.
7. **Bank-teller side.** Every save with money at stake involved bank staff; AARP BankSafe-trained staff saved 12x more; Hyderabad Police asked RBI for a "real-time intervention protocol for the signature pattern of a digital arrest in progress" [snippet]. No hackathon project targets the counter. (Roadmap, not MVP.)

---

## 4. Design principles the evidence supports

- Target authorised payments and persuasion in progress, not credential theft.
- Insert a trusted human, not a warning. Warnings habituate; humans don't.
- Notification-only trusted contact; never give the guardian account power (CHI 2022/2025: informal helpers end up holding credentials; CSCW 2020 "illusion of choice").
- Forced yes/no consent at onboarding decides adoption.
- Three states, not two: safe / watching / likely scam. LLM detectors hit ~1.0 recall but 0.70–0.77 precision on hard data; an "uncertain" state adds +0.10–0.15 precision and prevents users disabling the feature.
- Explain the tactic (authority, urgency, secrecy, payment-method switch), not a score. Google's UPI LLM work: 89% reasoning accuracy, 32% new valid reasons.
- Transcribe then classify; frontier model + few-shot Indian pretexts beats fine-tuning on the tiny public Hindi sets (~120 messages).
- Route around deepfake voice with out-of-band verification. Do not claim a detector.
- Make reporting fast and shame-free; let the guardian file on the elder's behalf.
- Simulate friction ("pause, ask family, resume") in UI; real holds are a bank function.

---

## 5. The pivot: "Doosri Raay" (Second Opinion) — the outsider agent

Tagline: *Isolation is the weapon. A second opinion is the antidote.* (I4C's own advisory: "Speak to your relatives and friends before taking any action to transfer money.")

Primary user: the guardian. The parent is asked for nothing under duress: the hero signal is passive.

**Two hero flows, one minor tool, three time-boxed stretches** (authoritative scope and schedule: `docs/BUILD_PLAN.md`):

1. **Isolation ladder (hero, passive).** The parent's app is a genuinely useful Panchang tile (tithi, weather, medicine reminder, family photo). Opening it each morning *is* the check-in. A missed open plus an unanswered guardian call, the two-signal rule, triggers a Step Functions ladder: guardian 1 → guardian 2 → named neighbour with a script and address → 112 guidance. Zero victim action; nothing appears on the parent's screen; nothing is recorded. → Gaps 1, 2, 3 (the onboarding consent makes the family the pre-authorised second opinion).
2. **Recovery case manager (hero).** After a loss: Claude vision extracts UTR/amount/payee/time from screenshots, code validates them (12-digit UTR regex, amount, date) and the user confirms each field beside the image → fixed-template 1930 script and freeze letter, LLM-written NCRP narrative enforced to ≥200 chars and the allowed character set → state e-Zero FIR threshold → MRM eligibility and document checklist → refund-scam guard. A long-running Step Functions case where every human step is a `waitForTaskToken` callback with a deadline (24 h NCRP, 30-day Chakshu) that escalates to a guardian. → Gap 5.
3. **Classifier (minor tool).** One Bedrock Converse call with structured output, three states (none / watching / likely), tactic explanation, never the word "safe"; screenshot text treated as untrusted input. Async: 202 + poll.
4. **Stretch, only if both heroes are green:** *Puchho* (parent taps "someone says they are CBI" → Polly Hindi plays the I4C line on the parent's phone and guardians are notified; "someone says my son is in trouble" → the son is pinged with a code-word challenge; this is the only place voice is used), a covert triple-tap SOS sending location only (no audio), and Web Push for guardian tasks. → Gap 4.

**Explicitly dropped:** hotspot map; Transcribe audio path; "agent conferences a guardian" (a PWA cannot place calls); ambient audio on SOS (mic indicator, and a second capture during a WhatsApp call gets silence); in-call listening; voice-clone detection; mock UPI freeze; red overlay warnings; SES email.

**AWS mapping (Ship It, 8 services):** Amplify Hosting PWA (parent tile, guardian dashboard, one-browser `/demo` split view) + Cognito (JWT on every route, circle derived from the token) → API Gateway (throttled) → Lambda (plain Converse for the classifier; Strands container only for the recovery agent, where multi-step tool use is real) → Bedrock (Claude Sonnet 4.6 via global profile from ap-south-1, Haiku 4.5 fallback in an env var) → S3 (hardened, size-capped presigned POST, 7-day expiry) → DynamoDB (circle, check-ins, tasks with task tokens, cases) → Step Functions (`Watch` per-parent deadline, `Ladder`, `RecoveryCase`; all human steps via `waitForTaskToken`). No EventBridge Scheduler: each check-in starts the next `Watch` execution, so the missed-check-in trigger is itself visible in the console. Polly is a 9th service only if Puchho ships.

**Regulatory tailwind to cite:** RBI Apr 2026 paper proposes exactly a "trusted person" for 70+ and 1-hour holds (not in force); SC 13-point directions (4 Aug 2026) demand victim-accessible systems; SC hearing again 16 Sep 2026; PM Mann Ki Baat warnings (Oct 2024, Feb 2026). Pitch line: "We built the trusted-person layer the RBI is proposing, today, without waiting for the banks."

**Demo (3:00):** the single authoritative script is section 9 of `docs/BUILD_PLAN.md`. In brief: sourced numbers and a *generic mock* "SCAM DETECTED" overlay (never other teams' demos) → Papa's Panchang tile, "opening it is the check-in" → Watch expires in the Step Functions console, Ladder runs, guardian taps "no answer", neighbour script; Papa's screen never changes and nothing is recorded → classifier card in the "watching" state → recovery case with validated fields beside the screenshot, 1930 script, NCRP narrative, e-Zero FIR threshold, MRM checklist, callback timer expiring into a guardian task → 3-second console tour of the eight services → eval table, prior art named (Kavach, Rakshak, SwarVed), roadmap. No voice plays anywhere in the ladder; Polly appears only in the Puchho stretch, which is inserted after the classifier card if it ships.

**Numbers for the hook (verified, cite each on screen):** ₹22,495 cr lost to cyber fraud in 2025 (MHA); 1,03,488 senior-citizen complaints, ₹4,005 cr (MHA, Rajya Sabha, 5 Aug 2026); digital arrest 2,97,727 complaints / ₹4,057.7 cr since 2022 (government data via News18, Jul 2026); Karnataka digital-arrest recovery 5% (2025) → 2.2% (Jan–Feb 2026, TOI); Mumbai 1930 hold rate 25.68% (Rediff, May 2026); ₹10,700 cr frozen vs ₹323 cr refunded nationally (IE/FE, Jul 2026, snippet). Do **not** use "51% never report" (unverified).

---

## 6. Risks specific to the pivot

- **Kavach's "family verification challenge" is the nearest prior art.** Differentiate visibly: passive ladder with zero victim action, a parent UX with no warnings at all, the validated recovery pipeline, and a deployed product with an evaluation harness and a 70-item test set (model numbers are produced by `python eval/run_eval.py` after deployment). Say so in the writeup.
- **A polling PWA does not buzz in the background.** Web Push (VAPID) on Android Chrome is a stretch; otherwise the guardian view is shown in the foreground in demo mode and the README says so.
- **False escalations** (parent forgot to open the tile). Mitigate: two-signal rule (missed check-in AND an unanswered guardian call), a "watching" state before rung 2, and a holiday mode.
- **A false "no red flags" verdict is the worst classifier failure.** Three states, never "safe", always "still ask family"; screenshot text is untrusted input and outputs are enum-constrained.
- **Vision can invent UTRs.** Regex and range validation in code, user confirmation beside the image, nothing filed automatically.
- **Consent and dignity.** Parent controls what is shared; guardian never sees balances; pact is revocable. Cite CPF model.
- **No public APIs** for 1930/NCRP/MRM/Chakshu. Ship copy-to-clipboard + deep links; be explicit.

---

## 7. Sources (selected; full lists in agent reports)

Government / courts: i4c.mha.gov.in; cybercrime.gov.in (advisory TAU/ADV/003, 6 Mar 2025); sancharsaathi.gov.in; Rediff 20 May 2026 (Mumbai hold rate); Daily Pioneer (Amit Shah review, Jun 2026); FPJ 21 Aug 2026 (MRM); Deccan Chronicle (MRM rules); NIE 4 Aug 2026 (SC 13-point directions); FPJ 11 Feb 2026 (SC on RBI); ANI 5 Aug 2026 (MHA Rajya Sabha reply); News18 Jul 2026 (digital-arrest data 2022–May 2026); TOI Bengaluru Mar 2026 (Karnataka recovery); Deccan Chronicle / Business Today Apr 2026 (RBI paper); Business Today 25 Nov 2025 (UPI Circle); FPJ (PhonePe Protect); Zee/TaxGuru Sep 2026 (FRI ₹5,043 cr).

Cases: TOI 30 Aug 2026 (Alwar 165 days); NIE 28 Aug 2026 (Bhopal 97 days); FPJ / HT Aug 2026 (Nerul ₹1.57 cr); the420.in (Moradabad, Rajkot); TOI (Pune bank manager); The Hindu (Nalgonda); HT Lucknow Jan 2026 (victim quotes, psychologists); FPJ (Indore rescues).

Evidence: PSR reimbursement dashboard; UK Finance 2025; SPF Annual Scams Brief 2025 (PDF); NASC/ACCC; FINRA Notice 26-02; AARP BankSafe; Anderson CHI 2015; Akhawe & Felt USENIX 2013; Latulipe CHI 2022/2025; Mentis PACM HCI 2020; LaRubbio SOUPS 2025 (arXiv 2508.11579); Shen et al. arXiv 2502.03964; Topcuoglu arXiv 2607.17353; Chang arXiv 2412.00621; Dahiphale (Google) arXiv 2410.19845; Müller Interspeech 2022; Deepfake-Eval-2024 arXiv 2503.02857; XMAD-Bench arXiv 2506.00462; Anatomy of a Scam Call arXiv 2608.24127.

Products / prior art: apps.apple.com/in Truecaller listing; FPJ + MediaNama 2–3 Jun 2026 (Google fake-call detection); web.whoscall.com; scamdekho.in; emoha.com; khyaal.com; eversafe.com; getcarefull.com; greenlight.com/family-shield; finra.org Rule 2165; stopscamsuk.org.uk/159; monzo.com/fraud; scamshield.gov.sg; hiya.com; resemble.ai/detect; pindrop.com; GitHub: PhiBao/rakshak, Mehatva/swarved-ai, harshgounder/kavach, TrombokenduShiv/Vyuha, diivyaaanshii/ScamShieldAI, voiceesprit/CallGuard, raushan-in/dapa; GitHub search API counts (created >2025-01-01).

Datasets for a Hindi/English eval: karanverma19/Indian_Multilingual_Scam_Message_Dataset (120, few-shot exemplars); ysangam/Indian_Cyber_Scam_PhoneCall_Hinglish_Dataset; shaw/scambench-training (37k, 14 languages incl. Hindi); FredZhang7/all-scam-spam; BothBosu/scam-dialogue. Build a 150–300 item hand-written Hindi/Hinglish eval with 30% benign and 20% adversarially softened items; report precision/recall per pretext.
