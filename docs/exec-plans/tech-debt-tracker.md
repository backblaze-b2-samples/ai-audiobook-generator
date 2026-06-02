<!-- last_verified: 2026-06-02 -->
# Tech Debt Tracker

Known tech debt items. Agents update this when they discover or create tech debt.

| Description | Impact | Proposed Resolution | Priority | Status |
|---|---|---|---|---|
| In-process narration jobs (`BackgroundTasks`) | A server restart loses in-flight narration; chapters already written to B2 survive, but the job won't resume | Move to a durable worker/queue (e.g. Redis + RQ) and resume from the manifest's per-chapter status | Medium | Open |
| Dashboard "audio hours/day" attributes a book's whole duration to its creation day | Activity chart is a coarse proxy, not true per-chapter render timing | Record per-chapter render timestamps in the manifest and aggregate those | Low | Open |
| Client-side chapter preview duplicates backend split heuristics | Two implementations of the same rules can drift | Expose a `/books/preview` endpoint, or keep the preview clearly labelled as an estimate (current approach) | Low | Open |
