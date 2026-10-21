"""Generate and store images through the user-configured image provider."""

from __future__ import annotations

import base64
import hashlib
import httpx

from ...util.config import get_settings
from ...database.store import get_active_llm_config


class ImageGenError(RuntimeError):
    pass


def _key() -> str:
    s = get_settings()
    if s.image_api_key:
        return s.image_api_key

    return (get_active_llm_config() or {}).get("api_key", "")


async def generate(prompt: str, *, timeout: float = 300.0) -> tuple[bytes, str]:
    s = get_settings()
    key = _key()
    if not key:
        raise ImageGenError('No image-model API key is configured. Set image_api_key in Settings or choose a writing provider account that supports image generation.')
    body = {"model": s.image_model, "prompt": prompt, "size": s.image_size, "n": 1}
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.post(f"{s.image_base_url}/images/generations", json=body,
                             headers={"Authorization": f"Bearer {key}",
                                      "Content-Type": "application/json"})
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPStatusError as exc:
        raise ImageGenError(f"Image model returned {exc.response.status_code}："
                            f"{exc.response.text[:200]}") from exc
    except httpx.HTTPError as exc:
        raise ImageGenError(f"Cannot reach the image model: {exc}") from exc

    item = (data.get("data") or [{}])[0]
    if item.get("b64_json"):
        return base64.b64decode(item["b64_json"]), s.image_model
    url = item.get("url")
    if not url:
        raise ImageGenError(f"The image model returned no image: {str(data)[:200]}")
    async with httpx.AsyncClient(timeout=timeout) as c:
        got = await c.get(url)
        got.raise_for_status()
        return got.content, s.image_model


def save(png: bytes) -> str:
    d = get_settings().kite_data_dir / "assets"
    d.mkdir(parents=True, exist_ok=True)
    name = hashlib.sha256(png).hexdigest()[:24] + ".png"
    path = d / name
    if not path.exists():
        path.write_bytes(png)
    return f"/api/assets/{name}"
