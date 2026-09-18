# AI tools used

Disclosure as required by the hackathon rules.

| Tool | Used for | By whom |
|---|---|---|
| **Claude Code (Claude Fable 5.1, Anthropic)** | Research synthesis (`research-existing-solutions-and-how-to-win.md`), architecture and build plan, and code generation across the repo: `infra/`, `backend/`, `frontend/`, `eval/`, `scripts/`, the docs and this README. Also drafted the 70-item eval set and the synthetic demo screenshots. | Whole team, in pair-programming sessions |
| **Amazon Bedrock: Claude Sonnet 4.6 (`global.anthropic.claude-sonnet-4-6`), fallback Claude Haiku 4.5** | Runtime only: the three-state classifier (one Converse call with forced tool use) and the NCRP narrative inside the recovery agent. The model never decides anything unvalidated: enums, lengths and character sets are enforced in code. | Product runtime |
| **Strands Agents SDK** | Tool-calling loop for the recovery agent (container Lambda). | Product runtime |

All AWS-side deployment, testing, the eval run against the real models, the demo recording and the Hindi copy
review were done by the team. Every number in the README was checked by a human against the source listed
beside it.

Add a row here for any other tool a teammate used (design tools, transcription, video editing, etc.):

| Tool | Used for | By whom |
|---|---|---|
| _(none yet)_ | | |
