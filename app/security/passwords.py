"""Argon2id 密码哈希。"""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("密码至少需要 12 个字符")
    return _hasher.hash(password)


def verify_password(encoded: str, candidate: str) -> bool:
    try:
        return _hasher.verify(encoded, candidate)
    except (VerifyMismatchError, InvalidHashError):
        return False
