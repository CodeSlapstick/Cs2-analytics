# 2. ER Diagram — CS2 Scouting

Conceptual data model for the report.

**How this maps to the code as built** (`backend/models.py`):

| Diagram entity | Reality |
|---|---|
| `DEMO` + `MATCH` | one table, `matches` (the demo filename is a column on the match) |
| `ROUND` | `rounds` |
| `DUEL` | `kills` |
| `PLAYER` | `players` (keyed by `steam_id`) |
| `MATCH_PLAYER` | `match_players` — the many-to-many join between players and matches |
| `CLUSTER_RESULT` | **not a table** — clustering output lives in `output/grid_ml1.json`, which the API reads and caches |

`DEMO` and `CLUSTER_RESULT` are kept separate here because they are separate *concepts*
in the pipeline even though the storage differs.

```mermaid
erDiagram
    DEMO ||--|| MATCH : "parses into"
    MATCH ||--o{ ROUND : "has"
    ROUND ||--o{ DUEL : "contains"
    PLAYER ||--o{ DUEL : "is killer in"
    PLAYER ||--o{ DUEL : "is victim in"
    MATCH ||--o{ MATCH_PLAYER : "rosters"
    PLAYER ||--o{ MATCH_PLAYER : "appears in"
    MATCH ||--o{ CLUSTER_RESULT : "produces"

    DEMO {
        int id PK
        string filename
        string map
        datetime upload_date
        int match_id FK
    }

    MATCH {
        int id PK
        string team_a
        string team_b
        datetime date
    }

    ROUND {
        int id PK
        int match_id FK
        int round_number
        string winner_side
        bool bomb_planted
    }

    DUEL {
        int id PK
        int round_id FK
        int killer_id FK
        int victim_id FK
        float position_x
        float position_y
        string weapon
        int tick_time
    }

    PLAYER {
        int id PK
        string steam_id
        string name
    }

    MATCH_PLAYER {
        int match_id PK,FK
        string steam_id PK,FK
        string side
    }

    CLUSTER_RESULT {
        int id PK
        int match_id FK
        string cluster_type
        int grid_cell_x
        int grid_cell_y
        float ct_win_rate
    }
```

![ER diagram](02-er-diagram.png)
