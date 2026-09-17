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
- **The model is back-of-house; the product shows facts.** Nothing on screen is a model's output (decision 2026-09-18: "เอา ML ไว้หลังบ้าน ไม่ต้องโชว์ให้ user", following 2026-09-17's "หน้า demo reviewer ก็คือหน้า demo reviewer"). The round page shows what the demo recorded; `/analysis` shows counted deaths from the team's own matches measured against the professional reference set. `research/grid_ml1.py` still defines what the reference set is and how the 32×32 grid is cut, and `research/site_ml.py` still powers "อ่านทางเราออกไหม", but there is no page, button or endpoint that displays hotspots, fight types or per-cell duel-win rates to a user.
- **One way of drawing a map.** Every map in the product is the same soft heatmap — weighted circles at cell centres, blurred, a continuous ramp where darker = more — with the same zone labels and the same hover, where a table row highlights its zone on the map. Colour is never assigned arbitrarily: the ramp follows the side being viewed (CT blue, T orange, both sides red), ordered values get an ordered ramp, and the two saturated side hues are never reused for anything else. Comparisons are always shares, never raw counts, because the two sets hold different numbers of matches.
- **Choices explain themselves.** The three analysis modes are cards with a one-line answer each ("ตรงไหนเราตายบ่อยกว่าทีมอาชีพ", …) so a first-time viewer never has to click to find out; rendering knobs (radius / blur / opacity) are folded away under "ปรับการแสดงผล".
- **Players are numbers, not colours.** Every player is identified by side colour (CT blue / T orange) plus a number 1–5 that is the same in the team list, on the map and in the timeline; names appear on the map only for the selected or highlighted player.
- **Facts, never judgments.** The product reports what happened and the dataset's numbers with their source; it never grades a player.
- **Upload any demo.** Any CS2 `.dem` the team records can be uploaded and parsed automatically.
- **The team's own demos never train the model.** Reference demos (`demos/reference/`, `matches.source='reference'`) and uploads (`demos/uploads/`, `source='upload'`) are separated on disk and in the database; no training script reads the upload folder, and `matches.source` defaults to `'upload'` so an unverified match can never drift into the training set. The `/analysis` page uses that separation as its feature: it measures the team's uploaded matches **against** the reference set the model learned from, rather than against itself.

## Operating Context

- Sessions are collaborative review: several people looking at one laptop, or a projector / shared screen.
- Landing: after login the first page is **สถิติของฉัน** (`/player`) — the player's own numbers, with their Steam avatar in the top bar; nav order is สถิติของฉัน → แมตช์ → เครื่องมือวิเคราะห์. Accounts without a Steam link land on an empty state that says why and offers the two pages that work without it.
- Main flow: log in (or one-click guest) → pick a match in the sidebar (or upload a demo) → step through rounds with the round strip or ← / → → choose the side to shade, select deaths, players and grenades on the map, press play to watch positions over time.
- Second flow (`/analysis`): compare the team's uploaded matches with the professional set on the same map. The page speaks plain Thai — "ทีมอาชีพ", not "training set" — because the people using it do not need the ML vocabulary; it answers where this team dies more often than the professional dataset and by how much. The death map is coloured by the side being viewed (CT blue, T orange, both sides red) in five steps, pale for few deaths to deep for many. Cells where the team has fewer than 3 deaths stay unpainted, because a one-match sample cannot support a claim.
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
- **Access:** username/password or Steam login (JWT in an httpOnly cookie); the whole app sits behind login on one origin (port 3000). A one-click **guest** account (`GUEST_LOGIN=1`) can view everything but cannot upload demos (`POST /api/demos` answers 403).
- **Look:** light "coach's desk" theme (`frontend/src/styles.css`): paper-coloured page, the map is the only dark surface, the only saturated colours are CT blue and T orange (red = opposing side wins duels there / errors, green = survived). Type: Anuphan for text, Chakra Petch for identifying numbers. The `/login` page keeps its own dark tactical world by design.

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
3. **One round, one readable map.** The core unit is a single round understood at a glance; everything else supports it. Every symbol drawn on the map is explained in the key under it.
4. **Shareable exact views.** Any view the team is discussing can be reopened by anyone from the URL.
5. **Readable together.** Designed for a group looking at one screen: laptop-first, legible on a projector.
