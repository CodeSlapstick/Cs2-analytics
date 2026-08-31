/**
 * อัปโหลดไฟล์ .dem ผ่านหน้าเว็บ
 *
 *   POST /api/uploads?filename=x.dem[&tickrate=128]   body = ไฟล์ดิบ -> { job_id }
 *   GET  /api/uploads/:jobId                          สถานะงานหนึ่ง
 *   GET  /api/uploads                                 งานทั้งหมดในรอบนี้
 *
 * ส่งไฟล์เป็น body ดิบ (application/octet-stream) ไม่ใช่ multipart/form-data
 * เพราะ multipart ต้องพึ่งไลบรารีเพิ่ม ส่วนไฟล์ดิบ pipe เข้าดิสก์ได้ตรง ๆ ด้วยของที่มีอยู่
 * และไม่มีจังหวะไหนที่ไฟล์ 300 MB ต้องอยู่ในหน่วยความจำทั้งก้อน
 * (express.json() ไม่แตะ body ที่ content-type ไม่ใช่ json สตรีมจึงมาถึงมือเราครบ)
 */
import { Router } from 'express';
import { createWriteStream, rmSync } from 'node:fs';
import { pipeline } from 'node:stream/promises';
import { Transform } from 'node:stream';
import { requireAuth } from '../lib/auth.js';
import { enqueueDemo, getJob, listJobs, uploadTarget, MAX_UPLOAD_BYTES } from '../services/demoJobs.js';

export const uploadsRouter = Router();

const wrap = (fn) => (req, res, next) => fn(req, res, next).catch(next);

/** ตัดสตรีมทิ้งทันทีที่เกินโควตา แทนที่จะปล่อยให้เขียนจนดิสก์เต็มแล้วค่อยรู้ */
function limitSize(max) {
  let seen = 0;
  return new Transform({
    transform(chunk, _enc, cb) {
      seen += chunk.length;
      if (seen > max) {
        cb(new Error(`ไฟล์ใหญ่เกิน ${Math.round(max / 1024 / 1024)} MB`));
        return;
      }
      cb(null, chunk);
    },
  });
}

uploadsRouter.post(
  '/uploads',
  requireAuth,
  wrap(async (req, res) => {
    const filename = String(req.query.filename || '').trim();
    if (!filename.toLowerCase().endsWith('.dem')) {
      return res.status(400).json({ error: 'ต้องเป็นไฟล์ .dem เท่านั้น (ส่งชื่อไฟล์มาที่ ?filename=)' });
    }

    const tickrate = req.query.tickrate ? Number(req.query.tickrate) : null;
    if (tickrate !== null && !Number.isFinite(tickrate)) {
      return res.status(400).json({ error: 'tickrate ต้องเป็นตัวเลข' });
    }

    const declared = Number(req.headers['content-length'] || 0);
    if (declared > MAX_UPLOAD_BYTES) {
      return res.status(413).json({ error: `ไฟล์ใหญ่เกิน ${Math.round(MAX_UPLOAD_BYTES / 1024 / 1024)} MB` });
    }

    const { path } = uploadTarget(filename);
    try {
      await pipeline(req, limitSize(MAX_UPLOAD_BYTES), createWriteStream(path));
    } catch (e) {
      // อัปโหลดไม่สำเร็จ อย่าทิ้งไฟล์ครึ่ง ๆ กลาง ๆ ไว้กินดิสก์
      try {
        rmSync(path, { force: true });
      } catch {
        /* ปล่อยผ่าน — ข้อความจริงที่ผู้ใช้ต้องรู้คือ e.message ด้านล่าง */
      }
      return res.status(413).json({ error: e.message });
    }

    const jobId = enqueueDemo({
      demoPath: path,
      originalName: filename,
      tickrate,
      uploadedBy: req.user.steam64_id,
    });
    res.status(202).json({ job_id: jobId, ...getJob(jobId) });
  })
);

uploadsRouter.get(
  '/uploads',
  requireAuth,
  wrap(async (_req, res) => res.json(listJobs()))
);

uploadsRouter.get(
  '/uploads/:jobId',
  requireAuth,
  wrap(async (req, res) => {
    const job = getJob(req.params.jobId);
    if (!job) return res.status(404).json({ error: 'ไม่พบงานนี้ (อาจหมดอายุหรือ backend รีสตาร์ตไปแล้ว)' });
    res.json(job);
  })
);
