# Coach ML experiment

Open `/coach` from the Coach navigation tab. Pick an uploaded match, T or CT and
a round. The page offers up to three opening-pattern candidates and reference
round links, or an explicit unavailable reason. Selection lives in URL parameters.

## What is trained

The dataset has no coach-labeled tactic names. This experiment discovers four
opening clusters separately for T and CT using real Mirage player callouts at
5/15/25 seconds and recorded Utility counts in the first 30 seconds. Names describe
the centroid (e.g. Mid pressure or Balanced hold); they are not ground-truth plans.

A 64-tree shallow Random Forest learns which of those patterns was used in winning
professional rounds, conditioned on pre-round team equipment and pistol status.
The recommendation input has no target-round movement, Utility or outcome.
Output weights are a distribution over patterns used by winning references,
**not a round-win probability or a causal estimate of the best tactic**.

Only `source='reference'` is queried for training. The validation split holds out
entire matches, with scaling and clustering fitted on training matches only.
Accuracy measures imitation of the pattern in winning held-out rounds; the
baseline always predicts the most frequent winning training pattern. After
validation, the deployed taxonomy/policy refits on all eligible reference rounds.
Training-set match IDs are blocked from receiving inference recommendations.

## First actual training run

Reference source: the application's PostgreSQL database, 50 professional Mirage
matches. Complete samples: T 708 team-rounds; CT 719 team-rounds. 37 training
matches and 13 held-out matches, random seed 42.

| Side | Winning held-out rounds | Pattern accuracy | Majority baseline |
| --- | ---: | ---: | ---: |
| T | 113 | 43.4% | 38.9% |
| CT | 91 | 65.9% | 50.5% |

One held-out split is an initial experiment, not a robust performance claim. No
causal comparison between tactics was performed. Tactical options require at
least 20 winning reference rounds across three matches. If evaluation does not
beat baseline, the UI marks options as exploratory.

## Ownership and rerun

- `backend/coach.py`: pure context/snapshot derivation, taxonomy assignment and
  portable JSON inference. Cached artifact loading refreshes when its mtime changes.
- `backend/coach_data.py`: common SQL adapter for training and inference.
- `research/coach_ml.py`: offline fitting, match-held-out evaluation and JSON export.
- `backend/app.py`: authenticated `/api/coach/{demo_file}?side=t|ct` orchestration.
- `frontend/src/CoachPage.tsx`, `coach.css`: match/round navigation and ML evidence UI.
- `frontend/src/api.ts`, `i18n/en-coach.ts`: typed transport and localization.

Training never runs in an HTTP request and never modifies uploaded data or the
reference flag. No database migration is needed. The generated artifact is
`output/coach_model.json` (ignored, mounted into the API container).

```powershell
# Use the same reference database as the running app:
docker compose exec -T api python research/coach_ml.py --map de_mirage
# Or the local DATABASE_URL (may point to a different database):
.venv/Scripts/python.exe research/coach_ml.py --map de_mirage
```

The reference dataset needs at least 120 complete team-rounds over eight matches
per side. Missing 5-person equipment or recorded snapshots are not imputed. This
version supports Mirage only and inherits the stored start_tick provenance and
Utility coverage limitations described in `docs/opening-route.md`. Existing
data combines Incendiary with Molotov. Other maps/model absence produce unavailable
states instead of fallback recommendations.
