"""
Vigile — Worker Binary Distribution API

Endpoints:
  GET /api/nodes/binary/{os}/{arch}/worker          → FileResponse with ETag
  GET /api/nodes/binary/{os}/{arch}/worker.sha256    → plain text
  GET /api/nodes/binary/manifest.json                → cached manifest (admin/diagnostic)
  GET /api/nodes/binary/public-key                   → public key for script verification
"""

import asyncio
import hashlib
import json
import logging
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse, PlainTextResponse, Response

from master.api.deps import get_settings
from master.config import Settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/nodes/binary", tags=["worker-binary"])

# ---------------------------------------------------------------------------
# Supported platforms
# ---------------------------------------------------------------------------

SUPPORTED: dict[str, list[str]] = {
    "linux": ["amd64", "arm64", "armv7"],
    "darwin": ["amd64", "arm64"],
    "freebsd": ["amd64", "arm64", "armv7"],
}

# ---------------------------------------------------------------------------
# In-memory caches (module-level, protected by asyncio.Lock)
# ---------------------------------------------------------------------------

_manifest_cache: dict = {"data": None, "fetched_at": 0.0}
_revocation_cache: dict = {"data": None, "fetched_at": 0.0}
_cache_lock: asyncio.Lock = asyncio.Lock()


def _validate_os_arch(os_name: str, arch: str) -> None:
    if os_name not in SUPPORTED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported OS: {os_name}. Must be one of: {', '.join(SUPPORTED)}",
        )
    if arch not in SUPPORTED[os_name]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported arch '{arch}' for OS '{os_name}'. "
                   f"Must be one of: {', '.join(SUPPORTED[os_name])}",
        )


_GITHUB_RELEASE_RE = re.compile(
    r"^https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/releases/(?P<kind>latest/download|download/(?P<tag>[^/]+))/(?P<filename>.+)$"
)


async def _github_api_download(url: str, token: str, timeout: int) -> bytes:
    match = _GITHUB_RELEASE_RE.match(url)
    if not match:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Unsupported GitHub release URL format: {url}",
        )
    owner = match.group("owner")
    repo = match.group("repo")
    kind = match.group("kind")
    filename = match.group("filename")
    if kind == "latest/download":
        release_url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    else:
        tag = match.group("tag")
        release_url = f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{tag}"

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        headers = {"Authorization": f"Bearer {token}"}
        release_resp = await client.get(release_url, headers=headers)
        release_resp.raise_for_status()
        release = release_resp.json()
        asset_id = None
        for asset in release.get("assets", []):
            if asset.get("name") == filename:
                asset_id = asset.get("id")
                break
        if not asset_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Asset {filename} not found in release",
            )
        asset_headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/octet-stream",
        }
        asset_url = f"https://api.github.com/repos/{owner}/{repo}/releases/assets/{asset_id}"
        resp = await client.get(asset_url, headers=asset_headers)
        resp.raise_for_status()
        return resp.content


async def _fetch_url(url: str, settings: Settings, timeout: int = 30) -> bytes:
    token = settings.worker_binary_github_token
    if token and _GITHUB_RELEASE_RE.match(url):
        try:
            return await _github_api_download(url, token, timeout)
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"GitHub API returned {exc.response.status_code} for {url}",
            )
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Cannot reach GitHub API: {exc}",
            )

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.content
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Registry returned {exc.response.status_code} for {url}",
        )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Cannot reach registry: {exc}",
        )


def verify_minisign(
    binary_path: Path,
    sig_content: str,
    public_key: str,
) -> bool:
    """
    Verify a minisign (Ed25519) signature using the minisign CLI.
    Falls back to accepting the binary if no public key is configured (dev mode).
    """
    if not public_key:
        logger.warning("No WORKER_BINARY_PUBLIC_KEY configured — skipping signature verification")
        return True

    if shutil.which("minisign") is None:
        logger.error("minisign CLI not found — cannot verify signature")
        return False

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            sig_file = tmp / "worker.sig"
            sig_file.write_text(sig_content, encoding="utf-8")

            result = subprocess.run(
                [
                    "minisign",
                    "-Vm",
                    str(binary_path),
                    "-P",
                    public_key,
                    "-x",
                    str(sig_file),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                return True
            logger.error("Signature verification failed: %s", result.stderr or result.stdout)
            return False
    except Exception as exc:
        logger.error("Signature verification error: %s", exc)
        return False


async def _fetch_and_cache(
    settings,
    os_name: str,
    arch: str,
) -> Path:
    """Download binary, verify signature, write to local cache. Returns cached file path."""
    manifest = await _fetch_manifest(settings)
    binary_info = None
    for b in manifest.get("binaries", []):
        if b["os"] == os_name and b["arch"] == arch:
            binary_info = b
            break
    if not binary_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No binary found for {os_name}/{arch} in manifest",
        )

    cache_dir = Path(settings.worker_binary_cache_dir) / os_name / arch
    cache_dir.mkdir(parents=True, exist_ok=True)

    binary_path = cache_dir / "worker"
    sha256_path = cache_dir / "worker.sha256"
    sig_path = cache_dir / "worker.sig"

    tmp_dir = cache_dir / ".tmp"
    async with _cache_lock:
        try:
            binary_data = await _fetch_url(binary_info["url"], settings)
            sha256_data = await _fetch_url(binary_info["url"] + ".sha256", settings)
            sig_data = await _fetch_url(binary_info["url"] + ".sig", settings)

            tmp_dir.mkdir(parents=True, exist_ok=True)
            tmp_bin = tmp_dir / "worker"
            tmp_bin.write_bytes(binary_data)
            (tmp_dir / "worker.sha256").write_bytes(sha256_data)
            (tmp_dir / "worker.sig").write_bytes(sig_data)

            expected_sha256 = sha256_data.decode().strip().split()[0]
            actual_sha256 = hashlib.sha256(binary_data).hexdigest()
            if expected_sha256 != actual_sha256:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="SHA256 mismatch after download — binary corrupted in transit",
                )

            sig_text = sig_data.decode().strip()
            if not verify_minisign(tmp_bin, sig_text, settings.worker_binary_public_key):
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Minisign signature verification failed — binary may be tampered",
                )

            tmp_bin.rename(binary_path)
            sha256_path.write_bytes(sha256_data)
            sig_path.write_bytes(sig_data)
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    return binary_path


async def _fetch_manifest(settings) -> dict:
    now = time.time()
    if _manifest_cache["data"] and (now - _manifest_cache["fetched_at"]) < settings.worker_binary_cache_ttl_seconds:
        return _manifest_cache["data"]

    data = await _fetch_url(settings.worker_binary_manifest_url, settings)
    manifest = json.loads(data)
    _manifest_cache["data"] = manifest
    _manifest_cache["fetched_at"] = now
    return manifest


async def _is_version_revoked(settings, version: str) -> bool:
    revocations = await _fetch_revocations(settings)
    if "*" in revocations.get("revoked", []):
        return True
    return version in revocations.get("revoked", [])


async def _fetch_revocations(settings) -> dict:
    now = time.time()
    if _revocation_cache["data"] and (now - _revocation_cache["fetched_at"]) < settings.worker_binary_revocation_ttl_seconds:
        return _revocation_cache["data"]

    try:
        data = await _fetch_url(settings.worker_binary_revocation_url, settings, timeout=10)
        parsed = json.loads(data)
        _revocation_cache["data"] = parsed
        _revocation_cache["fetched_at"] = now
        return parsed
    except HTTPException as e:
        logger.warning("Failed to fetch revocation list (network): %s. Failing open.", e.detail)
        return {"revoked": [], "revoked_at": {}}
    except json.JSONDecodeError as e:
        logger.error("Revocation list is malformed JSON: %s. Failing closed.", e)
        return {"revoked": ["*"], "revoked_at": {}}


async def refresh_binary_cache() -> dict:
    """Force-clear caches (called from admin endpoint and for testing)."""
    global _manifest_cache, _revocation_cache
    _manifest_cache = {"data": None, "fetched_at": 0.0}
    _revocation_cache = {"data": None, "fetched_at": 0.0}
    return {"status": "ok", "message": "Binary caches cleared."}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/{os}/{arch}/worker")
async def get_worker_binary(
    os: str,
    arch: str,
    request: Request,
    settings=Depends(get_settings),
) -> Response:
    _validate_os_arch(os, arch)

    cache_dir = Path(settings.worker_binary_cache_dir) / os / arch
    binary_path = cache_dir / "worker"

    if binary_path.exists():
        age = time.time() - binary_path.stat().st_mtime
        if age < settings.worker_binary_cache_ttl_seconds:
            manifest = await _fetch_manifest(settings)
            version = manifest.get("version", "")
            if version and await _is_version_revoked(settings, version):
                raise HTTPException(
                    status_code=status.HTTP_410_GONE,
                    detail=f"Version {version} has been revoked. Upgrade required.",
                )
            return FileResponse(
                binary_path,
                media_type="application/octet-stream",
                filename=f"vigile-worker-{os}-{arch}",
                headers={"ETag": f'"{hashlib.sha256(binary_path.read_bytes()).hexdigest()}"'},
            )

    binary_path = await _fetch_and_cache(settings, os, arch)

    manifest = await _fetch_manifest(settings)
    version = manifest.get("version", "")
    if version and await _is_version_revoked(settings, version):
        binary_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=f"Version {version} has been revoked. Upgrade required.",
        )

    return FileResponse(
        binary_path,
        media_type="application/octet-stream",
        filename=f"vigile-worker-{os}-{arch}",
        headers={"ETag": f'"{hashlib.sha256(binary_path.read_bytes()).hexdigest()}"'},
    )


@router.get("/{os}/{arch}/worker.sha256")
async def get_worker_sha256(
    os: str,
    arch: str,
    settings=Depends(get_settings),
) -> PlainTextResponse:
    _validate_os_arch(os, arch)

    cache_dir = Path(settings.worker_binary_cache_dir) / os / arch
    sha256_path = cache_dir / "worker.sha256"

    if not sha256_path.exists():
        await _fetch_and_cache(settings, os, arch)

    sha256_content = sha256_path.read_text().strip()
    return PlainTextResponse(content=sha256_content + "\n")


@router.get("/manifest.json")
async def get_manifest(
    settings=Depends(get_settings),
) -> dict:
    manifest = await _fetch_manifest(settings)
    return manifest


@router.get("/public-key")
async def get_public_key(
    settings=Depends(get_settings),
) -> PlainTextResponse:
    if not settings.worker_binary_public_key:
        raise HTTPException(status_code=404, detail="Public key not configured")
    return PlainTextResponse(content=settings.worker_binary_public_key + "\n")
