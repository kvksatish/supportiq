"""
Internationalization (i18n) core functionality
"""
import gettext
from pathlib import Path
from typing import Iterable, Optional

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

SUPPORTED_LOCALES = ['zh-CN', 'en-US']
DEFAULT_LOCALE = 'zh-CN'
RUNTIME_FALLBACK_LOCALES = ('en-US', 'zh-CN')

LOCALES_DIR = Path(__file__).parent / 'locales'

_translations = {}
_normalized_locale_cache: dict[str, str] = {}
_locale_fallback_cache: dict[str, list[str]] = {}

_LOCALE_ALIAS_MAP = {
    'en': 'en-US',
    'fr': 'fr-FR',
    'ja': 'ja-JP',
    'de': 'de-DE',
    'es': 'es-ES',
    'zh-hans': 'zh-CN',
    'zh-cn': 'zh-CN',
    'zh-sg': 'zh-CN',
    'zh-hant': 'zh-Hant',
    'zh-tw': 'zh-TW',
    'zh-hk': 'zh-HK',
    'zh-mo': 'zh-HK',
}


def normalize_locale(locale: Optional[str]) -> Optional[str]:
    if not locale:
        return None

    cleaned = locale.strip().replace('_', '-')
    if not cleaned:
        return None

    cached = _normalized_locale_cache.get(cleaned)
    if cached:
        return cached

    parts = [part for part in cleaned.split('-') if part]
    if not parts:
        return None

    normalized_parts = [parts[0].lower()]
    for part in parts[1:]:
        if len(part) == 4 and part.isalpha():
            normalized_parts.append(part.title())
        elif len(part) in (2, 3) and part.isalpha():
            normalized_parts.append(part.upper())
        else:
            normalized_parts.append(part)

    normalized = _LOCALE_ALIAS_MAP.get('-'.join(normalized_parts).lower(), '-'.join(normalized_parts))
    _normalized_locale_cache[cleaned] = normalized
    return normalized


def _dedupe_preserve_order(locales: Iterable[Optional[str]]) -> list[str]:
    seen = set()
    ordered = []
    for locale in locales:
        normalized = normalize_locale(locale)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def build_locale_fallbacks(locale: Optional[str]) -> list[str]:
    normalized = normalize_locale(locale)
    if not normalized:
        return list(RUNTIME_FALLBACK_LOCALES)

    cached = _locale_fallback_cache.get(normalized)
    if cached:
        return cached.copy()

    fallbacks = [normalized]
    language = normalized.split('-', 1)[0]
    lower_normalized = normalized.lower()

    if language == 'zh':
        if 'Hant' in normalized or lower_normalized in {'zh-tw', 'zh-hk', 'zh-mo'}:
            fallbacks.extend(['zh-Hant', 'zh-TW', 'zh-HK', 'zh-CN', 'zh'])
        else:
            fallbacks.extend(['zh-Hans', 'zh-CN', 'zh'])
    else:
        preferred = _LOCALE_ALIAS_MAP.get(language)
        if preferred:
            fallbacks.append(preferred)
        fallbacks.append(language)

    resolved = _dedupe_preserve_order([*fallbacks, *RUNTIME_FALLBACK_LOCALES])
    _locale_fallback_cache[normalized] = resolved
    return resolved.copy()


def parse_accept_language(header_value: str) -> list[str]:
    candidates: list[tuple[float, int, str]] = []
    for index, raw_part in enumerate(header_value.split(',')):
        part = raw_part.strip()
        if not part:
            continue

        locale_part, *params = [segment.strip() for segment in part.split(';')]
        if locale_part == '*':
            continue

        quality = 1.0
        for param in params:
            if not param.startswith('q='):
                continue
            try:
                quality = float(param[2:])
            except ValueError:
                quality = 0.0
            break

        normalized = normalize_locale(locale_part)
        if normalized:
            candidates.append((quality, index, normalized))

    ordered = [locale for _, _, locale in sorted(candidates, key=lambda item: (-item[0], item[1]))]
    return _dedupe_preserve_order(ordered)


def get_translation(locale: str = DEFAULT_LOCALE):
    """Get translation function for the specified language"""
    normalized_locale = normalize_locale(locale) or DEFAULT_LOCALE
    gettext_locale = normalized_locale.replace('-', '_')

    if gettext_locale not in [l.replace('-', '_') for l in SUPPORTED_LOCALES]:
        gettext_locale = DEFAULT_LOCALE.replace('-', '_')

    if gettext_locale in _translations:
        return _translations[gettext_locale]

    locale_dir = LOCALES_DIR / gettext_locale / 'LC_MESSAGES'

    try:
        translator = gettext.translation(
            'messages',
            localedir=str(locale_dir.parent.parent),
            languages=[gettext_locale]
        )
        translator.install()
        _translations[gettext_locale] = translator.gettext
        return translator.gettext
    except FileNotFoundError:
        _translations[gettext_locale] = lambda x: x
        return lambda x: x


def _(message: str, locale: str = DEFAULT_LOCALE) -> str:
    """Translation function"""
    translator = get_translation(locale)
    return translator(message)


def get_locale_from_request(request: Request) -> str:
    """Extract locale parameter from request"""
    if hasattr(request.state, 'locale'):
        return request.state.locale

    locale = normalize_locale(request.query_params.get('locale'))
    if locale:
        return locale

    accept_language = request.headers.get('accept-language', '')
    for candidate in parse_accept_language(accept_language):
        return candidate

    return DEFAULT_LOCALE


class I18nMiddleware(BaseHTTPMiddleware):
    """Internationalization middleware - uses Starlette BaseHTTPMiddleware"""

    async def dispatch(self, request: Request, call_next):
        locale = get_locale_from_request(request)
        request.state.locale = locale
        response = await call_next(request)
        return response
