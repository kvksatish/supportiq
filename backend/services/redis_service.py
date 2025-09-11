"""Redis service."""

import json
import logging
from typing import Any, Optional, Dict, List
from datetime import timedelta

from config import settings

logger = logging.getLogger(__name__)


class RedisService:
    """Redis service wrapper"""

    def __init__(self):
        """Initialize Redis connection"""
        import redis.asyncio as redis

        self.redis_url = settings.redis_url
        self.cache_ttl = settings.redis_cache_ttl
        self.rate_limit_ttl = settings.redis_rate_limit_ttl

        self.pool = redis.ConnectionPool.from_url(
            self.redis_url,
            max_connections=20,
            decode_responses=True,
        )
        self.client = redis.Redis(connection_pool=self.pool)

        logger.info(f"Redis service initialized: {self.redis_url}")

    async def close(self):
        """Close Redis connection"""
        await self.client.close()
        await self.pool.disconnect()


    async def get_cache(self, key: str) -> Optional[Any]:
        """

        Args:

        Returns:
        """
        try:
            value = await self.client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error(f"Redis get error: {e}")
            return None

    async def set_cache(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> bool:
        """

        Args:

        Returns:
        """
        try:
            ttl = ttl or self.cache_ttl
            await self.client.setex(key, ttl, json.dumps(value, default=str))
            return True
        except Exception as e:
            logger.error(f"Redis set error: {e}")
            return False

    async def delete_cache(self, key: str) -> bool:
        """

        Args:

        Returns:
        """
        try:
            await self.client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Redis delete error: {e}")
            return False

    async def delete_pattern(self, pattern: str) -> int:
        """

        Args:

        Returns:
        """
        try:
            keys = []
            async for key in self.client.scan_iter(match=pattern):
                keys.append(key)
            if keys:
                await self.client.delete(*keys)
            return len(keys)
        except Exception as e:
            logger.error(f"Redis delete pattern error: {e}")
            return 0


    async def check_rate_limit(
        self,
        key: str,
        max_requests: int,
        window_seconds: int = 60,
    ) -> tuple[bool, int]:
        """

        Args:

        Returns:
            (allowed, remaining_requests)
        """
        try:
            import time

            now = time.time()
            window_start = now - window_seconds

            pipe = self.client.pipeline()

            pipe.zremrangebyscore(key, 0, window_start)

            pipe.zcard(key)

            pipe.zadd(key, {str(now): now})

            pipe.expire(key, window_seconds)

            results = await pipe.execute()
            current_count = results[1]

            remaining = max(0, max_requests - current_count - 1)
            allowed = current_count < max_requests

            return allowed, remaining

        except Exception as e:
            logger.error(f"Redis rate limit error: {e}")
            return True, max_requests

    async def get_rate_limit_info(
        self,
        key: str,
        window_seconds: int = 60,
    ) -> Dict[str, int]:
        """

        Args:

        Returns:
        """
        try:
            import time

            now = time.time()
            window_start = now - window_seconds

            await self.client.zremrangebyscore(key, 0, window_start)
            count = await self.client.zcard(key)

            return {
                "current_count": count,
                "window_seconds": window_seconds,
            }
        except Exception as e:
            logger.error(f"Redis get rate limit info error: {e}")
            return {"current_count": 0, "window_seconds": window_seconds}


    async def cache_agent(self, agent_id: str, agent_data: Dict) -> bool:
        """Cache Agent configuration"""
        key = f"agent:{agent_id}"
        return await self.set_cache(key, agent_data, ttl=300)  # 5 minutes

    async def get_cached_agent(self, agent_id: str) -> Optional[Dict]:
        """Get cached Agent configuration"""
        key = f"agent:{agent_id}"
        return await self.get_cache(key)

    async def invalidate_agent(self, agent_id: str) -> bool:
        """Invalidate Agent cache"""
        key = f"agent:{agent_id}"
        return await self.delete_cache(key)

    async def cache_session(
        self,
        session_id: str,
        session_data: Dict,
        ttl: int = 3600,
    ) -> bool:
        """Cache session data"""
        key = f"session:{session_id}"
        return await self.set_cache(key, session_data, ttl=ttl)

    async def get_cached_session(self, session_id: str) -> Optional[Dict]:
        """Get cached session data"""
        key = f"session:{session_id}"
        return await self.get_cache(key)


    async def enqueue_task(
        self,
        queue_name: str,
        task_data: Dict,
    ) -> bool:
        """

        Args:

        Returns:
        """
        try:
            await self.client.lpush(
                f"queue:{queue_name}",
                json.dumps(task_data, default=str),
            )
            return True
        except Exception as e:
            logger.error(f"Redis enqueue error: {e}")
            return False

    async def dequeue_task(
        self,
        queue_name: str,
        timeout: int = 0,
    ) -> Optional[Dict]:
        """

        Args:

        Returns:
        """
        try:
            if timeout > 0:
                result = await self.client.brpop(
                    f"queue:{queue_name}",
                    timeout=timeout,
                )
                if result:
                    return json.loads(result[1])
            else:
                result = await self.client.rpop(f"queue:{queue_name}")
                if result:
                    return json.loads(result)
            return None
        except Exception as e:
            logger.error(f"Redis dequeue error: {e}")
            return None

    async def get_queue_length(self, queue_name: str) -> int:
        """Get queue length"""
        try:
            return await self.client.llen(f"queue:{queue_name}")
        except Exception as e:
            logger.error(f"Redis queue length error: {e}")
            return 0


    async def publish(self, channel: str, message: dict) -> int:
        """Publish message to specified channel"""
        try:
            return await self.client.publish(
                channel,
                json.dumps(message, default=str),
            )
        except Exception as e:
            logger.error(f"Redis publish error: {e}")
            return 0

    def get_pubsub(self):
        """Get Pub/Sub object (for subscribing)"""
        return self.client.pubsub()


    async def health_check(self) -> bool:
        """

        Returns:
        """
        try:
            await self.client.ping()
            return True
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return False


_redis_services: Dict[int, RedisService] = {}


async def get_redis() -> RedisService:
    """Get Redis service instance"""
    import asyncio

    loop_id = id(asyncio.get_running_loop())
    service = _redis_services.get(loop_id)
    if service is None:
        service = RedisService()
        _redis_services[loop_id] = service
    return service


async def close_redis():
    """Close Redis connection"""
    services = list(_redis_services.values())
    _redis_services.clear()
    for service in services:
        await service.close()
