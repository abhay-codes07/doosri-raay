# Prior art

We name what exists so the judges do not have to. Facts and links below come from
`research-existing-solutions-and-how-to-win.md` (16 Sep 2026), which counted GitHub repos created since
1 Jan 2025 with "scam detection" (3,355), "UPI fraud" (1,620) and "digital arrest" (159) in the name or
description. The stack "AI listens to the call → detects digital arrest → red warning → alert family →
freeze UPI → one-tap 1930" is the median Indian hackathon submission of 2026.

## Hackathon projects

| Project | Where | What it does | What we take from it |
|---|---|---|---|
| **Kavach** | [github.com/harshgounder/kavach](https://github.com/harshgounder/kavach) (IIC 3.0) | Whisper transcription + LLM on the live call, a PASS → CAUTION → PAUSE → KILL ladder, red overlay, a "family verification challenge", mock UPI freeze, 1930 link | Closest prior art. The ladder idea is right; ours is driven by the *family's* signals, not the victim's phone |
| **Rakshak** | [github.com/PhiBao/rakshak](https://github.com/PhiBao/rakshak) (BunnieX 2026) | Same stack: in-call audio, LLM verdict, red warning, family alert, one-tap 1930 | Family alert exists but fires on a warning the victim has been told to ignore |
| **SwarVed** | [github.com/Mehatva/swarved-ai](https://github.com/Mehatva/swarved-ai) (SIH 2026, MHA track) | Voice-first, Hindi-focused in-call scam detection and warning | Vernacular focus; still a victim-side detector |
| **CallGuard** | [github.com/voiceesprit/CallGuard](https://github.com/voiceesprit/CallGuard) | In-call transcription and LLM scam scoring with an alert | Same frame |
| **ScamShieldAI** | [github.com/diivyaaanshii/ScamShieldAI](https://github.com/diivyaaanshii/ScamShieldAI) (ET Hackathon) | Message/call scam classifier with a warning UI | Same frame |

None of these ships working Android in-call audio (Android blocks it) and the voice-clone detection claims are
lab-only: in-the-wild deepfake-audio AUC drops by roughly 48% and cross-language detection is near chance
(Deepfake-Eval-2024, XMAD-Bench 2025). We do not claim a detector; we route around it.

## Products

| Product | Where | What it does | Gap |
|---|---|---|---|
| **ScamDekho** | [scamdekho.in](https://scamdekho.in) | Paste a link, message or screenshot, get a score and a 1930 link | Requires the panicked elder to paste; nobody does that during a video "arrest" |
| **Truecaller Family** (₹249/mo, ₹1,489/yr) | [Truecaller on the Indian App Store](https://apps.apple.com/in) | Crowd number reputation, "AI caller ID", family plan alerts the child about suspicious *calls* to a parent, 11 Indian languages | Digital arrest runs on WhatsApp/Skype video from fresh numbers; no transaction or isolation signal, nothing after the loss |
| **Google fake-call verification** (Jun 2026) | Reported by FPJ and MediaNama, 2–3 Jun 2026 | Verifies a call claiming to be a *saved contact* via an encrypted RCS handshake; both sides need Phone by Google; Android 12+; on by default | Does nothing for "I am CBI" calls or WhatsApp video; does not judge content; no family loop |
| **EverSafe / Carefull** (US) | [eversafe.com](https://eversafe.com), [getcarefull.com](https://getcarefull.com) | Transaction-anomaly monitoring across accounts; trusted advocates get alerts; care team after fraud | US-only, Plaid-dependent; no Indian equivalent (Account Aggregator is unused for elder fraud) |
| **Singapore ScamShield + CPF Trusted Contact** | [scamshield.gov.sg](https://scamshield.gov.sg) | Police SMS-blast suspected victims (S$267.5m averted; "many victims unaware until the SMS"); CPF trusted contact receives notification copies with **no** account power; 1,266 in-person interventions | The proven model. Nothing like it exists in India for families; this is the precedent for our notification-only guardian |

## The four things Doosri Raay does differently

1. **A passive ladder with zero victim action.** Every project above needs the victim to notice a warning, tap a
   button or paste a message while a "CBI officer" watches them on video. Our hero signal is the parent *not*
   opening the Panchang tile by their daily deadline, confirmed by a guardian call that goes unanswered (the
   two-signal rule). The Step Functions ladder then works guardian 1 → guardian 2 → named neighbour → 112
   guidance. The parent does nothing, and nothing appears on their screen.
2. **A parent UX with no warnings at all.** Warnings habituate by the second exposure (Anderson, CHI 2015) and a
   scammer simply orders the victim to ignore the red overlay. The parent's app is a genuinely useful tithi,
   weather, medicine and family-photo tile. There is no scam vocabulary on it, so there is nothing for a
   scammer to see or to counter.
3. **A validated end-to-end recovery pipeline.** Everyone else stops at a 1930 button. We run the real sequence:
   screenshot extraction validated in code (12-digit UTR regex, amount range, parseable time) and confirmed by
   the user beside the image, a fixed-template 1930 script, an NCRP narrative enforced to the portal's
   constraints, the state's e-Zero FIR threshold, MRM refund eligibility and its document checklist, and a
   guard against the fake "MHA refund fee" SMS that targets prior victims. Every human step is a
   `waitForTaskToken` callback with a deadline that escalates to a guardian. No peer-reviewed AI reporting
   assistant exists (OpenAlex sweep in the research doc), so this novelty claim is an honest one.
4. **A deployed product with published eval numbers.** A live Amplify URL with seeded judge accounts, eight
   AWS services each doing visible work in the demo, and a 70-item Hindi/Hinglish/English eval with 30%
   benign controls, 20% adversarially softened items and two prompt-injection probes, results in
   `eval/results.md` with the caveat that it is a hand-built set, not field accuracy.

## Regulatory context we build toward, not against

- RBI discussion paper (Apr 2026): 1-hour hold on transfers above ₹10k, a nominated trusted person for
  customers over 70 for transfers above ₹50k, a kill switch. **Not in force**; industry pushback. We build the
  trusted-person layer now, bank-independent.
- Supreme Court 13-point directions (4 Aug 2026) on digital arrest, including a request that DoT examine time
  limits on video calls; hearing continued 16 Sep 2026.
- I4C advisory TAU/ADV/003 (6 Mar 2025): "Speak to your relatives and friends before taking any action to
  transfer money." That sentence is our product.
