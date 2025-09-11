"""Scrapling service HTTP client"""

import httpx
import logging
from typing import Dict, Any, List, Tuple
from datetime import datetime, timezone

from config import settings

logger = logging.getLogger(__name__)


class ScraplingClient:
    """Scrapling microservice HTTP client"""

    def __init__(self, base_url: str = None, timeout: int = 60):
        self.base_url = (base_url or settings.scrapling_service_url).rstrip("/")
        self.timeout = timeout

    async def fetch(self, url: str) -> Dict[str, Any]:
        """

        Args:

        Returns:
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/fetch",
                    json={"url": url, "timeout": self.timeout},
                )
                resp.raise_for_status()
                data = resp.json()

                # Add server-side timestamp
                if data.get("success") and data.get("metadata"):
                    data["metadata"]["fetched_at"] = datetime.now(timezone.utc).isoformat()
                    data["metadata"]["fetcher"] = "scrapling"

                return data

        except httpx.TimeoutException:
            logger.error(f"Timeout fetching {url} via Scrapling service ({self.timeout}s)")
            return {"success": False, "error": f"Timeout after {self.timeout} seconds"}
        except httpx.ConnectError:
            logger.error(f"Cannot connect to Scrapling service at {self.base_url}")
            return {"success": False, "error": "Scrapling service unavailable"}
        except Exception as e:
            logger.error(f"Scrapling client error for {url}: {e}")
            return {"success": False, "error": str(e)}

    async def discover_subpages(
        self, url: str, max_depth: int = 1, max_pages: int = 20
    ) -> List[Tuple[str, int]]:
        """

        Args:

        Returns:
            Discovered subpage URL and depth list [(url, depth), ...]
        """
        # Calculate timeout: scrapling-service BFS fetches each page with 30s internal
        # timeout. Use max(self.timeout, 30 + max_pages * 30) so we don't cut off
        # in-progress BFS work.
        discover_timeout = max(self.timeout, 30 + max_pages * 30)
        try:
            async with httpx.AsyncClient(timeout=discover_timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/discover",
                    json={
                        "url": url,
                        "max_depth": max_depth,
                        "max_pages": max_pages,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                return [(item["url"], item["depth"]) for item in data.get("urls", [])]

        except httpx.TimeoutException:
            logger.error(f"Timeout discovering subpages from {url} via Scrapling service")
            return []
        except httpx.ConnectError:
            logger.error(f"Cannot connect to Scrapling service at {self.base_url}")
            return []
        except Exception as e:
            logger.error(f"Scrapling client error discovering subpages from {url}: {e}")
            return []

    async def health_check(self) -> bool:
        """Check whether Scrapling service is reachable"""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self.base_url}/health")
                return resp.status_code == 200
        except Exception:
            return False


_default_client: ScraplingClient = None


def get_scrapling_client() -> ScraplingClient:
    """Get global ScraplingClient instance"""
    global _default_client
    if _default_client is None:
        _default_client = ScraplingClient()
    return _default_client
