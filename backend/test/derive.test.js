/**
 * เทสต์ชั้นคำนวณของ ETL — สร้างแมตช์เล็ก ๆ ที่รู้คำตอบล่วงหน้าแล้วตรวจทีละสูตร
 *
 * แมตช์ทดสอบ: 2 vs 2 (ทีม 2 = A,B / ทีม 3 = C,D) จำนวน 3 รอบ tickrate 64
 * ทุกกรณีที่เทสต์ตรงนี้เป็นเคสที่เคยคิดผิดได้ง่ายทั้งนั้น (trade, clutch, teamkill)
 */
import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { deriveMatch, validateMatch } from '../src/etl/derive.js';

const A = '76561198000000001';
const B = '76561198000000002';
const C = '76561198000000003';
const D = '76561198000000004';

const kill = (round, tick, actor, victim, extra = {}) => ({
  type: 'kill', round_number: round, tick, actor_steam64: actor, victim_steam64: victim,
  headshot: false, weapon: 'ak47', ...extra,
});

function baseDoc(rounds, events) {
  return {
    schema_version: 1,
    match: { external_id: 'test-1', map_name: 'de_mirage', tickrate: 64, source: 'sample' },
    players: [
      { steam64_id: A, name: 'A', team_number: 2 },
      { steam64_id: B, name: 'B', team_number: 2 },
      { steam64_id: C, name: 'C', team_number: 3 },
      { steam64_id: D, name: 'D', team_number: 3 },
    ],
    rounds,
    events,
  };
}

const statsOf = (result, id) => result.stats.find((s) => s.steam64_id === id);

describe('validateMatch', () => {
  test('ผ่านเมื่อข้อมูลครบ', () => {
    const doc = baseDoc([{ round_number: 1, winner_team_number: 2 }], []);
    assert.deepEqual(validateMatch(doc).errors, []);
  });

  test('ไม่ผ่านเมื่อไม่มี external_id หรือ rounds ข้ามลำดับ', () => {
    const noId = baseDoc([{ round_number: 1, winner_team_number: 2 }], []);
    noId.match.external_id = '';
    assert.ok(validateMatch(noId).errors.some((e) => e.includes('external_id')));

    const skipped = baseDoc(
      [{ round_number: 1, winner_team_number: 2 }, { round_number: 3, winner_team_number: 3 }],
      []
    );
    assert.ok(validateMatch(skipped).errors.some((e) => e.includes('1..N')));
  });

  test('เตือน (ไม่ error) เมื่อ event อ้างถึงคนที่ไม่อยู่ในรายชื่อผู้เล่น', () => {
    const doc = baseDoc(
      [{ round_number: 1, winner_team_number: 2 }],
      [kill(1, 100, '76561199999999999', C)]
    );
    const { errors, warnings } = validateMatch(doc);
    assert.deepEqual(errors, []);
    assert.ok(warnings.some((w) => w.includes('ไม่อยู่ในรายชื่อผู้เล่น')));
  });
});

describe('การนับคิล/เดธพื้นฐาน', () => {
  const doc = baseDoc(
    [{ round_number: 1, winner_team_number: 2 }],
    [
      kill(1, 1000, A, C, { headshot: true, assister_steam64: B }),
      kill(1, 2000, A, D),
    ]
  );
  const result = deriveMatch(doc);

  test('นับคิล เฮดช็อต และแอสซิสต์', () => {
    const a = statsOf(result, A);
    assert.equal(a.kills, 2);
    assert.equal(a.headshot_kills, 1);
    assert.equal(statsOf(result, B).assists, 1);
  });

  test('คนที่รอดจนจบรอบได้ rounds_survived', () => {
    assert.equal(statsOf(result, A).rounds_survived, 1);
    assert.equal(statsOf(result, C).rounds_survived, 0);
  });

  test('สรุปผลแพ้ชนะจากสกอร์รวม', () => {
    assert.equal(result.match.score_team2, 1);
    assert.equal(statsOf(result, A).won, true);
    assert.equal(statsOf(result, C).won, false);
  });
});

describe('opening duel', () => {
  test('คิลแรกของรอบเท่านั้นที่นับเป็น opening', () => {
    const result = deriveMatch(
      baseDoc(
        [{ round_number: 1, winner_team_number: 2 }],
        [kill(1, 500, A, C), kill(1, 900, A, D)]
      )
    );
    assert.equal(statsOf(result, A).opening_kills, 1);
    assert.equal(statsOf(result, C).opening_deaths, 1);
    assert.equal(statsOf(result, D).opening_deaths, 0, 'คนที่ตายคนที่สองไม่ใช่ opening death');
  });

  test('แต่ละรอบมี opening ของตัวเอง', () => {
    const result = deriveMatch(
      baseDoc(
        [
          { round_number: 1, winner_team_number: 2 },
          { round_number: 2, winner_team_number: 3 },
        ],
        [kill(1, 500, A, C), kill(2, 500, C, A)]
      )
    );
    assert.equal(statsOf(result, A).opening_kills, 1);
    assert.equal(statsOf(result, C).opening_kills, 1);
  });
});

describe('trade kill', () => {
  test('ล้างแค้นให้เพื่อนภายใน 5 วินาที = trade', () => {
    // C ฆ่า A ที่ tick 1000 -> B ฆ่า C ที่ tick 1200 (ห่าง ~3 วินาทีที่ 64 tick)
    const result = deriveMatch(
      baseDoc([{ round_number: 1, winner_team_number: 2 }], [kill(1, 1000, C, A), kill(1, 1200, B, C)])
    );
    assert.equal(statsOf(result, B).trade_kills, 1);
    assert.equal(statsOf(result, A).traded_deaths, 1);
  });

  test('เกิน 5 วินาทีแล้วไม่นับเป็น trade', () => {
    // ห่าง 400 tick ที่ 64 tick ≈ 6.25 วินาที
    const result = deriveMatch(
      baseDoc([{ round_number: 1, winner_team_number: 2 }], [kill(1, 1000, C, A), kill(1, 1401, B, C)])
    );
    assert.equal(statsOf(result, B).trade_kills, 0);
    assert.equal(statsOf(result, A).traded_deaths, 0);
  });

  test('ฆ่าคนที่ไม่ได้ฆ่าเพื่อนเรา ไม่ใช่ trade', () => {
    const result = deriveMatch(
      baseDoc([{ round_number: 1, winner_team_number: 2 }], [kill(1, 1000, C, A), kill(1, 1100, B, D)])
    );
    assert.equal(statsOf(result, B).trade_kills, 0);
  });
});

describe('clutch', () => {
  test('เหลือคนเดียวเจอศัตรู 1 คนแล้วทีมชนะ = ชนะคลัตช์', () => {
    // C ฆ่า A -> เหลือ B คนเดียวสู้กับ C,D -> B เก็บทั้งคู่ ทีม 2 ชนะรอบ
    const result = deriveMatch(
      baseDoc(
        [{ round_number: 1, winner_team_number: 2 }],
        [kill(1, 1000, C, A), kill(1, 2000, B, C), kill(1, 3000, B, D)]
      )
    );
    const b = statsOf(result, B);
    assert.equal(b.clutches_attempted, 1);
    assert.equal(b.clutches_won, 1);
  });

  test('เหลือคนเดียวแล้วทีมแพ้ = นับเป็นความพยายาม แต่ไม่ชนะ', () => {
    const result = deriveMatch(
      baseDoc(
        [{ round_number: 1, winner_team_number: 3 }],
        [kill(1, 1000, C, A), kill(1, 2000, D, B)]
      )
    );
    const b = statsOf(result, B);
    assert.equal(b.clutches_attempted, 1);
    assert.equal(b.clutches_won, 0);
  });

  test('รอบเดียวนับคลัตช์ให้คนเดิมไม่เกินหนึ่งครั้ง', () => {
    const result = deriveMatch(
      baseDoc(
        [{ round_number: 1, winner_team_number: 2 }],
        [kill(1, 1000, C, A), kill(1, 2000, B, C), kill(1, 2500, B, D)]
      )
    );
    assert.equal(statsOf(result, B).clutches_attempted, 1);
  });

  test('ฆ่าศัตรูคนสุดท้ายจนหมดทีม ไม่ถือว่าเป็นคลัตช์ของอีกฝ่าย', () => {
    const result = deriveMatch(
      baseDoc(
        [{ round_number: 1, winner_team_number: 2 }],
        [kill(1, 1000, A, C), kill(1, 1100, A, D)]
      )
    );
    assert.equal(statsOf(result, A).clutches_attempted, 0, 'ฝั่งเรายังครบ ไม่ใช่สถานการณ์ 1vX');
  });
});

describe('ดาเมจและยูทิลิตี้', () => {
  const doc = baseDoc(
    [{ round_number: 1, winner_team_number: 2 }],
    [
      { type: 'damage', round_number: 1, tick: 100, actor_steam64: A, victim_steam64: C, weapon: 'ak47', damage: 40 },
      { type: 'damage', round_number: 1, tick: 200, actor_steam64: A, victim_steam64: C, weapon: 'hegrenade', damage: 30 },
      { type: 'damage', round_number: 1, tick: 300, actor_steam64: A, victim_steam64: C, weapon: 'inferno', damage: 20 },
      // ดาเมจใส่เพื่อนร่วมทีม ต้องไม่ถูกนับ
      { type: 'damage', round_number: 1, tick: 400, actor_steam64: A, victim_steam64: B, weapon: 'hegrenade', damage: 50 },
      { type: 'grenade', round_number: 1, tick: 50, actor_steam64: A, weapon: 'smokegrenade' },
      { type: 'grenade', round_number: 1, tick: 60, actor_steam64: A, weapon: 'flashbang' },
    ]
  );
  const a = statsOf(deriveMatch(doc), A);

  test('รวมดาเมจเฉพาะที่ทำใส่ศัตรู', () => {
    assert.equal(a.damage, 90);
  });

  test('แยกดาเมจยูทิลิตี้ (he + molotov) ออกมาต่างหาก', () => {
    assert.equal(a.utility_damage, 50);
  });

  test('นับจำนวนระเบิดที่ขว้าง', () => {
    assert.equal(a.grenades_thrown, 2);
  });
});

describe('เคสที่มักคิดผิด', () => {
  test('teamkill: เหยื่อนับว่าตาย แต่คนยิงไม่ได้คิล', () => {
    const result = deriveMatch(
      baseDoc([{ round_number: 1, winner_team_number: 3 }], [kill(1, 1000, A, B)])
    );
    assert.equal(statsOf(result, A).kills, 0);
    assert.equal(statsOf(result, B).deaths, 1);
    assert.equal(statsOf(result, B).opening_deaths, 1, 'ยังนับเป็นคนแรกที่ตายของรอบ');
  });

  test('event ที่อยู่นอกรอบที่มีอยู่จริง ถูกตัดทิ้ง', () => {
    const result = deriveMatch(
      baseDoc([{ round_number: 1, winner_team_number: 2 }], [kill(1, 100, A, C), kill(9, 100, A, D)])
    );
    assert.equal(statsOf(result, A).kills, 1);
    assert.equal(result.events.length, 1);
  });

  test('flash assist นับเป็นทั้ง assist และ flash assist', () => {
    const result = deriveMatch(
      baseDoc(
        [{ round_number: 1, winner_team_number: 2 }],
        [kill(1, 100, A, C, { assister_steam64: B, meta: { assistedflash: true } })]
      )
    );
    assert.equal(statsOf(result, B).assists, 1);
    assert.equal(statsOf(result, B).flash_assists, 1);
  });

  test('KPI ถูกคิดให้ผู้เล่นทุกคนพร้อม metrics ที่ใช้', () => {
    const result = deriveMatch(
      baseDoc([{ round_number: 1, winner_team_number: 2 }], [kill(1, 100, A, C)])
    );
    assert.equal(result.kpi.length, 4);
    const kpiA = result.kpi.find((k) => k.steam64_id === A);
    assert.ok(kpiA.metrics.kpr > 0);
    assert.ok(Number.isFinite(kpiA.aim));
  });
});
