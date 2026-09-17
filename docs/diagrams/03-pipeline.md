# 3. Data Flow / Pipeline Diagram — CS2 Scouting

End-to-end: a `.dem` file goes in, two unsupervised models run over it, both get
validated, and only then does anything reach the screen.

Real numbers from `output/grid_ml1.json` (50 reference matches on `de_mirage`):
7,158 duels · 17 hotspots · 192 of 341 grid cells pass the 10-duel threshold · k = 3.

```mermaid
flowchart LR
    A["Demo Upload<br/>.dem file"] --> B["Parse with awpy<br/>backend/parser.py"]
    B --> C["Feature Extraction<br/>position · timing · economy"]
    C --> D[("Store in Database<br/>PostgreSQL")]

    D --> E["MeanShift<br/>Hotspot Analysis<br/>bandwidth = 300"]
    D --> F["KMeans<br/>Fight-Type Clustering<br/>32x32 grid, k = 3"]

    E --> G{"Validation"}
    F --> G

    G --> G1["silhouette score<br/>0.285 at k = 3"]
    G --> G2["bootstrap stability<br/>77% hotspots recur"]
    G --> G3["held-out CT win rate<br/>68.6 / 58.7 / 41.7 %"]

    G1 --> H["Visualization<br/>React frontend"]
    G2 --> H
    G3 --> H

    H --> H1["Death heatmap<br/>/analysis"]
    H --> H2["Cluster context<br/>round review page"]

    classDef store fill:#C7E9E3,stroke:#3B4570,color:#1B1F3B
    classDef model fill:#C9D2EE,stroke:#3B4570,color:#1B1F3B
    classDef check fill:#FFE0D2,stroke:#FF6B35,color:#1B1F3B
    classDef ui fill:#DCE3F7,stroke:#3B4570,color:#1B1F3B

    class D store
    class E,F model
    class G,G1,G2,G3 check
    class H,H1,H2 ui
```

![Pipeline diagram](03-pipeline.png)
