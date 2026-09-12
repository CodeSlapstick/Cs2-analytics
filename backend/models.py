# -*- coding: utf-8 -*-
"""
backend/models.py — SQLAlchemy 2.0 models ของทุกตาราง (แหล่งความจริงของสคีมา)

ตารางจริงในฐานข้อมูลถูกสร้างด้วย Alembic (backend/alembic/versions/) ไม่ใช่ Base.metadata.create_all
ไฟล์นี้ต้องตรงกับ migration ล่าสุดเสมอ — เวลาแก้สคีมาให้แก้ที่นี่ แล้วเขียน migration คู่กัน

ชื่อตารางเทียบกับเอกสารดีไซน์ Sprint 2
    player_round_stats ในเอกสาร  =  ตาราง player_rounds ที่นี่ (ชื่อเดิมจาก Sprint 1, view ทุกตัวอ้างชื่อนี้อยู่)
"""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import REAL
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class MatchStatus:
    """สถานะของแมตช์ตั้งแต่อัปโหลดจนดูได้ — worker เป็นคนขยับ"""
    QUEUED = "queued"      # รับไฟล์แล้ว รอ worker หยิบ
    PARSING = "parsing"    # worker กำลังแกะเดโม + โหลดเข้าฐานข้อมูล
    DONE = "done"          # เปิดดูได้
    ERROR = "error"        # พัง — ดูสาเหตุที่ matches.error_message
    ALL = (QUEUED, PARSING, DONE, ERROR)


class Account(Base):
    """บัญชีสำหรับล็อกอินหน้าเว็บ (username/password + JWT ใน httpOnly cookie) — migration 0005, backend/auth.py"""
    __tablename__ = "accounts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(Text, nullable=False)          # ไม่สนตัวพิมพ์ (unique บน lower(username))
    password_hash: Mapped[str | None] = mapped_column(Text)              # pbkdf2_sha256$รอบ$salt$hash — NULL = บัญชีที่ล็อกอินด้วย Steam
    steam_id: Mapped[int | None] = mapped_column(BigInteger)             # SteamID64 (migration 0007) — NULL = บัญชี username/password
    avatar: Mapped[str | None] = mapped_column(Text)                     # URL รูปโปรไฟล์จาก Steam (ว่างได้)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("accounts_username_lower_idx", text("lower(username)"), unique=True),
        Index("accounts_steam_id_idx", "steam_id", unique=True),
    )


class User(Base):
    """ผู้ใช้จากระบบ Steam login เดิม — เลิกใช้แล้ว (แทนด้วย Account) เก็บตารางไว้ไม่ลบ ไม่มีโค้ดเขียนลงแล้ว"""
    __tablename__ = "users"
    steamid: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(255))
    avatar: Mapped[str | None] = mapped_column(Text)
    profile_url: Mapped[str | None] = mapped_column(Text)
    mode: Mapped[str | None] = mapped_column(String(32))           # 'steam' = ล็อกอินจริง, 'dev' = โหมดทดสอบ
    last_login: Mapped[datetime | None] = mapped_column(DateTime, server_default=text("CURRENT_TIMESTAMP"))


class Player(Base):
    """นักแข่งที่โผล่ในเดโม — คีย์คือ SteamID64 ชื่อเก็บล่าสุดที่เห็น"""
    __tablename__ = "players"
    steam_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)


class Match(Base):
    """แมตช์ = ไฟล์ .dem หนึ่งไฟล์ — แถวถูกสร้างทันทีที่อัปโหลด (status=queued) ก่อนจะรู้แมพ/tickrate"""
    __tablename__ = "matches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    demo_file: Mapped[str] = mapped_column(Text, unique=True, nullable=False)   # ชื่อไฟล์ .dem ใช้กันโหลดซ้ำ
    map_name: Mapped[str | None] = mapped_column(Text)        # NULL จนกว่า worker จะแกะเสร็จ
    tickrate: Mapped[int | None] = mapped_column(Integer)     # 64 หรือ 128 tick/วินาที
    team_a: Mapped[str | None] = mapped_column(Text)          # แกะจากชื่อไฟล์ "A-vs-B-Map.dem"
    team_b: Mapped[str | None] = mapped_column(Text)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    # --- สถานะงาน parse (Sprint 2) ---
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'queued'"))
    error_message: Mapped[str | None] = mapped_column(Text)   # เก็บทุก error จาก worker ตามข้อกำหนด
    job_id: Mapped[str | None] = mapped_column(Text)          # id ของงานใน RQ ไว้ถามสถานะคิว
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("status IN ('queued', 'parsing', 'done', 'error')", name="matches_status_check"),
        Index("matches_status_idx", "status"),
    )


class MatchPlayer(Base):
    """ใครเล่นในแมตช์ไหน — สรุปจาก player_rounds ตอนโหลด (start_side = ฝั่งในรอบแรกที่เล่น = ระบุทีม)"""
    __tablename__ = "match_players"
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), primary_key=True)
    steam_id: Mapped[int] = mapped_column(ForeignKey("players.steam_id"), primary_key=True)
    start_side: Mapped[str | None] = mapped_column(Text)
    rounds: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    team_clan: Mapped[str | None] = mapped_column(Text)   # ชื่อทีมคงที่ทั้งแมตช์ (clan tag หรือ Team A/B) — migration 0004

    __table_args__ = (
        CheckConstraint("start_side IN ('ct', 't')", name="match_players_start_side_check"),
        Index("match_players_player_idx", "steam_id"),
    )


class Round(Base):
    """รอบ — แต่ละแมตช์มี 16-30 รอบ"""
    __tablename__ = "rounds"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), nullable=False)
    round_num: Mapped[int] = mapped_column(Integer, nullable=False)
    start_tick: Mapped[int | None] = mapped_column(Integer)        # tick ที่ freeze time จบ
    bomb_plant_tick: Mapped[int | None] = mapped_column(Integer)   # NULL = รอบนี้ไม่มีการวางระเบิด
    winner_side: Mapped[str | None] = mapped_column(Text)
    end_reason: Mapped[str | None] = mapped_column(Text)           # t_killed / ct_killed / bomb_defused / ...
    bomb_plant_x: Mapped[float | None] = mapped_column(REAL)       # จุดที่วางบอมบ์ (migration 0004)
    bomb_plant_y: Mapped[float | None] = mapped_column(REAL)
    bomb_site: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("match_id", "round_num"),
        CheckConstraint("winner_side IN ('ct', 't')", name="rounds_winner_side_check"),
        Index("rounds_match_idx", "match_id"),
    )


class Kill(Base):
    """คิล — หนึ่งแถวต่อการฆ่าหนึ่งครั้ง ตารางหลักที่ทุกสถิติคำนวณจาก"""
    __tablename__ = "kills"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    round_id: Mapped[int] = mapped_column(ForeignKey("rounds.id", ondelete="CASCADE"), nullable=False)
    tick: Mapped[int] = mapped_column(Integer, nullable=False)
    attacker_id: Mapped[int | None] = mapped_column(ForeignKey("players.steam_id"))   # NULL = ตายจากระเบิด/ตกที่สูง
    victim_id: Mapped[int] = mapped_column(ForeignKey("players.steam_id"), nullable=False)
    assister_id: Mapped[int | None] = mapped_column(ForeignKey("players.steam_id"))
    attacker_side: Mapped[str | None] = mapped_column(Text)
    victim_side: Mapped[str] = mapped_column(Text, nullable=False)
    weapon: Mapped[str] = mapped_column(Text, nullable=False)
    headshot: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    hitgroup: Mapped[str | None] = mapped_column(Text)
    attacker_blind: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    thru_smoke: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    noscope: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    assisted_flash: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    penetrated: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    distance: Mapped[float | None] = mapped_column(REAL)
    attacker_x: Mapped[float | None] = mapped_column(REAL)
    attacker_y: Mapped[float | None] = mapped_column(REAL)
    attacker_z: Mapped[float | None] = mapped_column(REAL)
    attacker_place: Mapped[str | None] = mapped_column(Text)
    victim_x: Mapped[float | None] = mapped_column(REAL)
    victim_y: Mapped[float | None] = mapped_column(REAL)
    victim_z: Mapped[float | None] = mapped_column(REAL)
    victim_place: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("attacker_side IN ('ct', 't')", name="kills_attacker_side_check"),
        CheckConstraint("victim_side IN ('ct', 't')", name="kills_victim_side_check"),
        Index("kills_round_idx", "round_id"),
        Index("kills_attacker_idx", "attacker_id"),
        Index("kills_victim_idx", "victim_id"),
        Index("kills_weapon_idx", "weapon"),
    )


class Damage(Base):
    """ดาเมจ — หนึ่งแถวต่อการสร้างความเสียหายหนึ่งครั้ง (ADR / KAST ใช้)"""
    __tablename__ = "damages"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    round_id: Mapped[int] = mapped_column(ForeignKey("rounds.id", ondelete="CASCADE"), nullable=False)
    tick: Mapped[int] = mapped_column(Integer, nullable=False)
    attacker_id: Mapped[int | None] = mapped_column(ForeignKey("players.steam_id"))
    victim_id: Mapped[int] = mapped_column(ForeignKey("players.steam_id"), nullable=False)
    weapon: Mapped[str | None] = mapped_column(Text)
    damage: Mapped[int] = mapped_column(Integer, nullable=False)
    hitgroup: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (Index("damages_round_idx", "round_id"), Index("damages_attacker_idx", "attacker_id"))


class PlayerRound(Base):
    """ผู้เล่นรายรอบ (= player_round_stats ในเอกสารดีไซน์)

    ครึ่งแรกมาจาก parser ตรง ๆ (ฝั่ง / มูลค่าอุปกรณ์ / รอดไหม)
    ครึ่งหลังคือฟีเจอร์ที่ backend/features.py คำนวณตอนโหลด ตามนิยามใน definitions.py
    """
    __tablename__ = "player_rounds"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    round_id: Mapped[int] = mapped_column(ForeignKey("rounds.id", ondelete="CASCADE"), nullable=False)
    steam_id: Mapped[int] = mapped_column(ForeignKey("players.steam_id"), nullable=False)
    side: Mapped[str] = mapped_column(Text, nullable=False)
    equip_value: Mapped[int | None] = mapped_column(Integer)   # มูลค่าอุปกรณ์ตอน freeze time จบ
    balance: Mapped[int | None] = mapped_column(Integer)       # เงินในกระเป๋าตอนนั้น
    survived: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    # --- ฟีเจอร์ (migration 0003) ---
    buy_type: Mapped[str | None] = mapped_column(Text)          # pistol / full / force / eco
    kills: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    deaths: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    assists: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    headshots: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    damage: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    opening_kill: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    opening_death: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    trade_kills: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    was_traded: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    clutch_vs: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    clutch_won: Mapped[bool | None] = mapped_column(Boolean)
    kast: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    features_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    __table_args__ = (
        UniqueConstraint("round_id", "steam_id"),
        CheckConstraint("side IN ('ct', 't')", name="player_rounds_side_check"),
        CheckConstraint("buy_type IS NULL OR buy_type IN ('pistol', 'full', 'force', 'eco')",
                        name="player_rounds_buy_type_check"),
        Index("player_rounds_player_idx", "steam_id"),
    )


class PlayerPosition(Base):
    """ตำแหน่งผู้เล่นที่ 1 Hz — หนึ่งแถวต่อคนต่อวินาที เฉพาะช่วงที่รอบกำลังเล่นและคนนั้นยังมีชีวิต"""
    __tablename__ = "player_positions"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), nullable=False)
    round_num: Mapped[int] = mapped_column(Integer, nullable=False)
    tick: Mapped[int] = mapped_column(Integer, nullable=False)
    steam_id: Mapped[int] = mapped_column(ForeignKey("players.steam_id"), nullable=False)
    side: Mapped[str | None] = mapped_column(Text)
    x: Mapped[float] = mapped_column(REAL, nullable=False)
    y: Mapped[float] = mapped_column(REAL, nullable=False)
    z: Mapped[float | None] = mapped_column(REAL)
    health: Mapped[int | None] = mapped_column(SmallInteger)
    place: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("side IN ('ct', 't')", name="player_positions_side_check"),
        Index("player_positions_match_round_idx", "match_id", "round_num"),
        Index("player_positions_player_idx", "steam_id"),
    )


class Grenade(Base):
    """ระเบิด — หนึ่งแถวต่อลูกที่ขว้าง (utility per round)"""
    __tablename__ = "grenades"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    round_id: Mapped[int] = mapped_column(ForeignKey("rounds.id", ondelete="CASCADE"), nullable=False)
    tick: Mapped[int] = mapped_column(Integer, nullable=False)
    thrower_id: Mapped[int | None] = mapped_column(ForeignKey("players.steam_id"))
    side: Mapped[str | None] = mapped_column(Text)
    type: Mapped[str] = mapped_column(Text, nullable=False)   # flash / smoke / he / molotov / decoy
    # migration 0006: ขว้างจากไหน ตกที่ไหน ควัน/ไฟหมดเมื่อไร (NULL = แกะด้วย parser รุ่นก่อน schema 6)
    throw_x: Mapped[float | None] = mapped_column(REAL)
    throw_y: Mapped[float | None] = mapped_column(REAL)
    land_x: Mapped[float | None] = mapped_column(REAL)
    land_y: Mapped[float | None] = mapped_column(REAL)
    land_tick: Mapped[int | None] = mapped_column(Integer)
    end_tick: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        CheckConstraint("side IN ('ct', 't')", name="grenades_side_check"),
        Index("grenades_round_idx", "round_id"),
        Index("grenades_thrower_idx", "thrower_id"),
    )
