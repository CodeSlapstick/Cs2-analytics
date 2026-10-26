import { useEffect, useRef } from "react";
import type { MatchEconomy } from "../../api";

export const ECONOMY_TEAM_COLORS = ["#b98300", "#6a55e0"] as const;

export function ReportEconomyChart({ data }: { data: MatchEconomy }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    node.dataset.ready = "false";
    let disposed = false;
    let chart: { setOption(option: unknown): void; resize(): void; dispose(): void } | undefined;
    void import("echarts").then((echarts) => {
      if (disposed || !node) return;
      chart = echarts.init(node, undefined, { renderer: "canvas", devicePixelRatio: 2 });
      chart.setOption({
        animation: false,
        grid: { left: 58, right: 18, top: 34, bottom: 36 },
        tooltip: { show: false },
        legend: { top: 0, data: data.teams },
        xAxis: { type: "category", name: "รอบ", data: data.rounds.map((round) => round.round_num), axisLabel: { interval: 0, fontSize: 9 } },
        yAxis: { type: "value", name: "มูลค่าอุปกรณ์ ($)", axisLabel: { formatter: (value: number) => `$${Math.round(value / 1000)}k` } },
        series: data.teams.map((team, index) => ({
          name: team,
          type: "line",
          connectNulls: false,
          showSymbol: true,
          symbolSize: 4,
          lineStyle: { width: 2, color: ECONOMY_TEAM_COLORS[index] },
          itemStyle: { color: ECONOMY_TEAM_COLORS[index] },
          data: data.rounds.map((round) => round.teams[team]?.equip ?? null),
        })),
      });
      chart.resize();
      requestAnimationFrame(() => { if (!disposed && node) node.dataset.ready = "true"; });
    }).catch(() => { if (node) node.dataset.ready = "error"; });
    return () => { disposed = true; chart?.dispose(); };
  }, [data]);
  return <div ref={ref} className="pr-economy-chart" data-report-chart data-ready="false" role="img" aria-label="กราฟมูลค่าอุปกรณ์ของทั้งสองทีมแยกตามรอบ" />;
}
