/**
 * เทสต์ตัวจับคู่ trade — รันด้วย `npm test`
 *
 * ฟังก์ชันนี้ถูกแยกออกมาเพราะมีสองที่ที่ใช้: ตัวนับ trade_kills/traded_deaths
 * ในสกอร์บอร์ด กับการวิเคราะห์ "ตายตรงไหนแล้วไม่มีใครล้างแค้นให้" ในหน้าแมพ
 * ก่อนแยกออกมา สองที่นั้นเขียนคนละแบบแล้วให้คำตอบต่างกัน (13 กับ 10 จากข้อมูลชุดเดียวกัน)
 * เทสต์ชุดนี้จึงล็อกพฤติกรรมไว้ไม่ให้แตกอีก
 *
 * ทีม 2 กับทีม 3 เป็นคนละฝั่งเสมอ ตามนิยามของทั้งระบบ
 */
import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { matchTrades, TRADE_WINDOW_SECONDS } from '../src/etl/derive.js';

const TICKRATE = 64;
const WINDOW = TRADE_WINDOW_SECONDS * TICKRATE;

/** ย่อการเขียนคิลหนึ่งรายการ: ใครฆ่าใคร ทีมไหน ตอน tick ไหน */
const kill = (actor, actorTeam, victim, victimTeam, tick) => ({
  actor, actorTeam, victim, victimTeam, tick,
});

describe('จับคู่คิลล้างแค้นกับศพ', () => {
  test('ฆ่าคืนภายในเวลา = ล้างแค้นให้ศพนั้น', () => {
    const kills = [
      kill('E1', 3, 'A1', 2, 1000), // ศัตรูฆ่าเพื่อนเรา
      kill('A2', 2, 'E1', 3, 1000 + WINDOW - 10), // เราฆ่ามันคืนทัน
    ];
    assert.deepEqual(matchTrades(kills, TICKRATE), [-1, 0]);
  });

  test('ฆ่าคืนช้าเกิน 5 วินาที ไม่นับ', () => {
    const kills = [
      kill('E1', 3, 'A1', 2, 1000),
      kill('A2', 2, 'E1', 3, 1000 + WINDOW + 1),
    ];
    assert.deepEqual(matchTrades(kills, TICKRATE), [-1, -1]);
  });

  test('ฆ่าคนอื่นที่ไม่ใช่คนที่ฆ่าเพื่อนเรา ไม่นับเป็นล้างแค้น', () => {
    const kills = [
      kill('E1', 3, 'A1', 2, 1000),
      kill('A2', 2, 'E2', 3, 1050), // E2 ไม่ใช่คนที่ฆ่า A1
    ];
    assert.deepEqual(matchTrades(kills, TICKRATE), [-1, -1]);
  });

  test('หนึ่งคิลล้างแค้นได้หนึ่งศพเท่านั้น', () => {
    // นี่คือกรณีที่เคยทำให้สองหน้าให้ตัวเลขไม่ตรงกัน:
    // ศัตรูคนเดียวฆ่าเพื่อนเราสองคน แล้วเราฆ่ามันคืนหนึ่งครั้ง
    const kills = [
      kill('E1', 3, 'A1', 2, 1000),
      kill('E1', 3, 'A2', 2, 1060),
      kill('A3', 2, 'E1', 3, 1120),
    ];
    const r = matchTrades(kills, TICKRATE);
    assert.deepEqual(r, [0, -1, -1].map((_, i) => (i === 2 ? 0 : -1)),
      'ต้องล้างแค้นให้ศพแรกศพเดียว ไม่ใช่ทั้งสองศพ');
    assert.equal(r.filter((j) => j >= 0).length, 1);
  });

  test('ล้างแค้นได้เฉพาะเพื่อนร่วมทีม ไม่ใช่ศพของศัตรู', () => {
    const kills = [
      kill('A1', 2, 'E1', 3, 1000), // เราฆ่าศัตรู
      kill('E2', 3, 'A1', 2, 1050), // ศัตรูอีกคนฆ่าเรา — ไม่ใช่การล้างแค้นของฝั่งเรา
    ];
    const r = matchTrades(kills, TICKRATE);
    assert.equal(r[1], 0, 'ฝั่งศัตรูก็ล้างแค้นให้พวกมันเองได้ตามนิยามเดียวกัน');
  });

  test('คิลที่ไม่มีคนยิง (ตกเหว/ระเบิด) ไม่ล้างแค้นให้ใคร และไม่ถูกล้างแค้น', () => {
    const kills = [
      { actor: null, actorTeam: null, victim: 'A1', victimTeam: 2, tick: 1000 },
      kill('A2', 2, 'E1', 3, 1050),
    ];
    assert.deepEqual(matchTrades(kills, TICKRATE), [-1, -1]);
  });

  test('รายการว่างคืนอาร์เรย์ว่าง ไม่พัง', () => {
    assert.deepEqual(matchTrades([], TICKRATE), []);
  });

  test('tickrate 128 ทำให้หน้าต่างเวลากว้างเป็นสองเท่าในหน่วย tick', () => {
    const kills = [
      kill('E1', 3, 'A1', 2, 1000),
      kill('A2', 2, 'E1', 3, 1000 + 5 * 128 - 10),
    ];
    assert.deepEqual(matchTrades(kills, 128), [-1, 0], 'ที่ 128 tick/วินาที ยังอยู่ในเวลา');
    assert.deepEqual(matchTrades(kills, 64), [-1, -1], 'ที่ 64 tick/วินาที เกินเวลาไปแล้ว');
  });
});
