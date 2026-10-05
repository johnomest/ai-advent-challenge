# E2E Scenario: Week 3 Days 11-14

Platforms: Web and Backend. Use a fresh isolated Edge context for each check. A mock provider may verify application behavior; a live DeepSeek call must be identified separately.

## Day 11 — memory layers

- [x] 1. Open the Day 11 app in Edge and confirm the chat, composer, and memory inspector render without browser errors. ✅ (isolated Edge; mock provider)
- [x] 2. Save distinct short-term, working, and long-term facts; confirm each appears in its labelled layer. ✅ (isolated Edge; mock provider)
- [x] 3. Send a question; confirm the relevant memory is reflected in the request/response evidence. ✅ (isolated Edge; mock provider)
- [x] 4. Create a new chat; confirm short-term and working facts are absent while long-term fact persists; refresh and confirm persistence. ✅ (isolated Edge; mock provider)

## Day 12 — profiles

- [x] 5. Open Day 12, create two profiles with visibly different style/format constraints and select each in a separate fresh chat. ✅ (isolated Edge; mock provider)
- [x] 6. Send the same question in both chats; confirm distinct selected profiles are shown and provider payloads differ accordingly. ✅ (isolated Edge; mock provider)
- [x] 7. Refresh and confirm profile assignment persists per chat. ✅ (isolated Edge; mock provider)

## Day 13 — task state

- [x] 8. Open Day 13, save current step and expected action, then advance from planning to execution. ✅ (isolated Edge; mock provider)
- [x] 9. Pause, refresh, and confirm stage/step/action persist and chat sending is blocked; resume and confirm sending works. ✅ (isolated Edge; mock provider)
- [x] 10. Advance through validation, rework to execution, then validation and done; confirm illegal stage skips are rejected by the backend. ✅ (isolated Edge; mock provider)

## Day 14 — invariants

- [x] 11. Open Day 14 and save typed language, architecture, and budget invariants. ✅ (isolated Edge; mock provider)
- [x] 12. Submit a compatible proposed solution via the real chat flow; confirm a passed check and response. ✅ (isolated Edge; mock provider)
- [x] 13. Submit a conflicting proposed solution; confirm a blocked check names the rule and the unsafe proposal is not accepted as a valid answer. ✅ (isolated Edge; mock provider)
- [x] 14. Refresh and confirm invariants and last check persist; test that untrusted markup in a memory field displays as text. ✅ (isolated Edge; mock provider)

## Cross-cutting UX

- [x] 15. At desktop width, confirm center chat and right inspector remain usable; a new long reply starts scrolling from its beginning. ✅ (isolated Edge; mock provider)
- [x] 16. At mobile width, confirm inspector drawer opens/closes by keyboard and no horizontal overflow occurs. ✅ (isolated Edge; mock provider)
- [x] 17. Confirm asynchronous completion for chat A does not overwrite currently selected chat B. ✅ (isolated Edge; mock provider)

## Validation evidence — 2026-09-18

- Python: four independent `python -m unittest -q` runs; 35 tests each, 134 executed successfully and 6 feature-gated skips (3/2/1/0 for days 11/12/13/14).
- JavaScript: all four `node --test static/week.test.cjs` suites passed, including regression checks for proposal persistence after send/recovery; `node --check` passed for all eight JS files.
- Edge: 17/17 steps passed with isolated contexts, temporary SQLite databases, and a mock provider behind the real app/server request path. Browser contexts and mock servers closed after validation.
- Desktop 1600×1000: reply beginning 16px below transcript top; inspector width 335px; no horizontal overflow. Mobile 390×844: drawer Enter/Escape and focus restoration passed; no horizontal overflow.
- Screenshots: `week3-desktop.png`, `week3-mobile.png` (mock responses, no secrets or personal data).
- One separate live DeepSeek call through Day14 `ChatAgent.ask`: model `deepseek-v4-flash`, JSON mode, language Python / architecture monolith / budget 500 against cap 1000; `last_check.status=passed`, answer `OK`, provider usage 253 prompt + 26 completion = 279 tokens. No existing chats or databases used; key was not printed. This is a live backend smoke check, not a live full-browser test.
- All four project data directories are Git-ignored; `git diff --check` passed.
- One rollback: Day14 proposal checkbox was cleared after send, contradicting video instructions. Executing preserved it; remaining E2E resumed at step13, and repeated-send/recovery regression checks passed. No previously completed scenario steps were rerun.
