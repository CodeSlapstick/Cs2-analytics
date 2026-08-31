/**
 * เทสต์สูตร KPI — รันด้วย `npm test`
 *
 * ตรงนี้คือหัวใจของโปรเจกต์ที่กรรมการจะถามแน่ ๆ ว่า "คะแนนคิดยังไง"
 * เทสต์จึงเขียนแบบอธิบายพฤติกรรมที่ตั้งใจ ไม่ใช่แค่ล็อกตัวเลขไว้เฉย ๆ
 */
import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import {
  computeKpi,
  metricsFromStats,
  normalizeWeights,
  scorePlayer,
  teamProfile,
  KPI_DIMENSIONS,
} from '../src/lib/kpi.js';

/** ผู้เล่นระดับกลาง: ตัวเลขทุกตัวตรงกับค่าฐานพอดี → ทุกมิติควรได้ 0 */
const AVERAGE_PLAYER = {
  rounds_played: 100,
  kills: 72,
  deaths: 68,
  headshot_kills: 32, // 32/72 ≈ 0.444
  damage: 7500,
  utility_damage: 420,
  grenades_thrown: 160,
  flash_assists: 6,
  opening_kills: 8,
  opening_deaths: 8, // opening 16 ครั้ง = 16% ของรอบ, ชนะครึ่ง
  trade_kills: 12,
  traded_deaths: 15, // 15/68 ≈ 0.22
  rounds_survived: 32,
  clutches_won: 2,
  clutches_attempted: 10,
};

describe('metricsFromStats', () => {
  test('แปลงตัวนับดิบเป็นอัตราส่วนได้ถูก', () => {
    const m = metricsFromStats(AVERAGE_PLAYER);
    assert.equal(m.adr, 75);
    assert.equal(m.kpr, 0.72);
    assert.equal(m.dpr, 0.68);
    assert.equal(+m.hs_pct.toFixed(3), 0.444);
    assert.equal(m.opening_attempt_rate, 0.16);
    assert.equal(m.opening_win_pct, 0.5);
    assert.equal(m.clutch_win_pct, 0.2);
  });

  test('หารศูนย์คืน null ไม่ใช่ 0 หรือ NaN', () => {
    const m = metricsFromStats({ rounds_played: 0, kills: 0, deaths: 0 });
    assert.equal(m.adr, null);
    assert.equal(m.hs_pct, null, 'ยังไม่เคยฆ่าใคร ≠ อัตรายิงหัว 0%');
    assert.equal(m.clutch_win_pct, null);
  });
});

describe('computeKpi', () => {
  test('ผู้เล่นที่ตรงค่าฐานทุกตัว ได้ทุกมิติใกล้ 0', () => {
    const kpi = computeKpi(metricsFromStats(AVERAGE_PLAYER));
    for (const dim of KPI_DIMENSIONS) {
      assert.ok(Math.abs(kpi[dim]) < 1, `${dim} ควรใกล้ 0 แต่ได้ ${kpi[dim]}`);
    }
  });

  test('ยิงแม่นขึ้น = มิติ aim สูงขึ้น และไม่ไปกระทบมิติอื่น', () => {
    const base = computeKpi(metricsFromStats(AVERAGE_PLAYER));
    const sharper = computeKpi(
      metricsFromStats({ ...AVERAGE_PLAYER, damage: 10000, kills: 95, headshot_kills: 55 })
    );
    assert.ok(sharper.aim > base.aim + 3, `aim ควรขึ้นชัดเจน (${base.aim} -> ${sharper.aim})`);
    assert.equal(sharper.utility, base.utility, 'มิติ utility ไม่ควรขยับตามการยิง');
  });

  test('คะแนนถูกตัดที่ ±10 แม้สถิติจะโหดเกินจริง', () => {
    const inhuman = computeKpi(
      metricsFromStats({
        ...AVERAGE_PLAYER,
        kills: 400,
        damage: 90000,
        headshot_kills: 400,
        deaths: 1,
      })
    );
    assert.ok(inhuman.aim <= 10, `ต้องไม่เกิน 10 แต่ได้ ${inhuman.aim}`);
    assert.ok(inhuman.positioning <= 10);
  });

  test('มิติที่ไม่มีข้อมูลเลยคืน null (ไม่ใช่ 0 ซึ่งแปลว่า "ระดับกลาง")', () => {
    const noClutch = computeKpi(
      metricsFromStats({ ...AVERAGE_PLAYER, clutches_attempted: 0, clutches_won: 0 })
    );
    assert.equal(noClutch.clutch, null);
    assert.ok(noClutch.aim !== null, 'มิติอื่นต้องยังคิดได้ตามปกติ');
  });
});

describe('น้ำหนัก KPI ที่โค้ชตั้งเอง', () => {
  test('normalizeWeights จำกัดช่วง 0–5 และเติมมิติที่ขาด', () => {
    const w = normalizeWeights({ aim: 99, positioning: -4, utility: 2 });
    assert.equal(w.aim, 5);
    assert.equal(w.positioning, 0);
    assert.equal(w.utility, 2);
    assert.equal(w.clutch, 1, 'มิติที่ไม่ได้ส่งมาใช้ค่าเริ่มต้น 1');
  });

  test('น้ำหนัก 0 = ตัดมิตินั้นออกจากคะแนนรวมไปเลย', () => {
    const rating = { aim: 10, positioning: 0, utility: 0, clutch: 0, opening: 0 };
    const onlyAim = scorePlayer(rating, normalizeWeights({ aim: 1, positioning: 0, utility: 0, clutch: 0, opening: 0 }));
    assert.equal(onlyAim, 10, 'เหลือแต่มิติ aim คะแนนต้องเท่ากับ aim');
    assert.equal(scorePlayer(rating, normalizeWeights({})), 2, 'ให้น้ำหนักเท่ากันหมด = ค่าเฉลี่ย');
  });

  test('scorePlayer คืน null เมื่อไม่มี rating', () => {
    assert.equal(scorePlayer(null, normalizeWeights({})), null);
  });
});

describe('teamProfile', () => {
  test('หามิติแข็งสุด/อ่อนสุดจากค่าเฉลี่ยของสมาชิก', () => {
    const members = [
      { rating: { aim: 4, positioning: -2, utility: 0, clutch: 1, opening: 2 } },
      { rating: { aim: 6, positioning: -4, utility: 0, clutch: 1, opening: 2 } },
      { rating: null }, // สมาชิกที่ยังไม่มีข้อมูล ต้องไม่ถูกนับ
    ];
    const { average, strongest, weakest } = teamProfile(members);
    assert.equal(average.aim, 5);
    assert.equal(strongest.dimension, 'aim');
    assert.equal(weakest.dimension, 'positioning');
  });

  test('ทีมที่ยังไม่มีสมาชิกที่มีข้อมูล คืน null ทั้งหมด', () => {
    const { average, strongest } = teamProfile([{ rating: null }]);
    assert.equal(average, null);
    assert.equal(strongest, null);
  });
});
