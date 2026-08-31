import jwt from 'jsonwebtoken';
import { config } from '../config.js';

export function issueToken(user) {
  return jwt.sign(
    { sub: user.id, steam64_id: user.steam64_id, name: user.display_name },
    config.jwtSecret,
    { expiresIn: '7d' }
  );
}

export function setAuthCookie(res, token) {
  res.cookie(config.cookieName, token, {
    httpOnly: true,
    sameSite: 'lax',
    secure: config.isProd,
    maxAge: 7 * 24 * 60 * 60 * 1000,
  });
}

/** แนบ req.user ถ้ามี token ที่ถูกต้อง — ไม่บล็อกถ้าไม่มี */
export function attachUser(req, _res, next) {
  const token = req.cookies?.[config.cookieName];
  if (token) {
    try {
      req.user = jwt.verify(token, config.jwtSecret);
    } catch {
      req.user = null;
    }
  }
  next();
}

/** บังคับว่าต้อง login */
export function requireAuth(req, res, next) {
  if (!req.user) return res.status(401).json({ error: 'ต้องเข้าสู่ระบบก่อน' });
  next();
}
