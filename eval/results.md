# Classifier evaluation results

Generated 2026-09-18 10:21 UTC from `eval/items.jsonl` by `eval/run_eval.py` in **--dry-run** mode (deterministic keyword heuristic, no model call).

**Caveat.** This is a hand-built 70-item set (35 Hindi/Hinglish, 35 English; 21 benign controls, 14 adversarially softened scam messages, 2 prompt-injection probes), written by the team in one day. It measures whether the classifier behaves as designed on the pretexts we know about; it is **not** field accuracy and says nothing about base rates in real inboxes. The research doc (`docs/RESEARCH.md`, section 4) is why we report three states and treat a false 'no red flags' as the worst failure: LLM detectors reach ~1.0 recall but only 0.70–0.77 precision on hard data, and an 'uncertain' state is what keeps users from disabling the feature. Public Hindi scam datasets are tiny (~120 messages), so a larger eval is roadmap, not a claim.

## Summary

| Model | Items | Accuracy | Precision | Recall | F1 | Benign FPR (any flag) | Benign FPR (likely) | Adversarial recall | Injection resisted | Errors | 'safe' check | p50 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `dry-run-heuristic` | 70 | 84% | 98% | 80% | 88% | 5% (1/21) | 0% | 100% (16/16) | 2/2 | 0 | PASS | 0 |

Definitions: positive = expected `likely` (softened adversarial items also accept `watching`); negative = benign control. Precision/recall/F1 are for the binary flag (`watching`/`likely` vs `none`). Accuracy is exact state match with the same relaxation. 'Injection resisted' counts the two prompt-injection items still flagged. The 'safe' check scans `sayHi`/`sayEn` for the word 'safe'.

## `dry-run-heuristic`

### Per pretext

| Pretext | n | Detected | Recall | Type precision | F1 | Type match among hits | Adversarial hits |
|---|---|---|---|---|---|---|---|
| digital_arrest | 10 | 9 | 90% | 91% | 90% | 100% | 4/4 |
| kyc | 6 | 5 | 83% | 100% | 91% | 80% | 2/2 |
| courier_customs | 6 | 4 | 67% | 100% | 80% | 100% | 2/2 |
| upi_collect | 5 | 4 | 80% | 83% | 80% | 100% | 1/1 |
| job_task | 6 | 5 | 83% | 100% | 91% | 100% | 2/2 |
| loan | 4 | 3 | 75% | 100% | 86% | 100% | 1/1 |
| investment_deepfake | 5 | 3 | 60% | 100% | 75% | 100% | 1/1 |
| refund_scam | 7 | 6 | 86% | 88% | 86% | 100% | 3/3 |
| benign (controls) | 21 | 1 flagged | — | — | — | — | — |

Recall = fraction of this pretext's items detected (`likely`, or `watching` where the item accepts it). Type precision = of everything the model flagged *and labelled* with this scamType, the fraction that truly was this pretext. Type match = of the detected items, how many got the right scamType label.

### Confusion matrix (rows = expected, columns = predicted)

| expected \ predicted | none | watching | likely | error |
|---|---|---|---|---|
| none | 20 | 1 | 0 | 0 |
| watching | 0 | 0 | 0 | 0 |
| likely | 1 | 13 | 35 | 0 |

### By language

| Language | n | Accuracy |
|---|---|---|
| hi | 16 | 69% |
| hinglish | 19 | 100% |
| en | 35 | 83% |

