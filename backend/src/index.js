import express from 'express';
import cookieParser from 'cookie-parser';
import cors from 'cors';
import { config } from './config.js';
import { getDb, query } from './db.js';
import { attachUser, requireAuth } from './lib/auth.js';
import { authRouter } from './routes/auth.js';
import { playersRouter } from './routes/players.js';
import { matchesRouter } from './routes/matches.js';
import { mapsRouter } from './routes/maps.js';
import { uploadsRouter } from './routes/uploads.js';

const app = express();

app.use(cors({ origin: config.frontendUrl, credentials: true }));
app.use(express.json({ limit: '256kb' }));
app.use(cookieParser());
app.use(attachUser);

app.get('/health', async (_req, res) => {
  try {
    const db = await getDb();
    const [row] = await query('SELECT COUNT(*)::int AS matches FROM matches');
    res.json({ ok: true, db: db.driver, matches: row.matches, steam_key: Boolean(config.steamApiKey) });
  } catch (e) {
    res.status(503).json({ ok: false, error: e.message, hint: 'รัน npm run db:migrate หรือยัง' });
  }
});

/** ตัวเลขภาพรวมของทั้งระบบ — หน้าแดชบอร์ดใช้บอกว่าตอนนี้มีข้อมูลอยู่เท่าไร */
app.get('/api/overview', requireAuth, async (_req, res, next) => {
  try {
    const [row] = await query(`
      SELECT (SELECT COUNT(*)::int FROM matches)                       AS matches,
             (SELECT COUNT(*)::int FROM matches WHERE source = 'demo') AS demo_matches,
             (SELECT COUNT(*)::int FROM players)                       AS players,
             (SELECT COUNT(*)::int FROM rounds)                        AS rounds,
             (SELECT COUNT(*)::int FROM events)                        AS events,
             (SELECT MAX(finished_at) FROM matches)                    AS latest_match_at
    `);
    res.json(row);
  } catch (e) {
    next(e);
  }
});

app.use('/auth', authRouter);
app.use('/api', playersRouter);
app.use('/api', matchesRouter);
app.use('/api', mapsRouter);
app.use('/api', uploadsRouter);

app.use((_req, res) => res.status(404).json({ error: 'ไม่พบเส้นทางนี้' }));

// eslint-disable-next-line no-unused-vars
app.use((err, _req, res, _next) => {
  console.error('[error]', err);
  const status = err.status || 500;
  res.status(status).json({
    error: status === 500 ? 'เกิดข้อผิดพลาดภายในระบบ' : err.message,
  });
});

// ต่อฐานข้อมูลให้ติดก่อนเปิดรับ request จะได้เจอปัญหาตอนสตาร์ต ไม่ใช่ตอนผู้ใช้กดหน้าแรก
const db = await getDb();
console.log(`[db] ใช้ driver: ${db.driver}`);

app.listen(config.port, () => {
  console.log(`API พร้อมใช้งานที่ ${config.backendUrl}`);
});
