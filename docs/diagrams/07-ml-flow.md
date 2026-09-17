# 7. ML Algorithm / Decision Flowchart

Two unsupervised branches run over the same duel data, then three independent checks
decide whether the structure is real. The CT win rate is held out of both models and
only re-enters at the last gate.

All values are the ones actually produced by `research/grid_ml1.py`
(50 matches · `de_mirage` · 7,158 duels).

```mermaid
flowchart TD
    A["Duel data in<br/>7,158 duels, outcome hidden"] --> B["Run MeanShift<br/>bandwidth = 300"]
    A --> D["Build 32x32 grid cells<br/>keep cells with >= 10 duels<br/>192 of 341 cells"]

    B --> C["Extract hotspots<br/>17 found, 75% of all duels"]

    D --> E["Run KMeans for k = 2..8"]
    E --> F["Compute silhouette per k"]
    F --> G{"Highest silhouette?"}
    G -->|"k = 3, score 0.285"| H["Select k = 3"]
    G -->|"other k scores lower"| E

    H --> I["Bootstrap resample 20x"]
    I --> J{"ARI stable?"}
    J -->|"no - structure is noise"| X["Reject clustering"]
    J -->|"yes - 77% hotspots recur"| K["Assign fight-type clusters"]

    C --> L["Hold out CT win rate<br/>never seen during fitting"]
    K --> L

    L --> M{"Win rate differs<br/>across clusters?"}
    M -->|"no - clusters meaningless"| X
    M -->|"yes - 68.6 / 58.7 / 41.7 %<br/>vs map mean 54.0%"| N["Output:<br/>validated cluster types<br/>+ hotspot map"]

    classDef data fill:#DCE3F7,stroke:#3B4570,color:#1B1F3B
    classDef model fill:#C9D2EE,stroke:#3B4570,color:#1B1F3B
    classDef gate fill:#FFE0D2,stroke:#FF6B35,color:#1B1F3B
    classDef good fill:#C7E9E3,stroke:#3B4570,color:#1B1F3B
    classDef bad fill:#FECACA,stroke:#B91C3C,color:#1B1F3B

    class A,D data
    class B,C,E,F,H,I,K model
    class G,J,M,L gate
    class N good
    class X bad
```

![ML decision flowchart](07-ml-flow.png)
