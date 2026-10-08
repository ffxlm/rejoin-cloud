"""
security.py — รหัสเครื่อง / token
------------------------------------------------------------------
- device_code: ให้ผู้ใช้พิมพ์ใน APK — รูปแบบ "RJ-XXXXX-XXXXX" (กันตัวอักษรสับสน)
- device_token: ออกให้ APK หลังลงทะเบียน — "rj_<random>"
- เก็บเป็น hash เสมอ:
    * lookup = sha256(secret)         → ใช้ค้นหาแบบ O(1) (ไม่ใช่ความลับ)
    * token_hash = Argon2(secret)     → ยืนยันตัวตนจริง (กัน DB หลุด)
"""
from __future__ import annotations

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError

# พารามิเตอร์ Argon2: สมดุลความปลอดภัย/ความเร็ว (ไม่หนักเกินไปต่อ heartbeat)
_ph = PasswordHasher(time_cost=2, memory_cost=32 * 1024, parallelism=1)

# กันตัวอักษรสับสน: ไม่มี I, O, 0, 1
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _rand_chars(n: int) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(n))


def generate_device_code() -> str:
    """รหัสเครื่องให้ผู้ใช้พิมพ์: RJ-XXXXX-XXXXX"""
    return f"RJ-{_rand_chars(5)}-{_rand_chars(5)}"


def generate_token() -> str:
    """device_token ความยาวสูง (ใช้เป็น Bearer)"""
    return "rj_" + secrets.token_urlsafe(32)


def lookup_key(secret: str) -> str:
    """sha256 hex ไว้ค้นหาใน DB (deterministic, ไม่ใช่ความลับ)"""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def hash_secret(secret: str) -> str:
    return _ph.hash(secret)


def verify_secret(stored_hash: str, secret: str) -> bool:
    try:
        return _ph.verify(stored_hash, secret)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    except Exception:
        return False
