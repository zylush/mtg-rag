# MTG Rules Desk documentation

Start with the [product requirements](PRD.md), then use the sections below for
implementation, operation, and verification details.

## Architecture

- [System architecture](architecture/Architecture.md) — complete runtime, data,
  retrieval, and cloud design.
- [Architecture essentials](architecture/architecture-essentials.md) — concise
  onboarding guide and glossary.
- [P0 conversation-context remediation plan](architecture/P0-CONVERSATION-CONTEXT-REMEDIATION-PLAN.md)
  — release architecture, acceptance criteria, rollout, and rollback for the open follow-up P0.
- [Agent contract](architecture/agent.md) — assistant scope, grounding, citations,
  confidence, and failure behavior.
- [Visual backend architecture](architecture/visual-backend-architecture.md) —
  narrated request and ingestion flows.

## Operations and assurance

- [Operations runbook](operations/OPERATIONS.md) — bootstrap, deployment,
  rollback, recovery, and incident response.
- [Security model](operations/SECURITY.md) — trust boundaries, controls, and
  residual risks.
- [Attribution and launch decisions](operations/ATTRIBUTION-AND-LAUNCH.md) —
  source policy evidence and launch decisions.
- [Production readiness audit](operations/PRODUCTION-AUDIT.md) — current
  ship/block assessment.
- [Risk and edge-case audit](operations/RISK-AND-EDGE-CASE-AUDIT.md) — prioritized
  correctness, reliability, security, and scaling risks.
- [Integration lessons](operations/INTEGRATION-LESSONS.md) — deployment and
  integration findings.

## Verification evidence

Feature-level TDD records and live verification notes are kept in
[testing](testing/).
