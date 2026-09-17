# 4. Sequence Diagram — upload a demo and view results

Matches the shipped behaviour: the upload returns `202` immediately with a status URL,
the worker parses in the background, and the frontend polls every 2 seconds until the
match reports `done`.

```mermaid
sequenceDiagram
    autonumber
    actor U as Player / Coach
    participant FE as Frontend (React)
    participant API as Backend API (FastAPI)
    participant W as awpy Parser (worker)
    participant DB as Database (PostgreSQL)

    U->>FE: drag .dem onto upload box
    FE->>API: POST /api/demos (multipart)
    API->>DB: INSERT match (status = queued)
    API-->>FE: 202 Accepted + status_url
    API->>W: enqueue parse_demo(match_id)

    Note over W: runs in its own container,<br/>user does not wait on it

    loop every 2 s until done
        FE->>API: GET /api/matches/{id}
        API->>DB: SELECT status
        DB-->>API: queued / parsing / done
        API-->>FE: status
    end

    W->>W: parse .dem with awpy
    W->>W: feature extraction<br/>(opening · trade · KAST · clutch)
    W->>DB: INSERT rounds, kills, positions
    W->>DB: UPDATE match status = done

    FE->>API: GET /api/analysis/deaths?map&side&rounds&players
    API->>DB: aggregate deaths into 32x32 grid
    DB-->>API: cell counts + shares
    API->>API: read cached output/grid_ml1.json
    API-->>FE: overlay JSON + radar image path
    FE-->>U: render heatmap
```

![Sequence diagram](04-sequence.png)
