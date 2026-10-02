// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { PlayerBehaviorSection } from "./AnalysisPage";
import { LangProvider } from "./i18n";

const renderBehavior = (node: ReactNode) => render(<LangProvider>{node}</LangProvider>);

describe("player behavior presentation", () => {
  it("keeps T and CT separate and describes signals neutrally", () => {
    renderBehavior(<PlayerBehaviorSection loading={false} error={null} data={{
      available: true,
      players: [
        { steamid: "1", name: "ผู้เล่น一", side: "t", rounds: 8, available: true, role: "Entry", distance: 1.2, margin: .3,
          signals: [{ feature: "early_engagement_rate", direction: "higher", z: 1.1, value: .5 }] },
        { steamid: "1", name: "ผู้เล่น一", side: "ct", rounds: 3, available: false, reason: "insufficient_rounds", minimum_rounds: 5 },
      ],
      source: { kind: "reference_only", matches: 50, version: 2, model: "kmeans" },
    }} />);
    expect(screen.getAllByText("ผู้เล่น一")).toHaveLength(2);
    expect(screen.getByText("พบมากกว่าค่ากลางอ้างอิง")).toBeTruthy();
    expect(screen.getByText(/ข้อมูลยังไม่พอ/)).toBeTruthy();
    expect(screen.queryByText(/เก่ง|แย่|มั่นใจ/)).toBeNull();
  });

  it("shows a stable empty state when the model or map is unavailable", () => {
    renderBehavior(<PlayerBehaviorSection loading={false} error={null} data={{ available: false, reason: "unsupported_map" }} />);
    expect(screen.getByText("ยังแสดงรูปแบบการเล่นไม่ได้")).toBeTruthy();
    expect(screen.getByText("player_behavior_unsupported_map")).toBeTruthy();
  });
});
