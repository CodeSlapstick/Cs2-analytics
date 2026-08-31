/**
 * คิวงานแปลงไฟล์ .dem ที่อัปโหลดผ่านหน้าเว็บ
 *
 *   อัปโหลด -> data/uploads/<jobId>.dem
 *          -> spawn python parser/parse_demo.py  (ประมาณ 1–3 นาทีต่อไฟล์ 300 MB)
 *          -> loadMatch(doc) ในโปรเซสเดียวกับ API
 *
 * ทำไมต้องเป็น "งาน" ไม่ใช่ตอบกลับใน request เดียว: parse ไฟล์ 300 MB ใช้เวลาเป็นนาที
 * ซึ่งนานกว่า timeout ของ proxy/browser ทั่วไป ถ้ารอในคำขอเดียวผู้ใช้จะเจอ error
 * ทั้งที่งานยังวิ่งอยู่ดี ๆ จึงตอบ jobId กลับไปทันทีแล้วให้หน้าเว็บถามสถานะเป็นระยะ
 *
 * ทำไม ETL ต้องรันในโปรเซสนี้ ไม่ spawn `node src/etl/cli.js`: PGlite เปิดไฟล์
 * ฐานข้อมูลได้ทีละโปรเซสเท่านั้น ถ้า spawn ออกไป โปรเซสลูกจะเปิดฐานข้อมูลไม่ได้
 * เพราะ API ถือไฟล์อยู่ เรียก loadMatch() ตรง ๆ จึงเป็นทางเดียวที่ทำงานได้ทั้งสอง driver
 *
 * คิวอยู่ในหน่วยความจำ — รีสตาร์ต backend แล้วประวัติงานหาย (ไฟล์ .dem
 * กับแมตช์ที่โหลดสำเร็จยังอยู่) พอสำหรับงานที่โค้ชกดเองทีละไฟล์
 * ถ้าวันหนึ่งต้องรองรับหลายคนพร้อมกัน ค่อยย้ายไปเก็บเป็นตารางในฐานข้อมูล
 */
import { spawn } from 'node:child_process';
import { createWriteStream, existsSync, mkdirSync, readFileSync, rmSync, statSync } from 'node:fs';
import { randomUUID } from 'node:crypto';
import { resolve, join } from 'node:path';
import { loadMatch } from '../etl/load.js';

const UPLOAD_DIR = resolve(process.cwd(), process.env.UPLOAD_DIR || 'data/uploads');
const MATCH_DIR = resolve(process.cwd(), process.env.MATCH_JSON_DIR || 'data/matches');
// parser อยู่นอกโฟลเดอร์ backend — backend/ -> รากโปรเจกต์ -> parser/
const PARSER = resolve(process.cwd(), '..', 'parser', 'parse_demo.py');
const ZONE_FITTER = resolve(process.cwd(), '..', 'parser', 'map_zones.py');
const PYTHON = process.env.PYTHON_BIN || 'python';

/** ไฟล์ .dem ของแมตช์เต็มแมพอยู่ราว 100–400 MB — 800 MB เผื่อไว้เกินพอ */
export const MAX_UPLOAD_BYTES = 800 * 1024 * 1024;

/** งานที่จบแล้วถูกลบทิ้งหลังจากนี้ เพื่อไม่ให้ Map โตไปเรื่อย ๆ */
const JOB_TTL_MS = 60 * 60 * 1000;

/** ทำทีละงาน — parse กิน RAM หลักร้อย MB สองงานพร้อมกันบนเครื่อง dev มีสิทธิ์ OOM */
const queue = [];
let running = false;

const jobs = new Map();

function sweep() {
  const now = Date.now();
  for (const [id, job] of jobs) {
    if (job.finished_at && now - job.finished_at > JOB_TTL_MS) jobs.delete(id);
  }
}

function setStage(job, stage, message) {
  job.stage = stage;
  job.message = message;
  job.updated_at = Date.now();
  job.log.push({ at: new Date().toISOString(), stage, message });
}

export function getJob(id) {
  const job = jobs.get(id);
  if (!job) return null;
  // ไม่ส่ง path จริงบนเครื่องเซิร์ฟเวอร์ออกไปให้ client
  const { demoPath, jsonPath, ...safe } = job;
  return safe;
}

export function listJobs() {
  sweep();
  return [...jobs.values()]
    .sort((a, b) => b.created_at - a.created_at)
    .map(({ demoPath, jsonPath, ...safe }) => safe);
}

/**
 * รับไฟล์ที่อัปโหลดแล้ว (เขียนลงดิสก์เรียบร้อย) เข้าคิวประมวลผล
 * @returns {string} jobId สำหรับให้หน้าเว็บถามสถานะ
 */
export function enqueueDemo({ demoPath, originalName, tickrate = null, uploadedBy = null }) {
  sweep();
  const id = randomUUID();
  const job = {
    id,
    filename: originalName,
    size_bytes: existsSync(demoPath) ? statSync(demoPath).size : null,
    tickrate,
    uploaded_by: uploadedBy,
    stage: 'queued',
    message: 'รอคิวประมวลผล',
    created_at: Date.now(),
    updated_at: Date.now(),
    finished_at: null,
    result: null,
    error: null,
    log: [],
    demoPath,
    jsonPath: null,
  };
  jobs.set(id, job);
  queue.push(id);
  drain();
  return id;
}

async function drain() {
  if (running) return;
  const id = queue.shift();
  if (!id) return;
  running = true;
  try {
    await processJob(jobs.get(id));
  } finally {
    running = false;
    if (queue.length) drain();
  }
}

/** ท้าย ๆ ของ stderr พอให้รู้ว่าพังเพราะอะไร โดยไม่ยัด log ทั้งก้อนใส่หน้าเว็บ */
function lastLines(text, n = 4) {
  return String(text).trim().split('\n').slice(-n).join('\n').trim();
}

function runParser(job) {
  return new Promise((done, fail) => {
    mkdirSync(MATCH_DIR, { recursive: true });
    const args = [PARSER, job.demoPath, '-o', MATCH_DIR];
    if (job.tickrate) args.push('--tickrate', String(job.tickrate));

    // PYTHONIOENCODING กันข้อความไทยจาก parser กลายเป็นตัวยึกยือ — คอนโซล Windows
    // ดีฟอลต์เป็น cp874 และเมื่อ stdout เป็น pipe ตัวแปรนี้คือทางที่แน่นอนที่สุด
    const child = spawn(PYTHON, args, {
      cwd: resolve(process.cwd(), '..'),
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
    });
    let stdout = '';
    let stderr = '';
    child.stdout.setEncoding('utf8');
    child.stderr.setEncoding('utf8');
    child.stdout.on('data', (c) => {
      stdout += c;
    });
    // parser รายงานความคืบหน้าทาง stderr (stdout สงวนไว้ให้บรรทัด OUTPUT_JSON เท่านั้น)
    child.stderr.on('data', (c) => {
      stderr += c;
      const line = String(c).trim().split('\n').pop();
      if (line) setStage(job, 'parsing', line);
    });
    child.on('error', (e) =>
      fail(new Error(`เรียก ${PYTHON} ไม่ได้ (${e.message}) — ติดตั้ง Python แล้วรัน pip install -r parser/requirements.txt`))
    );
    child.on('close', (code) => {
      if (code !== 0) return fail(new Error(lastLines(stderr) || `parser จบด้วยรหัส ${code}`));
      // parser พิมพ์ "OUTPUT_JSON=<path>" ลง stdout เมื่อเขียนไฟล์สำเร็จ
      const m = stdout.match(/^OUTPUT_JSON=(.+)$/m);
      if (!m) return fail(new Error(`parser ไม่ได้บอกว่าเขียนไฟล์ไหน: ${lastLines(stderr)}`));
      done(resolve(resolve(process.cwd(), '..'), m[1].trim()));
    });
  });
}

/**
 * แบ่งโซนของแมพนั้นใหม่หลังโหลดแมตช์เสร็จ
 *
 * รันอัตโนมัติเพราะถ้าไม่รัน แมตช์ที่เพิ่งอัปโหลดจะยังไม่ปรากฏในหน้าวิเคราะห์พื้นที่
 * ซึ่งผู้ใช้ไม่มีทางรู้ว่าต้องไปรันคำสั่งอะไรต่อ
 *
 * ผลข้างเคียงที่ต้องรู้: ขอบเขตโซนขยับได้ทุกครั้งที่ fit ใหม่ ตัวเลขที่โค้ชจดไว้
 * สัปดาห์ก่อนจึงอาจไม่ตรงกับที่เห็นวันนี้ — ไฟล์โซนบันทึก fit_from ไว้เสมอว่า
 * มาจากกี่แมตช์ไหนบ้าง จึงย้อนตรวจได้ว่าตัวเลขชุดไหนมาจากข้อมูลชุดไหน
 *
 * ล้มเหลวไม่ทำให้ทั้งงานล้มเหลว — แมตช์โหลดเข้าฐานข้อมูลเรียบร้อยแล้ว
 * แค่ยังไม่มีโซนให้ดู (เช่นแมพใหม่ที่ยังมีจุดตายไม่พอ) บันทึกเป็นคำเตือนพอ
 */
function refitZones(job, mapName) {
  return new Promise((done) => {
    if (!mapName || !existsSync(ZONE_FITTER)) return done(null);

    const child = spawn(PYTHON, [ZONE_FITTER, mapName], {
      cwd: resolve(process.cwd(), '..'),
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
    });
    let stderr = '';
    child.stderr.setEncoding('utf8');
    child.stderr.on('data', (c) => {
      stderr += c;
      const line = String(c).trim().split('\n').pop();
      if (line) setStage(job, 'zones', line);
    });
    child.on('error', (e) => done(`แบ่งโซนไม่สำเร็จ: ${e.message}`));
    child.on('close', (code) => done(code === 0 ? null : lastLines(stderr, 2) || `map_zones.py จบด้วยรหัส ${code}`));
  });
}

async function processJob(job) {
  if (!job) return;
  try {
    if (!existsSync(PARSER)) {
      throw new Error(`ไม่พบ ${PARSER} — โครงสร้างโฟลเดอร์ไม่ตรงกับที่คาดไว้`);
    }
    setStage(job, 'parsing', 'กำลังแปลงไฟล์ .dem (ไฟล์ใหญ่ใช้เวลาหลายนาที)');
    job.jsonPath = await runParser(job);

    setStage(job, 'loading', 'กำลังโหลดเข้าฐานข้อมูล');
    const doc = JSON.parse(readFileSync(job.jsonPath, 'utf8'));
    const r = await loadMatch(doc);

    const mapName = doc.match?.map_name ?? null;
    setStage(job, 'zones', `กำลังแบ่งโซนของ ${mapName} ใหม่ให้รวมแมตช์นี้`);
    const zoneError = await refitZones(job, mapName);

    job.result = {
      external_id: r.external_id,
      match_id: r.match_id ?? null,
      map_name: mapName,
      replaced: r.replaced,
      rounds: r.inserted.rounds,
      players: r.inserted.players,
      events: r.inserted.events,
      zones_refitted: !zoneError,
      warnings: [...r.warnings, ...(zoneError ? [`แมตช์เข้าระบบแล้ว แต่แบ่งโซนใหม่ไม่สำเร็จ — ${zoneError}`] : [])],
    };
    setStage(job, 'done', r.replaced ? 'อัปเดตทับแมตช์เดิม' : 'เพิ่มแมตช์ใหม่เรียบร้อย');
  } catch (e) {
    job.error = e.message;
    setStage(job, 'failed', e.message);
  } finally {
    job.finished_at = Date.now();
    // ไฟล์ .dem ดิบใหญ่มากและไม่ได้ใช้ต่อ — normalized JSON เก็บทุกอย่างที่ระบบต้องใช้แล้ว
    // (และ map_zones.py ก็ fit จาก JSON ไม่ใช่จาก .dem)
    try {
      if (job.demoPath && existsSync(job.demoPath)) rmSync(job.demoPath, { force: true });
    } catch {
      /* ลบไม่ได้ก็ไม่ใช่เรื่องคอขาดบาดตาย ปล่อยไว้ให้คนมาเก็บกวาดทีหลัง */
    }
  }
}

/** ที่เก็บไฟล์อัปโหลดชั่วคราว — route เรียกก่อนเริ่มเขียนไฟล์ */
export function uploadTarget(originalName) {
  mkdirSync(UPLOAD_DIR, { recursive: true });
  const safe = String(originalName || 'demo.dem').replace(/[^\w.\-]/g, '_').slice(-80);
  return { path: join(UPLOAD_DIR, `${Date.now()}-${safe}`), createWriteStream };
}
