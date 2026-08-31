import { Router } from 'express';
import { config } from '../config.js';
import { query, one } from '../db.js';
import { buildLoginUrl, verifyReturn, getPlayerSummary } from '../services/steam.js';
import { issueToken, setAuthCookie } from '../lib/auth.js';

export const authRouter = Router();

// 1) ผู้ใช้กดปุ่ม "เข้าสู่ระบบด้วย Steam" -> เด้งไปหน้า Steam
authRouter.get('/steam', (_req, res) => {
  res.redirect(buildLoginUrl());
});

// 2) Steam ส่งกลับมาที่นี่ -> ตรวจสอบ -> บันทึกผู้ใช้ -> ออก JWT -> กลับไป frontend
authRouter.get('/steam/return', async (req, res) => {
  try {
    const steam64Id = await verifyReturn(req.query);
    if (!steam64Id) {
      return res.redirect(`${config.frontendUrl}/login?error=steam_verify_failed`);
    }

    const summary = await getPlayerSummary(steam64Id).catch(() => null);
    const name = summary?.personaname || `Player ${steam64Id.slice(-4)}`;
    const avatar = summary?.avatarfull || null;
    const profileUrl = summary?.profileurl || `https://steamcommunity.com/profiles/${steam64Id}`;

    await query(
      `INSERT INTO users (steam64_id, display_name, avatar_url, profile_url)
       VALUES ($1, $2, $3, $4)
       ON CONFLICT (steam64_id) DO UPDATE SET
         display_name  = EXCLUDED.display_name,
         avatar_url    = EXCLUDED.avatar_url,
         profile_url   = EXCLUDED.profile_url,
         last_login_at = now()`,
      [steam64Id, name, avatar, profileUrl]
    );

    const user = await one('SELECT * FROM users WHERE steam64_id = $1', [steam64Id]);
    setAuthCookie(res, issueToken(user));
    res.redirect(config.frontendUrl);
  } catch (e) {
    console.error('[auth/steam/return]', e);
    res.redirect(`${config.frontendUrl}/login?error=server_error`);
  }
});

authRouter.post('/logout', (_req, res) => {
  res.clearCookie(config.cookieName);
  res.json({ ok: true });
});

// เส้นทางลัดสำหรับ dev: login ด้วย steam64 ตรง ๆ โดยไม่ผ่าน Steam
// เปิดใช้ได้เสมอตอน development (ปิดเฉพาะ production เท่านั้น)
authRouter.post('/dev-login', async (req, res, next) => {
  try {
    if (config.isProd) {
      return res.status(403).json({ error: 'ใช้ได้เฉพาะตอน development' });
    }
    const steam64Id = String(req.body?.steam64_id || '').trim();
    if (!/^\d{17}$/.test(steam64Id)) {
      return res.status(400).json({ error: 'steam64_id ต้องเป็นตัวเลข 17 หลัก' });
    }

    // ถ้า steam64 นี้เคยโผล่ในไฟล์ .dem ที่โหลดไว้ ใช้ชื่อในเกมเลย จะได้ตรงกับสกอร์บอร์ด
    const known = await one('SELECT name FROM players WHERE steam64_id = $1', [steam64Id]);
    await query(
      `INSERT INTO users (steam64_id, display_name, profile_url) VALUES ($1, $2, $3)
       ON CONFLICT (steam64_id) DO UPDATE SET last_login_at = now()`,
      [
        steam64Id,
        known?.name || `Dev ${steam64Id.slice(-4)}`,
        `https://steamcommunity.com/profiles/${steam64Id}`,
      ]
    );
    const user = await one('SELECT * FROM users WHERE steam64_id = $1', [steam64Id]);
    setAuthCookie(res, issueToken(user));
    res.json({ ok: true, user });
  } catch (e) {
    next(e);
  }
});
