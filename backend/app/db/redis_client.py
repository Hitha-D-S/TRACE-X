"""
TRACE-X Redis Client — cache, event buffering, and transient state.
Includes automatic in-memory fallback if Redis is unavailable.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import redis.asyncio as aioredis
from redis.exceptions import ConnectionError, TimeoutError

from app.core.config import get_settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)

_redis: Optional[aioredis.Redis] = None
_use_local_fallback: bool = False

# Local In-Memory Fallback Stores
_local_buffer: List[str] = []
_local_processed: set[str] = set()
_local_cache: Dict[str, str] = {}


async def get_redis() -> Optional[aioredis.Redis]:
    global _redis, _use_local_fallback
    if _use_local_fallback:
        return None
    if _redis is None:
        try:
            settings = get_settings()
            _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        except Exception as e:
            logger.warning("redis_init_failed_using_in_memory_fallback", error=str(e))
            _use_local_fallback = True
            return None
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        try:
            await _redis.close()
        except Exception:
            pass
        _redis = None


# ── Transaction Buffer ───────────────────────────────────────

BUFFER_KEY = "tracex:tx_buffer"
PROCESSED_KEY = "tracex:processed_ids"
ALERT_STREAM_KEY = "tracex:alert_stream"


async def buffer_transaction(tx: Dict[str, Any]) -> None:
    """Push transaction JSON to the Redis buffer list."""
    r = await get_redis()
    val = json.dumps(tx, default=str)
    if r is None:
        _local_buffer.append(val)
        return
    try:
        await r.rpush(BUFFER_KEY, val)
    except (ConnectionError, TimeoutError, OSError) as e:
        logger.warning("redis_write_failed_falling_back", error=str(e))
        global _use_local_fallback
        _use_local_fallback = True
        _local_buffer.append(val)


async def flush_transaction_buffer(batch_size: int = 50) -> List[Dict[str, Any]]:
    """Pop up to batch_size transactions from the buffer."""
    r = await get_redis()
    if r is None:
        batch = _local_buffer[:batch_size]
        del _local_buffer[:batch_size]
        return [json.loads(item) for item in batch]
    try:
        pipe = r.pipeline()
        pipe.lrange(BUFFER_KEY, 0, batch_size - 1)
        pipe.ltrim(BUFFER_KEY, batch_size, -1)
        results = await pipe.execute()
        raw_list = results[0]
        return [json.loads(item) for item in raw_list]
    except (ConnectionError, TimeoutError, OSError):
        global _use_local_fallback
        _use_local_fallback = True
        batch = _local_buffer[:batch_size]
        del _local_buffer[:batch_size]
        return [json.loads(item) for item in batch]


async def is_already_processed(tx_id: str) -> bool:
    """Idempotency check — returns True if this tx was already handled."""
    r = await get_redis()
    if r is None:
        return tx_id in _local_processed
    try:
        return bool(await r.sismember(PROCESSED_KEY, tx_id))
    except (ConnectionError, TimeoutError, OSError):
        global _use_local_fallback
        _use_local_fallback = True
        return tx_id in _local_processed


async def mark_processed(tx_id: str, ttl_seconds: int = 86400) -> None:
    """Mark a transaction ID as processed (expires after TTL)."""
    r = await get_redis()
    if r is None:
        _local_processed.add(tx_id)
        return
    try:
        pipe = r.pipeline()
        pipe.sadd(PROCESSED_KEY, tx_id)
        pipe.expire(PROCESSED_KEY, ttl_seconds)
        await pipe.execute()
    except (ConnectionError, TimeoutError, OSError):
        global _use_local_fallback
        _use_local_fallback = True
        _local_processed.add(tx_id)


# ── Alert Broadcasting ───────────────────────────────────────

async def publish_alert(alert: Dict[str, Any]) -> None:
    """Publish a new alert to the Redis pub/sub channel for SSE/WS consumers."""
    r = await get_redis()
    val = json.dumps(alert, default=str)
    if r is None:
        # local fallback: no-op since no active subscribers
        return
    try:
        await r.publish(ALERT_STREAM_KEY, val)
    except (ConnectionError, TimeoutError, OSError):
        global _use_local_fallback
        _use_local_fallback = True


# ── Graph Snapshot Cache ─────────────────────────────────────

GRAPH_CACHE_KEY = "tracex:graph_snapshot:{dataset_id}"
GRAPH_CACHE_TTL = 30  # seconds


async def get_graph_cache(dataset_id: str) -> Optional[Dict]:
    r = await get_redis()
    key = dataset_id or "all"
    if r is None:
        raw = _local_cache.get(key)
        return json.loads(raw) if raw else None
    try:
        raw = await r.get(GRAPH_CACHE_KEY.format(dataset_id=key))
        return json.loads(raw) if raw else None
    except (ConnectionError, TimeoutError, OSError):
        global _use_local_fallback
        _use_local_fallback = True
        raw = _local_cache.get(key)
        return json.loads(raw) if raw else None


async def set_graph_cache(dataset_id: str, data: Dict, ttl: int = GRAPH_CACHE_TTL) -> None:
    r = await get_redis()
    key = dataset_id or "all"
    val = json.dumps(data, default=str)
    if r is None:
        _local_cache[key] = val
        return
    try:
        await r.setex(
            GRAPH_CACHE_KEY.format(dataset_id=key),
            ttl,
            val,
        )
    except (ConnectionError, TimeoutError, OSError):
        global _use_local_fallback
        _use_local_fallback = True
        _local_cache[key] = val


# ── Health Check ─────────────────────────────────────────────

async def health_check() -> bool:
    try:
        r = await get_redis()
        if r is None:
            return True  # Fallback is ready
        return await r.ping()
    except Exception:
        return False


def reset_local_state() -> None:
    """Clear in-memory fallback stores (used in testing)."""
    _local_buffer.clear()
    _local_processed.clear()
    _local_cache.clear()
