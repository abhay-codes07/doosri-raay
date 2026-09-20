# Prior art

We name what exists so the judges do not have to. Counts and links below come from the public READMEs of the projects named, fetched on 18 Sep 2026.
(16 Sep 2026), which counted GitHub repos created since 1 Jan 2025 with "scam detection" (3,355),
"UPI fraud" (1,620) and "digital arrest" (159) in the name or description. Many of them, and several
well-built hackathon entries, share a common shape: analyse the call or message → warn the user →
alert the family → point to 1930. We chose a different frame, described at the end of this page.

## Hackathon and student projects

The descriptions below are limited to what each project's public README states (as read on 18 Sep 2026).
We have not run these projects and make no claim about how they perform.

| Project | Where | What its README says it does | What we chose to do differently |
|---|---|---|---|
| **Kavach** | [github.com/harshgounder/kavach](https://github.com/harshgounder/kavach) (IIC 3.0) | According to its README, a Hindi-first call-security platform with an intervention loop "recognize → interrupt → verify → package → report": voice-spoof detection (AASIST-Hindi), coercion-script analysis, a fusion ladder with PASS / CAUTION / PAUSE / KILL verdicts, the ability to pause a transaction and alert a trusted family member, and a signed evidence packet prepared for 1930 / Chakshu. | The closest prior art we found, and the ladder idea is one we share. Ours is driven by the family's signals (a missed check-in plus an unanswered guardian call) rather than by analysis of the victim's call. |
| **Rakshak** | [github.com/PhiBao/rakshak](https://github.com/PhiBao/rakshak) (BunnieX 2026) | According to its README, a real-time system that "listens alongside the person being targeted", recognises the digital-arrest playbook, warns them aloud in Hindi or English, alerts the family during the call, deploys a counter-agent to stall the caller, and generates an evidence pack for cybercrime.gov.in / 1930. | Rakshak alerts the family from inside the call. We alert the family from outside it, so nothing depends on the victim's phone or on the victim heeding a warning. |
| **SwarVed AI** | [github.com/Mehatva/swarved-ai](https://github.com/Mehatva/swarved-ai) (SIH 2026) | According to its README, on-device detection of AI voice cloning and digital-arrest scams on Android (Kotlin + native C++, ONNX), a dual-stream audio model, offline processing with no audio stored, and 1930 integration. | Vernacular and privacy-first, which we admire. We do not attempt voice or deepfake detection at all; we route around the call. |
| **CallGuard** | [github.com/voiceesprit/CallGuard](https://github.com/voiceesprit/CallGuard) | According to its README, real-time scam detection during calls using anti-spoof, speech-recognition and text-classification models, scoring conversations against Cialdini's influence principles and returning CRITICAL / HIGH / MEDIUM / LOW alerts with recommended actions. | Its tactic taxonomy (authority, scarcity, ...) is close to the one our checker explains. Our checker is a minor tool and never the hero flow. |
| **ScamShield AI** | [github.com/diivyaaanshii/ScamShieldAI](https://github.com/diivyaaanshii/ScamShieldAI) (ET Hackathon) | According to its README, an AI-assisted analyser for suspicious messages (Python + Streamlit, LLM API) with keyword and pattern detection and risk-level classification, and a disclaimer that results are advisory. | We share the "advisory, never authoritative" stance; we go one step further and never render the word "safe". |

We are grateful to these teams for publishing their work as open source; reading their READMEs is what
sharpened the framing below.

Two facts from the research doc shaped our choice not to build on in-call audio, and they are about the
platform and the benchmarks, not about any project above: Android restricts third-party access to in-call
audio, and in-the-wild deepfake-audio detection loses roughly 48% AUC with cross-language detection near
chance (Deepfake-Eval-2024, XMAD-Bench 2025). We do not claim a detector; we route around the call.

## Products

| Product | Where | What it does | Gap |
|---|---|---|---|
| **ScamDekho** | [scamdekho.in](https://scamdekho.in) | Paste a link, message or screenshot, get a score and a 1930 link | Requires the panicked elder to paste; nobody does that during a video "arrest" |
| **Truecaller Family** (₹249/mo, ₹1,489/yr) | [Truecaller on the Indian App Store](https://apps.apple.com/in) | Crowd number reputation, "AI caller ID", family plan alerts the child about suspicious *calls* to a parent, 11 Indian languages | Digital arrest runs on WhatsApp/Skype video from fresh numbers; no transaction or isolation signal, nothing after the loss |
| **Google fake-call verification** (Jun 2026) | Reported by FPJ and MediaNama, 2–3 Jun 2026 | Verifies a call claiming to be a *saved contact* via an encrypted RCS handshake; both sides need Phone by Google; Android 12+; on by default | Does nothing for "I am CBI" calls or WhatsApp video; does not judge content; no family loop |
| **EverSafe / Carefull** (US) | [eversafe.com](https://eversafe.com), [getcarefull.com](https://getcarefull.com) | Transaction-anomaly monitoring across accounts; trusted advocates get alerts; care team after fraud | US-only, Plaid-dependent; no Indian equivalent (Account Aggregator is unused for elder fraud) |
| **Singapore ScamShield + CPF Trusted Contact** | [scamshield.gov.sg](https://scamshield.gov.sg) | Police SMS-blast suspected victims (S$267.5m averted; "many victims unaware until the SMS"); CPF trusted contact receives notification copies with **no** account power; 1,266 in-person interventions | The proven model. Nothing like it exists in India for families; this is the precedent for our notification-only guardian |

## What we chose to do differently

1. **A passive ladder with zero victim action.** The projects above ask the victim to notice a warning, tap a
   button or paste a message, at a moment when a "CBI officer" may be watching them on video. Our hero signal
   is the parent *not* opening the Panchang tile by their daily deadline, confirmed by a guardian call that goes
   unanswered (the two-signal rule). The Step Functions ladder then works guardian 1 → guardian 2 → named
   neighbour → 112 guidance. The parent does nothing, and nothing appears on their screen.
2. **A parent UX with no warnings at all.** Warnings habituate by the second exposure (Anderson, CHI 2015) and a
   scammer can simply order the victim to ignore a red overlay. The parent's app is a genuinely useful tithi,
   weather, medicine and family-photo tile. There is no scam vocabulary on it, so there is nothing for a
   scammer to see or to counter.
3. **A validated end-to-end recovery pipeline.** Most tools stop at a 1930 link. We run the sequence:
   screenshot extraction validated in code (12-digit UTR regex, amount range, parseable time) and confirmed by
   the user beside the image, a fixed-template 1930 script, an NCRP narrative enforced to the portal's
   constraints, the state's e-Zero FIR threshold, MRM refund eligibility and its document checklist, and a
   guard against the fake "MHA refund fee" SMS that targets prior victims. Every human step is a
   `waitForTaskToken` callback with a deadline that escalates to a guardian. We found no peer-reviewed AI
   reporting assistant (OpenAlex sweep in the research doc), so we describe this as new with that caveat.
4. **A deployable product with an evaluation harness and a 70-item test set.** One SAM stack, seeded judge
   accounts, the AWS services listed in the README each doing visible work in the demo, and a 70-item
   Hindi/Hinglish/English test set with 21 benign controls, 14 adversarially softened scams and 2
   prompt-injection probes (16 items carry `adversarial: true`). Model numbers are produced by
   `python eval/run_eval.py` after deployment; until that run, `eval/results.md` is a placeholder and no
   accuracy figure is claimed. It is a hand-built set, not field accuracy.

## Regulatory context we build toward, not against

- RBI discussion paper (Apr 2026): 1-hour hold on transfers above ₹10k, a nominated trusted person for
  customers over 70 for transfers above ₹50k, a kill switch. **Not in force**; industry pushback. We build the
  trusted-person layer now, bank-independent.
- Supreme Court 13-point directions (4 Aug 2026) on digital arrest, including a request that DoT examine time
  limits on video calls; hearing continued 16 Sep 2026.
- I4C advisory TAU/ADV/003 (6 Mar 2025): "Speak to your relatives and friends before taking any action to
  transfer money." That sentence is our product.
