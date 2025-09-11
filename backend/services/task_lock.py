"""Task mutex lock service - prevents crawl and index rebuild concurrency conflicts"""

import asyncio
import logging
from typing import Dict, Optional, Set
from datetime import datetime, timezone
from enum import Enum

logger = logging.getLogger(__name__)


class TaskType(str, Enum):
    """Task type"""

    INDEX_REBUILD = "index_rebuild"
    URL_CRAWL = "url_crawl"
    URL_FETCH = "url_fetch"
    URL_REFETCH = "url_refetch"
    URL_DELETE = "url_delete"
    KB_RESET = "kb_reset"


class TaskLock:
    """Task mutex lock manager."""

    def __init__(self):
        self._locks: Dict[str, asyncio.Lock] = {}
        self._active_tasks: Dict[str, Dict[str, datetime]] = {}
        self._task_handles: Dict[str, Dict[str, asyncio.Task]] = {}
        self._pending_rebuild: Set[str] = set()
        self._cancelled_tasks: Dict[str, Set[str]] = {}
        self._lock_creation_lock = asyncio.Lock()  # Protects lock creation

    def _get_lock(self, agent_id: str) -> asyncio.Lock:
        """Get Agent-specific lock (thread-safe)"""
        if agent_id in self._locks:
            return self._locks[agent_id]
        lock = asyncio.Lock()
        self._locks[agent_id] = lock
        return lock

    async def _get_or_create_lock(self, agent_id: str) -> asyncio.Lock:
        """Thread-safely get or create Agent-specific lock"""
        if agent_id in self._locks:
            return self._locks[agent_id]
        async with self._lock_creation_lock:
            if agent_id not in self._locks:
                self._locks[agent_id] = asyncio.Lock()
            return self._locks[agent_id]

    async def acquire_task(
        self, agent_id: str, task_type: TaskType, task_id: str
    ) -> tuple[bool, Optional[str]]:
        """Try to acquire task lock.

        Args:
            agent_id: Agent ID

        Returns:
            (success, error_message) - returns (True, None) on success, (False, error_message) on failure
        """
        lock = await self._get_or_create_lock(agent_id)
        async with lock:
            if agent_id not in self._active_tasks:
                self._active_tasks[agent_id] = {}

            active = self._active_tasks[agent_id]

            if task_type == TaskType.INDEX_REBUILD:
                crawl_tasks = [
                    t
                    for t in active.keys()
                    if t.startswith(("crawl_", "fetch_", "refetch_", "delete_"))
                ]
                if crawl_tasks:
                    return (
                        False,
                        f"An ongoing crawl task exists: {crawl_tasks[0]}. Wait for it to complete before rebuilding the index.",
                    )

                rebuild_tasks = [t for t in active.keys() if t.startswith("rebuild_")]
                if rebuild_tasks:
                    return False, f"Index rebuild already in progress: {rebuild_tasks[0]}"

            elif task_type in (
                TaskType.URL_CRAWL,
                TaskType.URL_FETCH,
                TaskType.URL_REFETCH,
            ):
                blocking_tasks = [
                    t for t in active.keys() if t.startswith(("rebuild_", "delete_"))
                ]
                if blocking_tasks:
                    return (
                        False,
                        f"Task in progress: {blocking_tasks[0]}. Wait for it to complete before starting a crawl.",
                    )

            elif task_type == TaskType.URL_DELETE:
                blocking_tasks = [
                    t for t in active.keys() if t.startswith(("rebuild_", "delete_"))
                ]
                if blocking_tasks:
                    return (
                        False,
                        f"Task in progress: {blocking_tasks[0]}. Wait for it to complete before deleting.",
                    )

            active[task_id] = datetime.now(timezone.utc)
            logger.info(f"Task acquired: {task_id} for agent {agent_id}")
            return True, None

    async def register_task_handle(
        self, agent_id: str, task_id: str, task: asyncio.Task
    ):
        """Record the running asyncio Task handle for proper cancellation."""
        lock = await self._get_or_create_lock(agent_id)
        async with lock:
            self._task_handles.setdefault(agent_id, {})[task_id] = task

    async def release_task(self, agent_id: str, task_id: str):
        """Release task lock.

        Args:
            agent_id: Agent ID
        """
        lock = await self._get_or_create_lock(agent_id)
        async with lock:
            if agent_id in self._active_tasks:
                if task_id in self._active_tasks[agent_id]:
                    del self._active_tasks[agent_id][task_id]
                    logger.info(f"Task released: {task_id} for agent {agent_id}")
            if agent_id in self._cancelled_tasks:
                self._cancelled_tasks[agent_id].discard(task_id)
                if not self._cancelled_tasks[agent_id]:
                    del self._cancelled_tasks[agent_id]
            if agent_id in self._task_handles:
                self._task_handles[agent_id].pop(task_id, None)
                if not self._task_handles[agent_id]:
                    del self._task_handles[agent_id]

            if agent_id in self._pending_rebuild and not self._active_tasks.get(
                agent_id
            ):
                self._pending_rebuild.discard(agent_id)
                return True  # Indicates a rebuild is needed
        return False

    async def schedule_rebuild_after_tasks(self, agent_id: str):
        """Schedule index rebuild after current task completes.

        Args:
            agent_id: Agent ID
        """
        lock = await self._get_or_create_lock(agent_id)
        async with lock:
            self._pending_rebuild.add(agent_id)
            logger.info(
                f"Scheduled index rebuild after current tasks for agent {agent_id}"
            )

    def has_pending_rebuild(self, agent_id: str) -> bool:
        """Check whether there is a pending index rebuild"""
        return agent_id in self._pending_rebuild

    def get_active_tasks(self, agent_id: str) -> Dict[str, datetime]:
        """Get Agent active task list"""
        return self._active_tasks.get(agent_id, {}).copy()

    def get_registered_task_ids(self, agent_id: str) -> Set[str]:
        """Get task IDs that have registered asyncio task handles."""
        return set(self._task_handles.get(agent_id, {}).keys())

    def is_task_running(self, agent_id: str, task_type: TaskType) -> bool:
        """Check whether a specific task type is running"""
        if agent_id not in self._active_tasks:
            return False

        prefix_map = {
            TaskType.INDEX_REBUILD: "rebuild_",
            TaskType.URL_CRAWL: "crawl_",
            TaskType.URL_FETCH: "fetch_",
            TaskType.URL_REFETCH: "refetch_",
            TaskType.URL_DELETE: "delete_",
        }
        prefix = prefix_map.get(task_type, "")
        return any(t.startswith(prefix) for t in self._active_tasks[agent_id])

    def has_any_active_task(self, agent_id: str) -> bool:
        """Check whether there are any active tasks"""
        return bool(self._active_tasks.get(agent_id))

    async def cancel_tasks(
        self, agent_id: str, task_types: Optional[Set[TaskType]] = None
    ) -> list[str]:
        """Mark active tasks for the specified agent as cancelled."""
        lock = await self._get_or_create_lock(agent_id)
        async with lock:
            active = self._active_tasks.get(agent_id, {})
            task_handles = self._task_handles.get(agent_id, {})
            if not active and not task_handles:
                return []

            prefix_map = {
                TaskType.INDEX_REBUILD: "rebuild_",
                TaskType.URL_CRAWL: "crawl_",
                TaskType.URL_FETCH: "fetch_",
                TaskType.URL_REFETCH: "refetch_",
                TaskType.URL_DELETE: "delete_",
            }
            prefixes = {
                prefix_map[task_type]
                for task_type in (task_types or set(prefix_map.keys()))
                if task_type in prefix_map
            }
            task_handles = self._task_handles.get(agent_id, {})
            cancellable_task_ids = set(active.keys()) | set(task_handles.keys())
            cancelled = [
                task_id
                for task_id in cancellable_task_ids
                if any(task_id.startswith(prefix) for prefix in prefixes)
            ]
            if cancelled:
                self._cancelled_tasks.setdefault(agent_id, set()).update(cancelled)
                for task_id in cancelled:
                    task = task_handles.get(task_id)
                    if task and not task.done():
                        task.cancel()
            return cancelled

    def is_cancelled(self, agent_id: str, task_id: str) -> bool:
        """Check whether a task has been marked as cancelled."""
        return task_id in self._cancelled_tasks.get(agent_id, set())


task_lock = TaskLock()
