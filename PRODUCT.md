# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

A Counter-Strike 2 team (players and their coach) reviewing its **own** matches after they are played. They sit together, usually around one laptop or a shared screen, open a match, and walk through it round by round to understand how each death happened: who died, where, when, to whom, and what utility was in play at that moment.

The same team uploads its own `.dem` files; the product is not limited to professional matches.

Secondary, near-term audience: the SP-404 Senior Project advisor and defense committee (UTCC STECH), who see the product demonstrated on a projector.

## Product Purpose

Turn a raw demo file into a round-by-round review the team can read in minutes instead of scrubbing through the replay. Upload a `.dem`, it is parsed in the background, and every round becomes one map with every death, shooter and grenade placed where and when it happened, plus context learned from a dataset of professional matches.

Success: after reviewing a round, the team can say what happened and where the fights were decided, backed by facts from the demo, without anyone being told they "played badly".

## Positioning

- **Round-by-round map story.** One map per round shows every death, the shooter, and every grenade (who threw it, where it landed, how long it lasted), with the moment each happened; selecting a death shows only the utility active at that second.
- **ML context per death.** Each death is placed in a grid-cell type and hotspot learned without labels (MeanShift + KMeans, `research/grid_ml1.py`) from 50 professional Mirage matches, so the team sees how that area of the map usually plays out across the dataset.
- **Facts, never judgments.** The product reports what happened and the dataset's numbers with their source; it never grades a player.
- **Upload any demo.** Any CS2 `.dem` the team records can be uploaded and parsed automatically.

## Operating Context

- Sessions are collaborative review: several people looking at one laptop, or a projector / shared screen.
- Main flow: log in → pick a match in the sidebar (or upload a demo) → step through rounds with the round strip or ← / → → select deaths, players and grenades on the map.
- All view state lives in the URL (`/matches/{demo_file}/rounds/{n}` plus query flags), so a teammate can open the exact same view from a shared link and refresh never loses the place.
- Parsing runs in a background worker; a freshly uploaded match shows progress and opens round 1 when done.

## Capabilities and Constraints

- **Interface language:** Thai, with Counter-Strike terms kept in English (CT, T, ADR, KAST, smoke, flash, HE, molotov, opening, trade, clutch, weapon names, map callouts).
- **Screens:** must work well on 1366–1536 px laptop screens (the common case) and must read from a distance on a projector.
- **Maps:** only Mirage and Dust2 have calibrated radar images (`assets/radars.json`); other maps are future work. The ML context model exists for Mirage only.
- **Data per death:** victim and attacker positions at the moment of death, weapon, headshot, flash/smoke/wallbang flags.
- **Movement over time:** player positions are recorded once per second (1 Hz) while the round is live, and only while a player is alive. The round page can play them back over time (โหมดเล่นย้อน: play/pause, scrub, 1×/2×/4×), revealing deaths, active utility and the planted bomb as the clock reaches them. The once-per-second sampling is stated on screen, because the motion between two samples is drawn to look continuous and is not recorded in the demo. There is no weapon, aim or view-angle replay.
- **Data per grenade:** thrower, type, throw position, landing position, land time, and end time for smokes and fires. Decoys have no landing position.
- **Feature definitions** (opening kill, trade within 5 s, buy type thresholds, clutch, ADR, KAST) are fixed in `backend/features.py` and must not be redefined in the UI.
- **Coordinates:** all game-to-pixel conversion happens in the backend (`backend/review.py`); the frontend never computes map positions.
- **Language rules enforced by tests** (`backend/tests/test_review.py`): the UI must never call the grid model's `ct_win` a "round win probability" ("โอกาสชนะรอบ", "win probability"), and must never use judging language about players ("เล่นแย่", "ยืนผิด").
- **Access:** username/password login (JWT in an httpOnly cookie); the whole app sits behind login on one origin (port 3000).

## Brand Commitments

- Product name as shown in the app: **CS2 SCOUTING** (repository: CS2 Scouting Platform).
- Voice: factual, neutral, analytical. Numbers from the dataset are always shown together with their source (for example "ทั้งดาต้าเซ็ต 50 แมตช์ …").

## Evidence on Hand

- 51 parsed matches in the database: 50 professional Mirage demos from HLTV plus one team-uploaded Dust2 match.
- `data/all_kills.csv`: kills from the 50 Mirage matches (7,270 death points used for radar calibration).
- `output/grid_ml1.json` (+ cells / hotspots CSV, map PNG): the unsupervised model's cell types and hotspots that the round page reads.
- `assets/maps/*.png` radar images and `assets/radars.json` calibration values.
- Absent, and not to be fabricated: user testimonials, usage metrics, user studies, team or customer names beyond the teams inside the demo files, and any accuracy claim for the model beyond what `research/grid_ml1.py` reports.

## Product Principles

1. **Facts, not verdicts.** Show what the demo recorded and what the dataset says; let the team draw the conclusion.
2. **Every model number carries its source.** Context from the ML model always says where it comes from, and is never presented as a prediction about the round.
3. **One round, one readable map.** The core unit is a single round understood at a glance; everything else supports it.
4. **Shareable exact views.** Any view the team is discussing can be reopened by anyone from the URL.
5. **Readable together.** Designed for a group looking at one screen: laptop-first, legible on a projector.
