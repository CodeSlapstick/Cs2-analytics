async function request(path, options = {}) {
  const res = await fetch(path, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const err = new Error(data?.error || `เกิดข้อผิดพลาด (${res.status})`);
    err.status = res.status;
    err.payload = data;
    throw err;
  }
  return data;
}

const qs = (params) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : '';
};

export const api = {
  me: () => request('/api/me'),
  logout: () => request('/auth/logout', { method: 'POST' }),
  devLogin: (steam64_id) =>
    request('/auth/dev-login', { method: 'POST', body: JSON.stringify({ steam64_id }) }),

  /** ตัวเลขภาพรวมของระบบ (จำนวนแมตช์/ผู้เล่น/events ที่โหลดเข้ามาแล้ว) */
  overview: () => request('/api/overview'),

  players: (q = '') => request(`/api/players${qs({ q })}`),
  profile: (steam64) => request(`/api/players/${steam64}`),
  playerMatches: (steam64, limit) => request(`/api/players/${steam64}/matches${qs({ limit })}`),
  compare: (a, b) => request(`/api/compare${qs({ a, b })}`),

  matches: (opts = {}) => request(`/api/matches${qs(opts)}`),
  match: (matchId) => request(`/api/matches/${matchId}`),
  matchKills: (matchId) => request(`/api/matches/${matchId}/kills`),
  addNote: (matchId, body) =>
    request(`/api/matches/${matchId}/notes`, { method: 'POST', body: JSON.stringify({ body }) }),
  deleteNote: (id) => request(`/api/notes/${id}`, { method: 'DELETE' }),

  maps: () => request('/api/maps'),
  mapZones: (map, matchId) => request(`/api/maps/${map}/zones${qs({ match_id: matchId })}`),
  mapInsights: (map, side) => request(`/api/maps/${map}/insights${qs({ side })}`),

  uploadJobs: () => request('/api/uploads'),
  uploadJob: (jobId) => request(`/api/uploads/${jobId}`),

  teams: () => request('/api/teams'),
  createTeam: (name, is_opponent = false) =>
    request('/api/teams', { method: 'POST', body: JSON.stringify({ name, is_opponent }) }),
  deleteTeam: (id) => request(`/api/teams/${id}`, { method: 'DELETE' }),
  teamOverview: (id) => request(`/api/teams/${id}/overview`),
  addMember: (id, payload) =>
    request(`/api/teams/${id}/members`, { method: 'POST', body: JSON.stringify(payload) }),
  removeMember: (id, memberId) =>
    request(`/api/teams/${id}/members/${memberId}`, { method: 'DELETE' }),
  setWeights: (id, weights) =>
    request(`/api/teams/${id}/kpi-weights`, { method: 'PUT', body: JSON.stringify({ weights }) }),
};


/**
 * ส่งไฟล์ .dem ขึ้นเซิร์ฟเวอร์
 *
 * ใช้ XMLHttpRequest ไม่ใช่ fetch เพราะ fetch ยังบอกความคืบหน้าของ "ขาขึ้น" ไม่ได้
 * (ReadableStream ฝั่ง request body ยังไม่รองรับทั่วถึง) และไฟล์ 300 MB ที่ไม่มี
 * แถบความคืบหน้าจะดูเหมือนเว็บค้าง
 *
 * ส่งเป็น body ดิบ ไม่ใช่ FormData — ฝั่ง backend pipe ลงดิสก์ตรง ๆ ได้เลย
 * โดยไม่ต้องมีไลบรารีแกะ multipart
 */
export function uploadDemo(file, { tickrate, onProgress } = {}) {
  return new Promise((resolve, reject) => {
    const params = qs({ filename: file.name, tickrate });
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `/api/uploads${params}`);
    xhr.withCredentials = true;
    xhr.setRequestHeader('Content-Type', 'application/octet-stream');

    xhr.upload.onprogress = (e) => onProgress?.(e.loaded);
    xhr.onload = () => {
      let data = null;
      try {
        data = xhr.responseText ? JSON.parse(xhr.responseText) : null;
      } catch {
        return reject(new Error('เซิร์ฟเวอร์ตอบกลับมาในรูปแบบที่อ่านไม่ออก'));
      }
      if (xhr.status >= 200 && xhr.status < 300) return resolve(data);
      const err = new Error(data?.error || `อัปโหลดไม่สำเร็จ (${xhr.status})`);
      err.status = xhr.status;
      reject(err);
    };
    xhr.onerror = () => reject(new Error('เชื่อมต่อเซิร์ฟเวอร์ไม่ได้ระหว่างอัปโหลด'));
    xhr.send(file);
  });
}
