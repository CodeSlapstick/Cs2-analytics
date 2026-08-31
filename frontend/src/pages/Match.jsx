import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api } from '../api.js';
import {
  Loading, ErrorBox, Signed, SourceTag, fmtPct, fmtNum, fmtDateTime,
} from '../components/ui.jsx';

const TEAM_LABEL = { 2: 'ทีมที่เริ่มฝั่ง T', 3: 'ทีมที่เริ่มฝั่ง CT' };

function Scoreboard({ stats, teamNumber, score }) {
  const rows = stats
    .filter((p) => p.team_number === teamNumber)
    .sort((a, b) => (b.performance_rating ?? -99) - (a.performance_rating ?? -99));
  if (rows.length === 0) return null;

  return (
    <div className="card">
      <h3>
        {TEAM_LABEL[teamNumber] || `ทีม ${teamNumber}`} · <span className="mono">{score}</span>
      </h3>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>ผู้เล่น</th>
              <th className="num">K</th><th className="num">D</th><th className="num">A</th>
              <th className="num">K/D</th><th className="num">ADR</th><th className="num">HS%</th>
              <th className="num" title="ฆ่าคนแรกของรอบ / ตายเป็นคนแรกของรอบ">เปิดไฟต์</th>
              <th className="num" title="ชนะคลัตช์ / ครั้งที่เจอสถานการณ์ 1vX">คลัตช์</th>
              <th className="num">KPI</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => (
              <tr key={p.steam64_id}>
                <td><Link to={`/player/${p.steam64_id}`}>{p.name}</Link></td>
                <td className="num">{p.kills}</td>
                <td className="num">{p.deaths}</td>
                <td className="num">{p.assists}</td>
                <td className="num">{fmtNum(p.kd)}</td>
                <td className="num">{fmtNum(p.adr, 1)}</td>
                <td className="num">{fmtPct(p.hs_pct, 0)}</td>
                <td className="num mono">{p.opening_kills}/{p.opening_deaths}</td>
                <td className="num mono">{p.clutches_won}/{p.clutches_attempted}</td>
                <td className="num"><Signed value={p.performance_rating} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** ไทม์ไลน์รอบ — แถบเล็ก ๆ บอกว่ารอบไหนใครชนะ และชนะด้วยเหตุผลอะไร */
function RoundTimeline({ rounds }) {
  if (!rounds?.length) return null;
  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <h3>ไทม์ไลน์รายรอบ</h3>
      <div className="rounds">
        {rounds.map((r) => (
          <div
            key={r.round_number}
            className={`round r${r.winner_team_number}`}
            title={`รอบ ${r.round_number} · ${TEAM_LABEL[r.winner_team_number]} ชนะ` +
                   `${r.end_reason ? ` (${r.end_reason})` : ''}${r.bomb_planted ? ' · วางระเบิด' : ''}`}
          >
            {r.round_number}
          </div>
        ))}
      </div>
      <p className="small muted" style={{ marginBottom: 0 }}>
        สีทอง = ทีมที่เริ่มฝั่ง T ชนะ · สีฟ้า = ทีมที่เริ่มฝั่ง CT ชนะ (เอาเมาส์ชี้เพื่อดูเหตุผลที่จบรอบ)
      </p>
    </div>
  );
}

export default function Match() {
  const { matchId } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [draft, setDraft] = useState('');
  const [saving, setSaving] = useState(false);

  const load = () => api.match(matchId).then(setData).catch(setError);
  useEffect(() => { setData(null); setError(null); load(); }, [matchId]);

  const addNote = async () => {
    if (!draft.trim()) return;
    setSaving(true);
    try {
      const note = await api.addNote(matchId, draft.trim());
      setData((d) => ({ ...d, notes: [note, ...d.notes] }));
      setDraft('');
    } catch (e) {
      setError(e);
    } finally {
      setSaving(false);
    }
  };

  const removeNote = async (id) => {
    await api.deleteNote(id).catch(() => {});
    setData((d) => ({ ...d, notes: d.notes.filter((n) => n.id !== id) }));
  };

  if (error && !data) return <><h1>รายละเอียดแมตช์</h1><ErrorBox error={error} /></>;
  if (!data) return <Loading />;

  const { match, notes } = data;
  const scoreOf = (team) => match.team_scores.find((t) => t.team_number === team)?.score ?? 0;

  return (
    <>
      <h1>{match.map_name}</h1>
      <p className="sub">
        {fmtDateTime(match.finished_at)}
        {' · สกอร์ '}
        <span className="mono">{scoreOf(2)} – {scoreOf(3)}</span>
        {' · '}{match.rounds_played} รอบ{' · '}
        <SourceTag source={match.source} />
        {match.demo_file && <> · <span className="mono small">{match.demo_file}</span></>}
      </p>

      <RoundTimeline rounds={match.rounds} />

      <div className="grid" style={{ marginBottom: 16 }}>
        {[2, 3].map((t) => (
          <Scoreboard key={t} stats={match.stats} teamNumber={t} score={scoreOf(t)} />
        ))}
      </div>

      <div className="card">
        <h3>โน้ตของโค้ช</h3>
        <p className="small muted" style={{ marginTop: 0 }}>
          บันทึกสิ่งที่เห็นจากแมตช์นี้ไว้ผูกกับตัวแมตช์ (โน้ตไม่หายแม้จะโหลดไฟล์ .dem นี้ทับใหม่)
        </p>
        <textarea rows={3} value={draft} onChange={(e) => setDraft(e.target.value)}
                  placeholder="เช่น: retake ไซต์ B ช้าเพราะไม่มีคนคุม mid ต้องซ้อม default ใหม่" />
        <div style={{ marginTop: 10 }}>
          <button className="primary" onClick={addNote} disabled={saving || !draft.trim()}>
            {saving ? 'กำลังบันทึก…' : 'บันทึกโน้ต'}
          </button>
        </div>

        {notes.length > 0 && (
          <table style={{ marginTop: 18 }}>
            <tbody>
              {notes.map((n) => (
                <tr key={n.id}>
                  <td>
                    <div>{n.body}</div>
                    <div className="small muted">{n.author} · {fmtDateTime(n.created_at)}</div>
                  </td>
                  <td className="num" style={{ width: 90 }}>
                    <button className="ghost" onClick={() => removeNote(n.id)}>ลบ</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
