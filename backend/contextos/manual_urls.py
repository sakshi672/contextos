"""User-invoked URL capture with a bounded, public-network-only fetch."""

import hashlib
import http.client
import ipaddress
import os
import socket
import ssl
import time
import uuid
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .auth import write_session
from .database import connection
from .extract_text import PermanentExtractionError

router = APIRouter(prefix="/v1/urls", tags=["manual URLs"])
MAX_HTML_BYTES = 2 * 1024 * 1024
MAX_TEXT_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 3
FETCH_SECONDS = 10


class UrlInput(BaseModel):
    source_url: str = Field(min_length=1, max_length=2048)
    user_note: str = Field(default="", max_length=20000)


def checked_url(value: str) -> tuple[str, str, int]:
    if any(char.isspace() for char in value):
        raise ValueError("invalid_url")
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise ValueError("invalid_url") from exc
    if (parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password or
            port != (443 if parsed.scheme == "https" else 80)):
        raise ValueError("invalid_url")
    host = host.encode("idna").decode("ascii").lower()
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        raise ValueError("private_address")
    blocked = {part.strip().lower() for part in os.environ.get("CONTEXT_OS_CAPTURE_BLOCKED_DOMAINS", "").split(",") if part.strip()}
    if host in blocked or any(host.endswith("." + domain) for domain in blocked):
        raise ValueError("blocked_domain")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if not literal.is_global:
            raise ValueError("private_address")
    return parsed.scheme, host, port


def public_address(host: str, port: int) -> str:
    addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if not addresses:
        raise ValueError("dns_failed")
    ips = {item[4][0] for item in addresses}
    if any(not ipaddress.ip_address(ip).is_global or ipaddress.ip_address(ip).is_multicast for ip in ips):
        raise ValueError("private_address")
    return sorted(ips)[0]


class PinnedHTTP(http.client.HTTPConnection):
    def __init__(self, host: str, port: int, ip: str, timeout: float):
        super().__init__(host, port, timeout=timeout)
        self.pinned_ip = ip

    def connect(self):
        self.sock = socket.create_connection((self.pinned_ip, self.port), self.timeout)


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host: str, port: int, ip: str, timeout: float):
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self.pinned_ip = ip

    def connect(self):
        sock = socket.create_connection((self.pinned_ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class PageParser(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "form", "nav", "footer"}
    BREAK = {"p", "div", "section", "article", "main", "h1", "h2", "h3", "h4", "li", "br"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.title_depth = 0
        self.title = []
        self.parts = []
        self.metadata = {}

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        values = dict(attrs)
        if tag in self.SKIP:
            self.skip_depth += 1
        if self.skip_depth:
            return
        if tag == "title":
            self.title_depth += 1
        if tag == "meta":
            key = (values.get("property") or values.get("name") or "").lower()
            if key in {"og:title", "og:site_name", "og:image", "article:author", "author",
                       "article:published_time", "date", "description"}:
                self.metadata.setdefault(key, values.get("content", "").strip())
        if tag in self.BREAK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self.SKIP and self.skip_depth:
            self.skip_depth -= 1
            return
        if self.skip_depth:
            return
        if tag == "title" and self.title_depth:
            self.title_depth -= 1
        if tag in self.BREAK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.skip_depth:
            return
        if self.title_depth:
            self.title.append(data)
        else:
            self.parts.append(data)


def page_data(raw: bytes, content_type: str, url: str) -> dict:
    charset = "utf-8"
    for item in content_type.split(";")[1:]:
        key, separator, value = item.strip().partition("=")
        if separator and key.lower() == "charset":
            charset = value.strip(' "').lower()
    try:
        html = raw.decode(charset, errors="replace")
    except LookupError:
        html = raw.decode("utf-8", errors="replace")
    parser = PageParser()
    parser.feed(html)
    body = "\n".join(line.strip() for line in "".join(parser.parts).splitlines() if line.strip())
    if len(body.encode("utf-8")) > MAX_TEXT_BYTES:
        body = body.encode("utf-8")[:MAX_TEXT_BYTES].decode("utf-8", errors="ignore")
    title = (parser.metadata.get("og:title") or "".join(parser.title).strip() or url)[:240]
    image = parser.metadata.get("og:image")
    image_uri = urljoin(url, image) if image else None
    if image_uri:
        try:
            checked_url(image_uri)
        except ValueError:
            image_uri = None
    published = parser.metadata.get("article:published_time") or parser.metadata.get("date")
    try:
        published_at = datetime.fromisoformat(published.replace("Z", "+00:00")) if published else None
        if published_at and published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
    except ValueError:
        published_at = None
    return {"title": title, "body": body, "author": (parser.metadata.get("article:author") or parser.metadata.get("author") or "")[:500] or None,
            "image_uri": image_uri[:2048] if image_uri else None, "published_at": published_at}


def fetch_page(url: str) -> dict:
    deadline = time.monotonic() + FETCH_SECONDS
    for _ in range(MAX_REDIRECTS + 1):
        scheme, host, port = checked_url(url)
        ip = public_address(host, port)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError("fetch_timeout")
        connection_type = PinnedHTTPS if scheme == "https" else PinnedHTTP
        conn = connection_type(host, port, ip, min(remaining, FETCH_SECONDS))
        try:
            parsed = urlsplit(url)
            target = (parsed.path or "/") + ("?" + parsed.query if parsed.query else "")
            host_header = f"[{host}]" if ":" in host else host
            conn.request("GET", target, headers={"Host": host_header, "User-Agent": "ContextOS/0.1 (user-requested capture)",
                                                 "Accept": "text/html", "Accept-Encoding": "identity"})
            response = conn.getresponse()
            if response.status in {301, 302, 303, 307, 308}:
                location = response.getheader("Location")
                if not location:
                    raise ValueError("redirect_without_location")
                url = urljoin(url, location)
                continue
            if response.status != 200:
                raise ValueError(f"http_{response.status}")
            content_type = response.getheader("Content-Type", "").lower()
            if not content_type.startswith("text/html"):
                raise ValueError("not_html")
            if response.getheader("Content-Encoding", "identity").lower() != "identity":
                raise ValueError("unsupported_encoding")
            length = response.getheader("Content-Length")
            if length:
                try:
                    declared_size = int(length)
                except ValueError as exc:
                    raise ValueError("invalid_content_length") from exc
                if declared_size > MAX_HTML_BYTES:
                    raise ValueError("page_too_large")
            chunks, size = [], 0
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ValueError("fetch_timeout")
                if conn.sock is not None:
                    conn.sock.settimeout(remaining)
                chunk = response.read1(min(65536, MAX_HTML_BYTES + 1 - size))
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_HTML_BYTES:
                    raise ValueError("page_too_large")
                chunks.append(chunk)
            raw = b"".join(chunks)
            return page_data(raw, content_type, url) | {"final_url": url}
        finally:
            conn.close()
    raise ValueError("too_many_redirects")


@router.post("", status_code=201)
def save_url(payload: UrlInput, session: dict = Depends(write_session)) -> dict:
    try:
        _, host, _ = checked_url(payload.source_url)
    except ValueError as exc:
        raise HTTPException(422, detail=f"URL cannot be fetched ({exc})") from exc
    account_id, memory_id = session["account_id"], uuid.uuid4()
    with connection() as db:
        row = db.execute("""INSERT INTO memories (id, account_id, kind, title, source_uri,
            source_domain, captured_at, status, user_note, capture_method)
            VALUES (%s, %s, 'web_page', %s, %s, %s, now(), 'pending', %s, 'manual')
            RETURNING id, kind, title, source_uri, status, captured_at""",
            (memory_id, account_id, host, payload.source_url, host, payload.user_note)).fetchone()
        db.execute("""INSERT INTO extraction_jobs (id, account_id, memory_id, job_type)
            VALUES (%s, %s, %s, 'fetch_url')""", (uuid.uuid4(), account_id, memory_id))
    return {"data": row, "error": None}


def handle(job: dict) -> None:
    with connection() as db:
        row = db.execute("""SELECT source_uri FROM memories WHERE id = %s AND account_id = %s
            AND kind = 'web_page' AND capture_method = 'manual'""",
            (job["memory_id"], job["account_id"])).fetchone()
    if row is None:
        raise PermanentExtractionError("missing_manual_url")
    try:
        page = fetch_page(row["source_uri"])
    except (ValueError, OSError, ssl.SSLError, http.client.HTTPException) as exc:
        reason = str(exc)[:80] if isinstance(exc, ValueError) else "fetch_failed"
        with connection() as db:
            db.execute("""UPDATE memories SET status = 'partial', capture_reason = %s,
                updated_at = now() WHERE id = %s AND account_id = %s""",
                (reason, job["memory_id"], job["account_id"]))
        return
    body = page["body"]
    status = "ready" if body else "partial"
    with connection() as db:
        latest = db.execute("""SELECT version, content_sha256 FROM memory_contents
            WHERE memory_id = %s AND account_id = %s AND provenance = 'extracted'
            ORDER BY version DESC LIMIT 1 FOR UPDATE""",
            (job["memory_id"], job["account_id"])).fetchone()
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        if body and (latest is None or latest["content_sha256"] != digest):
            db.execute("""UPDATE memory_contents SET is_active = false WHERE memory_id = %s
                AND account_id = %s AND provenance = 'extracted' AND is_active""",
                (job["memory_id"], job["account_id"]))
            db.execute("""INSERT INTO memory_contents (id, account_id, memory_id, version,
                provenance, body, content_sha256, processor_version, status, is_active)
                VALUES (%s,%s,%s,%s,'extracted',%s,%s,'manual-html-v1','ready',true)""",
                (uuid.uuid4(), job["account_id"], job["memory_id"],
                 1 if latest is None else latest["version"] + 1, body, digest))
        db.execute("""UPDATE memories SET title = %s, published_at = %s,
            source_author = %s, source_image_uri = %s, status = %s, capture_reason = %s,
            updated_at = now() WHERE id = %s AND account_id = %s""",
            (page["title"], page["published_at"], page["author"], page["image_uri"],
             status, "extracted_text_only" if body else "no_readable_text",
             job["memory_id"], job["account_id"]))
