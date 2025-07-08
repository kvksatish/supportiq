import hashlib
import uuid

from sqlalchemy import (
    Column,
    String,
    DateTime,
    Integer,
    Text,
    Boolean,
    ForeignKey,
    JSON,
    Enum as SQLEnum,
    Index,
    Float,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base
from config import DEFAULT_AGENT_MAX_TOKENS, DEFAULT_AGENT_SIMILARITY_THRESHOLD


def normalize_url(url: str) -> str:
    """Normalize URL (for deduplication)"""
    url = url.strip().lower()
    if url.endswith("/"):
        url = url[:-1]
    if url.startswith("https://www."):
        url = url.replace("https://www.", "https://", 1)
    elif url.startswith("http://www."):
        url = url.replace("http://www.", "http://", 1)
    return url


def compute_content_hash(content: str) -> str:
    """Calculate content hash (for deduplication)"""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class Workspace(Base):
    """Workspace model"""

    __tablename__ = "workspaces"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, default="Default Workspace")
    owner_email = Column(String(255), unique=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    agents = relationship(
        "Agent", back_populates="workspace", cascade="all, delete-orphan"
    )
    quotas = relationship("WorkspaceQuota", back_populates="workspace", uselist=False)
    admin_users = relationship("AdminUser", back_populates="workspace")


class Agent(Base):
    """Agent model"""

    __tablename__ = "agents"

    id = Column(
        String(50), primary_key=True, default=lambda: f"agt_{uuid.uuid4().hex[:12]}"
    )
    workspace_id = Column(
        Integer, ForeignKey("workspaces.id"), nullable=False, index=True
    )

    name = Column(String(100), nullable=False, default="AI Agent")
    description = Column(Text, nullable=True)
    agent_type = Column(String(50), nullable=False, default="website_support")
    channel_mode = Column(String(50), nullable=False, default="web_widget")
    avatar = Column(String(500), nullable=True)

    system_prompt = Column(
        Text, nullable=False, default="You are a helpful customer service assistant."
    )
    model = Column(String(100), nullable=False, default="gpt-4o-mini")
    temperature = Column(Float, nullable=False, default=0.7)
    max_tokens = Column(Integer, nullable=False, default=DEFAULT_AGENT_MAX_TOKENS)

    api_key = Column(String(500), nullable=True)
    api_base = Column(String(500), nullable=True, default="https://api.openai.com/v1")

    # Jina Embedding API Key
    jina_api_key = Column(String(500), nullable=True)

    # SiliconFlow Embedding API Key
    siliconflow_api_key = Column(String(500), nullable=True)

    provider_type = Column(
        SQLEnum(
            "openai",
            "openai_native",
            "google",
            "anthropic",
            "xai",
            "openrouter",
            "zai",
            "deepseek",
            "volcengine",
            "moonshot",
            "aliyun_bailian",
            "siliconflow",
            name="llm_provider",
        ),
        nullable=True,
        default="openai",
    )

    azure_endpoint = Column(String(500), nullable=True)
    azure_deployment_name = Column(String(100), nullable=True)
    azure_api_version = Column(String(20), nullable=True)

    anthropic_version = Column(String(20), nullable=True, default="2023-06-01")

    google_project_id = Column(String(100), nullable=True)
    google_region = Column(String(50), nullable=True)

    provider_config = Column(JSON, nullable=True)

    embedding_provider = Column(String(20), nullable=False, default="jina")
    embedding_api_base = Column(String(500), nullable=True)
    embedding_model = Column(String(100), nullable=False, default="jina-embeddings-v3")
    embedding_batch_size = Column(Integer, nullable=False, default=4)
    kb_setup_completed = Column(Boolean, nullable=False, default=False)
    crawl_max_depth = Column(Integer, nullable=False, default=2)  # Site-wide crawl depth
    crawl_max_pages = Column(Integer, nullable=False, default=20)  # Max pages for site-wide crawl
    url_fetch_interval_days = Column(
        Integer, nullable=False, default=7
    )  # URL auto-fetch interval (days)
    enable_auto_fetch = Column(
        Boolean, nullable=False, default=False
    )  # Whether auto-fetch is enabled

    top_k = Column(Integer, nullable=False, default=8)
    similarity_threshold = Column(
        Float, nullable=False, default=DEFAULT_AGENT_SIMILARITY_THRESHOLD
    )
    enable_context = Column(Boolean, nullable=False, default=False)

    rate_limit_per_minute = Column(
        Integer, nullable=False, default=20
    )  # Per-minute conversation limit (0 = unlimited)
    restricted_reply = Column(
        Text, nullable=True, default="Sorry, the service is currently restricted. Please try again later."
    )  # Auto-reply (rate limiting, AI service errors, etc.)
    last_error_code = Column(String(50), nullable=True)
    last_error_message = Column(Text, nullable=True)
    last_error_at = Column(DateTime(timezone=True), nullable=True)
    allowed_widget_origins = Column(JSON, nullable=True, default=None)

    persona_type = Column(
        String(20), nullable=False, default="general"
    )  # general, customer-service, sales, custom

    widget_title = Column(String(100), nullable=True, default="AI Support")
    widget_color = Column(String(20), nullable=True, default="#06B6D4")
    welcome_message = Column(
        Text, nullable=True, default="Hello! I am the Basjoo assistant. How can I help you?"
    )
    history_days = Column(Integer, nullable=False, default=30)

    is_active = Column(Boolean, default=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)
    purge_after = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    kb_id = Column(
        String(36), ForeignKey("knowledge_bases.id"), nullable=True, index=True
    )

    workspace = relationship("Workspace", back_populates="agents")
    url_sources = relationship(
        "URLSource", back_populates="agent", cascade="all, delete-orphan"
    )
    knowledge_files = relationship(
        "KnowledgeFile", back_populates="agent", cascade="all, delete-orphan"
    )
    chat_sessions = relationship(
        "ChatSession", back_populates="agent", cascade="all, delete-orphan"
    )
    members = relationship(
        "AgentMember", back_populates="agent", cascade="all, delete-orphan"
    )
    knowledge_base = relationship("KnowledgeBase", back_populates="agents")


class URLSource(Base):
    """URL knowledge source model"""

    __tablename__ = "url_sources"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(String(50), ForeignKey("agents.id"), nullable=False, index=True)

    url = Column(String(1000), nullable=False, index=True)
    normalized_url = Column(String(1000), nullable=False, index=True)  # Normalized URL

    status = Column(
        SQLEnum("pending", "fetching", "success", "failed", name="url_status"),
        default="pending",
        index=True,
    )
    last_fetch_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)

    title = Column(String(500), nullable=True)
    content = Column(Text, nullable=True)  # Cleaned body content
    content_hash = Column(String(64), nullable=True)  # For deduplication

    fetch_metadata = Column(
        JSON, nullable=True
    )  # etag, last_modified, content_length, etc.
    is_indexed = Column(Boolean, nullable=False, default=False)  # Whether indexed/trained
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    agent = relationship("Agent", back_populates="url_sources")

    __table_args__ = (
        Index("ix_url_sources_agent_status", "agent_id", "status"),
        UniqueConstraint("agent_id", "normalized_url", name="uq_agent_normalized_url"),
    )


class KnowledgeFile(Base):
    """Knowledge file model"""

    __tablename__ = "knowledge_files"

    id = Column(
        String(50), primary_key=True, default=lambda: f"kf_{uuid.uuid4().hex[:12]}"
    )
    agent_id = Column(String(50), ForeignKey("agents.id"), nullable=False, index=True)

    filename = Column(String(500), nullable=False)
    file_size = Column(Integer, nullable=True)  # bytes
    file_type = Column(String(50), nullable=True)  # pdf, txt, csv, etc.

    status = Column(
        SQLEnum(
            "uploading", "processing", "ready", "failed", "pending", name="file_status"
        ),
        default="uploading",
        index=True,
    )
    error_message = Column(Text, nullable=True)

    metadata_json = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    agent = relationship("Agent", back_populates="knowledge_files")

    __table_args__ = (Index("ix_knowledge_files_agent", "agent_id"),)


class ChatSession(Base):
    """Chat session model"""

    __tablename__ = "chat_sessions"

    id = Column(
        String(50), primary_key=True, default=lambda: f"sess_{uuid.uuid4().hex[:12]}"
    )
    agent_id = Column(String(50), ForeignKey("agents.id"), nullable=False, index=True)

    session_id = Column(
        String(100), nullable=False, index=True
    )  # Client-provided session_id
    locale = Column(String(10), nullable=True, default="zh-CN")

    visitor_id = Column(String(100), nullable=True, index=True)  # Visitor identifier
    visitor_ip = Column(String(50), nullable=True)  # Visitor IP
    visitor_user_agent = Column(String(500), nullable=True)  # Visitor browser info
    visitor_country = Column(String(50), nullable=True)  # Visitor country
    visitor_region = Column(String(50), nullable=True)  # Visitor province/region
    visitor_city = Column(String(50), nullable=True)  # Visitor city

    status = Column(String(20), nullable=False, default="active", index=True)

    message_count = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    agent = relationship("Agent", back_populates="chat_sessions")
    messages = relationship(
        "ChatMessage", back_populates="session", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index(
            "uq_chat_sessions_active_session",
            "agent_id",
            "session_id",
            unique=True,
            sqlite_where=text("status != 'closed'"),
        ),
        Index("ix_chat_sessions_agent_session", "agent_id", "session_id"),
        Index("ix_chat_sessions_updated", "updated_at"),
    )


class ChatMessage(Base):
    """Chat message model"""

    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(
        String(50), ForeignKey("chat_sessions.id"), nullable=False, index=True
    )

    role = Column(
        SQLEnum("user", "assistant", "system", name="message_role"), nullable=False
    )
    content = Column(Text, nullable=False)

    sender_type = Column(String(20), nullable=True)  # 'agent', 'human'
    sender_id = Column(String(50), nullable=True)  # Admin ID (when sent by human)

    sources = Column(
        JSON, nullable=True
    )  # [{"type": "url", "title": "...", "url": "...", "snippet": "..."}]

    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("ChatSession", back_populates="messages")

    __table_args__ = (
        Index("ix_chat_messages_session_created", "session_id", "created_at"),
    )


class WorkspaceQuota(Base):
    """Workspace quota model"""

    __tablename__ = "workspace_quotas"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(
        Integer, ForeignKey("workspaces.id"), nullable=False, unique=True, index=True
    )

    max_agents = Column(Integer, default=10)
    max_urls = Column(Integer, default=500)
    max_qa_items = Column(Integer, default=100)
    max_messages_per_day = Column(Integer, default=1500)
    max_total_text_mb = Column(Integer, default=20)  # Maximum text size MB

    used_urls = Column(Integer, default=0)
    used_qa_items = Column(Integer, default=0)
    used_messages_today = Column(Integer, default=0)
    used_total_text_mb = Column(Float, default=0.0)

    last_message_reset = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    workspace = relationship("Workspace", back_populates="quotas")


class AgentMember(Base):
    """Per-agent admin membership."""

    __tablename__ = "agent_members"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(String(50), ForeignKey("agents.id"), nullable=False, index=True)
    admin_user_id = Column(
        Integer, ForeignKey("admin_users.id"), nullable=False, index=True
    )
    role = Column(String(50), default="admin", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    agent = relationship("Agent", back_populates="members")
    admin_user = relationship("AdminUser", back_populates="agent_members")

    __table_args__ = (
        UniqueConstraint("agent_id", "admin_user_id", name="uq_agent_member_admin"),
    )


class IndexJob(Base):
    """Index build task model"""

    __tablename__ = "index_jobs"

    id = Column(
        String(50), primary_key=True, default=lambda: f"job_{uuid.uuid4().hex[:12]}"
    )
    agent_id = Column(String(50), ForeignKey("agents.id"), nullable=False, index=True)

    job_type = Column(
        SQLEnum("full", "incremental", "url_refetch", name="job_type"), nullable=False
    )
    status = Column(
        SQLEnum("queued", "running", "completed", "failed", name="job_status"),
        default="queued",
        index=True,
    )

    params = Column(JSON, nullable=True)  # {"url_ids": [...], "force": true}

    result = Column(JSON, nullable=True)  # {"chunks_indexed": 100, "errors": []}
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_jobs_agent_status", "agent_id", "status"),
        Index("ix_jobs_created", "created_at"),
    )


class AdminUser(Base):
    """Admin user model (for management dashboard login)"""

    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    name = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True)
    role = Column(String(50), default="admin", nullable=False)
    workspace_id = Column(
        Integer, ForeignKey("workspaces.id"), nullable=True, index=True
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    workspace = relationship("Workspace", back_populates="admin_users")
    agent_members = relationship(
        "AgentMember", back_populates="admin_user", cascade="all, delete-orphan"
    )


class Tenant(Base):
    """Tenant table (multi-tenant top level)"""

    __tablename__ = "tenants"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False)
    slug = Column(String(50), unique=True, nullable=False, index=True)
    plan = Column(String(20), nullable=False, default="free")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    knowledge_bases = relationship(
        "KnowledgeBase", back_populates="tenant", cascade="all, delete-orphan"
    )


class KnowledgeBase(Base):
    """Knowledge base table (per-agent isolated KB)"""

    __tablename__ = "knowledge_bases"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    embedding_model = Column(String(100), nullable=False, default="BAAI/bge-m3")
    embedding_base_url = Column(String(500), nullable=True)
    vector_backend = Column(String(20), nullable=False, default="qdrant")
    qdrant_collection = Column(String(50), unique=True, nullable=False, index=True)
    is_locked = Column(
        Boolean, nullable=False, default=False
    )  # Lock embedding config once chunks exist
    chunk_size = Column(Integer, nullable=False, default=512)
    chunk_overlap = Column(Integer, nullable=False, default=64)
    status = Column(
        SQLEnum(
            "active",
            "resetting",
            "processing",
            "error",
            name="kb_status",
        ),
        default="active",
        nullable=False,
        index=True,
    )
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    tenant = relationship("Tenant", back_populates="knowledge_bases")
    documents = relationship(
        "KbDocument", back_populates="knowledge_base", cascade="all, delete-orphan"
    )
    agents = relationship("Agent", back_populates="knowledge_base")


class KbDocument(Base):
    """Document table"""

    __tablename__ = "kb_documents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    kb_id = Column(
        String(36), ForeignKey("knowledge_bases.id"), nullable=False, index=True
    )
    tenant_id = Column(
        String(36), ForeignKey("tenants.id"), nullable=False, index=True
    )  # Redundant, for easy filtering
    filename = Column(String(500), nullable=False)
    file_type = Column(String(20), nullable=True)
    status = Column(
        SQLEnum("pending", "processing", "ready", "error", name="kb_doc_status"),
        default="pending",
        index=True,
    )
    chunk_count = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    file_size = Column(Integer, nullable=True)
    storage_path = Column(String(1000), nullable=True)
    # Metadata for document source info (e.g., URL for crawled pages)
    metadata_json = Column(JSON, nullable=True, default=None)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    knowledge_base = relationship("KnowledgeBase", back_populates="documents")
    chunks = relationship(
        "KbChunk", back_populates="document", cascade="all, delete-orphan"
    )


class KbChunk(Base):
    """Chunk metadata table"""

    __tablename__ = "kb_chunks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    kb_id = Column(
        String(36), ForeignKey("knowledge_bases.id"), nullable=False, index=True
    )
    doc_id = Column(
        String(36), ForeignKey("kb_documents.id"), nullable=False, index=True
    )
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    vector_id = Column(String(100), nullable=True, index=True)  # Qdrant point id
    chunk_index = Column(Integer, nullable=False)
    content_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    document = relationship("KbDocument", back_populates="chunks")
