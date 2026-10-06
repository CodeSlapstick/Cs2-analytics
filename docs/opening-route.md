# Opening Route

Open `/opening-route` or use **Opening Route** in the top navigation. Authentication
and guest viewing use the existing app session. Select a player, map, side and
All / latest 5 / latest 10 matches. Filters are stored in the URL. All includes
undated matches; Latest excludes them instead of guessing their order from upload time.

Eight rounds are initially visible to keep the radar legible. Click a round to
toggle it, or Show all / Hide all. Marker numbers match the numbered round list;
colors use eight semantic series tokens, with a dashed path for later cycles.
Each round links to the existing Round Review as evidence.

Playback starts paused at 0 seconds, supports 1x/2x/4x, and stops at 30 seconds.
Seeking updates movement and Utility immediately. Reset pauses at 0. Changing
filters recreates the stage; unmounting cancels the animation frame.

## Ownership and data path

- `backend/app.py`: authenticated SQL adapters for `/api/opening-route/catalog`
  and `/api/opening-route`; player side comes from `player_rounds.side` for each round.
- `backend/opening_routes.py`: sole owner of opening-window selection, date policy,
  death cutoff, continuous segments and the API presentation model. Pure functions.
- `backend/review.py`: existing sole owner of world-to-radar conversion and shared
  Utility projection (`build_grenade_rows`), reused by Round Review and Opening Route.
- `frontend/src/api.ts`: typed transport, no page-local fetch.
- `frontend/src/openingRoutePlayback.ts`: marker/trail projection on one elapsed
  clock; no coordinate calibration or event derivation.
- `frontend/src/OpeningRoutePage.tsx`: URL filters, queries, navigation and a
  props-driven stage. `opening-route.css` extends the existing visual language.
- `frontend/src/i18n/en-opening.ts`: translations through the existing Thai-key i18n.

This project uses PostgreSQL demo facts, not the DAK v3 ZIP/package seam. DAK Studio
was inspected as a behavioral reference; no DAK source, dependency or contract was copied.
No migration, parser change or reference-model training is required.

## Recorded-data limits

- Match dates are not stored in `matches`. Only a valid explicit `YYYY-MM-DD` in
  the filename is treated as a date, labeled as such; imported_at is never substituted.
- `rounds.start_tick` normally means freeze end. The parser historically falls
  back to round start when the freeze event is absent, and persistence discards
  that distinction. The UI explicitly labels this unresolved provenance; it does
  not claim all stored anchors are verified live starts. Missing anchors/tickrates
  produce unavailable rounds rather than a fallback clock.
- Routes use real `player_positions` (8 Hz or legacy 1 Hz). Death terminates them.
  Invalid coordinates break a segment. Gaps over 1.5 times the median interval,
  capped at 1.5 seconds, break segments; interpolation occurs only inside a segment.
  Markers disappear beyond the final sample or during an outage; recorded trails remain.
- Utility counts are recorded throws in the inclusive 0–30 second window.
  No movement samples are required to display a recorded Utility event.
  Null clocks keep counts unknown (`—`). An empty event table does not certify
  full recording coverage; the UI says counts are recorded events only.
- Throw points, landing points and real sampled trajectories appear at their
  recorded times. They are historical event overlays, not inferred active smoke/fire
  areas. Missing coordinates/times/flight paths are never invented. Existing data
  combines Molotov and Incendiary; the legend names both without claiming distinction.
- Maps without a calibrated radar show an explicit unavailable state; there is no
  approximate coordinate fallback. Existing `assets/radars.json` remains authoritative.

## Validation

```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_opening_routes.py backend/tests/test_opening_routes_api.py backend/tests/test_review.py backend/tests/test_parser.py
.venv/Scripts/python.exe -m ruff check backend/app.py backend/review.py backend/opening_routes.py backend/tests/test_opening_routes*.py
cd frontend
npm test
npm run build
```

The backend tests include the repository's real `sample_match.json` fixture and
edge-case inputs for missing data, dates, the 30-second window and death cutoff.
Control tests verify seeking, Utility timing, hiding rounds, reset, evidence links,
elapsed-time playback, stopping at 30 and cleanup on filter change.
