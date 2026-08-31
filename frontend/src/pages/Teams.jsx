import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api.js';
import { RatingRadar, TeamBars } from '../components/charts.jsx';
import { Signed, Loading, ErrorBox, EmptyState, DIM_LABEL, DIM_HINT, fmtNum, fmtPct } from '../components/ui.jsx';

function KpiWeights({ team, onSaved }) {
  const [w, setW] = useState(team.kpi_weights);
  const [saving, setSaving] = useState(false);
  useEffect(() => setW(team.kpi_weights), [team.id]);

  const save = async () => {
    setSaving(true);
    try {
      const res = await api.setWeights(team.id, w);
      setW(res.weights);
      onSaved();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="card">
      <h3>Custom KPI — น้ำหนักที่โค้ชกำหนดเอง</h3>
      <p className="small muted" style={{ marginTop: 0 }}>
        ทีมที่เน้นเล่นช้าอาจให้น้ำหนักยูทิลิตี้มากกว่าการเปิดไฟต์ คะแนน KPI ของทีมจะคำนวณตามน้ำหนักนี้ (0–5)
      </p>
      <div className="grid cols-3">
        {Object.keys(DIM_LABEL).map((d) => (
          <div key={d}>
            <label>{DIM_LABEL[d]}</label>
            <input type="number" min="0" max="5" step="0.5" value={w[d] ?? 1}
                   onChange={(e) => setW({ ...w, [d]: Number(e.target.value) })} />
          </div>
        ))}
      </div>
      <button className="primary" style={{ marginTop: 12 }} onClick={save} disabled={saving}>
        {saving ? 'กำลังบันทึก…' : 'บันทึกน้ำหนักและคำนวณใหม่'}
      </button>
    </div>
  );
}

function Overview({ teamId, onChanged }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [form, setForm] = useState({ steam64_id: '', nickname: '', role: '' });
  const [known, setKnown] = useState([]);

  // รายชื่อผู้เล่นที่มีข้อมูลจริงในฐานข้อมูล — เอาไว้เลือกแทนการพิมพ์ Steam64 เอง
  useEffect(() => { api.players().then(setKnown).catch(() => setKnown([])); }, []);

  const load = () => {
    setError(null);
    api.teamOverview(teamId).then(setData).catch(setError);
  };
  useEffect(() => { setData(null); load(); }, [teamId]);

  const addMember = async () => {
    try {
      await api.addMember(teamId, form);
      setForm({ steam64_id: '', nickname: '', role: '' });
      load();
      onChanged();
    } catch (e) {
      setError(e);
    }
  };

  const removeMember = async (memberId) => {
    await api.removeMember(teamId, memberId).catch(() => {});
    load();
    onChanged();
  };

  if (error && !data) return <ErrorBox error={error} />;
  if (!data) return <Loading text="กำลังรวมข้อมูลสมาชิกทีม…" />;

  const { members, summary, team } = data;

  return (
    <>
      <ErrorBox error={error} />

      <div className="grid cols-2" style={{ marginBottom: 16 }}>
        <div className="card">
          <h3>โปรไฟล์ทีมโดยรวม</h3>
          {summary.average_rating
            ? <RatingRadar labels={DIM_LABEL} series={[{ name: team.name, rating: summary.average_rating }]} />
            : <p className="muted small">ยังไม่มีข้อมูลพอจะวาดกราฟ เพิ่มสมาชิกในทีมก่อน</p>}
        </div>
        <div className="card">
          <h3>สรุประดับทีม</h3>
          <table>
            <tbody>
              <tr>
                <td>คะแนน KPI ของทีม</td>
                <td className="num"><strong><Signed value={summary.team_kpi_score} /></strong></td>
              </tr>
              <tr>
                <td>มิติที่แข็งที่สุด</td>
                <td className="num">
                  {summary.strongest
                    ? <>{DIM_LABEL[summary.strongest.dimension]} <Signed value={summary.strongest.value} /></>
                    : '—'}
                </td>
              </tr>
              <tr>
                <td>มิติที่อ่อนที่สุด</td>
                <td className="num">
                  {summary.weakest
                    ? <>{DIM_LABEL[summary.weakest.dimension]} <Signed value={summary.weakest.value} /></>
                    : '—'}
                </td>
              </tr>
              <tr>
                <td>สมาชิกที่มีข้อมูลในฐานข้อมูล</td>
                <td className="num">{summary.covered} / {summary.total} คน</td>
              </tr>
              <tr>
                <td>อัตราชนะเฉลี่ยของสมาชิก</td>
                <td className="num">
                  {fmtPct(
                    members.filter((m) => m.winrate !== null).reduce((a, m, _i, arr) => a + m.winrate / arr.length, 0)
                  )}
                </td>
              </tr>
            </tbody>
          </table>
          {summary.weakest && (
            <div className="notice" style={{ marginTop: 12 }}>
              ข้อเสนอแนะ: จุดอ่อนของทีมอยู่ที่ <strong>{DIM_LABEL[summary.weakest.dimension]}</strong> —
              ควรตั้งเป็นหัวข้อหลักของการซ้อมรอบหน้า
            </div>
          )}
        </div>
      </div>

      {summary.covered > 0 && (
        <div className="card" style={{ marginBottom: 16 }}>
          <h3>คะแนน KPI รายคน (ตามน้ำหนักที่ตั้งไว้)</h3>
          <TeamBars members={members} />
        </div>
      )}

      <div className="card" style={{ marginBottom: 16 }}>
        <h3>สมาชิกทีม</h3>
        <table>
          <thead>
            <tr>
              <th>ชื่อ</th><th>บทบาท</th>
              <th className="num">แมตช์</th><th className="num">ADR</th><th className="num">K/D</th>
              {Object.keys(DIM_LABEL).map((d) => (
                <th key={d} className="num" title={DIM_HINT[d]}>{DIM_LABEL[d]}</th>
              ))}
              <th className="num">KPI</th><th></th>
            </tr>
          </thead>
          <tbody>
            {members.map((m) => (
              <tr key={m.member_id}>
                <td>
                  <Link to={`/player/${m.steam64_id}`}>{m.nickname}</Link>
                  {m.error && <div className="small neg">{m.error}</div>}
                </td>
                <td className="muted">{m.role || '—'}</td>
                <td className="num">{m.total_matches || '—'}</td>
                <td className="num">{fmtNum(m.adr, 1)}</td>
                <td className="num">{fmtNum(m.kd)}</td>
                {Object.keys(DIM_LABEL).map((d) => (
                  <td key={d} className="num"><Signed value={m.rating?.[d]} /></td>
                ))}
                <td className="num"><strong><Signed value={m.kpi_score} /></strong></td>
                <td className="num">
                  <button className="ghost" onClick={() => removeMember(m.member_id)}>ลบ</button>
                </td>
              </tr>
            ))}
            {members.length === 0 && (
              <tr><td colSpan={12} className="muted small">ยังไม่มีสมาชิก เพิ่มด้านล่างได้เลย</td></tr>
            )}
          </tbody>
        </table>

        <div className="row" style={{ marginTop: 16 }}>
          <div>
            <label>ผู้เล่นที่มีข้อมูลแล้ว</label>
            <select value={form.steam64_id}
                    onChange={(e) => setForm({ ...form, steam64_id: e.target.value })}>
              <option value="">— เลือกจากรายชื่อ หรือพิมพ์ Steam64 เอง —</option>
              {known.map((p) => (
                <option key={p.steam64_id} value={p.steam64_id}>
                  {p.name} ({p.total_matches} แมตช์)
                </option>
              ))}
            </select>
          </div>
          <div>
            <label>หรือใส่ Steam64 ID เอง</label>
            <input value={form.steam64_id} placeholder="765611980…"
                   onChange={(e) => setForm({ ...form, steam64_id: e.target.value })} />
          </div>
          <div>
            <label>ชื่อเล่น</label>
            <input value={form.nickname} onChange={(e) => setForm({ ...form, nickname: e.target.value })} />
          </div>
          <div>
            <label>บทบาท</label>
            <input value={form.role} placeholder="AWPer / IGL / Entry"
                   onChange={(e) => setForm({ ...form, role: e.target.value })} />
          </div>
          <button onClick={addMember} disabled={!form.steam64_id.trim()}>เพิ่มสมาชิก</button>
        </div>
      </div>

      <KpiWeights team={team} onSaved={load} />
    </>
  );
}

export default function Teams() {
  const [teams, setTeams] = useState(null);
  const [selected, setSelected] = useState(null);
  const [name, setName] = useState('');
  const [isOpponent, setIsOpponent] = useState(false);
  const [error, setError] = useState(null);

  const load = () =>
    api.teams()
      .then((t) => {
        setTeams(t);
        setSelected((cur) => (t.find((x) => x.id === cur) ? cur : t[0]?.id ?? null));
      })
      .catch(setError);

  useEffect(() => { load(); }, []);

  const create = async () => {
    if (!name.trim()) return;
    try {
      const t = await api.createTeam(name.trim(), isOpponent);
      setName('');
      setIsOpponent(false);
      await load();
      setSelected(t.id);
    } catch (e) {
      setError(e);
    }
  };

  const remove = async (id) => {
    await api.deleteTeam(id).catch(() => {});
    await load();
  };

  if (!teams) return <Loading />;

  return (
    <>
      <h1>ทีม</h1>
      <p className="sub">
        รวมผู้เล่นเป็นทีมเพื่อดูภาพระดับทีม — ใช้ได้ทั้งทีมเราเองและทีมคู่แข่งที่กำลังจะเจอ
      </p>

      <ErrorBox error={error} />

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="row">
          <div>
            <label>ชื่อทีมใหม่</label>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="เช่น UTCC eSports" />
          </div>
          <div style={{ flex: '0 0 auto' }}>
            <label>ประเภท</label>
            <select value={isOpponent ? 'opp' : 'own'}
                    onChange={(e) => setIsOpponent(e.target.value === 'opp')}>
              <option value="own">ทีมเรา</option>
              <option value="opp">ทีมคู่แข่ง</option>
            </select>
          </div>
          <button className="primary" onClick={create} disabled={!name.trim()}>สร้างทีม</button>
        </div>

        {teams.length > 0 && (
          <div className="row" style={{ marginTop: 16 }}>
            {teams.map((t) => (
              <button key={t.id}
                      className={t.id === selected ? 'primary' : ''}
                      style={{ flex: '0 0 auto' }}
                      onClick={() => setSelected(t.id)}>
                {t.name} {t.is_opponent ? '(คู่แข่ง)' : ''} · {t.member_count}
              </button>
            ))}
            {selected && (
              <button className="ghost" style={{ flex: '0 0 auto' }} onClick={() => remove(selected)}>
                ลบทีมที่เลือก
              </button>
            )}
          </div>
        )}
      </div>

      {selected
        ? <Overview teamId={selected} onChanged={load} />
        : (
          <EmptyState title="ยังไม่มีทีม">
            สร้างทีมแรกด้านบน แล้วเพิ่มผู้เล่นที่มีข้อมูลจากไฟล์ .dem เข้าไปเป็นสมาชิก
          </EmptyState>
        )}
    </>
  );
}
