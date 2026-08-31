/**
 * Map analytics — โซนที่ ML แบ่งไว้ พร้อมคะแนนของแต่ละโซน
 *
 *   GET /api/maps                          แมพทั้งหมดในระบบ + fit โซนไว้แล้วหรือยัง
 *   GET /api/maps/:map/zones               คะแนนโซนจากทุกแมตช์ของแมพนั้น
 *   GET /api/maps/:map/zones?match_id=13   เฉพาะแมตช์เดียว
 *   GET /api/maps/:map/insights            ข้อสรุปเชิงลึก (?side=t|ct แยกฝั่ง)
 */
import { Router } from 'express';
import { requireAuth } from '../lib/auth.js';
import { getZoneAnalytics, getAvailableMaps } from '../services/mapZones.js';
import { getMapInsights } from '../services/mapInsights.js';

export const mapsRouter = Router();

const wrap = (fn) => (req, res, next) => fn(req, res, next).catch(next);

mapsRouter.get(
  '/maps',
  requireAuth,
  wrap(async (_req, res) => res.json(await getAvailableMaps()))
);

mapsRouter.get(
  '/maps/:map/zones',
  requireAuth,
  wrap(async (req, res) => {
    const matchId = req.query.match_id ? Number(req.query.match_id) : null;
    if (req.query.match_id && !Number.isFinite(matchId)) {
      return res.status(400).json({ error: 'match_id ต้องเป็นตัวเลข' });
    }
    const data = await getZoneAnalytics(req.params.map, { matchId });
    if (!data) {
      return res.status(404).json({
        error: `ยังไม่ได้แบ่งโซนของแมพ ${req.params.map} — รัน python parser/map_zones.py ${req.params.map} ก่อน`,
      });
    }
    res.json(data);
  })
);

mapsRouter.get(
  '/maps/:map/insights',
  requireAuth,
  wrap(async (req, res) => {
    const matchId = req.query.match_id ? Number(req.query.match_id) : null;
    if (req.query.match_id && !Number.isFinite(matchId)) {
      return res.status(400).json({ error: 'match_id ต้องเป็นตัวเลข' });
    }
    const side = req.query.side ?? null;
    if (side !== null && side !== 't' && side !== 'ct') {
      return res.status(400).json({ error: "side ต้องเป็น 't' หรือ 'ct' เท่านั้น" });
    }
    const data = await getMapInsights(req.params.map, { matchId, side });
    if (!data) {
      return res.status(404).json({
        error: `ยังไม่มีข้อมูลพอสำหรับแมพ ${req.params.map} — ต้องมีทั้งไฟล์โซนและแมตช์จากไฟล์ .dem จริง`,
      });
    }
    res.json(data);
  })
);
