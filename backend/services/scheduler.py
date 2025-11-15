"""Scheduled task service"""

import logging
from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, delete

from database import AsyncSessionLocal
from models import (
    Agent,
    AgentMember,
    ChatMessage,
    ChatSession,
    KnowledgeFile,
    URLSource,
    Workspace,
    WorkspaceQuota,
)
from services.crawler import SiteCrawler

logger = logging.getLogger(__name__)


def as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if not dt:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class URLFetchScheduler:
    """URL auto-fetch scheduler"""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.running = False

    def start(self):
        """Start scheduler"""
        if not self.running:
            self.scheduler.start()
            self.running = True
            logger.info("URL fetch scheduler started")

            self.scheduler.add_job(
                self.check_and_fetch_urls,
                trigger=IntervalTrigger(hours=1),  # Check every hour
                id="check_url_fetches",
                name="Check and fetch URLs periodically",
                replace_existing=True,
            )
        else:
            logger.warning("Scheduler already running")

    def stop(self):
        """Stop scheduler"""
        if self.running:
            self.scheduler.shutdown()
            self.running = False
            logger.info("URL fetch scheduler stopped")

    async def check_and_fetch_urls(self):
        """

        """
        try:
            logger.info("Checking URLs that need to be refetched...")

            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Agent).where(Agent.enable_auto_fetch == True)
                )
                agents = result.scalars().all()

                for agent in agents:
                    await self.fetch_agent_urls(db, agent)

        except Exception as e:
            logger.exception(f"Error in check_and_fetch_urls: {e}")

    async def fetch_agent_urls(self, db: AsyncSession, agent: Agent):
        """Fetch URLs for a specific Agent; releases the session before executing HTTP requests"""
        try:
            interval_days = agent.url_fetch_interval_days or 7
            threshold_date = datetime.now(timezone.utc) - timedelta(days=interval_days)

            result = await db.execute(
                select(URLSource).where(
                    and_(
                        URLSource.agent_id == agent.id,
                        URLSource.status == "success",
                        (
                            (URLSource.last_fetch_at < threshold_date)
                            | (URLSource.last_fetch_at.is_(None))
                        ),
                    )
                )
            )
            url_sources = result.scalars().all()

            if not url_sources:
                logger.debug(f"No URLs need refetching for agent {agent.id}")
                return

            logger.info(
                f"Found {len(url_sources)} URLs to refetch for agent {agent.id} "
                f"(interval: {interval_days} days)"
            )

            crawler = SiteCrawler()

            for url_source in url_sources:
                await self.fetch_single_url(crawler, url_source.id, str(agent.id))

        except Exception as e:
            logger.exception(f"Error in fetch_agent_urls for agent {agent.id}: {e}")

    async def fetch_single_url(
        self,
        crawler: SiteCrawler,
        url_source_id: int,
        agent_id: str,
    ):
        """Fetch a single URL using a short-lived database session"""
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(URLSource).where(URLSource.id == url_source_id)
                )
                url_source = result.scalar_one_or_none()
                if not url_source:
                    return
                logger.info(f"Refetching URL {url_source.url} (ID: {url_source.id})")
                url = url_source.url
                old_hash = url_source.content_hash
                url_source.status = "fetching"
                await db.commit()

            page_result = await crawler.crawl_single_page(url)

            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(URLSource).where(URLSource.id == url_source_id)
                )
                url_source = result.scalar_one_or_none()
                if not url_source:
                    return

                if page_result.success:
                    new_hash = page_result.content_hash
                    if old_hash != new_hash:
                        url_source.status = "success"
                        url_source.title = page_result.title
                        url_source.content = page_result.content
                        url_source.content_hash = new_hash
                        url_source.last_fetch_at = datetime.now(timezone.utc)
                        url_source.fetch_metadata = page_result.metadata
                        logger.info(
                            f"URL {url_source.url} content changed, updated. "
                            f"Old hash: {old_hash[:8] if old_hash else 'None'}..., New hash: {new_hash[:8]}..."
                        )
                    else:
                        url_source.status = "success"
                        url_source.last_fetch_at = datetime.now(timezone.utc)
                        logger.info(
                            f"URL {url_source.url} content unchanged, only updated timestamp"
                        )

                    await db.commit()

                    if old_hash != new_hash:
                        logger.info(
                            f"URL content changed for {url_source.url} (self-KB handles indexing)"
                        )
                else:
                    url_source.status = "failed"
                    url_source.last_error = page_result.error or "Unknown error"
                    await db.commit()
                    logger.error(
                        f"Failed to refetch URL {url_source.url}: {page_result.error}"
                    )

        except Exception as e:
            logger.exception(
                f"Error in fetch_single_url for URL ID {url_source_id}: {e}"
            )
            try:
                async with AsyncSessionLocal() as db:
                    result = await db.execute(
                        select(URLSource).where(URLSource.id == url_source_id)
                    )
                    url_source = result.scalar_one_or_none()
                    if url_source:
                        url_source.status = "failed"
                        url_source.last_error = str(e)
                        await db.commit()
            except Exception:
                logger.exception("Failed to persist fetch_single_url error state")


url_fetch_scheduler = URLFetchScheduler()


class HistoryCleanupScheduler:
    """History cleanup scheduler"""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.running = False

    def start(self):
        """Start scheduler"""
        if not self.running:
            self.scheduler.start()
            self.scheduler.add_job(
                self.cleanup_expired_sessions,
                trigger="cron",
                hour=3,
                minute=0,
                id="cleanup_expired_sessions",
                name="Cleanup expired chat sessions daily",
                replace_existing=True,
            )
            self.running = True
            logger.info("History cleanup scheduler started")
        else:
            logger.warning("History cleanup scheduler already running")

    def stop(self):
        """Stop scheduler"""
        if self.running:
            self.scheduler.shutdown()
            self.running = False
            logger.info("History cleanup scheduler stopped")

    async def cleanup_expired_sessions(self):
        """

        """
        from models import ChatSession, ChatMessage

        try:
            logger.info("Starting cleanup of expired chat sessions...")

            async with AsyncSessionLocal() as db:
                result = await db.execute(select(Agent))
                agents = result.scalars().all()

                total_deleted = 0

                for agent in agents:
                    if agent.history_days <= 0:
                        continue  # Skip agents with no cleanup needed

                    cutoff_date = datetime.now(timezone.utc) - timedelta(
                        days=agent.history_days
                    )

                    expired_result = await db.execute(
                        select(ChatSession).where(
                            and_(
                                ChatSession.agent_id == agent.id,
                                or_(
                                    ChatSession.updated_at < cutoff_date,
                                    and_(
                                        ChatSession.updated_at.is_(None),
                                        ChatSession.created_at < cutoff_date,
                                    ),
                                ),
                            )
                        )
                    )
                    expired_sessions = expired_result.scalars().all()

                    for session in expired_sessions:
                        await db.delete(session)
                        total_deleted += 1

                await db.commit()
                logger.info(
                    f"Cleanup completed. Deleted {total_deleted} expired sessions."
                )

        except Exception as e:
            logger.exception(f"Error in cleanup_expired_sessions: {e}")


history_cleanup_scheduler = HistoryCleanupScheduler()


class SessionAutoCloseScheduler:
    """Session auto-close scheduler"""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.running = False
        self.inactivity_timeout_minutes = 30  # Auto-close after 30 minutes of inactivity

    def start(self):
        if not self.running:
            self.scheduler.start()
            self.scheduler.add_job(
                self.close_inactive_sessions,
                trigger="interval",
                minutes=5,
                id="close_inactive_sessions",
                name="Close inactive sessions",
                replace_existing=True,
            )
            self.running = True
            logger.info("Session auto-close scheduler started")

    def stop(self):
        if self.running:
            self.scheduler.shutdown()
            self.running = False
            logger.info("Session auto-close scheduler stopped")

    async def close_inactive_sessions(self):
        """Close sessions with long-term inactivity"""
        from models import ChatSession, ChatMessage

        try:
            async with AsyncSessionLocal() as db:
                cutoff = datetime.now(timezone.utc) - timedelta(
                    minutes=self.inactivity_timeout_minutes
                )

                result = await db.execute(
                    select(ChatSession).where(
                        ChatSession.status.in_(["active", "taken_over"])
                    )
                )
                sessions = result.scalars().all()

                closed = 0
                for session in sessions:
                    last_msg = await db.execute(
                        select(ChatMessage.created_at)
                        .where(ChatMessage.session_id == session.id)
                        .order_by(ChatMessage.created_at.desc())
                        .limit(1)
                    )
                    last_time = last_msg.scalar_one_or_none()

                    if last_time and last_time.tzinfo is None:
                        last_time = last_time.replace(tzinfo=timezone.utc)

                    if last_time:
                        should_close = last_time < cutoff
                    elif session.created_at:
                        created = session.created_at
                        if created.tzinfo is None:
                            created = created.replace(tzinfo=timezone.utc)
                        should_close = created < cutoff
                    else:
                        should_close = True

                    if should_close:
                        session.status = "closed"
                        closed += 1

                await db.commit()
                if closed > 0:
                    logger.info(f"Auto-closed {closed} inactive sessions")
        except Exception as e:
            logger.exception(f"Error in close_inactive_sessions: {e}")


session_auto_close_scheduler = SessionAutoCloseScheduler()


class AgentPurgeScheduler:
    """Permanently deletes agents after their restore window expires."""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.running = False

    def start(self):
        if self.running:
            return
        self.scheduler.start()
        self.running = True
        self.scheduler.add_job(
            self.purge_expired_agents,
            trigger=IntervalTrigger(hours=24),
            id="purge_expired_agents",
            name="Purge expired soft-deleted agents",
            replace_existing=True,
        )

    def stop(self):
        if self.running:
            self.scheduler.shutdown()
            self.running = False

    async def purge_expired_agents(self):
        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Agent).where(Agent.purge_after.is_not(None))
            )
            agents = [
                agent
                for agent in result.scalars().all()
                if as_utc(agent.purge_after) and as_utc(agent.purge_after) <= now
            ]
            for agent in agents:
                await self._purge_agent(db, agent)
            await db.commit()

    async def _purge_agent(self, db: AsyncSession, agent: Agent):
        session_ids = await db.execute(
            select(ChatSession.id).where(ChatSession.agent_id == agent.id)
        )
        ids = [row[0] for row in session_ids.all()]
        if ids:
            await db.execute(delete(ChatMessage).where(ChatMessage.session_id.in_(ids)))
        await db.execute(delete(ChatSession).where(ChatSession.agent_id == agent.id))
        await db.execute(delete(URLSource).where(URLSource.agent_id == agent.id))
        await db.execute(
            delete(KnowledgeFile).where(KnowledgeFile.agent_id == agent.id)
        )
        await db.execute(delete(AgentMember).where(AgentMember.agent_id == agent.id))
        workspace_id = agent.workspace_id
        await db.delete(agent)
        await db.execute(
            delete(WorkspaceQuota).where(WorkspaceQuota.workspace_id == workspace_id)
        )
        await db.execute(delete(Workspace).where(Workspace.id == workspace_id))


agent_purge_scheduler = AgentPurgeScheduler()
