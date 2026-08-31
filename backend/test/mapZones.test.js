/**
 * เทสต์ตรรกะการให้คะแนนโซน — รันด้วย `npm test`
 *
 * ทดสอบเฉพาะสองฟังก์ชันบริสุทธิ์ที่เป็นหัวใจของ Map analytics: การจับ event
 * เข้าโซน กับสูตรคะแนนได้เปรียบ ส่วนการอ่านไฟล์โซนและคิวรีฐานข้อมูลไม่เทสต์ที่นี่
 * เพราะเป็นการต่อท่อ ไม่ใช่ตรรกะที่จะพังเงียบ ๆ แล้วให้ตัวเลขผิดโดยไม่มีใครรู้
 *
 * โซนถูก fit ที่ parser/map_zones.py (Python + scikit-learn) เทสต์ของฝั่งนั้น
 * อยู่ที่ parser/test_parse_demo.py
 */
import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { nearestZone, zoneScore } from '../src/services/mapZones.js';

const ZONES = [
  { zone_id: 0, name: 'A', centroid: [0, 0] },
  { zone_id: 1, name: 'B', centroid: [1000, 0] },
  { zone_id: 2, name: 'C', centroid: [0, 1000] },
];

describe('จับพิกัดเข้าโซน', () => {
  test('เลือกโซนที่ centroid ใกล้ที่สุด', () => {
    assert.equal(nearestZone(ZONES, 50, 20).zone_id, 0);
    assert.equal(nearestZone(ZONES, 900, 10).zone_id, 1);
    assert.equal(nearestZone(ZONES, 30, 880).zone_id, 2);
  });

  test('จุดที่อยู่ไกลทุกโซนก็ยังต้องได้โซน ไม่ใช่ null', () => {
    // KMeans แบ่งพื้นที่ทั้งระนาบ ไม่มีคำว่า "นอกโซน" — ถ้าคืน null เหตุการณ์จะหายไปจากสถิติเงียบ ๆ
    assert.equal(nearestZone(ZONES, 99999, 99999).zone_id, 1);
  });

  test('พิกัดที่หายไปคืน null (ไม่ใช่ไปโผล่ที่โซนแรก)', () => {
    assert.equal(nearestZone(ZONES, null, 100), null);
    assert.equal(nearestZone(ZONES, 100, undefined), null);
  });
});

describe('คะแนนได้เปรียบของโซน', () => {
  test('คิลเท่าตายได้ 0 ไม่ว่าจะปะทะกันกี่ครั้ง', () => {
    assert.equal(zoneScore(1, 1), 0);
    assert.equal(zoneScore(50, 50), 0);
  });

  test('โซนที่ไม่มีการปะทะเลยคืน null (ไม่ใช่ 0 ซึ่งแปลว่า "สูสี")', () => {
    assert.equal(zoneScore(0, 0), null);
  });

  test('คิลมากกว่าตาย = คะแนนบวก และกลับด้านเป็นลบเมื่อสลับกัน', () => {
    const s = zoneScore(30, 10);
    assert.ok(s > 0, `ควรเป็นบวก แต่ได้ ${s}`);
    assert.equal(zoneScore(10, 30), -s);
  });

  test('ข้อมูลน้อยถูกดึงเข้าหา 0 แม้จะชนะขาด', () => {
    // 2-0 กับ 40-0 คือ "ชนะทุกครั้ง" เหมือนกัน แต่ 2 ครั้งยังสรุปไม่ได้
    // ตัวปรับ (pseudo-count) ต้องทำให้กรณีข้อมูลน้อยได้คะแนนต่ำกว่าอย่างชัดเจน
    const few = zoneScore(2, 0);
    const many = zoneScore(40, 0);
    assert.ok(few < many, `${few} ควรน้อยกว่า ${many}`);
    assert.ok(few < 7, `2-0 ไม่ควรเกือบเต็มสเกล แต่ได้ ${few}`);
  });

  test('คะแนนไม่หลุดออกนอกช่วง −10..+10', () => {
    for (const [k, d] of [[999, 0], [0, 999], [1, 0], [0, 1]]) {
      const s = zoneScore(k, d);
      assert.ok(s >= -10 && s <= 10, `zoneScore(${k},${d}) = ${s} หลุดช่วง`);
    }
  });
});
