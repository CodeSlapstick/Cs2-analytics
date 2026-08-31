#!/usr/bin/env node
/**
 * คำสั่งโหลดไฟล์ normalized JSON เข้าฐานข้อมูล
 *
 *   npm run etl -- ../parser/out/match1.json          โหลดไฟล์เดียว
 *   npm run etl -- data/matches                       โหลดทุกไฟล์ .json ในโฟลเดอร์
 *
 * ต่อจาก parser ฝั่ง Python ได้ตรง ๆ:
 *   python parser/parse_demo.py demo.dem -o backend/data/matches/ && npm run etl -- data/matches
 */
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { loadMatch } from './load.js';
import { closeDb } from '../db.js';

function collect(target) {
  const p = resolve(process.cwd(), target);
  if (statSync(p).isDirectory()) {
    return readdirSync(p)
      .filter((f) => f.endsWith('.json'))
      .sort()
      .map((f) => join(p, f));
  }
  return [p];
}

async function main() {
  const targets = process.argv.slice(2);
  if (targets.length === 0) {
    console.error('ใช้: npm run etl -- <ไฟล์.json | โฟลเดอร์>');
    process.exitCode = 1;
    return;
  }

  const paths = targets.flatMap(collect);
  if (paths.length === 0) {
    console.log('ไม่พบไฟล์ .json ที่จะโหลด');
    return;
  }

  let ok = 0;
  let failed = 0;
  for (const path of paths) {
    try {
      const doc = JSON.parse(readFileSync(path, 'utf8'));
      const r = await loadMatch(doc);
      ok += 1;
      const what = r.replaced ? 'อัปเดตทับของเดิม' : 'เพิ่มใหม่';
      console.log(
        `✓ ${r.external_id} (${what}) — ${r.inserted.rounds} รอบ, ` +
          `${r.inserted.players} ผู้เล่น, ${r.inserted.events} events`
      );
      for (const w of r.warnings) console.log(`  ! ${w}`);
    } catch (e) {
      failed += 1;
      console.error(`✗ ${path}\n  ${e.message}`);
    }
  }
  console.log(`\nสรุป: สำเร็จ ${ok} ไฟล์, ล้มเหลว ${failed} ไฟล์`);
  if (failed) process.exitCode = 1;
}

main()
  .catch((e) => {
    console.error(e);
    process.exitCode = 1;
  })
  .finally(() => closeDb());
