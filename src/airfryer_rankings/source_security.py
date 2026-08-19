from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Iterable
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests

from .models import HEADERS

_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_PRIVATE_HOST_SUFFIXES = (".internal", ".local", ".localhost", ".home", ".lan")
_BLOCKED_EXACT_HOSTS = {"localhost", "localhost.localdomain", "metadata.google.internal"}
_METADATA_IPS = {
    "169.254.169.254",
    "100.100.100.200",
}

# These hosts are useful infrastructure, social/search/shopping services, or generic
# publication platforms rather than independent recipe publishers. They are rejected
# during *candidate discovery* but are not part of the lower-level SSRF policy.
NON_PUBLISHER_SUFFIXES = (
    "amazon.com",
    "amazonaws.com",
    "apple.com",
    "bing.com",
    "cloudfront.net",
    "doubleclick.net",
    "duckduckgo.com",
    "facebook.com",
    "fb.com",
    "google.com",
    "googleapis.com",
    "googlesyndication.com",
    "instagram.com",
    "linkedin.com",
    "linktr.ee",
    "pinterest.com",
    "reddit.com",
    "shopify.com",
    "tiktok.com",
    "twitter.com",
    "x.com",
    "youtube.com",
)


class UnsafeNetworkTarget(ValueError):
    """Raised when an untrusted discovery URL could reach a non-public network target."""


Resolver = Callable[..., list[tuple]]


def normalize_candidate_domain(value: str) -> str | None:
    """Normalize a discovered hostname without collapsing meaningful subdomains.

    Only a leading ``www.`` alias is collapsed. ``recipes.example.com`` therefore
    remains distinct from ``example.com`` until a maintainer or future registrable-
    domain policy explicitly chooses otherwise.
    """

    raw = str(value or "").strip()
    if not raw:
        return None
    if "://" not in raw:
        raw = "https://" + raw
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return None
    if parsed.username or parsed.password:
        return None
    host = (parsed.hostname or "").strip().rstrip(".").lower()
    if not host:
        return None
    if host.startswith("www."):
        host = host[4:]
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        return None
    if len(host) > 253 or any(not label or len(label) > 63 for label in host.split(".")):
        return None
    if "." not in host:
        return None
    try:
        ipaddress.ip_address(host)
        return None
    except ValueError:
        pass
    return host


def candidate_domain_from_url(url: str) -> str | None:
    try:
        parsed = urlsplit(str(url or "").strip())
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"http", "https"}:
        return None
    return normalize_candidate_domain(parsed.hostname or "")


def is_non_publisher_domain(domain: str, extra_blocked: Iterable[str] = ()) -> bool:
    normalized = normalize_candidate_domain(domain)
    if not normalized:
        return True
    blocked = tuple(str(value).lower().lstrip(".") for value in extra_blocked if str(value).strip())
    for suffix in (*NON_PUBLISHER_SUFFIXES, *blocked):
        if normalized == suffix or normalized.endswith("." + suffix):
            return True
    labels = normalized.split(".")
    infrastructure_tokens = {"cdn", "img", "images", "static", "media", "assets", "ads", "analytics"}
    return bool(labels and labels[0] in infrastructure_tokens)


def _public_ip(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    if str(ip) in _METADATA_IPS:
        return False
    return bool(ip.is_global)


def resolve_public_addresses(host: str, resolver: Resolver = socket.getaddrinfo) -> tuple[str, ...]:
    normalized = normalize_candidate_domain(host)
    if not normalized:
        raise UnsafeNetworkTarget(f"invalid hostname: {host!r}")
    if normalized in _BLOCKED_EXACT_HOSTS or normalized.endswith(_PRIVATE_HOST_SUFFIXES):
        raise UnsafeNetworkTarget(f"private hostname is not allowed: {normalized}")
    try:
        answers = resolver(normalized, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise UnsafeNetworkTarget(f"hostname did not resolve publicly: {normalized}") from exc
    addresses = sorted({str(answer[4][0]) for answer in answers if len(answer) >= 5 and answer[4]})
    if not addresses:
        raise UnsafeNetworkTarget(f"hostname has no address records: {normalized}")
    unsafe = [address for address in addresses if not _public_ip(address)]
    if unsafe:
        raise UnsafeNetworkTarget(f"hostname resolves to non-public address(es): {normalized}: {unsafe}")
    return tuple(addresses)


def validate_public_url(url: str, resolver: Resolver = socket.getaddrinfo) -> str:
    raw = str(url or "").strip()
    try:
        parsed = urlsplit(raw)
    except ValueError as exc:
        raise UnsafeNetworkTarget("malformed URL") from exc
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise UnsafeNetworkTarget(f"unsupported URL scheme: {scheme or '<missing>'}")
    if parsed.username or parsed.password:
        raise UnsafeNetworkTarget("URLs containing credentials are not allowed")
    host = parsed.hostname or ""
    normalized = normalize_candidate_domain(host)
    if not normalized:
        raise UnsafeNetworkTarget(f"invalid public hostname: {host!r}")
    if parsed.port is not None and parsed.port not in {80, 443}:
        raise UnsafeNetworkTarget(f"non-standard network port is not allowed: {parsed.port}")
    resolve_public_addresses(normalized, resolver=resolver)
    netloc = normalized
    if parsed.port is not None:
        netloc += f":{parsed.port}"
    return urlunsplit((scheme, netloc, parsed.path or "/", parsed.query, ""))


def safe_get(
    session: requests.Session,
    url: str,
    timeout: int = 20,
    headers: dict | None = None,
    *,
    max_redirects: int = 5,
    resolver: Resolver = socket.getaddrinfo,
) -> requests.Response:
    """GET untrusted public-web content with DNS and redirect SSRF checks.

    Redirect following is explicit so every destination is independently validated.
    The function intentionally does not attempt IP pinning; callers still benefit from
    scheme/port restrictions, pre-request DNS checks, and redirect revalidation.
    """

    merged = dict(HEADERS)
    if headers:
        merged.update(headers)
    current = validate_public_url(url, resolver=resolver)
    for redirect_number in range(max_redirects + 1):
        response = session.get(current, headers=merged, timeout=timeout, allow_redirects=False)
        if response.status_code in _REDIRECT_STATUSES:
            if redirect_number >= max_redirects:
                raise requests.TooManyRedirects(f"more than {max_redirects} redirects for {url}")
            location = str(response.headers.get("Location") or "").strip()
            if not location:
                response.raise_for_status()
                return response
            current = validate_public_url(urljoin(current, location), resolver=resolver)
            continue
        if response.status_code != 304:
            response.raise_for_status()
        return response
    raise requests.TooManyRedirects(f"more than {max_redirects} redirects for {url}")
