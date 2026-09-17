# 5. Class Diagram — backend / analysis modules

The project is written as Python modules rather than a deep class hierarchy, so this
diagram models each module's responsibility as a class. Mapping to files:

| Class in diagram | Where it lives |
|---|---|
| `DemoParser` | `backend/parser.py` |
| `FeatureExtractor` | `backend/features.py` |
| `HotspotAnalyzer` | MeanShift section of `research/grid_ml1.py` |
| `FightTypeClassifier` | KMeans section of `research/grid_ml1.py` |
| `ClusterValidator` | validation section of `research/grid_ml1.py` |
| `HeatmapRenderer` | `backend/review.py` (`deaths_overlay`, `grid_overlay`) |

```mermaid
classDiagram
    class DemoParser {
        +str demo_path
        +int tickrate
        +parse() DemoData
        +extract_kills() list
        +extract_rounds() list
        +extract_positions() list
    }

    class FeatureExtractor {
        +int grid_n
        +int min_kills
        +build_duel_features(kills) DataFrame
        +to_grid_cells(x, y) tuple
        +cell_profile(cell) dict
    }

    class HotspotAnalyzer {
        +float bandwidth
        +int min_bin_freq
        +fit(positions) list
        +coverage() float
        +nearest_within(x, y) int
    }

    class FightTypeClassifier {
        +int k
        +list features
        +scan_k(2, 8) list
        +fit(cells) labels
        +name_clusters() dict
    }

    class ClusterValidator {
        +int n_boot
        +silhouette(labels) float
        +bootstrap_ari(n) float
        +holdout_win_rate(labels) dict
        +report() dict
    }

    class HeatmapRenderer {
        +RadarFrame frame
        +deaths_overlay(xs, ys) dict
        +grid_overlay(model) dict
        +cell_rect_pixel(cx, cy) tuple
    }

    class GridModel {
        +str map_name
        +dict clusters
        +dict cells
        +list hotspots
        +float ct_win_overall
    }

    DemoParser --> FeatureExtractor : feeds parsed rows
    FeatureExtractor --> HotspotAnalyzer : duel positions
    FeatureExtractor --> FightTypeClassifier : cell profiles
    FightTypeClassifier ..> ClusterValidator : labels to verify
    HotspotAnalyzer ..> ClusterValidator : hotspots to verify
    ClusterValidator --> GridModel : writes grid_ml1.json
    HeatmapRenderer o-- GridModel : reads cached model
```

![Class diagram](05-class-diagram.png)
