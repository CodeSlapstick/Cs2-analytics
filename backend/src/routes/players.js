import { Router } from 'express';
import { query, one } from '../db.js';
import { requireAuth } from '../lib/auth.js';
import { getPlayerProfile, getPlayerMatches } from '../services/analytics.js';
import { KPI_DIMENSIONS } from '../lib/kpi.js';

export const playersRouter = Router();

const isSteam64 = (v) => /^\d{17}$/.test(String(v || ''));

/** ครอบ handler แบบ async ให้ error เด้งเข้า error middleware ของ Express 4 ได้ */
const wrap = (fn) => (req, res, next) => fn(req, res, next).catch(next);

playersRouter.get(
  '/me',
  requireAuth,
  wrap(async (req, res) => {
    const user = await one('SELECT * FROM users WHERE id = $1', [req.user.sub]);
    res.json({ user });
  })
);

/** รายชื่อผู้เล่นที่มีข้อมูลในระบบ — ใช้เติม dropdown ฝั่งหน้าเว็บแทนการพิมพ์ Steam64 เอง */
playersRouter.get(
  '/players',
  requireAuth,
  wrap(async (req, res) => {
    const search = String(req.query.q || '').trim();
    const rows = await query(
      `SELECT p.steam64_id, p.name,
              COUNT(mp.id)::int AS total_matches,
              COALESCE(SUM(mp.rounds_played),0)::int AS rounds_played
         FROM players p
         LEFT JOIN match_players mp ON mp.steam64_id = p.steam64_id
        WHERE $1 = '' OR p.name ILIKE '%' || $1 || '%' OR p.steam64_id LIKE '%' || $1 || '%'
        GROUP BY p.steam64_id, p.name
        HAVING COUNT(mp.id) > 0
        ORDER BY total_matches DESC, p.name
        LIMIT 100`,
      [search]
    );
    res.json(rows);
  })
);

playersRouter.get(
  '/players/:steam64',
  requireAuth,
  wrap(async (req, res) => {
    if (!isSteam64(req.params.steam64)) {
      return res.status(400).json({ error: 'steam64_id ต้องเป็นตัวเลข 17 หลัก' });
    }
    const profile = await getPlayerProfile(req.params.steam64);
    if (!profile) {
      // ไม่มีข้อมูล ≠ ผู้เล่นห่วย — บอกให้ชัดว่ายังไม่มีแมตช์ของคนนี้ในฐานข้อมูล
      return res.status(404).json({
        error: 'ยังไม่มีข้อมูลแมตช์ของผู้เล่นคนนี้ในระบบ — โหลดไฟล์ .dem ที่มีเขาเข้ามาก่อน',
        steam64_id: req.params.steam64,
      });
    }
    res.json(profile);
  })
);

playersRouter.get(
  '/players/:steam64/matches',
  requireAuth,
  wrap(async (req, res) => {
    if (!isSteam64(req.params.steam64)) {
      return res.status(400).json({ error: 'steam64_id ต้องเป็นตัวเลข 17 หลัก' });
    }
    res.json(await getPlayerMatches(req.params.steam64, Number(req.query.limit) || 20));
  })
);

// เปรียบเทียบผู้เล่นสองคนแบบตัวต่อตัว (ผู้เล่นเรา vs ผู้เล่นคู่แข่ง)
playersRouter.get(
  '/compare',
  requireAuth,
  wrap(async (req, res) => {
    const { a, b } = req.query;
    if (!isSteam64(a) || !isSteam64(b)) {
      return res.status(400).json({ error: 'ต้องส่ง a และ b เป็น steam64_id 17 หลัก' });
    }
    const [pa, pb] = await Promise.all([getPlayerProfile(a), getPlayerProfile(b)]);
    const missing = [!pa && a, !pb && b].filter(Boolean);
    if (missing.length) {
      return res.status(404).json({ error: `ยังไม่มีข้อมูลของผู้เล่น: ${missing.join(', ')}` });
    }

    const diff = {};
    for (const d of KPI_DIMENSIONS) {
      const va = Number(pa.rating?.[d]);
      const vb = Number(pb.rating?.[d]);
      diff[d] = Number.isFinite(va) && Number.isFinite(vb) ? +(va - vb).toFixed(2) : null;
    }
    res.json({ a: pa, b: pb, diff });
  })
);
