"""API v1 Pydantic schemas"""

from pydantic import AliasChoices, BaseModel, Field, ConfigDict, field_validator
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from urllib.parse import urlsplit

from services.url_safety import validate_url_safe


def normalize_widget_origin(origin: str) -> str:
    raw_origin = origin.strip()
    if not raw_origin:
        raise ValueError("Widget origin cannot be empty")

    parsed = urlsplit(raw_origin)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Widget origins must start with http:// or https://")

    if parsed.username or parsed.password:
        raise ValueError("Widget origins cannot include credentials")

    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


# ========== Chat & Context Schemas ==========


class ChatRequest(BaseModel):
    """Chat request"""

    agent_id: str = Field(..., description="Agent ID")
    message: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="User message (limited to 1000 chars to prevent memory exhaustion)",
    )
    locale: Optional[str] = Field(None, description="Language")
    session_id: Optional[str] = Field(
        None, max_length=200, description="Session ID (for multi-turn conversations)"
    )
    visitor_id: Optional[str] = Field(None, max_length=100, description="Visitor identifier")
    timezone: Optional[str] = Field(None, description="Client timezone")
    params: Optional[Dict[str, Any]] = Field(
        None, description="Inference parameters (temperature, max_tokens, etc.)"
    )


class SourceItem(BaseModel):
    """Source item"""

    type: Literal["url", "file"] = Field(..., description="Source type")
    title: Optional[str] = Field(None, description="Title")
    url: Optional[str] = Field(None, description="URL (URL type)")
    snippet: Optional[str] = Field(None, description="Snippet")
    filename: Optional[str] = Field(None, description="Filename (file type)")


class UsageInfo(BaseModel):

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatResponse(BaseModel):

    reply: str = Field(..., description="AI reply")
    sources: List[SourceItem] = Field(default_factory=list, description="Referenced sources")
    usage: Optional[UsageInfo] = Field(None, description="Token usage")
    session_id: Optional[str] = Field(None, description="Session ID")
    message_id: Optional[int] = Field(None, description="Message ID")
    taken_over: bool = Field(False, description="Whether the session has been taken over by a human")


class ContextRequest(BaseModel):

    agent_id: str = Field(..., description="Agent ID")
    query: str = Field(..., min_length=1, max_length=500, description="Query text")
    top_k: Optional[int] = Field(5, ge=1, le=20, description="Number of results to return")
    locale: Optional[str] = Field(None, description="Language code")


class ContextItem(BaseModel):

    type: Literal["url", "file"] = Field(..., description="Type")
    url: Optional[str] = Field(None, description="URL (URL type)")
    title: Optional[str] = Field(None, description="Title")
    filename: Optional[str] = Field(None, description="Filename (file type)")
    score: float = Field(..., ge=0, le=1, description="Similarity score")


class ContextResponse(BaseModel):

    contexts: List[ContextItem] = Field(default_factory=list, description="Retrieval results")


# ========== URL Management Schemas ==========


def _validate_safe_ingest_url(url: str) -> str:
    normalized = (url or "").strip()
    if len(normalized) > 2048:
        raise ValueError("URL exceeds maximum length")
    safe, reason = validate_url_safe(normalized)
    if not safe:
        raise ValueError(f"Invalid URL: {normalized}")
    return normalized


class URLCreateRequest(BaseModel):

    urls: List[str] = Field(..., min_length=1, max_length=10, description="URL list")

    @field_validator("urls")
    @classmethod
    def validate_urls(cls, urls: List[str]) -> List[str]:
        return [_validate_safe_ingest_url(url) for url in urls]


class URLItem(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    normalized_url: str
    status: Literal["pending", "fetching", "success", "failed"]
    title: Optional[str] = None
    last_fetch_at: Optional[datetime] = None
    is_indexed: bool = False
    created_at: datetime
    updated_at: Optional[datetime] = None
    # KB indexing diagnostics
    indexing_status: Optional[Literal["pending", "processing", "ready", "error"]] = None
    indexing_error: Optional[str] = None
    last_error: Optional[str] = None


class URLListResponse(BaseModel):

    urls: List[URLItem]
    total: int
    quota: Dict[str, int] = Field(..., description="Quota info (used, max)")
    job_id: Optional[str] = Field(None, description="Background fetch job ID (auto-triggered when new URLs are created)")
    auto_fetch_queued: bool = Field(False, description="Whether background fetch has been auto-queued")


class URLRefetchRequest(BaseModel):

    url_ids: Optional[List[int]] = Field(
        None, max_length=500, description="URL ID list to re-fetch (re-fetches all if not specified)"
    )
    force: bool = Field(False, description="Whether to force re-fetch (ignore content hash)")


class URLRefetchResponse(BaseModel):

    job_id: str
    status: str
    message: str


class SiteCrawlRequest(BaseModel):

    url: str = Field(..., max_length=2048, description="Starting URL")
    max_depth: int = Field(2, ge=1, le=5, description="Maximum crawl depth")
    max_pages: int = Field(20, ge=1, le=500, description="Maximum number of pages")

    @field_validator("url")
    @classmethod
    def validate_url(cls, url: str) -> str:
        return _validate_safe_ingest_url(url)


class SiteCrawlResponse(BaseModel):

    job_id: str = Field(..., description="Task ID")
    status: str = Field(..., description="Task status")
    discovered: int = Field(..., description="Number of pages discovered")
    created: int = Field(..., description="Number of new URLs added")
    message: str = Field(..., description="Status message")


# ========== File Upload Schemas ==========


class FileItem(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    file_size: Optional[int] = None
    file_type: Optional[str] = None
    status: Literal["uploading", "processing", "ready", "failed", "pending"] = (
        "uploading"
    )
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class FileListResponse(BaseModel):

    files: List[FileItem]
    total: int
    quota: Dict[str, int] = Field(..., description="Quota info (used, max)")


class FileUploadResponse(BaseModel):

    uploaded: int = Field(..., description="Number of successfully uploaded items")
    failed: int = Field(..., description="Number of failures")
    files: List[FileItem] = Field(default_factory=list, description="List of uploaded files")
    errors: List[str] = Field(default_factory=list, description="Error messages")


# ========== KB Document Schemas ==========


class KbDocumentItem(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    file_type: Optional[str] = None
    status: Literal["pending", "processing", "ready", "error"] = "pending"
    chunk_count: int = 0
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None


class KbDocumentUploadResponse(BaseModel):

    uploaded: int = 0
    failed: int = 0
    documents: List[KbDocumentItem] = Field(default_factory=list)


class KbDocumentProgressResponse(BaseModel):

    status: str
    chunk_count: int = 0
    error_message: Optional[str] = None


# ========== KB Config/Reset Schemas ==========


class KbConfigResponse(BaseModel):
    """KB embedding configuration response"""

    id: str
    name: str
    embedding_model: str
    embedding_base_url: Optional[str] = None
    vector_backend: str
    chunk_size: int
    chunk_overlap: int
    is_locked: bool
    status: str


class KbConfigUpdate(BaseModel):
    """KB config update request (embedding fields blocked when locked)"""

    name: Optional[str] = None
    chunk_size: Optional[int] = None
    chunk_overlap: Optional[int] = None
    embedding_model: Optional[str] = None
    embedding_base_url: Optional[str] = None


class KbResetRequest(BaseModel):
    """KB reset request (change embedding model + reindex)"""

    new_embedding_model: str
    new_embedding_base_url: Optional[str] = None


class KbDetailResponse(KbConfigResponse):
    """KB detail with document/chunk counts"""

    document_count: int = 0
    ready_document_count: int = 0
    total_chunks: int = 0


class KbDeleteResponse(BaseModel):
    """KB delete response"""

    deleted: bool = True
    message: Optional[str] = None


# ========== Agent Management Schemas ==========


class AgentConfig(BaseModel):

    id: str
    workspace_id: Optional[int] = None
    name: str
    description: Optional[str] = None
    agent_type: str = Field(default="website_support")
    channel_mode: str = Field(default="web_widget")
    avatar: Optional[str] = None
    system_prompt: str
    model: str
    temperature: float = Field(..., ge=0, le=2)
    max_tokens: int = Field(..., ge=1, le=4096)
    api_key_set: bool = Field(
        default=False, description="Whether API key is configured"
    )
    api_key_masked: Optional[str] = Field(
        None, description="Masked API key (sk-***...abc)"
    )
    api_base: Optional[str] = None
    jina_api_key_set: bool = Field(
        default=False, description="Whether Jina API key is configured"
    )
    jina_api_key_masked: Optional[str] = Field(None, description="Masked Jina API key")
    siliconflow_api_key_set: bool = Field(
        default=False, description="Whether SiliconFlow embedding API key is configured"
    )
    siliconflow_api_key_masked: Optional[str] = Field(
        None, description="Masked SiliconFlow embedding API key"
    )
    provider_type: Optional[
        Literal[
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
        ]
    ] = Field("openai", description="AI provider type")
    azure_endpoint: Optional[str] = Field(None, description="Azure OpenAI endpoint URL")
    azure_deployment_name: Optional[str] = Field(
        None, description="Azure deployment name"
    )
    azure_api_version: Optional[str] = Field(
        "2023-12-01-preview", description="Azure API version"
    )
    anthropic_version: Optional[str] = Field(
        "2023-06-01", description="Anthropic API version"
    )
    google_project_id: Optional[str] = Field(None, description="Google project ID")
    google_region: Optional[str] = Field(None, description="Google region")
    provider_config: Optional[Dict[str, Any]] = Field(
        None, description="Provider-specific configuration"
    )
    embedding_provider: Literal["jina", "siliconflow", "custom"] = Field(
        "jina",
        description="Embedding provider: jina, siliconflow, or custom",
    )
    embedding_api_base: Optional[str] = Field(
        None, description="Embedding API base URL"
    )
    embedding_api_key_set: bool = Field(
        default=False,
        description="Whether the selected embedding provider has an effective API key configured",
    )
    embedding_model: str
    configuration_error: Optional[str] = Field(
        None,
        description="Non-fatal configuration problem (e.g. invalid custom embedding base); present only when the backend degraded gracefully so the admin can fix it",
    )
    crawl_max_depth: int = Field(
        default=2, ge=0, le=5, description="Crawl depth for site crawling"
    )
    crawl_max_pages: int = Field(
        default=20, ge=1, le=500, description="Max pages for site crawling"
    )
    top_k: int = Field(..., ge=1, le=20)
    similarity_threshold: float = Field(..., ge=0, le=1)
    enable_context: bool = Field(
        default=False, description="Enable conversation context"
    )
    enable_auto_fetch: bool = Field(
        default=False, description="Enable automatic URL fetching"
    )
    url_fetch_interval_days: int = Field(
        default=7, ge=1, le=30, description="URL fetch interval in days"
    )
    rate_limit_per_minute: int = Field(
        default=20, ge=0, description="Rate limit per minute (0 = unlimited)"
    )
    restricted_reply: Optional[str] = Field(
        default="Sorry, the service is currently restricted. Please try again later.",
        description="Fallback reply when service is restricted (rate limit, AI failure, etc.)",
    )
    last_error_code: Optional[str] = None
    last_error_message: Optional[str] = None
    last_error_at: Optional[str] = None
    persona_type: Optional[str] = Field(
        default="general",
        description="Persona type: general, customer-service, sales, custom",
    )
    widget_title: Optional[str] = Field(default="AI Support", description="Widget title")
    widget_color: Optional[str] = Field(
        default="#06B6D4", description="Widget theme color"
    )
    allowed_widget_origins: List[str] = Field(
        default_factory=list, description="Allowed widget embed origins"
    )
    welcome_message: Optional[str] = Field(None, description="Widget welcome message")
    history_days: int = Field(default=30, description="Chat history retention days")
    embedding_batch_size: int = Field(
        default=4, ge=1, le=64, description="Embedding batch size"
    )
    kb_setup_completed: bool = Field(
        default=False, description="Whether the knowledge base setup has been completed"
    )
    is_active: bool
    deleted_at: Optional[datetime] = None
    purge_after: Optional[datetime] = None
    status: Optional[str] = None
    url_count: int = 0
    file_count: int = 0
    active_session_count: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None
    kb_id: Optional[str] = Field(None, description="Bound knowledge base ID (optional)")

    model_config = ConfigDict(from_attributes=True)


class AgentUpdateRequest(BaseModel):

    name: Optional[str] = Field(None, min_length=1, max_length=10)

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, value: Any) -> Any:
        return _validate_agent_name(value)

    description: Optional[str] = Field(None, max_length=200)
    agent_type: Optional[
        Literal["website_support", "ai_clone", "sales_outreach", "custom"]
    ] = None
    channel_mode: Optional[Literal["web_widget", "whatsapp", "email", "custom"]] = None
    avatar: Optional[str] = Field(None, max_length=500)
    system_prompt: Optional[str] = Field(None, min_length=1)
    model: Optional[str] = Field(None, min_length=1)
    temperature: Optional[float] = Field(None, ge=0, le=2)
    api_key: Optional[str] = Field(None, min_length=0)
    api_base: Optional[str] = Field(None, min_length=1)
    jina_api_key: Optional[str] = Field(None, min_length=0)
    siliconflow_api_key: Optional[str] = Field(None, min_length=0)
    provider_type: Optional[
        Literal[
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
        ]
    ] = Field(None, description="AI provider type")
    azure_endpoint: Optional[str] = Field(None, description="Azure OpenAI endpoint URL")
    azure_deployment_name: Optional[str] = Field(
        None, description="Azure deployment name"
    )
    azure_api_version: Optional[str] = Field(None, description="Azure API version")
    anthropic_version: Optional[str] = Field(None, description="Anthropic API version")
    google_project_id: Optional[str] = Field(None, description="Google project ID")
    google_region: Optional[str] = Field(None, description="Google region")
    provider_config: Optional[Dict[str, Any]] = Field(
        None, description="Provider-specific configuration"
    )
    embedding_provider: Optional[Literal["jina", "siliconflow", "custom"]] = Field(
        None, description="Embedding provider: jina, siliconflow, or custom"
    )
    embedding_api_base: Optional[str] = Field(
        None, description="Embedding API base URL"
    )
    embedding_model: Optional[str] = Field(None, min_length=1)
    crawl_max_depth: Optional[int] = Field(
        None, ge=0, le=5, description="Crawl depth for site crawling"
    )
    crawl_max_pages: Optional[int] = Field(
        None, ge=1, le=500, description="Max pages for site crawling"
    )
    top_k: Optional[int] = Field(None, ge=1, le=20)
    similarity_threshold: Optional[float] = Field(
        None, ge=0, le=1, description="Minimum similarity score for retrieval results"
    )
    enable_context: Optional[bool] = Field(
        None, description="Enable conversation context"
    )
    enable_auto_fetch: Optional[bool] = Field(
        None, description="Enable automatic URL fetching"
    )
    url_fetch_interval_days: Optional[int] = Field(
        None, ge=1, le=30, description="URL fetch interval in days"
    )
    rate_limit_per_minute: Optional[int] = Field(
        None,
        ge=0,
        description="Rate limit per minute (0 = unlimited)",
        validation_alias=AliasChoices("rate_limit_per_minute", "rate_limit_per_hour"),
    )
    restricted_reply: Optional[str] = Field(
        None, description="Fallback reply when service is restricted"
    )
    persona_type: Optional[str] = Field(
        None, description="Persona type: general, customer-service, sales, custom"
    )
    widget_title: Optional[str] = Field(
        None, max_length=100, description="Widget title"
    )
    widget_color: Optional[str] = Field(
        None, max_length=20, description="Widget theme color"
    )
    allowed_widget_origins: Optional[List[str]] = Field(
        None, description="Allowed widget embed origins"
    )
    welcome_message: Optional[str] = Field(None, description="Widget welcome message")
    history_days: Optional[int] = Field(
        None, ge=1, le=365, description="Chat history retention days"
    )
    embedding_batch_size: Optional[int] = Field(
        None, ge=1, le=64, description="Embedding batch size"
    )

    @field_validator("allowed_widget_origins")
    @classmethod
    def validate_allowed_widget_origins(
        cls, origins: Optional[List[str]]
    ) -> Optional[List[str]]:
        if origins is None:
            return None

        normalized_origins: List[str] = []
        seen_origins = set()
        for origin in origins:
            normalized_origin = normalize_widget_origin(origin)
            if normalized_origin in seen_origins:
                continue
            seen_origins.add(normalized_origin)
            normalized_origins.append(normalized_origin)

        return normalized_origins


AGENT_NAME_MAX_DISPLAY_WIDTH = 10


def _agent_name_display_width(value: str) -> int:
    import unicodedata

    return sum(
        2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1 for char in value
    )


def _validate_agent_name(value: Any) -> Any:
    if value is None or not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped:
        raise ValueError("Agent name cannot be empty")
    width = _agent_name_display_width(stripped)
    if width > AGENT_NAME_MAX_DISPLAY_WIDTH:
        raise ValueError(
            f"Agent name must be at most {AGENT_NAME_MAX_DISPLAY_WIDTH} display units "
            "(10 ASCII characters or 5 Chinese characters)"
        )
    return stripped


class AgentCreateRequest(BaseModel):

    name: str = Field(..., min_length=1, max_length=10)
    description: str | None = Field(None, max_length=200)
    agent_type: Literal["website_support", "ai_clone", "sales_outreach", "custom"] = (
        "website_support"
    )
    channel_mode: Literal["web_widget", "whatsapp", "email", "custom"] = "web_widget"

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, value: Any) -> Any:
        return _validate_agent_name(value)

    system_prompt: str | None = Field(None, min_length=1)
    persona_type: str | None = "general"
    widget_title: str | None = Field(None, max_length=100)
    welcome_message: str | None = None


class AgentListResponse(BaseModel):

    agents: list[AgentConfig]
    total: int


class AgentMemberCreateRequest(BaseModel):

    email: str
    name: str | None = None
    password: str | None = None
    role: Literal["admin", "support"] = "support"


class AgentMemberItem(BaseModel):
    id: int
    email: str
    name: str
    is_active: bool
    role: str
    member_role: str


class AgentMemberListResponse(BaseModel):
    members: list[AgentMemberItem]
    total: int


# ========== Index Management Schemas ==========


class IndexRebuildRequest(BaseModel):

    force: bool = Field(False, description="Whether to force rebuild")


class IndexRebuildResponse(BaseModel):

    job_id: str
    status: str
    message: str


class IndexStatusResponse(BaseModel):

    agent_id: str
    job_id: Optional[str] = None
    status: str
    result: Optional[Dict[str, Any]] = None


class IndexInfoResponse(BaseModel):

    agent_id: str
    urls_indexed: int
    files_indexed: int
    index_exists: bool
    status: str


class URLCancelResponse(BaseModel):

    cancelled: int
    task_ids: List[str]
    message: str


# ========== Quota Schemas ==========


class QuotaInfo(BaseModel):

    max_agents: int
    max_urls: int
    max_files: int
    max_messages_per_day: int
    max_total_text_mb: int
    used_agents: int
    used_urls: int
    used_files: int
    used_messages_today: int
    used_total_text_mb: float
    remaining_urls: int
    remaining_files: int
    remaining_messages_today: int


# ========== Session Schemas ==========


class SessionListItem(BaseModel):

    id: str
    session_id: str
    visitor_id: str | None = None
    visitor_country: str | None = None
    visitor_city: str | None = None
    status: str = "active"
    message_count: int = 0
    created_at: datetime
    updated_at: datetime | None = None
    last_message: str | None = None


class SessionListResponse(BaseModel):

    items: list[SessionListItem]
    total: int


# ========== Auth Schemas ==========


class AdminRegisterRequest(BaseModel):

    email: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=8, max_length=100)
    name: str = Field(..., min_length=1, max_length=100)


class AdminLoginRequest(BaseModel):

    email: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class AdminResponse(BaseModel):

    id: int
    email: str
    name: str
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):

    access_token: str
    token_type: str = "bearer"


# ========== Models List Schemas ==========


class ModelsListRequest(BaseModel):

    provider_type: Literal["openai_native", "google", "deepseek"] = Field(
        ..., description="AI provider type"
    )
    api_key: str | None = Field(None, description="API key (if not using saved key)")
    agent_id: str | None = Field(None, description="Agent ID (to use saved API key)")


class ModelsListResponse(BaseModel):

    models: list[str] = Field(default_factory=list, description="Available models")


# ========== Sources Summary Schemas ==========


class SourcesURLSummary(BaseModel):

    total: int = Field(..., description="Total URL count")
    indexed: int = Field(..., description="Trained count")
    pending: int = Field(..., description="Pending count")
    total_size_kb: float = Field(..., description="Total size (KB)")


class SourcesFileSummary(BaseModel):

    total: int = Field(..., description="Total file count")
    ready: int = Field(..., description="Ready count")
    processing: int = Field(..., description="Processing count")
    total_size_kb: float = Field(..., description="Total size (KB)")


class SourcesSummaryResponse(BaseModel):

    urls: SourcesURLSummary
    files: SourcesFileSummary
    has_pending: bool = Field(..., description="Whether there is pending content")


# ========== KB Retrieval Schemas ==========


class RetrieveRequest(BaseModel):
    """Retrieval request body"""

    query: str = Field(..., min_length=1, max_length=1000)
    top_k: int = Field(5, ge=1, le=20)


class RetrieveChunk(BaseModel):
    """Single retrieval result (no vector_id or collection exposed)"""

    text: str
    doc_id: str
    chunk_index: int
    score: float
    filename: Optional[str] = None


class RetrieveResponse(BaseModel):
    """Wrapper for consistency"""

    results: List[RetrieveChunk] = []
