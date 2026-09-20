# AI tools used

Disclosure as required by the hackathon rules.

| Tool | Used for | By whom |
|---|---|---|
| **Claude Code (Claude Fable 5.1, Anthropic)** | Research synthesis, architecture and build plan, and code generation across the repo: `infra/`, `backend/`, `frontend/`, `eval/`, `scripts/`, the docs and the README. Also drafted the 70-item eval set and the synthetic demo screenshots. Claude Code also ran the local checks on the team's machines: `pytest` for the backend, `npm run build` / `tsc` for the frontend, `sam validate` / `infra/validate_asl.py`, the Docker build of the recovery-agent image, and `python eval/run_eval.py --dry-run` (the harness only, no model call). | Whole team, in pair-programming sessions |
| **Amazon Bedrock: Claude Sonnet 4.6 (`global.anthropic.claude-sonnet-4-6`), fallback Claude Haiku 4.5** | Runtime only: the three-state classifier (one Converse call with forced tool use) and the NCRP narrative inside the recovery agent. The model never decides anything unvalidated: enums, lengths and character sets are enforced in code. | Product runtime |
| **Strands Agents SDK** | Tool-calling loop for the recovery agent (container Lambda). | Product runtime |
| **Amazon Polly** | Runtime only: the Hindi I4C line played by *Puchho* on the parent tile. | Product runtime |

What Claude Code did **not** do: it never had AWS credentials. All AWS deployment (`sam deploy`, Amplify
Hosting, Cognito seeding, the SSM VAPID parameter, Budgets), the eval run against the real models, the demo
recording and the Hindi copy review are performed by the team. At the time of writing the stack has not
been deployed yet; the "Deployment status" section of the README is updated by the team when it is. Every
number in the README was checked by a human against the source listed beside it.

Add a row here for any other tool a teammate used (design tools, transcription, video editing, etc.):

| Tool | Used for | By whom |
|---|---|---|
| _(none yet)_ | | |
