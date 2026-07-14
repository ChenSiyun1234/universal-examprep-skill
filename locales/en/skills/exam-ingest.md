# exam-ingest — en student-facing pack

> This file is the en language pack for student-visible wording; behavior lives in [skills/exam-ingest/SKILL.md](../../../skills/exam-ingest/SKILL.md) (the control layer, single source of truth).

## Student-facing Output
Use the receipt matching validator readiness; never turn process completion into a generic “ready” claim.

- `ready`: `Prep workspace initialized and validated: 3 wiki chapters + 18 bank items. No current validator warnings. Next: Chapter 1.`
- `usable_with_gaps`: `Prep workspace built with 2 declared gaps. I will name them before we begin; teaching may proceed without presenting those gaps as complete.`
- `blocked`: `The files were compiled, but review is blocking study: 2 source-backed issues remain. I will resolve or explicitly close each one before teaching.`

Dependency-preflight consent line (asked once for the exact missing capability reported by the current route):

> This materials route needs `<capability>` and it is not installed. The audited command is `<command>`. Install it now? If not, I will stop this unsupported route and report which files cannot be imported.

Post-install receipt:

> Dependency available — rerunning the same preflight and build. A different route, machine, or changed environment may require a separate check.
