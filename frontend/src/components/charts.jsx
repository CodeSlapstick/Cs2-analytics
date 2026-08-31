/**
 * กราฟทั้งหมดของระบบ — ใช้ Apache ECharts
 *
 * Sprint 1 เปลี่ยนจาก Recharts มาเป็น ECharts ด้วยสองเหตุผล
 *   1) เรดาร์ของ Recharts กำหนดช่วงแกนเป็นค่าติดลบ (-10 ถึง +10) ไม่ได้ตรง ๆ
 *      ซึ่งเป็นสเกลของ KPI เรา ทำให้ผู้เล่นที่คะแนนติดลบดูเหมือนมีค่าเป็น 0
 *   2) ข้อมูลจากไฟล์ .dem จริงจะเยอะขึ้นมาก (heatmap พิกัดคิลใน sprint ถัดไป
 *      คือหลักพันจุดต่อแมตช์) ECharts วาดบน canvas จึงไหวกว่า SVG ของ Recharts
 *
 * import แบบเลือกเฉพาะโมดูลที่ใช้ (`echarts/core` + echarts.use) ไม่ใช่ `from 'echarts'`
 * ทั้งก้อน — วัดจริงด้วย npm run build: 772 KB (gzip 259 KB) เทียบกับ 1,334 KB
 * (gzip 446 KB) ถ้า import ทั้งก้อน
 * ⚠️ จะใช้กราฟชนิดใหม่ ต้องมาเพิ่มชนิดนั้นใน echarts.use() ข้างล่างนี้ด้วย
 *    ไม่งั้นกราฟจะไม่ขึ้นและไม่มี error บอกให้รู้ตัว
 */
import { useEffect, useRef } from 'react';
import * as echarts from 'echarts/core';
import { RadarChart, LineChart, BarChart } from 'echarts/charts';
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  MarkLineComponent,
  DatasetComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

echarts.use([
  RadarChart, LineChart, BarChart,
  GridComponent, TooltipComponent, LegendComponent, MarkLineComponent, DatasetComponent,
  CanvasRenderer,
]);

// สีชุดเดียวกับตัวแปรใน styles.css (ECharts อ่าน CSS variable เองไม่ได้)
const C = {
  gold: '#e0a33e',
  blue: '#5b9bf3',
  line: '#1e3459',
  muted: '#8ea3c4',
  faint: '#546b90',
  panel: '#102647',
  ink: '#e8eefb',
  good: '#43c08a',
  bad: '#e8615d',
};

const TOOLTIP = {
  backgroundColor: C.panel,
  borderColor: C.line,
  textStyle: { color: C.ink, fontSize: 12 },
};

export const SERIES_COLORS = [C.gold, C.blue];

/**
 * ครอบ ECharts ให้ใช้แบบ React ได้
 * - สร้าง instance ครั้งเดียวต่อ element
 * - ปรับขนาดตามกล่องด้วย ResizeObserver (การ์ดในกริดเปลี่ยนความกว้างได้ตลอด)
 * - dispose ตอน unmount ไม่งั้น canvas ค้างใน memory เวลาเปลี่ยนหน้าไปมา
 */
function EChart({ option, height = 300, className }) {
  const ref = useRef(null);
  const chartRef = useRef(null);

  useEffect(() => {
    if (!ref.current) return undefined;
    const chart = echarts.init(ref.current, null, { renderer: 'canvas' });
    chartRef.current = chart;
    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(ref.current);
    return () => {
      ro.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    // notMerge = true เพื่อให้ series ที่หายไป (เช่นเปลี่ยนจากเทียบ 2 คนเหลือ 1 คน) หายจริง
    chartRef.current?.setOption(option, { notMerge: true });
  }, [option]);

  return <div ref={ref} className={className} style={{ width: '100%', height }} />;
}

const fmt = (v) => (v === null || v === undefined ? '—' : Number(v).toFixed(2));

/**
 * เรดาร์ KPI 5 มิติ — เทียบได้สูงสุด 2 ชุด (ผู้เล่นเรา vs คู่แข่ง หรือ ทีม vs ทีม)
 * แกนตรึงที่ -10 ถึง +10 เสมอ ไม่ปรับตามข้อมูล เพื่อให้เรดาร์ของคนละหน้าเทียบกันด้วยตาได้
 */
export function RatingRadar({ series, labels, height = 320 }) {
  const dims = Object.keys(labels);
  const option = {
    color: SERIES_COLORS,
    tooltip: { ...TOOLTIP, trigger: 'item' },
    legend: series.length > 1
      ? { bottom: 0, textStyle: { color: C.muted, fontSize: 12 }, data: series.map((s) => s.name) }
      : undefined,
    radar: {
      indicator: dims.map((d) => ({ name: labels[d], min: -10, max: 10 })),
      shape: 'polygon',
      splitNumber: 4,
      axisName: { color: C.muted, fontSize: 12 },
      splitLine: { lineStyle: { color: C.line } },
      splitArea: { areaStyle: { color: ['rgba(16,38,71,.35)', 'rgba(11,26,51,.35)'] } },
      axisLine: { lineStyle: { color: C.line } },
    },
    series: [
      {
        type: 'radar',
        emphasis: { focus: 'series' },
        data: series.map((s, i) => ({
          name: s.name,
          // มิติที่ยังไม่มีข้อมูล (null) วาดเป็น 0 = ระดับกลาง ไม่ใช่จุดต่ำสุด
          value: dims.map((d) => Number(s.rating?.[d] ?? 0)),
          areaStyle: { opacity: 0.25 },
          lineStyle: { width: 2 },
          symbolSize: 5,
          itemStyle: { color: SERIES_COLORS[i % SERIES_COLORS.length] },
        })),
      },
    ],
  };
  return <EChart option={option} height={height} />;
}

/**
 * ฟอร์มย้อนหลัง — คะแนนรวม KPI ต่อแมตช์ เรียงจากเก่าไปใหม่
 * มีเส้นประที่ 0 เพื่อให้เห็นทันทีว่าแมตช์ไหนอยู่เหนือ/ใต้ค่ากลาง
 */
export function FormChart({ matches, height = 260 }) {
  const data = [...matches].reverse();
  const option = {
    color: [C.gold],
    grid: { left: 38, right: 16, top: 18, bottom: 28 },
    tooltip: {
      ...TOOLTIP,
      trigger: 'axis',
      formatter: (params) => {
        const p = params[0];
        const m = data[p.dataIndex];
        const result = { win: 'ชนะ', loss: 'แพ้', tie: 'เสมอ' }[m.outcome] || '';
        return [
          `แมตช์ที่ ${p.dataIndex + 1} · ${m.map_name}`,
          `ผล: ${result} ${m.score ? `${m.score[0]}–${m.score[1]}` : ''}`,
          `คะแนน KPI: ${fmt(m.performance_rating)}`,
          `ADR: ${fmt(m.adr)} · K/D: ${m.kills}/${m.deaths}`,
        ].join('<br/>');
      },
    },
    xAxis: {
      type: 'category',
      data: data.map((_, i) => i + 1),
      axisLine: { lineStyle: { color: C.line } },
      axisLabel: { color: C.faint, fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: C.faint, fontSize: 11 },
      splitLine: { lineStyle: { color: C.line } },
    },
    series: [
      {
        type: 'line',
        smooth: true,
        showSymbol: data.length <= 30,
        symbolSize: 6,
        lineStyle: { width: 2 },
        // จุดสีเขียว/แดงตามผลแพ้ชนะของแมตช์นั้น
        itemStyle: {
          color: (p) => (data[p.dataIndex]?.outcome === 'win' ? C.good : data[p.dataIndex]?.outcome === 'loss' ? C.bad : C.muted),
        },
        data: data.map((m) => Number(m.performance_rating ?? 0)),
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { color: C.muted, type: 'dashed', width: 1 },
          data: [{ yAxis: 0 }],
          label: { show: false },
        },
      },
    ],
  };
  return <EChart option={option} height={height} />;
}

/**
 * แท่งเทียบรายมิติระหว่างผู้เล่นสองคน — บวก = ฝั่งเราดีกว่า
 * ใช้ในหน้า "เทียบผู้เล่น" คู่กับเรดาร์ (เรดาร์ดูภาพรวม แท่งดูส่วนต่างเป็นตัวเลข)
 */
export function DiffBars({ diff, labels, names, height = 260 }) {
  const dims = Object.keys(labels);
  const values = dims.map((d) => Number(diff?.[d] ?? 0));
  const option = {
    grid: { left: 90, right: 24, top: 10, bottom: 28 },
    tooltip: {
      ...TOOLTIP,
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params) => {
        const p = params[0];
        const better = p.value >= 0 ? names[0] : names[1];
        return `${p.name}<br/>ส่วนต่าง ${fmt(Math.abs(p.value))} — ${better} ได้เปรียบ`;
      },
    },
    xAxis: {
      type: 'value',
      axisLabel: { color: C.faint, fontSize: 11 },
      splitLine: { lineStyle: { color: C.line } },
    },
    yAxis: {
      type: 'category',
      data: dims.map((d) => labels[d]),
      axisLabel: { color: C.muted, fontSize: 12 },
      axisLine: { lineStyle: { color: C.line } },
    },
    series: [
      {
        type: 'bar',
        data: values.map((v) => ({ value: v, itemStyle: { color: v >= 0 ? C.good : C.bad } })),
        barWidth: '55%',
        label: {
          show: true,
          position: 'right',
          color: C.muted,
          fontSize: 11,
          formatter: (p) => fmt(p.value),
        },
      },
    ],
  };
  return <EChart option={option} height={height} />;
}

/** แท่งเทียบผู้เล่นในทีม เรียงจากคะแนน KPI มากไปน้อย */
export function TeamBars({ members, height = 280 }) {
  const rows = [...members]
    .filter((m) => m.kpi_score !== null && m.kpi_score !== undefined)
    .sort((a, b) => a.kpi_score - b.kpi_score);
  const option = {
    grid: { left: 96, right: 30, top: 10, bottom: 28 },
    tooltip: { ...TOOLTIP, trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: {
      type: 'value',
      axisLabel: { color: C.faint, fontSize: 11 },
      splitLine: { lineStyle: { color: C.line } },
    },
    yAxis: {
      type: 'category',
      data: rows.map((m) => m.nickname),
      axisLabel: { color: C.muted, fontSize: 12 },
      axisLine: { lineStyle: { color: C.line } },
    },
    series: [
      {
        type: 'bar',
        name: 'คะแนน KPI',
        data: rows.map((m) => ({
          value: m.kpi_score,
          itemStyle: { color: m.kpi_score >= 0 ? C.gold : C.bad },
        })),
        barWidth: '55%',
        label: { show: true, position: 'right', color: C.muted, fontSize: 11, formatter: (p) => fmt(p.value) },
      },
    ],
  };
  return <EChart option={option} height={height} />;
}
