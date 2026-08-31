import { config } from '../config.js';

const STEAM_OPENID = 'https://steamcommunity.com/openid/login';
const NS = 'http://specs.openid.net/auth/2.0';

/** สร้าง URL สำหรับส่งผู้ใช้ไปหน้า login ของ Steam (OpenID 2.0) */
export function buildLoginUrl() {
  const params = new URLSearchParams({
    'openid.ns': NS,
    'openid.mode': 'checkid_setup',
    'openid.return_to': `${config.backendUrl}/auth/steam/return`,
    'openid.realm': config.backendUrl,
    'openid.identity': `${NS}/identifier_select`,
    'openid.claimed_id': `${NS}/identifier_select`,
  });
  return `${STEAM_OPENID}?${params.toString()}`;
}

/**
 * ตรวจว่า callback ที่ Steam ส่งกลับมาเป็นของจริง
 * วิธี: ยิงพารามิเตอร์ทั้งชุดกลับไปหา Steam ด้วย mode=check_authentication
 * ห้ามเชื่อ claimed_id ตรง ๆ โดยไม่ตรวจ มิฉะนั้นใครก็ปลอม steamid ได้
 * @returns {Promise<string|null>} steam64_id ถ้าผ่าน, null ถ้าไม่ผ่าน
 */
export async function verifyReturn(query) {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (k.startsWith('openid.')) params.set(k, String(v));
  }
  params.set('openid.mode', 'check_authentication');

  const res = await fetch(STEAM_OPENID, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: params.toString(),
  });
  const text = await res.text();
  if (!/is_valid\s*:\s*true/i.test(text)) return null;

  const claimed = String(query['openid.claimed_id'] || '');
  const m = claimed.match(/^https?:\/\/steamcommunity\.com\/openid\/id\/(\d{17})$/);
  return m ? m[1] : null;
}

/** ดึงชื่อ/รูปโปรไฟล์จาก Steam Web API */
export async function getPlayerSummary(steam64Id) {
  if (!config.steamApiKey) {
    return {
      steamid: steam64Id,
      personaname: `Player ${steam64Id.slice(-4)}`,
      avatarfull: null,
      profileurl: `https://steamcommunity.com/profiles/${steam64Id}`,
    };
  }
  const url = new URL('https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/');
  url.searchParams.set('key', config.steamApiKey);
  url.searchParams.set('steamids', steam64Id);
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Steam API ${res.status}`);
  const json = await res.json();
  return json?.response?.players?.[0] || null;
}
