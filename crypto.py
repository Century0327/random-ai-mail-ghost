# -*- coding: utf-8 -*-
"""
Ghost Mail 加密模块
使用 AES-GCM 对对话历史进行加密/解密
密钥从环境变量 CONVERSATION_KEY 读取（32字节十六进制字符串）
"""

import os
import base64
import json
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from logger import setup_logger

logger = setup_logger("ghost_crypto")


def derive_key(passphrase: str) -> bytes:
    """从用户口令派生 32 字节密钥（AES-256）"""
    salt = b"ghost_mail_v2_salt"  # 固定盐值，保证同一口令派生同一密钥
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    return kdf.derive(passphrase.encode("utf-8"))


def get_key() -> bytes:
    """从环境变量获取密钥；未设置时自动生成并提示用户保存"""
    raw = os.environ.get("CONVERSATION_KEY", "").strip()
    if not raw:
        logger.warning("[CRYPTO] CONVERSATION_KEY 未设置，对话历史将不加密")
        return b""
    return derive_key(raw)


def encrypt(data: dict, key: bytes) -> bytes:
    """加密 dict → 返回 base64 字符串（IV + 密文）"""
    if not key:
        # 未设置密钥：明文存储（仅本地测试用，公共仓库不推荐）
        return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)  # 每次随机 IV
    plaintext = json.dumps(data, ensure_ascii=False).encode("utf-8")
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return base64.b64encode(nonce + ciphertext)


def decrypt(blob: bytes, key: bytes) -> dict:
    """解密 → 返回 dict"""
    if not key:
        # 明文模式（向后兼容）
        try:
            return json.loads(blob.decode("utf-8"))
        except Exception:
            return {"full": [], "summary": ""}
    try:
        raw = base64.b64decode(blob)
        nonce, ciphertext = raw[:12], raw[12:]
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return json.loads(plaintext.decode("utf-8"))
    except Exception as e:
        logger.error(f"[CRYPTO] 解密失败: {e}")
        return {"full": [], "summary": ""}


def load_conversation(path: str, key: bytes) -> dict:
    """从文件加载对话历史"""
    if not os.path.exists(path):
        return {"full": [], "summary": ""}
    with open(path, "rb") as f:
        blob = f.read()
    if not blob:
        return {"full": [], "summary": ""}
    return decrypt(blob, key)


def save_conversation(path: str, data: dict, key: bytes):
    """保存对话历史到文件"""
    blob = encrypt(data, key)
    with open(path, "wb") as f:
        f.write(blob)
    mode = "加密" if key else "明文"
    logger.info(f"[CRYPTO] 对话历史已保存（{mode}模式）")


def generate_key_hint() -> str:
    """生成密钥提示（用于首次配置时提示用户）"""
    import secrets
    return secrets.token_hex(16)
