"""Vision: hand one image to a model with visual capability.

**It can be independent of the writing LLM**: writing may switch to a hosted provider while vision goes to
the local machine (the "Vision" field in settings / ``VISION_BASE_URL``) — images never leave the intranet,
and measured: the local muse-glimmer-30b really has vision (it reads table structure and numbers in images,
and ``capabilities`` reports ``multimodal``). If not configured separately it follows the writing model
(``store.get_active_vision_config``, P19 #1).

This does exactly one thing: send one request with an image and bring back the text result. Deciding "is
this a table" or "what format to convert to" is the caller's business.
"""

from __future__ import annotations

import base64

import httpx

from ..database import store
from ..util import i18n, llm, providers


class VisionError(RuntimeError):
    pass


# Within one service process, the parameter capabilities of an endpoint/model do not change between two
# consecutive images. Remember the result after the first negotiation driven by an explicit 400, so

_UNSUPPORTED_CHAT_PARAMS: dict[tuple[str, str], set[str]] = {}


def _remember_unsupported(key: tuple[str, str], param: str) -> None:
    _UNSUPPORTED_CHAT_PARAMS.setdefault(key, set()).add(param)


async def ask_image(prompt: str, image: bytes, mime: str = "image/png",
                    *, max_tokens: int = 1200, timeout: float = 300.0,
                    system: str = "", cfg: dict | None = None) -> str:
    """Show the model one image with a question and return its answer.

    The image is inlined as a data URI, never written to disk or exposed as a URL — an image on this path
    may be a casual screenshot containing sensitive information, and must not be published just so the
    model can fetch it.

    `cfg` (used by "Test" in settings, P23 #4): the **not-yet-saved values in the inputs** for address /
    model name / key. The probe must go through this function, never build its own request — **a gate must
    guard the real source** (P21): if the probe's request and the real vision request were two pieces of
    code, changing one and forgetting the other would leave the probe green while the real path is broken.
    """

    # it used to read only .env)
    cfg = cfg or store.get_active_vision_config()
    b64 = base64.b64encode(image).decode()

    # local muse-glimmer-30b): glued together, the model repeated the instructions verbatim, then talked to
    # itself in English and never output an answer; moved into system, it behaved immediately.
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
    ]})
    endpoint_key = (str(cfg["base_url"]).rstrip("/"), str(cfg["model"]))
    unsupported = _UNSUPPORTED_CHAT_PARAMS.get(endpoint_key, set())
    # When following the writing config, `family` (`util/providers.py`; old configs carry only `provider`,
    # looked up by id) already says which token-limit field to send. A separately configured vision endpoint
    # has neither -> compatible: send the widely accepted max_tokens first, then negotiate.
    token_field = ("max_completion_tokens"
                   if providers.family_for(cfg) == "openai" or "max_tokens" in unsupported
                   else "max_tokens")
    body = {
        "model": cfg["model"],
        "messages": messages,
        token_field: max_tokens,
    }
    if "temperature" not in unsupported:
        body["temperature"] = 0.1
    headers = {"Authorization": f"Bearer {cfg['api_key'] or 'no-key'}"}
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            # The user can put any OpenAI-compatible endpoint into "Vision". Some only accept
            # max_completion_tokens, some only accept the default temperature, and one endpoint may reject
            # each in turn. Each retry adjusts only the parameter explicitly named in the 400; at most these
            # two known differences are handled, and any other 400 is reported to the user as-is.
            for _attempt in range(3):
                r = await c.post(f"{cfg['base_url']}/chat/completions",
                                 json=body, headers=headers)
                if llm.rejects_max_tokens(r.status_code, r.content) and \
                        llm.swap_to_max_completion_tokens(body):
                    _remember_unsupported(endpoint_key, "max_tokens")
                    continue
                if llm.drop_unsupported_temperature(body, r.status_code, r.content):
                    _remember_unsupported(endpoint_key, "temperature")
                    continue
                break

            # added "Test (sends one image)" in settings really sent an image for the first time, and the
            # entry saved in the user's DB (`gpt-5.6-luna` @ api.openai.com) answered 400 "Unsupported
            # parameter: 'max_tokens' is not supported with this model. Use 'max_completion_tokens'
            # instead." — i.e. **vision on that entry had never worked** (image-to-table / screen-activity
            # descriptions all go through here); nothing had ever sent an image before, so nobody knew.
            # We cannot switch everything to `max_completion_tokens`: the local ones (Ollama / LM Studio /
            # llama.cpp) accept `max_tokens`. When following an `openai`-family config the right field is
            # used directly; unknown endpoints are adjusted per the server's reply and the result is
            # remembered for later images.


            # `max_tokens`.
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPStatusError as exc:
        raise VisionError(i18n.msg("Vision model returned {code}: {text}",
                                   code=exc.response.status_code,
                                   text=exc.response.text[:200])) from exc
    except httpx.HTTPError as exc:
        raise VisionError(i18n.msg("Cannot reach the vision model ({base}): {err} - test it in the Vision "
                                   "section of Settings", base=cfg["base_url"], err=exc)) from exc
    try:
        msg = data["choices"][0]["message"]
    except (KeyError, IndexError) as exc:
        raise VisionError(i18n.msg("Unrecognized response shape from the vision model: {data}",
                                   data=str(data)[:200])) from exc
    # Some local models put the content in reasoning_content and leave content empty (measured:
    # muse-glimmer does this when max_tokens is too small), so look at both
    return (msg.get("content") or msg.get("reasoning_content") or "").strip()
