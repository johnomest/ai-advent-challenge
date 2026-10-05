# E2E Scenario: Day 15 — Controlled State Transitions

Platforms: Backend and Web. Run Web checks in isolated Microsoft Edge contexts. Re-read this file before every browser action and continue from the first unchecked step.

## Backend and startup

- [x] 1. Run the complete Python and JavaScript test suites; confirm databases are ignored and the project starts on port 8772. ✅ 42 Python tests; 1 JS suite; JS syntax, diff --check, git check-ignore pass; isolated mock server listens on 8772.
- [x] 2. Open the Day 15 app in Edge; confirm GOOST chat and the expanded task-state panel render without console errors. ✅ Edge 1440×1000; task panel expanded; no page errors.

## Forbidden paths and plan approval

- [x] 3. From planning, request a direct transition to done; confirm HTTP/UI refusal, clear reason, and unchanged stage/revision/history. ✅ HTTP 409 invalid_transition; full task snapshot unchanged, visible reason.
- [x] 4. Request execution without a saved and approved plan; confirm precondition refusal and unchanged state. ✅ Execution precondition 409; stage/revision/history/artifacts unchanged.
- [x] 5. Save a plan, approve it, then transition to execution; confirm revision/history and allowed transitions update. ✅ Saved plan → approval → execution; revision/history 3; validation awaits result.

## Pause and recovery

- [x] 6. Pause during execution; confirm transition and message controls are blocked while unsaved input remains visible. ✅ Paused; transition/send disabled; both unsaved drafts remain visible.
- [x] 7. Refresh the page, confirm persisted stage/artifacts/pause, resume, and continue without re-entering the plan. ✅ Reload retained pause, stage, revision/history and plan; resume succeeded.

## Validation, rework, completion

- [x] 8. Save an execution result and transition to validation. ✅ Execution artifact saved; validation entered.
- [x] 9. Save a failed validation and request done; confirm refusal with unchanged stage. ✅ Failed validation blocks done with 409; full task unchanged.
- [x] 10. Transition back to execution; confirm stale execution and validation artifacts are cleared. ✅ Rework clears execution and validation in DB and UI, keeps approved plan.
- [x] 11. Save a new execution result, return to validation, save passed validation, and transition to done. ✅ Reworked result + passed validation → done; revision/history 13. Harness arithmetic corrected; completed actions not repeated.
- [x] 12. In done, confirm new task mutations and model messages are blocked while read-only state/history remain available. ✅ Terminal controls disabled; direct mutations/message return 409 task_done; readable task/history retained.

## Model boundary and resilience

- [x] 13. Ask the assistant to ignore stages and claim implementation is complete while planning; confirm server-owned stage does not change and incompatible response kind is rejected. ✅ Deterministic wrong kind=implementation at planning → 502; task and transcript unchanged.
- [x] 14. Verify a stale revision from another tab is rejected and unsaved form text survives authoritative refresh. ✅ Second tab advanced revision; stale save → 409; authoritative revision refreshed, local plan draft preserved.
- [x] 15. Start a mutation in chat A and switch to chat B; confirm late success/refusal does not overwrite chat B status or state. ✅ Delayed real PATCH success and refusal in A; switching sidebar to B preserves B task/status/error.

## Responsive and live provider

- [x] 16. Check desktop and 390px mobile layouts, keyboard navigation, inspector drawer Escape/focus restoration, and absence of horizontal overflow. ✅ 1440px/390px no horizontal overflow; mobile inspector Tab/Escape/focus restoration passed; screenshots saved.
- [x] 17. Make one minimal live DeepSeek request through Day 15 without exposing the key; distinguish this smoke check from mock-provider E2E. ✅ One real request through isolated Day 15 HTTP server, model deepseek-v4-flash, max_tokens=128: HTTP 200; assertions confirmed planning, revision 0, two saved messages. Key never printed. Final diagnostic print hit Windows cp1252 UnicodeEncodeError after successful assertions; no second paid request made.

## Validation notes

- Steps 2–16 used a deterministic mock provider and isolated headless Microsoft Edge contexts. The wrong-kind response was injected by the provider stub; task endpoints used the real server and SQLite.
- The full lifecycle ended at revision/history 13. Initial harness expectation 15 was an arithmetic error; assertions were corrected and validation resumed without replaying completed steps.
- Creating a new chat requires the existing creation dialog confirmation; the harness was corrected accordingly before continuing step 13.
- Desktop/mobile screenshots were visually inspected; no layout defect observed. Runtime page errors: none.
- The live provider smoke validates one small planning response, not general answer quality or guaranteed resistance of prose to prompt injection.
