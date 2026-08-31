/**
 * ชั้นเชื่อมฐานข้อมูล — PostgreSQL
 *
 * Sprint 1 ย้ายจาก SQLite (node:sqlite) มาเป็น PostgreSQL เพราะข้อมูลจากไฟล์ .dem
 * โตเร็วมาก (ตาราง events หลักหมื่นแถวต่อไม่กี่สิบแมตช์) และต้องใช้ jsonb + index
 * แบบที่ SQLite ทำได้ไม่ดีเท่า
 *
 * มีสอง driver ให้เลือก ใช้ SQL ชุดเดียวกันทั้งคู่:
 *
 *   1) ตั้ง DATABASE_URL  -> ต่อ PostgreSQL จริงผ่าน node-postgres (ใช้ตอน deploy
 *      และตอนรัน `docker compose up -d db` ในเครื่องตัวเอง)
 *   2) ไม่ตั้ง DATABASE_URL -> ใช้ PGlite (PostgreSQL 18 คอมไพล์เป็น WebAssembly
 *      รันในโปรเซส Node เลย เก็บไฟล์ที่ backend/data/pgdata)
 *
 * ทำไมต้องมีข้อ 2: เหตุผลเดียวกับตอนที่เลือก node:sqlite แทน better-sqlite3 คือ
 * คนในทีมและกรรมการต้องรันโปรเจกต์ได้โดยไม่ต้องลง PostgreSQL server หรือ Docker
 * ก่อน — แต่คราวนี้ไม่ต้องแลกด้วยการเปลี่ยนภาษา SQL เพราะ PGlite คือ Postgres จริง
 * (`SELECT version()` ตอบ "PostgreSQL 18.3 ... on wasm32") ดังนั้น migration,
 * jsonb, ON CONFLICT, window function ที่เขียนไว้ ใช้ได้เหมือนกันทั้งสองทาง
 */
import { mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { config } from './config.js';

let impl = null;

async function createImpl() {
  if (config.databaseUrl) {
    const { default: pg } = await import('pg');
    const pool = new pg.Pool({ connectionString: config.databaseUrl, max: 10 });
    // pg คืนค่า BIGINT เป็นสตริงโดยดีฟอลต์ (กันเลขเกิน 2^53 เพี้ยน) แต่ id ของเรา
    // ไม่มีทางโตขนาดนั้น และ frontend เทียบ id เป็นตัวเลข จึงแปลงกลับเป็น Number
    pg.types.setTypeParser(20, (v) => Number(v));
    pg.types.setTypeParser(1700, (v) => Number(v)); // numeric
    return {
      driver: 'postgres',
      query: (text, params) => pool.query(text, params),
      exec: (sql) => pool.query(sql),
      tx: async (fn) => {
        const client = await pool.connect();
        try {
          await client.query('BEGIN');
          const out = await fn({
            query: (t, p) => client.query(t, p),
            exec: (sql) => client.query(sql),
          });
          await client.query('COMMIT');
          return out;
        } catch (e) {
          await client.query('ROLLBACK').catch(() => {});
          throw e;
        } finally {
          client.release();
        }
      },
      close: () => pool.end(),
    };
  }

  const { PGlite } = await import('@electric-sql/pglite');
  // PGLITE_DIR='memory://' = ฐานข้อมูลในหน่วยความจำ หายไปเมื่อจบโปรเซส (เทสต์ใช้แบบนี้)
  const target = config.pgliteDir;
  const dir = target.startsWith('memory://') ? target : resolve(process.cwd(), target);
  if (dir !== target) mkdirSync(dir, { recursive: true });
  const lite = await PGlite.create(dir === target ? dir : { dataDir: dir });
  console.warn(
    '[db] ไม่ได้ตั้ง DATABASE_URL — ใช้ PGlite (Postgres ฝังในโปรเซส) ที่ data/pgdata\n' +
      '     ⚠ PGlite เปิดไฟล์ชุดนี้ได้ทีละโปรเซสเท่านั้น: ต้องปิด backend ก่อนรัน db:migrate / db:seed / etl\n' +
      '     ถ้าอยากรันพร้อมกัน ให้ใช้ Postgres จริง: docker compose up -d db แล้วตั้ง DATABASE_URL ใน .env'
  );
  return {
    driver: 'pglite',
    query: (text, params) => lite.query(text, params ?? []),
    exec: (sql) => lite.exec(sql),
    tx: (fn) =>
      lite.transaction((t) =>
        fn({ query: (q, p) => t.query(q, p ?? []), exec: (sql) => t.exec(sql) })
      ),
    close: () => lite.close(),
  };
}

/** เชื่อมต่อครั้งเดียวแล้วใช้ซ้ำ (เรียกซ้ำได้ ไม่สร้าง pool ใหม่) */
export async function getDb() {
  if (!impl) impl = createImpl();
  return impl;
}

/** ยิง SQL แล้วคืนแถวทั้งหมด — พารามิเตอร์ใช้ $1, $2 … เท่านั้น (กัน SQL injection) */
export async function query(text, params) {
  const d = await getDb();
  const res = await d.query(text, params);
  return res.rows ?? [];
}

/** คืนแถวแรก หรือ null ถ้าไม่เจอ */
export async function one(text, params) {
  const rows = await query(text, params);
  return rows[0] ?? null;
}

/** รัน SQL หลายคำสั่งรวดเดียว (เช่นไฟล์ migration) — ห้ามใส่พารามิเตอร์ */
export async function exec(sql) {
  const d = await getDb();
  return d.exec(sql);
}

/** ครอบหลายคำสั่งไว้ใน transaction เดียว — ETL ใช้ตัวนี้เพื่อให้ "โหลดครบ หรือไม่โหลดเลย" */
export async function tx(fn) {
  const d = await getDb();
  return d.tx(fn);
}

export async function closeDb() {
  if (!impl) return;
  const d = await impl;
  impl = null;
  await d.close();
}
