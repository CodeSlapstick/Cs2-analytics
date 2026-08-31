#!/usr/bin/env node
/**
 * ตัวรัน migration — `npm run db:migrate`
 *
 * อ่านไฟล์ .sql ใน db/migrations/ เรียงตามชื่อ แล้วรันเฉพาะไฟล์ที่ยังไม่เคยรัน
 * (จำไว้ในตาราง schema_migrations) รันซ้ำกี่รอบก็ได้ ผลเท่าเดิม
 *
 * แต่ละไฟล์รันอยู่ใน transaction เดียว — ถ้าพังกลางไฟล์จะ rollback ทั้งไฟล์
 * ไม่เหลือ schema ค้างครึ่ง ๆ กลาง ๆ
 *
 * ตัวเลือก
 *   --reset   ลบ schema ทิ้งทั้งหมดแล้วสร้างใหม่ (ห้ามใช้ตอน NODE_ENV=production)
 *   --status  ดูว่าไฟล์ไหนรันไปแล้วบ้าง ไม่แก้อะไร
 */
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { config } from '../src/config.js';
import { getDb, query, exec, closeDb } from '../src/db.js';

const migrationsDir = resolve(dirname(fileURLToPath(import.meta.url)), 'migrations');

const files = () =>
  readdirSync(migrationsDir)
    .filter((f) => f.endsWith('.sql'))
    .sort();

async function ensureTable() {
  await exec(`
    CREATE TABLE IF NOT EXISTS schema_migrations (
      version    TEXT PRIMARY KEY,
      applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
  `);
}

async function applied() {
  const rows = await query('SELECT version FROM schema_migrations');
  return new Set(rows.map((r) => r.version));
}

async function reset() {
  if (config.isProd) throw new Error('--reset ใช้ตอน NODE_ENV=production ไม่ได้');
  console.warn('[migrate] --reset: ลบ schema public ทั้งหมดแล้วสร้างใหม่');
  await exec('DROP SCHEMA public CASCADE; CREATE SCHEMA public;');
}

async function main() {
  const args = process.argv.slice(2);
  const db = await getDb();
  console.log(`[migrate] driver = ${db.driver}${config.databaseUrl ? ' (DATABASE_URL)' : ''}`);

  if (args.includes('--reset')) await reset();
  await ensureTable();
  const done = await applied();

  if (args.includes('--status')) {
    for (const f of files()) console.log(`${done.has(f) ? '  ✓' : '  ·'} ${f}`);
    return;
  }

  let count = 0;
  for (const file of files()) {
    if (done.has(file)) continue;
    const sql = readFileSync(join(migrationsDir, file), 'utf8');
    const started = Date.now();
    const { tx } = await import('../src/db.js');
    await tx(async (t) => {
      await t.exec(sql);
      await t.query('INSERT INTO schema_migrations (version) VALUES ($1)', [file]);
    });
    count += 1;
    console.log(`[migrate] ✓ ${file} (${Date.now() - started} ms)`);
  }

  console.log(count === 0 ? '[migrate] ไม่มี migration ใหม่ ฐานข้อมูลเป็นเวอร์ชันล่าสุดแล้ว' : `[migrate] เสร็จ ${count} ไฟล์`);
}

main()
  .catch((e) => {
    console.error('[migrate] ล้มเหลว:', e.message);
    process.exitCode = 1;
  })
  .finally(() => closeDb());
