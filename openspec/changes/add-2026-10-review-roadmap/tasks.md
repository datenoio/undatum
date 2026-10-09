## 1. Roadmap adoption
- [ ] 1.1 Approve the phase plan and gate criteria in this change
- [ ] 1.2 Create GitHub milestones `v1.7.1`, `v1.8`, `v1.9`, `v2.0` and one issue per mapped change
- [ ] 1.3 Export the review report to `dev/docs/REPOSITORY_REVIEW_2026-10-07.md` so the
      evidence lives in the repository next to the 2026-09-18 review

## 2. OpenSpec hygiene
- [ ] 2.1 Restore `release-quality`, `data-validation` and `documentation` specs from their
      archived deltas into `openspec/specs/`
- [ ] 2.2 Reconcile `database-ingestion` with `database-integration`, `data-analysis` with the
      stats requirements in `data-processing`, and `data-visualization` with the Plot Command
      requirement; merge or restore so no archived requirement is lost
- [ ] 2.3 Archive `add-undatum-improvement-roadmap` (tasks 4.3 and 4.4 stay deferred; 4.7 is
      superseded by `add-data-quality-report`)
- [ ] 2.4 Move `openspec/changes/PROPOSAL_STATUS_SUMMARY.md` and
      `openspec/changes/SCHEMA_IMPROVEMENTS_SUMMARY.md` to `dev/docs/` or delete them
- [ ] 2.5 Run `openspec validate --strict` for all specs and changes

## 3. Gate tracking
- [ ] 3.1 Record gate 1 evidence (clean install on all supported Python versions, contract
      matrix green) before starting Phase 1 work
- [ ] 3.2 Record gate 2 evidence (lint clean, mypy ratchet enforced, startup ≤ 0.3 s on CI)
- [ ] 3.3 Record gate 3 evidence (all row-wise transforms streaming; 1M rows ≤ 300 MB peak RSS)
