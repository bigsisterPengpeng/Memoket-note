"""Provider presets and request families.

OpenAI endpoints use max_completion_tokens. Compatible and local endpoints
receive both output-limit fields and can explicitly reject an unsupported one.
Optional reasoning parameters depend on the model. Legacy provider IDs preserve
existing settings, and each preset stores its own credentials independently.
"""

from __future__ import annotations

from dataclasses import dataclass

FAMILIES = ("openai", "compatible", "local")
GROUPS = ("hosted", "local", "custom")


@dataclass(frozen=True)
class Preset:
    id: str
    label: str
    base_url: str          # factory default (no trailing slash); the user may override it
    family: str            # openai | compatible | local (request-body shape, see module docstring)
    group: str             # hosted | local | custom (grouping in the settings dropdown)
    needs_key: bool = True
    models: tuple[str, ...] = ()   # suggested model names (`<datalist>`), not an exhaustive list
    docs: str = ""                 # the page the address / model names were verified against


_PRESETS: tuple[Preset, ...] = (
    # ---- hosted services
    Preset("openai", "OpenAI", "https://api.openai.com/v1", "openai", "hosted", True,
           ("gpt-6.1-sol", "gpt-6-astra", "gpt-6-luna"),
           "https://developers.openai.com/api/docs/models"),
    # Compatibility layer docs: max_tokens and max_completion_tokens both accepted; reasoning_effort
    # ignored; Claude 4.7+ returns 400 for temperature < 1 (`llm._rejects_temperature` strips it by param).
    Preset("anthropic", "Anthropic Claude", "https://api.anthropic.com/v1", "compatible", "hosted", True,
           ("claude-sonnet-5-5", "claude-opus-5-5", "claude-haiku-5-5", "claude-fable-5-1"),
           "https://platform.claude.com/docs/en/api/openai-sdk"),
    Preset("gemini", "Google Gemini", "https://generativelanguage.googleapis.com/v1beta/openai", "compatible", "hosted", True,
           ("gemini-3.8-flash", "gemini-4-argon", "gemini-3.6-flash", "gemini-3.5-flash-lite"),
           "https://ai.google.dev/gemini-api/docs/openai"),
    # xAI marked /chat/completions legacy in 2026-02 (Responses API recommended) but still serves it; this is what we call.
    Preset("xai", "xAI Grok", "https://api.x.ai/v1", "compatible", "hosted", True,
           ("grok-4.7", "grok-4.6", "grok-4.5"),
           "https://docs.x.ai/docs/overview"),
    # DeepSeek documents the base_url without /v1 (`https://api.deepseek.com`).
    Preset("deepseek", "DeepSeek", "https://api.deepseek.com", "compatible", "hosted", True,
           ("deepseek-flash", "deepseek-v4-pro"),
           "https://api-docs.deepseek.com/"),
    # Model Studio now recommends workspace-specific domains; the docs state the legacy
    # dashscope.aliyuncs.com endpoint keeps working, so the default is the one that needs no WorkspaceId.
    Preset("qwen", "Qwen / Alibaba Model Studio", "https://dashscope.aliyuncs.com/compatible-mode/v1", "compatible", "hosted", True,
           ("qwen3.8-max", "qwen3.7-plus", "qwen3.8-flash", "qwen-plus"),
           "https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope"),
    Preset("moonshot", "Moonshot Kimi", "https://api.moonshot.cn/v1", "compatible", "hosted", True,
           ("kimi-k3", "kimi-k2.6", "kimi-k2.7-code-highspeed"),
           "https://platform.kimi.com/docs/guide/start-using-kimi-api"),
    Preset("zhipu", "Zhipu GLM", "https://open.bigmodel.cn/api/paas/v4", "compatible", "hosted", True,
           ("glm-5.3", "glm-5.3-flash", "glm-5.2"),
           "https://docs.bigmodel.cn/cn/guide/develop/openai/introduction"),
    # The China platform docs now give api.minimax.cn (international is api.minimax.io).
    Preset("minimax", "MiniMax", "https://api.minimax.cn/v1", "compatible", "hosted", True,
           ("MiniMax-M3", "MiniMax-M3.1-Flash", "MiniMax-M2.7"),
           "https://platform.minimax.cn/docs/api-reference/text-openai-api"),
    Preset("mistral", "Mistral", "https://api.mistral.ai/v1", "compatible", "hosted", True,
           ("mistral-large-latest", "mistral-small-latest"),
           "https://docs.mistral.ai/api/"),
    Preset("groq", "Groq", "https://api.groq.com/openai/v1", "compatible", "hosted", True,
           ("llama-3.3-70b-versatile", "openai/gpt-oss-120b", "openai/gpt-oss-20b", "llama-3.1-8b-instant"),
           "https://console.groq.com/docs/openai"),
    # `~vendor/family-latest` is OpenRouter's own "always newest" alias (the quickstart uses it).
    Preset("openrouter", "OpenRouter", "https://openrouter.ai/api/v1", "compatible", "hosted", True,
           ("~openai/gpt-sol-latest", "~anthropic/claude-sonnet-latest", "openai/gpt-4o-mini"),
           "https://openrouter.ai/docs/quickstart"),
    # ---- local servers
    Preset("ollama", "Ollama", "http://127.0.0.1:11434/v1", "local", "local", False,
           ("qwen3:8b", "gpt-oss:20b", "qwen3-vl:8b"),
           "https://docs.ollama.com/openai"),
    # LM Studio's model id is whatever is loaded in its UI (the docs list no fixed names); use "Test"
    # to list /models and pick one.
    Preset("lmstudio", "LM Studio", "http://127.0.0.1:1234/v1", "local", "local", False,
           (),
           "https://lmstudio.ai/docs/app/api/endpoints/openai"),
    # Legacy id: "local model". Empty address / model fall back to .env / factory defaults
    # (`store.get_active_llm_config`).
    Preset("local", "Local / self-hosted (custom address)", "http://127.0.0.1:11434/v1", "local", "local", False,
           ("qwen3:8b", "gpt-oss:20b"),
           ""),
    # ---- custom: legacy id `gpt`, any OpenAI-compatible endpoint. The request body follows OpenAI
    # itself (existing users' real databases point this slot at reasoning-tier models on
    # api.openai.com; not a byte of that path may change).
    Preset("gpt", "Custom OpenAI-compatible endpoint", "https://api.openai.com/v1", "openai", "custom", True,
           (),
           ""),
)

PROVIDERS: dict[str, Preset] = {p.id: p for p in _PRESETS}
"""Presets by id. The order is the order of the settings dropdown (dicts keep insertion order)."""

DEFAULT_FAMILY = "compatible"
"""Unknown provider ids / configs without a provider are treated as this: both limit fields are sent.
**Fail towards the safe side**: treating an endpoint as openai (no `max_tokens`) when it is really
Ollama means no output limit at all (`tests/test_p30.py`)."""


def family_of(provider_id: str | None) -> str:
    """Request-body shape for a provider id. Unknown ids get `DEFAULT_FAMILY`."""
    p = PROVIDERS.get(str(provider_id or ""))
    return p.family if p else DEFAULT_FAMILY


def family_for(cfg: dict | None) -> str:
    """Request-body shape for an active config (the dict `store.get_active_llm_config()` returns).

    `family` (the new field) wins; otherwise the `provider` id is looked up (old monkeypatches and a
    separately configured vision endpoint carry only `provider`, or nothing); otherwise `DEFAULT_FAMILY`."""
    cfg = cfg or {}
    fam = cfg.get("family")
    if fam in FAMILIES:
        return str(fam)
    return family_of(cfg.get("provider"))


def preset_dicts() -> list[dict]:
    """API shape (never includes credentials)."""
    return [{"id": p.id, "label": p.label, "base_url": p.base_url, "family": p.family,
             "group": p.group, "needs_key": p.needs_key, "models": list(p.models), "docs": p.docs}
            for p in _PRESETS]
