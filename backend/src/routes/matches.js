import { Router } from 'express';
import { requireAuth } from '../lib/auth.js';
import { listMatches } from '../services/analytics.js';

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
