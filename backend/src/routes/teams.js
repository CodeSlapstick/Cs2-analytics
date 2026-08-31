import { Router } from 'express';
import { query, one } from '../db.js';
import { requireAuth } from '../lib/auth.js';
import { getPlayerProfile } from '../services/analytics.js';
import { normalizeWeights, scorePlayer, teamProfile, KPI_DIMENSIONS } from '../lib/kpi.js';

export const teamsRouter = Router();

const isSteam64 = (v) => /^\d{17}$/.test(String(v || ''));
const wrap = (fn) => (req, res, next) => fn(req, res, next).catch(next);

function ownedTeam(teamId, userId) {
  return one('SELECT * FROM teams WHERE id = $1 AND owner_id = $2', [Number(teamId), userId]);
}

teamsRouter.get(
  '/teams',
  requireAuth,
  wrap(async (req, res) => {
    const teams = await query(
      `SELECT t.*, (SELECT COUNT(*)::int FROM team_members m WHERE m.team_id = t.id) AS member_count
         FROM teams t WHERE t.owner_id = $1 ORDER BY t.is_opponent, t.created_at`,
      [req.user.sub]
    );
    res.json(teams.map((t) => ({ ...t, kpi_weights: normalizeWeights(t.kpi_weights) })));
  })
);

teamsRouter.post(
  '/teams',
  requireAuth,
  wrap(async (req, res) => {
    const name = String(req.body?.name || '').trim();
    if (!name) return res.status(400).json({ error: 'ต้องตั้งชื่อทีม' });
    const team = await one(
      'INSERT INTO teams (name, owner_id, is_opponent) VALUES ($1, $2, $3) RETURNING *',
      [name.slice(0, 80), req.user.sub, Boolean(req.body?.is_opponent)]
    );
    res.status(201).json({ ...team, kpi_weights: normalizeWeights(team.kpi_weights), member_count: 0 });
  })
);

teamsRouter.delete(
  '/teams/:id',
  requireAuth,
  wrap(async (req, res) => {
    const deleted = await one('DELETE FROM teams WHERE id = $1 AND owner_id = $2 RETURNING id', [
      Number(req.params.id),
      req.user.sub,
    ]);
    if (!deleted) return res.status(404).json({ error: 'ไม่พบทีม' });
    res.json({ ok: true });
  })
);

teamsRouter.put(
  '/teams/:id/kpi-weights',
  requireAuth,
  wrap(async (req, res) => {
    const team = await ownedTeam(req.params.id, req.user.sub);
    if (!team) return res.status(404).json({ error: 'ไม่พบทีม' });
    const weights = normalizeWeights(req.body?.weights);
    await query('UPDATE teams SET kpi_weights = $1 WHERE id = $2', [JSON.stringify(weights), team.id]);
    res.json({ ok: true, weights });
  })
);

teamsRouter.post(
  '/teams/:id/members',
  requireAuth,
  wrap(async (req, res) => {
    const team = await ownedTeam(req.params.id, req.user.sub);
    if (!team) return res.status(404).json({ error: 'ไม่พบทีม' });

    const steam64Id = String(req.body?.steam64_id || '').trim();
    if (!isSteam64(steam64Id)) {
      return res.status(400).json({ error: 'steam64_id ต้องเป็นตัวเลข 17 หลัก' });
    }
    const { count } = await one('SELECT COUNT(*)::int AS count FROM team_members WHERE team_id = $1', [team.id]);
    if (count >= 10) return res.status(400).json({ error: 'หนึ่งทีมเพิ่มได้ไม่เกิน 10 คน' });

    const dup = await one('SELECT id FROM team_members WHERE team_id = $1 AND steam64_id = $2', [
      team.id,
      steam64Id,
    ]);
    if (dup) return res.status(409).json({ error: 'ผู้เล่นคนนี้อยู่ในทีมแล้ว' });

    // ถ้าไม่ได้ตั้งชื่อเล่นมา ใช้ชื่อในเกมจากไฟล์ .dem ที่โหลดไว้
    const known = await one('SELECT name FROM players WHERE steam64_id = $1', [steam64Id]);
    await query(
      'INSERT INTO team_members (team_id, steam64_id, nickname, role) VALUES ($1, $2, $3, $4)',
      [
        team.id,
        steam64Id,
        String(req.body?.nickname || '').slice(0, 40) || known?.name || null,
        String(req.body?.role || '').slice(0, 30) || null,
      ]
    );
    res.status(201).json({ ok: true, known_player: Boolean(known) });
  })
);

teamsRouter.delete(
  '/teams/:id/members/:memberId',
  requireAuth,
  wrap(async (req, res) => {
    const team = await ownedTeam(req.params.id, req.user.sub);
    if (!team) return res.status(404).json({ error: 'ไม่พบทีม' });
    await query('DELETE FROM team_members WHERE id = $1 AND team_id = $2', [
      Number(req.params.memberId),
      team.id,
    ]);
    res.json({ ok: true });
  })
);

/**
 * ภาพรวมทีม — รวมโปรไฟล์ของสมาชิกทุกคนเป็นคะแนนระดับทีมตามน้ำหนัก KPI ที่โค้ชตั้งไว้
 * สมาชิกที่ยังไม่มีแมตช์ในฐานข้อมูลจะติดธง error ไว้ ไม่ถูกนับในคะแนนทีม
 */
teamsRouter.get(
  '/teams/:id/overview',
  requireAuth,
  wrap(async (req, res) => {
    const team = await ownedTeam(req.params.id, req.user.sub);
    if (!team) return res.status(404).json({ error: 'ไม่พบทีม' });

    const weights = normalizeWeights(team.kpi_weights);
    const rows = await query('SELECT * FROM team_members WHERE team_id = $1 ORDER BY id', [team.id]);

    const members = await Promise.all(
      rows.map(async (m) => {
        const p = await getPlayerProfile(m.steam64_id, 10);
        return {
          member_id: Number(m.id),
          steam64_id: m.steam64_id,
          nickname: m.nickname || p?.name || m.steam64_id,
          role: m.role,
          name: p?.name || null,
          rating: p?.rating || null,
          winrate: p?.winrate ?? null,
          total_matches: p?.total_matches ?? 0,
          adr: p?.stats?.adr ?? null,
          kd: p?.stats?.kd ?? null,
          kpi_score: p ? scorePlayer(p.rating, weights) : null,
          error: p ? null : 'ยังไม่มีข้อมูลแมตช์ของผู้เล่นคนนี้',
        };
      })
    );

    const { average, strongest, weakest } = teamProfile(members);
    const scores = members.map((m) => m.kpi_score).filter((v) => v !== null);
    res.json({
      team: { ...team, kpi_weights: weights },
      members,
      summary: {
        dimensions: KPI_DIMENSIONS,
        average_rating: average,
        strongest,
        weakest,
        team_kpi_score: scores.length
          ? +(scores.reduce((a, b) => a + b, 0) / scores.length).toFixed(2)
          : null,
        covered: scores.length,
        total: members.length,
      },
    });
  })
);
