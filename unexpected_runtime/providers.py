from __future__ import annotations
import json, os, urllib.error, urllib.request
from urllib.parse import urlsplit
from typing import Protocol

class ProviderError(RuntimeError): pass
class Provider(Protocol):
    name: str
    def generate(self, *, system_prompt: str, user_prompt: str, agent_id: str, task_id: str, timeout: float) -> str: ...

class DeterministicMockProvider:
    name = "deterministic-mock"
    configured = True
    retry_safe = True
    def __init__(self): self.calls = 0; self.requests = []
    def generate(self, *, system_prompt: str, user_prompt: str, agent_id: str, task_id: str, timeout: float) -> str:
        self.calls += 1
        self.requests.append({"system_prompt":system_prompt,"user_prompt":user_prompt,"agent_id":agent_id,"task_id":task_id})
        return f"MOCK_OK agent={agent_id} task={task_id}. This deterministic response verifies runtime plumbing only."

class OpenAICompatibleProvider:
    name = "openai-compatible"
    def __init__(self, base_url: str, model: str, api_key: str, default_timeout: float = 30.0, *, name: str = "openai-compatible"):
        if not isinstance(base_url, str) or not base_url.strip() or not model or not api_key:
            raise ProviderError("OpenAI-compatible provider requires URL, model and key in the host environment.")
        try:
            parsed = urlsplit(base_url.strip())
            if (parsed.scheme.lower() != "https" or not parsed.hostname
                    or parsed.username is not None or parsed.password is not None
                    or parsed.query or parsed.fragment):
                raise ValueError("unsafe provider URL")
        except ValueError:
            raise ProviderError("OpenAI-compatible base URL must use HTTPS without embedded credentials, query or fragment.") from None
        path = parsed.path.rstrip("/")
        if not path.endswith("/chat/completions"):
            path += "/chat/completions"
        self.base_url = parsed._replace(path=path).geturl()
        self.name, self.model, self._api_key, self.default_timeout = name, model, api_key, float(default_timeout)
        self.configured = True
        self.verified = False
        self.retry_safe = False
    def generate(self, *, system_prompt: str, user_prompt: str, agent_id: str, task_id: str, timeout: float) -> str:
        body = {"model":self.model,"messages":[{"role":"system","content":system_prompt},{"role":"user","content":user_prompt}],"metadata":{"agent_id":agent_id,"task_id":task_id}}
        req = urllib.request.Request(self.base_url, data=json.dumps(body).encode(), headers={"Content-Type":"application/json","Authorization":"Bearer "+self._api_key}, method="POST")
        try:
            with urllib.request.build_opener(_NoRedirect()).open(req, timeout=min(timeout,self.default_timeout)) as resp:
                raw=resp.read(1_000_001)
            if len(raw)>1_000_000: raise ProviderError("Provider response exceeded 1 MB.")
            data=json.loads(raw.decode("utf-8"))
        except Exception as exc: raise ProviderError(f"Provider request failed ({type(exc).__name__}); inspect host diagnostics without secrets.") from None
        try: return str(data["choices"][0]["message"]["content"])
        except Exception: raise ProviderError("Provider returned an unexpected response schema.") from None

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl): return None

class AnthropicProvider:
    """Native Anthropic Messages API adapter; credentials remain server-side."""
    name = "anthropic"
    API_URL = "https://api.anthropic.com/v1/messages"
    API_VERSION = "2023-06-01"
    MAX_RESPONSE_BYTES = 1_000_000

    def __init__(self, api_key: str, model: str, default_timeout: float = 30.0):
        if not isinstance(api_key, str) or not api_key.strip() or not isinstance(model, str) or not model.strip():
            raise ProviderError("Anthropic provider requires a host-configured API key and model.")
        if not 0 < float(default_timeout) <= 120:
            raise ProviderError("Anthropic timeout must be between 0 and 120 seconds.")
        self._api_key = api_key.strip()
        self.model = model.strip()
        self.default_timeout = float(default_timeout)
        self.configured = True
        self.verified = False
        self.retry_safe = False

    def generate(self, *, system_prompt: str, user_prompt: str, agent_id: str, task_id: str, timeout: float) -> str:
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ProviderError("Anthropic request timeout must be positive.")
        body = {
            "model": self.model,
            "max_tokens": 1024,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
            "metadata": {"user_id": agent_id[:64]},
        }
        request = urllib.request.Request(
            self.API_URL,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "x-api-key": self._api_key,
                "anthropic-version": self.API_VERSION,
            },
            method="POST",
        )
        try:
            with urllib.request.build_opener(_NoRedirect()).open(
                request, timeout=min(float(timeout), self.default_timeout)
            ) as response:
                raw = response.read(self.MAX_RESPONSE_BYTES + 1)
            if len(raw) > self.MAX_RESPONSE_BYTES:
                raise ProviderError("Anthropic response exceeded 1 MB.")
            data = json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise ProviderError(f"Anthropic rejected the request (HTTP {exc.code}).") from None
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(f"Anthropic request failed ({type(exc).__name__}); inspect host diagnostics without secrets.") from None
        try:
            parts = [item["text"] for item in data["content"] if item.get("type") == "text" and isinstance(item.get("text"), str)]
            result = "\n".join(part for part in parts if part.strip()).strip()
            if not result:
                raise ValueError("empty content")
            return result
        except Exception:
            raise ProviderError("Anthropic returned an unexpected response schema.") from None


class OpenOxResponsesProvider:
    """OpenOx native Responses API adapter; credentials remain server-side."""

    name = "openox"
    MAX_RESPONSE_BYTES = 1_000_000

    def __init__(self, base_url: str, model: str, api_key: str, default_timeout: float = 30.0):
        if not isinstance(base_url, str) or not base_url.strip():
            raise ProviderError("OpenOx requires a host-configured HTTPS base URL.")
        if not isinstance(model, str) or not model.strip():
            raise ProviderError("OpenOx requires a host-configured model ID.")
        if not isinstance(api_key, str) or not api_key.strip():
            raise ProviderError("OpenOx requires a host-configured API key.")
        if not 0 < float(default_timeout) <= 120:
            raise ProviderError("OpenOx timeout must be between 0 and 120 seconds.")
        try:
            parsed = urlsplit(base_url.strip())
            if (parsed.scheme.lower() != "https" or not parsed.hostname
                    or parsed.username is not None or parsed.password is not None
                    or parsed.query or parsed.fragment):
                raise ValueError("unsafe provider URL")
        except ValueError:
            raise ProviderError("OpenOx base URL must use HTTPS without embedded credentials, query or fragment.") from None

        path = parsed.path.rstrip("/")
        if not path.endswith("/responses"):
            path += "/responses"
        self.base_url = parsed._replace(path=path).geturl()
        self.model = model.strip()
        self._api_key = api_key.strip()
        self.default_timeout = float(default_timeout)
        self.configured = True
        self.verified = False
        self.retry_safe = False

    def generate(self, *, system_prompt: str, user_prompt: str, agent_id: str,
                 task_id: str, timeout: float) -> str:
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ProviderError("OpenOx request timeout must be positive.")
        body = {
            "model": self.model,
            "instructions": system_prompt,
            "input": user_prompt,
            "metadata": {"agent_id": str(agent_id)[:64], "task_id": str(task_id)[:64]},
        }
        request = urllib.request.Request(
            self.base_url,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": "Bearer " + self._api_key,
            },
            method="POST",
        )
        try:
            with urllib.request.build_opener(_NoRedirect()).open(
                request, timeout=min(float(timeout), self.default_timeout)
            ) as response:
                raw = response.read(self.MAX_RESPONSE_BYTES + 1)
            if len(raw) > self.MAX_RESPONSE_BYTES:
                raise ProviderError("OpenOx response exceeded 1 MB.")
            data = json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error_code = None
            error_message = None
            try:
                upstream = json.loads(exc.read(8192).decode("utf-8"))
                if isinstance(upstream, dict):
                    detail = upstream.get("error", upstream)
                    if isinstance(detail, dict):
                        error_code = detail.get("code") or detail.get("type")
                        error_message = detail.get("message") or detail.get("detail")
                    elif isinstance(detail, str):
                        error_message = detail
            except Exception:
                pass
            diagnostic = f"OpenOx rejected the request (HTTP {exc.code}"
            if isinstance(error_code, (str, int)) and str(error_code).strip():
                diagnostic += f"; {str(error_code).strip()[:80]}"
            diagnostic += ")"
            if isinstance(error_message, str) and error_message.strip():
                safe_message = " ".join(error_message.split()).replace(self._api_key, "[redacted]")
                diagnostic += ": " + safe_message[:240]
            raise ProviderError(diagnostic) from None
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(
                f"OpenOx request failed ({type(exc).__name__}); inspect host diagnostics without secrets."
            ) from None

        try:
            direct_text = data.get("output_text")
            if isinstance(direct_text, str) and direct_text.strip():
                return direct_text.strip()
            parts = []
            for item in data.get("output", []):
                if not isinstance(item, dict) or item.get("type") != "message":
                    continue
                if item.get("role") not in (None, "assistant"):
                    continue
                for content in item.get("content", []):
                    if (isinstance(content, dict) and content.get("type") == "output_text"
                            and isinstance(content.get("text"), str) and content["text"].strip()):
                        parts.append(content["text"].strip())
            result = "\n".join(parts).strip()
            if not result:
                raise ValueError("empty output")
            return result
        except Exception:
            raise ProviderError("OpenOx returned an unexpected Responses API response schema.") from None


class ProviderRouter:
    """Immutable per-request provider selection over server-configured adapters."""
    def __init__(self, providers: dict[str, Provider], default_route: str = "mock"):
        self.providers = dict(providers)
        if not self.providers or default_route not in self.providers:
            raise ProviderError("Provider router requires a registered default route.")
        self.default_route = default_route
        self.name = getattr(self.providers[default_route], "name", default_route)
        self.configured = bool(getattr(self.providers[default_route], "configured", True))
        self.retry_safe = bool(getattr(self.providers[default_route], "retry_safe", False))
        self.model = getattr(self.providers[default_route], "model", None)
        self.verified = bool(getattr(self.providers[default_route], "verified", False))

    def resolve(self, route: str | None = None) -> Provider:
        selected = self.default_route if route is None else route
        if not isinstance(selected, str) or selected not in self.providers:
            raise ProviderError("Requested provider route is not configured or is unavailable.")
        return self.providers[selected]

    def generate(self, *, system_prompt: str, user_prompt: str, agent_id: str, task_id: str, timeout: float) -> str:
        return self.resolve().generate(system_prompt=system_prompt, user_prompt=user_prompt,
                                       agent_id=agent_id, task_id=task_id, timeout=timeout)

    def mark_success(self, route: str | None = None) -> None:
        provider = self.resolve(route)
        if getattr(provider, "name", "") != "deterministic-mock":
            try: provider.verified = True
            except Exception: pass

    def status(self) -> list[dict[str, object]]:
        items = []
        for route, provider in sorted(self.providers.items()):
            items.append({
                "id": route,
                "name": getattr(provider, "name", type(provider).__name__),
                "configured": bool(getattr(provider, "configured", True)),
                "verified": bool(getattr(provider, "verified", False)),
                "model": getattr(provider, "model", None),
                "default": route == self.default_route,
                "live": route != "mock",
            })
        return items


class OpenRouterProvider(OpenAICompatibleProvider):
    def __init__(self, api_key: str, model: str = "openrouter/free", default_timeout: float = 30.0):
        super().__init__("https://openrouter.ai/api/v1", model, api_key, default_timeout, name="openrouter")


class AIStudioGatewayProvider:
    """Use the authenticated AI Studio gateway; provider keys stay there."""
    name = "unexpected-ai-studio-gateway"
    configured = False
    MODES = {"openai","claude","both"}
    def __init__(self, endpoint: str, token: str, *, mode: str = "openai", default_timeout: float = 200.0):
        p = urlsplit(str(endpoint or "").strip())
        if p.scheme != "https" or not p.hostname or p.username or p.password or p.query or p.fragment:
            raise ProviderError("AI Studio gateway URL must be HTTPS without embedded credentials, query or fragment.")
        path = p.path.rstrip("/") or "/orchestrate"
        if path == "/": path = "/orchestrate"
        self.endpoint = p._replace(path=path).geturl()
        self._token = str(token or "").strip()
        self.mode = str(mode or "openai").strip().lower()
        if self.mode not in self.MODES: raise ProviderError("Gateway mode must be openai, claude or both.")
        self.default_timeout = float(default_timeout)
        if self.default_timeout <= 0: raise ProviderError("Gateway timeout must be positive.")
        self.configured = bool(self._token)
    def generate(self, *, system_prompt: str, user_prompt: str, agent_id: str, task_id: str, timeout: float) -> str:
        if not self._token: raise ProviderError("AI Studio gateway token is not configured in the runtime host.")
        task = f"uneXpected runtime agent: {agent_id}; task: {task_id}\n\nSYSTEM:\n{system_prompt}\n\nTASK AND CONTEXT:\n{user_prompt}"
        if len(task.encode("utf-16-le")) // 2 > 15000: raise ProviderError("Gateway task exceeds the 15,000 UTF-16-code-unit limit.")
        req = urllib.request.Request(self.endpoint, data=json.dumps({"task":task,"mode":self.mode},ensure_ascii=False).encode(),
            headers={"Content-Type":"application/json","Accept":"application/json","Authorization":"Bearer "+self._token},method="POST")
        try:
            opener=urllib.request.build_opener(_NoRedirect())
            with opener.open(req,timeout=min(max(float(timeout),0.1),self.default_timeout)) as resp: raw=resp.read(1_000_001)
            if len(raw)>1_000_000: raise ProviderError("Gateway response exceeded 1 MB.")
            data=json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc: raise ProviderError(f"AI Studio gateway rejected the request (HTTP {exc.code}).") from None
        except ProviderError: raise
        except Exception as exc: raise ProviderError(f"AI Studio gateway request failed ({type(exc).__name__}); check host diagnostics.") from None
        if not isinstance(data,dict) or data.get("ok") is not True or not isinstance(data.get("results"),dict):
            raise ProviderError("Gateway did not return a successful provider result.")
        candidates={"openai":("openai","synthesis"),"claude":("anthropic","synthesis"),"both":("synthesis","openai","anthropic")}[self.mode]
        for key in candidates:
            item=data["results"].get(key)
            status = str(item.get("status", "")).strip().upper() if isinstance(item, dict) else ""
            is_live = status.startswith("LIVE") and not any(marker in status for marker in ("MOCK", "FALLBACK", "DELIVERED", "NOT LIVE"))
            if isinstance(item,dict) and isinstance(item.get("text"),str) and item["text"].strip() and is_live:
                return f"[Live AI result: {item.get('label') or key}; model={item.get('model') or 'provider model'}]\n{item['text'].strip()}"
        raise ProviderError("Gateway returned no live provider response; simulated or failed output was rejected.")

def provider_from_env():
    mode=os.getenv("UNEXPECTED_PROVIDER","mock").strip().lower()
    if mode=="mock": return DeterministicMockProvider()
    if mode in ("openai_compatible","openai-compatible"):
        return OpenAICompatibleProvider(os.getenv("UNEXPECTED_BASE_URL",""),os.getenv("UNEXPECTED_MODEL",""),os.getenv("UNEXPECTED_API_KEY",""),float(os.getenv("UNEXPECTED_DEFAULT_TIMEOUT_SECONDS","30")))
    if mode in ("ai_studio_gateway","unexpected_gateway","unexpected-ai-studio"):
        return AIStudioGatewayProvider(os.getenv("UNEXPECTED_GATEWAY_URL","https://unexpected-ai-studio.onrender.com/orchestrate"),os.getenv("UNEXPECTED_GATEWAY_TOKEN",""),mode=os.getenv("UNEXPECTED_GATEWAY_MODE","openai"),default_timeout=float(os.getenv("UNEXPECTED_GATEWAY_TIMEOUT_SECONDS","200")))
    raise ProviderError(f"Unsupported UNEXPECTED_PROVIDER mode: {mode}")


def provider_router_from_env() -> ProviderRouter:
    """Build v8's native provider registry. The legacy gateway is not a production route."""
    legacy_mode = os.getenv("UNEXPECTED_PROVIDER", "mock").strip().lower()
    providers: dict[str, Provider] = {"mock": DeterministicMockProvider()}

    openai_key = (os.getenv("OPENAI_API_KEY") or os.getenv("UNEXPECTED_OPENAI_API_KEY") or "").strip()
    anthropic_key = (os.getenv("ANTHROPIC_API_KEY") or os.getenv("UNEXPECTED_ANTHROPIC_API_KEY") or "").strip()
    openrouter_key = (os.getenv("OPENROUTER_API_KEY") or os.getenv("UNEXPECTED_OPENROUTER_API_KEY") or "").strip()

    if legacy_mode in ("openai_compatible", "openai-compatible"):
        openai_key = openai_key or os.getenv("UNEXPECTED_API_KEY", "").strip()
        base_url = os.getenv("UNEXPECTED_BASE_URL", "https://api.openai.com/v1")
        model = os.getenv("UNEXPECTED_MODEL", "gpt-4.1-mini")
        if openai_key:
            providers["openai"] = OpenAICompatibleProvider(
                base_url, model, openai_key,
                float(os.getenv("UNEXPECTED_DEFAULT_TIMEOUT_SECONDS", "30")), name="openai"
            )
    elif openai_key:
        providers["openai"] = OpenAICompatibleProvider(
            os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            openai_key,
            float(os.getenv("UNEXPECTED_DEFAULT_TIMEOUT_SECONDS", "30")),
            name="openai",
        )

    if anthropic_key:
        providers["anthropic"] = AnthropicProvider(
            anthropic_key,
            os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929"),
            float(os.getenv("ANTHROPIC_TIMEOUT_SECONDS", "30")),
        )
    if openrouter_key:
        providers["openrouter"] = OpenRouterProvider(
            openrouter_key,
            os.getenv("OPENROUTER_MODEL", "openrouter/free"),
            float(os.getenv("OPENROUTER_TIMEOUT_SECONDS", "30")),
        )

    openox_key = (os.getenv("OPENOX_API_KEY") or "").strip()
    if openox_key:
        providers["openox"] = OpenOxResponsesProvider(
            os.getenv("OPENOX_BASE_URL", "https://api.openoxai.com/v1"),
            os.getenv("OPENOX_MODEL", "gpt-6-astra"),
            openox_key,
            float(os.getenv("OPENOX_TIMEOUT_SECONDS", "30")),
        )

    requested_default = os.getenv("UNEXPECTED_DEFAULT_PROVIDER", "").strip().lower()
    if not requested_default and legacy_mode in ("openai_compatible", "openai-compatible"):
        requested_default = "openai"
    default_route = requested_default if requested_default in providers else "mock"
    return ProviderRouter(providers, default_route=default_route)
