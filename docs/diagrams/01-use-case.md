# 1. Use Case Diagram — CS2 Scouting

PlantUML (Mermaid has no native use-case notation, so this one diagram uses PlantUML).

**Who triggers what**

- **Player / Coach** triggers everything they see: upload, browse, filter.
- **Background Worker** is a secondary (non-human) actor. It performs *Parse Demo*,
  which is pulled in by *Upload Demo* through an `<<include>>` — the user never
  starts parsing directly.
- *Filter by Round / Side / Player* is an `<<extend>>`: the heatmap and the weakness
  view work without it, filtering is optional refinement.

> **Note on "Export Heatmap Image":** this use case is marked `<<removed>>`. It existed in
> an earlier build and was taken out of the current one, so it is shown greyed to keep the
> diagram honest about what ships today. Delete the node if the report should only show
> live features.

```plantuml
@startuml
left to right direction
skinparam shadowing false
skinparam packageStyle rectangle
skinparam backgroundColor #F5F6FA
skinparam actor {
  BorderColor #1B1F3B
  BackgroundColor #FFE0D2
}
skinparam usecase {
  BorderColor #3B4570
  BackgroundColor #DCE3F7
  BorderColor<<system>> #3B4570
  BackgroundColor<<system>> #C7E9E3
  BorderColor<<removed>> #8A8FA3
  BackgroundColor<<removed>> #E3E5EE
  FontColor<<removed>> #8A8FA3
}

actor "Player / Coach" as user
actor "Background Worker" as worker <<secondary>>

rectangle "CS2 Scouting Platform" {
  usecase "Upload Demo" as UC1
  usecase "Parse Demo" as UC2 <<system>>
  usecase "View Death Heatmap" as UC3
  usecase "View Player Profile" as UC4
  usecase "View Opponent Weaknesses\n(clustering results)" as UC5
  usecase "Filter by Round / Side / Player" as UC6
  usecase "Export Heatmap Image" as UC7 <<removed>>
}

user --> UC1
user --> UC3
user --> UC4
user --> UC5

UC1 ..> UC2 : <<include>>
worker --> UC2

UC6 ..> UC3 : <<extend>>
UC6 ..> UC5 : <<extend>>
UC7 ..> UC3 : <<extend>>

note bottom of UC2
  Runs in the RQ worker container.
  awpy -> PostgreSQL. No user interaction.
end note

note bottom of UC7
  Removed from the current build.
end note
@enduml
```

![Use case diagram](01-use-case.png)
