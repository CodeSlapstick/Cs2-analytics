import { Router } from 'express';
import { query, one } from '../db.js';
import { requireAuth } from '../lib/auth.js';
import { listMatches, getMatchDetails, getMatchKillPositions } from '../services/analytics.js';

export const matchesRouter = Router();

const wrap = (fn) => (req, res, next) => fn(req, res, next).catch(next);

/** รายการแมตช์ทั้งหมดที่โหลดเข้าระบบแล้ว (?mine=1 = เฉพาะแมตช์ที่เราลงเล่น) */
matchesRouter.get(
  '/matches',
  requireAuth,
  wrap(async (req, res) => {
    const mine = req.query.mine === '1' || req.query.mine === 'true';
    res.json(
      await listMatches({
        limit: Math.min(Number(req.query.limit) || 30, 100),
        offset: Number(req.query.offset) || 0,
        steam64Id: mine ? req.user.steam64_id : req.query.steam64 || null,
      })
    );
  })
);

matchesRouter.get(
  '/matches/:matchId',
  requireAuth,
  wrap(async (req, res) => {
    const match = await getMatchDetails(req.params.matchId);
    if (!match) return res.status(404).json({ error: 'ไม่พบแมตช์นี้ในฐานข้อมูล' });

    const notes = await query(
      `SELECT n.id, n.body, n.created_at, u.display_name AS author
         FROM coach_notes n JOIN users u ON u.id = n.author_id
        WHERE n.match_id = $1 ORDER BY n.created_at DESC`,
      [match.id]
    );
    res.json({ match, notes });
  })
);

/** พิกัดคิลรายรอบ — เตรียมไว้ให้ heatmap ใน sprint ถัดไป */
matchesRouter.get(
  '/matches/:matchId/kills',
  requireAuth,
  wrap(async (req, res) => {
    const match = await one('SELECT id FROM matches WHERE id = $1', [Number(req.params.matchId)]);
    if (!match) return res.status(404).json({ error: 'ไม่พบแมตช์นี้ในฐานข้อมูล' });
    res.json(await getMatchKillPositions(match.id));
  })
);

matchesRouter.post(
  '/matches/:matchId/notes',
  requireAuth,
  wrap(async (req, res) => {
    const body = String(req.body?.body || '').trim();
    if (!body) return res.status(400).json({ error: 'โน้ตว่างไม่ได้' });
    if (body.length > 4000) return res.status(400).json({ error: 'โน้ตยาวเกิน 4000 ตัวอักษร' });

    const match = await one('SELECT id FROM matches WHERE id = $1', [Number(req.params.matchId)]);
    if (!match) return res.status(404).json({ error: 'ไม่พบแมตช์นี้ในฐานข้อมูล' });

    const teamId = req.body?.team_id ? Number(req.body.team_id) : null;
    const note = await one(
      `INSERT INTO coach_notes (author_id, match_id, team_id, body)
       VALUES ($1, $2, $3, $4) RETURNING id, body, created_at`,
      [req.user.sub, match.id, teamId, body]
    );
    const author = await one('SELECT display_name FROM users WHERE id = $1', [req.user.sub]);
    res.status(201).json({ ...note, author: author?.display_name || '' });
  })
);

matchesRouter.delete(
  '/notes/:id',
  requireAuth,
  wrap(async (req, res) => {
    const deleted = await one(
      'DELETE FROM coach_notes WHERE id = $1 AND author_id = $2 RETURNING id',
      [Number(req.params.id), req.user.sub]
    );
    if (!deleted) return res.status(404).json({ error: 'ไม่พบโน้ต หรือไม่ใช่โน้ตของคุณ' });
    res.json({ ok: true });
  })
);
