"""

- OpenAI Native (official interface)
- OpenAI Compatible (compatible interface, e.g. DeepSeek)
- Google (Gemini)
- Mock (for testing)
"""

import asyncio
import random
from abc import ABC, abstractmethod
from typing import AsyncGenerator, List, Dict, Optional, Awaitable, Callable, TypeVar
import logging
import html

from config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T")


class LLMError(Exception):
    """Base exception for classified LLM failures."""

    code = "PROVIDER_ERROR"


class APIKeyInvalidError(LLMError):
    code = "API_KEY_INVALID"


class APIKeyMissingError(LLMError):
    code = "API_KEY_MISSING"


class ProviderRateLimitedError(LLMError):
    code = "PROVIDER_RATE_LIMITED"


class ProviderUnavailableError(LLMError):
    code = "PROVIDER_UNAVAILABLE"


class ModelNotFoundError(LLMError):
    code = "MODEL_NOT_FOUND"


def classify_llm_error(error: Exception) -> LLMError:
    """Normalize provider-specific exceptions into stable error codes."""

    if isinstance(error, LLMError):
        return error

    status_code = getattr(error, "status_code", None)
    response = getattr(error, "response", None)
    if status_code is None and response is not None:
        status_code = getattr(response, "status_code", None)

    error_name = type(error).__name__.lower()
    message = str(error)
    lowered_message = message.lower()

    if (
        status_code == 401
        or "authenticationerror" in error_name
        or "invalid api key" in lowered_message
        or "incorrect api key" in lowered_message
        or "api key" in lowered_message and ("invalid" in lowered_message or "expired" in lowered_message)
    ):
        return APIKeyInvalidError(message)

    if (
        status_code == 404
        or "notfounderror" in error_name
        or "model not found" in lowered_message
        or "unknown model" in lowered_message
        or "does not exist" in lowered_message and "model" in lowered_message
    ):
        return ModelNotFoundError(message)

    if (
        status_code == 429
        or "ratelimiterror" in error_name
        or "rate limit" in lowered_message
        or "too many requests" in lowered_message
        or "quota" in lowered_message
    ):
        return ProviderRateLimitedError(message)

    if (
        "timeout" in lowered_message
        or "timed out" in lowered_message
        or "connection" in lowered_message
        or "unavailable" in lowered_message
        or "temporarily down" in lowered_message
        or "service unavailable" in lowered_message
        or "timeouterror" in error_name
        or "readtimeout" in error_name
        or "connecttimeout" in error_name
        or "apiconnectionerror" in error_name
        or "apierror" in error_name
    ):
        return ProviderUnavailableError(message)

    return LLMError(message)


def skips_openai_temperature(model: str) -> bool:
    """Return whether an OpenAI native model rejects temperature overrides."""
    return model.lower().startswith(("o1", "o3", "o4"))


async def retry_llm_operation(
    operation_name: str,
    operation: Callable[[], Awaitable[T]],
) -> T:
    """Retry transient provider failures with exponential backoff and jitter."""
    last_error: Optional[Exception] = None

    for attempt in range(1, settings.llm_retry_attempts + 1):
        try:
            return await operation()
        except Exception as error:
            classified = classify_llm_error(error)
            if not isinstance(classified, (ProviderRateLimitedError, ProviderUnavailableError)):
                raise classified from error
            last_error = classified
            if attempt >= settings.llm_retry_attempts:
                raise classified from error

            delay_cap = min(
                settings.llm_retry_max_delay_seconds,
                settings.llm_retry_base_delay_seconds * (2 ** (attempt - 1)),
            )
            delay = delay_cap + random.uniform(0, max(delay_cap * 0.1, 0.1))
            logger.warning(
                "%s failed with %s on attempt %s/%s, retrying in %.2fs",
                operation_name,
                classified.code,
                attempt,
                settings.llm_retry_attempts,
                delay,
            )
            await asyncio.sleep(delay)

    if last_error:
        raise last_error
    raise ProviderUnavailableError(f"{operation_name} failed without an error")


async def run_with_timeout(awaitable: Awaitable[T], timeout_seconds: int) -> T:
    return await asyncio.wait_for(awaitable, timeout=timeout_seconds)


def get_google_visible_text_parts(response_or_chunk: object) -> List[str]:
    candidates = getattr(response_or_chunk, "candidates", None)
    if candidates is not None:
        if not candidates:
            return []

        content = getattr(candidates[0], "content", None)
        parts = getattr(content, "parts", None) if content else None
        if parts is None:
            return []

        visible_parts = []
        for part in parts:
            text = getattr(part, "text", None)
            if text and not getattr(part, "thought", False):
                visible_parts.append(text)
        return visible_parts

    text = getattr(response_or_chunk, "text", None)
    return [text] if text else []




class BaseLLMService(ABC):
    """LLM service abstract base class"""

    def __init__(self, model: str, timeout: int = 30):
        """

        Args:
        """
        self.model = model
        self.timeout = timeout
        self.last_usage: Optional[Dict[str, int]] = None
        logger.info(
            f"Initializing {self.__class__.__name__}: model={model}, timeout={timeout}s"
        )

    def reset_last_usage(self) -> None:
        self.last_usage = None

    def set_last_usage(self, usage: Optional[object]) -> None:
        if not usage:
            logger.info("set_last_usage: usage is empty, clearing cached usage")
            self.last_usage = None
            return

        prompt_tokens = getattr(usage, "prompt_tokens", None)
        completion_tokens = getattr(usage, "completion_tokens", None)
        total_tokens = getattr(usage, "total_tokens", None)

        if isinstance(usage, dict):
            prompt_tokens = usage.get("prompt_tokens", prompt_tokens)
            completion_tokens = usage.get("completion_tokens", completion_tokens)
            total_tokens = usage.get("total_tokens", total_tokens)

        logger.info(
            "set_last_usage: type=%s prompt=%r completion=%r total=%r",
            type(usage).__name__,
            prompt_tokens,
            completion_tokens,
            total_tokens,
        )

        if all(isinstance(value, int) for value in (prompt_tokens, completion_tokens, total_tokens)):
            self.last_usage = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            }
            logger.info("set_last_usage: cached provider usage=%s", self.last_usage)
        else:
            logger.warning("set_last_usage: skipped because not all values are int")
            self.last_usage = None

    def get_last_usage(self) -> Optional[Dict[str, int]]:
        return self.last_usage

    @abstractmethod
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        stream: bool = True,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """

        Args:
            messages: Message list [{"role": "user", "content": "..."}]

        Yields:
        """
        pass

    @abstractmethod
    async def test_connection(self) -> bool:
        """

        Returns:
        """
        pass




class MockLLMService(BaseLLMService):
    """Mock LLM service - for testing and demo environments"""

    def __init__(self, model: str = "mock-model"):
        """Initialize Mock LLM"""
        super().__init__(model=model)
        logger.warning("Using Mock LLM service - for testing and demo only")

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        stream: bool = True,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """

        Args:

        Yields:
        """
        user_message = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_message = msg.get("content", "")
                break

        mock_response = self._generate_mock_response(user_message, system_prompt)

        if stream:
            words = mock_response.split()
            for i, word in enumerate(words):
                if i > 0:
                    word = " " + word
                yield word
        else:
            yield mock_response

    def _generate_mock_response(
        self, user_message: str, system_prompt: Optional[str] = None
    ) -> str:
        """Generate mock reply"""
        if not user_message:
            return "Hello! How can I help you?"

        if system_prompt and "XiaoWei" in system_prompt:
            prefix = "I am XiaoWei, "
        else:
            prefix = "I am an AI assistant, "

        if "hello" in user_message.lower() or "hi" in user_message.lower():
            return f"{prefix}Hello! Happy to help."
        elif "test" in user_message.lower():
            return f"{prefix}This is a simulated reply in a test environment. RAG retrieval is working, but the LLM is a Mock service."
        elif "question" in user_message.lower() or "problem" in user_message.lower():
            return f"{prefix}I received your question. In production, I will provide detailed answers based on the knowledge base."
        elif "thank" in user_message.lower():
            return f"{prefix}You're welcome! Feel free to ask if you have any more questions."
        else:
            sanitized_message = html.escape(user_message)
            return f"{prefix}Thank you for your question!

**Note**: This is using the Mock LLM service. To enable real AI, configure DEEPSEEK_API_KEY in .env or set up AI providers in system settings."

    async def test_connection(self) -> bool:
        """Test connection (Mock always returns True)"""
        return True


# ========== OpenAI Provider ==========


class OpenAIProvider(BaseLLMService):
    """OpenAI API provider (compatible interface, e.g. DeepSeek)"""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-3.5-turbo",
        timeout: int = 30,
    ):
        """

        Args:
        """
        super().__init__(model=model, timeout=timeout)
        from openai import AsyncOpenAI

        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
        )

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        stream: bool = True,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """

        Args:

        Yields:
        """
        try:
            if system_prompt:
                messages = [{"role": "system", "content": system_prompt}] + messages

            self.reset_last_usage()

            request_params = {
                "model": self.model,
                "messages": messages,
                "stream": stream,
                "temperature": 0.7 if temperature is None else temperature,
                "max_tokens": 2000 if max_tokens is None else max_tokens,
            }
            if stream:
                request_params["stream_options"] = {"include_usage": True}

            logger.info(
                "openai-compatible chat request model=%s stream=%s temperature=%r max_tokens=%r",
                self.model,
                stream,
                request_params["temperature"],
                request_params["max_tokens"],
            )

            async def create_response():
                return await self.client.chat.completions.create(**request_params)

            response = await retry_llm_operation(
                "openai-compatible chat request",
                create_response,
            )

            if stream:
                async for chunk in response:
                    if getattr(chunk, "usage", None):
                        self.set_last_usage(chunk.usage)
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
                        await asyncio.sleep(0)
            else:
                self.set_last_usage(getattr(response, "usage", None))
                if response.choices:
                    yield response.choices[0].message.content

        except LLMError:
            raise
        except Exception as e:
            logger.error(f"OpenAI API call failed: {str(e)}")
            raise classify_llm_error(e) from e

    async def test_connection(self) -> bool:
        """Test OpenAI API connectivity"""
        try:
            await run_with_timeout(
                self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": "Hello"}],
                    max_tokens=5,
                ),
                settings.llm_test_timeout_seconds,
            )
            return True
        except Exception as e:
            classified = classify_llm_error(e)
            logger.error(f"OpenAI API connection test failed [{classified.code}]: {str(e)}")
            return False


# ========== OpenAI Native Provider ==========


class OpenAINativeProvider(BaseLLMService):
    """OpenAI official API provider (fixed base_url)"""

    OPENAI_BASE_URL = "https://api.openai.com/v1"

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        timeout: int = 30,
    ):
        """

        Args:
        """
        super().__init__(model=model, timeout=timeout)
        from openai import AsyncOpenAI

        self.api_key = api_key
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=self.OPENAI_BASE_URL,
            timeout=timeout,
        )

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        stream: bool = True,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """

        Args:

        Yields:
        """
        try:
            if system_prompt:
                messages = [{"role": "system", "content": system_prompt}] + messages

            self.reset_last_usage()

            request_params = {
                "model": self.model,
                "messages": messages,
                "stream": stream,
                "max_tokens": 2000 if max_tokens is None else max_tokens,
            }
            if not skips_openai_temperature(self.model):
                request_params["temperature"] = 0.7 if temperature is None else temperature
            if stream:
                request_params["stream_options"] = {"include_usage": True}

            async def create_response():
                return await self.client.chat.completions.create(**request_params)

            response = await retry_llm_operation(
                "openai-native chat request",
                create_response,
            )

            if stream:
                async for chunk in response:
                    if getattr(chunk, "usage", None):
                        self.set_last_usage(chunk.usage)
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
                        await asyncio.sleep(0)
            else:
                self.set_last_usage(getattr(response, "usage", None))
                if response.choices:
                    yield response.choices[0].message.content

        except LLMError:
            raise
        except Exception as e:
            logger.error(f"OpenAI Native API call failed: {str(e)}")
            raise classify_llm_error(e) from e

    async def test_connection(self) -> bool:
        """Test OpenAI API connectivity"""
        try:
            await run_with_timeout(
                self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": "Hello"}],
                    max_tokens=5,
                ),
                settings.llm_test_timeout_seconds,
            )
            return True
        except Exception as e:
            classified = classify_llm_error(e)
            logger.error(f"OpenAI Native API connection test failed [{classified.code}]: {str(e)}")
            return False

    @staticmethod
    async def list_models(
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model_prefixes: tuple[str, ...] = ("gpt-", "o1", "o3", "o4", "chatgpt-"),
    ) -> List[str]:
        """Get available model list"""
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
        )
        models = await client.models.list()
        chat_models = [
            m.id for m in models.data
            if any(m.id.startswith(p) for p in model_prefixes)
        ]
        return sorted(chat_models, reverse=True)


# ========== Google Provider ==========


class GoogleProvider(BaseLLMService):
    """Google Gemini API provider"""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-pro",
        timeout: int = 30,
    ):
        """

        Args:
        """
        super().__init__(model=model, timeout=timeout)
        try:
            import google.generativeai as genai

            self.api_key = api_key
            genai.configure(api_key=api_key)
            self.client = genai.GenerativeModel(model)
        except ImportError:
            raise ImportError(
                "Google Generative AI SDK not installed. Run: pip install google-generativeai"
            )

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        stream: bool = True,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """

        Args:

        Yields:
        """
        try:
            prompt_parts = []

            if system_prompt:
                prompt_parts.append(f"System: {system_prompt}")

            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")

                if role == "system":
                    prompt_parts.append(f"System: {content}")
                elif role == "user":
                    prompt_parts.append(f"User: {content}")
                elif role == "assistant":
                    prompt_parts.append(f"Assistant: {content}")

            full_prompt = "\n\n".join(prompt_parts)

            generation_config = {
                "temperature": 0.7 if temperature is None else temperature,
                "max_output_tokens": 2000 if max_tokens is None else max_tokens,
            }

            async def create_stream_response():
                return await self.client.generate_content_async(
                    full_prompt,
                    stream=True,
                    generation_config=generation_config,
                )

            async def create_response():
                return await self.client.generate_content_async(
                    full_prompt,
                    generation_config=generation_config,
                )

            if stream:
                response = await retry_llm_operation(
                    "google chat request",
                    create_stream_response,
                )
                async for chunk in response:
                    for text in get_google_visible_text_parts(chunk):
                        yield text
                        await asyncio.sleep(0)
            else:
                response = await retry_llm_operation(
                    "google chat request",
                    create_response,
                )
                for text in get_google_visible_text_parts(response):
                    yield text

        except LLMError:
            raise
        except Exception as e:
            logger.error(f"Google API call failed: {str(e)}")
            raise classify_llm_error(e) from e

    async def test_connection(self) -> bool:
        """Test Google API connectivity"""
        try:
            await run_with_timeout(
                self.client.generate_content_async(
                    "Hello", generation_config={"max_output_tokens": 5}
                ),
                settings.llm_test_timeout_seconds,
            )
            return True
        except Exception as e:
            classified = classify_llm_error(e)
            logger.error(f"Google API connection test failed [{classified.code}]: {str(e)}")
            return False

    @staticmethod
    async def list_models(api_key: str) -> List[str]:
        """Get available model list"""
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        models = []
        for m in genai.list_models():
            if "generateContent" in m.supported_generation_methods:
                model_name = m.name.replace("models/", "")
                if model_name.startswith("gemini"):
                    models.append(model_name)
        return sorted(models, reverse=True)




def get_llm_service(
    agent=None,
    use_mock: bool = False,
    *,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    model: Optional[str] = None,
    provider_type: Optional[str] = None,
) -> BaseLLMService:
    """


    Args:

    Returns:
    """
    resolved_api_key = api_key if api_key is not None else getattr(agent, "api_key", None)
    resolved_api_base = api_base if api_base is not None else getattr(agent, "api_base", None)
    resolved_model = model if model is not None else getattr(agent, "model", None)
    resolved_provider_type = provider_type if provider_type is not None else getattr(agent, "provider_type", "openai")
    resolved_provider_type = resolved_provider_type or "openai"

    if use_mock or not resolved_api_key:
        logger.warning("Agent has no API Key, using Mock LLM service")
        return MockLLMService(model=resolved_model or "mock-model")

    if resolved_provider_type == "openai_native":
        logger.info("Using OpenAI Native Provider")
        return OpenAINativeProvider(
            api_key=resolved_api_key,
            model=resolved_model or "gpt-4o",
        )

    elif resolved_provider_type == "google":
        logger.info("Using Google Provider")
        return GoogleProvider(
            api_key=resolved_api_key,
            model=resolved_model or "gemini-pro",
        )

    elif resolved_provider_type == "anthropic":
        logger.info("Using Anthropic Provider (OpenAI Compatible)")
        return OpenAIProvider(
            api_key=resolved_api_key,
            base_url=resolved_api_base or "https://api.anthropic.com/v1",
            model=resolved_model or "claude-3-5-sonnet-20241022",
        )

    elif resolved_provider_type == "xai":
        logger.info("Using xAI Provider (OpenAI Compatible)")
        return OpenAIProvider(
            api_key=resolved_api_key,
            base_url=resolved_api_base or "https://api.x.ai/v1",
            model=resolved_model or "grok-2-latest",
        )

    elif resolved_provider_type == "openrouter":
        logger.info("Using OpenRouter Provider (OpenAI Compatible)")
        return OpenAIProvider(
            api_key=resolved_api_key,
            base_url=resolved_api_base or "https://openrouter.ai/api/v1",
            model=resolved_model or "openai/gpt-4o",
        )

    elif resolved_provider_type == "zai":
        logger.info("Using z.ai Provider (OpenAI Compatible)")
        return OpenAIProvider(
            api_key=resolved_api_key,
            base_url=resolved_api_base or "https://api.z.ai/v1",
            model=resolved_model or "z1-preview",
        )

    elif resolved_provider_type == "deepseek":
        logger.info("Using DeepSeek Provider (OpenAI Compatible)")
        return OpenAIProvider(
            api_key=resolved_api_key,
            base_url=resolved_api_base or "https://api.deepseek.com/v1",
            model=resolved_model or "deepseek-v4-flash",
        )

    elif resolved_provider_type == "volcengine":
        logger.info("Using Volcano Engine Provider (OpenAI Compatible)")
        return OpenAIProvider(
            api_key=resolved_api_key,
            base_url=resolved_api_base or "https://ark.cn-beijing.volces.com/api/v3",
            model=resolved_model or "doubao-pro-32k",
        )

    elif resolved_provider_type == "aliyun":
        logger.info("Using Alibaba Cloud Provider (OpenAI Compatible)")
        return OpenAIProvider(
            api_key=resolved_api_key,
            base_url=resolved_api_base or "https://dashscope.aliyuncs.com/compatible-mode/v1",
            model=resolved_model or "qwen-plus",
        )

    elif resolved_provider_type == "tencentcloud":
        logger.info("Using Tencent Cloud Provider (OpenAI Compatible)")
        return OpenAIProvider(
            api_key=resolved_api_key,
            base_url=resolved_api_base or "https://api.hunyuan.cloud.tencent.com/v1",
            model=resolved_model or "hunyuan-pro",
        )

    elif resolved_provider_type == "siliconflow":
        logger.info("Using SiliconFlow Provider (OpenAI Compatible)")
        return OpenAIProvider(
            api_key=resolved_api_key,
            base_url=resolved_api_base or "https://api.siliconflow.cn/v1",
            model=resolved_model or "deepseek-ai/DeepSeek-V3",
        )

    elif resolved_provider_type == "openai":
        logger.info("Using OpenAI Compatible Provider")
        return OpenAIProvider(
            api_key=resolved_api_key,
            base_url=resolved_api_base or "https://api.openai.com/v1",
            model=resolved_model or "gpt-4o",
        )

    else:
        logger.info(f"Unknown provider type '{resolved_provider_type}', using OpenAI Compatible interface")
        return OpenAIProvider(
            api_key=resolved_api_key,
            base_url=resolved_api_base or "https://api.openai.com/v1",
            model=resolved_model or "gpt-4o",
        )
