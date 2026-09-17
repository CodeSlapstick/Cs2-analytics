# CS2 Scouting — Documentation Diagrams

Seven diagrams covering requirements, data, process, and architecture. Each one has a
standalone `.md` file holding the editable source (Mermaid or PlantUML) plus a rendered
`.png` next to it, so the images can be dropped straight into a report or slide deck.

All numbers shown in the diagrams come from the real pipeline output
(`output/grid_ml1.json` — 50 reference matches on `de_mirage`, 7,158 duels).

| # | Diagram | Source | Syntax |
|---|---|---|---|
| 1 | Use Case | [01-use-case.md](01-use-case.md) | PlantUML |
| 2 | ER Diagram | [02-er-diagram.md](02-er-diagram.md) | Mermaid |
| 3 | Data Flow / Pipeline | [03-pipeline.md](03-pipeline.md) | Mermaid |
| 4 | Sequence | [04-sequence.md](04-sequence.md) | Mermaid |
| 5 | Class | [05-class-diagram.md](05-class-diagram.md) | Mermaid |
| 6 | System Architecture | [06-architecture.md](06-architecture.md) | Mermaid |
| 7 | ML Decision Flow | [07-ml-flow.md](07-ml-flow.md) | Mermaid |

---

## 1. Use Case Diagram

![Use case diagram](01-use-case.png)

The Player/Coach triggers upload, browsing and filtering directly, while *Parse Demo* is an internal job the background worker performs through an `<<include>>` from *Upload Demo*.

## 2. ER Diagram

![ER diagram](02-er-diagram.png)

Conceptual data model — one match holds many rounds, each round holds many duels, and players connect to matches many-to-many through `MATCH_PLAYER`.

## 3. Data Flow / Pipeline Diagram

![Pipeline diagram](03-pipeline.png)

A `.dem` file is parsed, turned into features, stored, then fanned out to MeanShift and KMeans — and nothing reaches the screen until all three validation checks pass.

## 4. Sequence Diagram

![Sequence diagram](04-sequence.png)

Upload returns `202` immediately and the frontend polls every 2 seconds while the worker parses in the background, so the user never waits on a blocking request.

## 5. Class Diagram

![Class diagram](05-class-diagram.png)

Each analysis responsibility is its own module: parsing feeds feature extraction, which feeds the two clustering models, which both hand their output to the validator.

## 6. System Architecture / Component Diagram

![Architecture diagram](06-architecture.png)

Solid arrows are the four components running today; the two dotted components — Statistical KDE Mode and Multi-Demo Aggregation — are designed but not yet built.

## 7. ML Algorithm / Decision Flowchart

![ML decision flowchart](07-ml-flow.png)

The clustering only survives if it clears three independent gates: silhouette picks `k = 3`, bootstrap resampling confirms stability, and the held-out CT win rate separates the clusters (68.6 / 58.7 / 41.7 % against a map mean of 54.0 %).

---

## Regenerating the images

Mermaid diagrams (needs `@mermaid-js/mermaid-cli`):

```bash
mmdc -i 03-pipeline.md -o 03-pipeline.png -b "#F5F6FA" -s 2
```

The use case diagram is PlantUML. With Java installed:

```bash
java -jar plantuml.jar 01-use-case.md -o .
```

Without Java, paste the `plantuml` block into <https://www.plantuml.com/plantuml> — that
is how `01-use-case.png` in this folder was produced.

## Also in this folder

Three hand-built SVG diagrams used inside `docs/progress1-slides-v3.pptx`. They are plain
HTML with inline SVG, so they can be opened in a browser and edited directly:

- `architecture.html` — the same architecture view, styled to match the slide deck
- `data-pipeline.html` — reference vs. upload data separation
- `validation.html` — the three validation gates
