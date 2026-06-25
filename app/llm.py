"""LLM client: Groq (primary) + optional Gemini + local Ollama fallback,
all via the OpenAI-compatible API. Streaming + tool-calling with failover.

Cloud providers stream; Ollama uses non-streaming (its streamed tool-calls are
unreliable, but non-streamed tool-calls work well)."""
import time
from openai import OpenAI

from . import config


def _is_rate_limit(err):
    s = str(err)
    return "429" in s or "RESOURCE_EXHAUSTED" in s or "rate limit" in s.lower()


def _short(err):
    if _is_rate_limit(err):
        return "rate limited (free-tier quota) - wait a few seconds and try again"
    return str(err).split("\n")[0][:180]


class LLM:
    def __init__(self):
        self.providers = []  # (name, client, model, stream)
        if config.GROQ_API_KEY:
            self.providers.append(("Groq", OpenAI(api_key=config.GROQ_API_KEY, base_url=config.GROQ_BASE_URL),
                                   config.GROQ_MODEL, True))
        if config.GEMINI_API_KEY:
            self.providers.append(("Gemini", OpenAI(api_key=config.GEMINI_API_KEY, base_url=config.GEMINI_BASE_URL),
                                   config.GEMINI_MODEL, True))
        if config.ollama_available():
            self.providers.append(("Local (Ollama)", OpenAI(api_key="ollama", base_url=config.OLLAMA_BASE_URL),
                                   config.OLLAMA_MODEL, False))
        self.active = self.providers[0][0] if self.providers else None

    def available(self):
        return bool(self.providers)

    def chat(self, messages, tools, on_token=None):
        """One model turn. Streams text via on_token(str). Returns (content, tool_calls)."""
        errors = []
        for idx, (name, client, model, stream) in enumerate(self.providers):
            is_primary = (idx == 0)
            for attempt in range(2):
                try:
                    result = self._complete(client, model, messages, tools, on_token, stream)
                    self.active = name
                    return result
                except Exception as e:
                    if is_primary and attempt == 0 and _is_rate_limit(e):
                        time.sleep(5)
                        continue
                    errors.append(f"{name}: {_short(e)}")
                    break
        raise RuntimeError("All providers failed. " + " | ".join(errors))

    def _complete(self, client, model, messages, tools, on_token, stream):
        if not stream:
            return self._once(client, model, messages, tools, on_token)
        return self._stream(client, model, messages, tools, on_token)

    def _once(self, client, model, messages, tools, on_token):
        r = client.chat.completions.create(
            model=model, messages=messages, tools=tools or None,
            tool_choice="auto" if tools else None, stream=False, temperature=0.3)
        m = r.choices[0].message
        content = m.content or ""
        calls = []
        for i, tc in enumerate(m.tool_calls or []):
            calls.append({"id": tc.id or f"call_{i}", "type": "function",
                          "function": {"name": tc.function.name, "arguments": tc.function.arguments or "{}"}})
        if on_token and content and not calls:   # only emit the final answer, not interim chatter
            on_token(content)
        return content, calls

    def _stream(self, client, model, messages, tools, on_token):
        stream = client.chat.completions.create(
            model=model, messages=messages, tools=tools or None,
            tool_choice="auto" if tools else None, stream=True, temperature=0.3)
        content = ""
        tool_calls = {}
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if getattr(delta, "content", None):
                content += delta.content
                if on_token:
                    on_token(delta.content)
            for tc in (getattr(delta, "tool_calls", None) or []):
                slot = tool_calls.setdefault(tc.index, {"id": None, "name": "", "arguments": ""})
                if tc.id:
                    slot["id"] = tc.id
                if tc.function and tc.function.name:
                    slot["name"] = tc.function.name
                if tc.function and tc.function.arguments:
                    slot["arguments"] += tc.function.arguments
        calls = []
        for i in sorted(tool_calls):
            c = tool_calls[i]
            calls.append({"id": c["id"] or f"call_{i}", "type": "function",
                          "function": {"name": c["name"], "arguments": c["arguments"] or "{}"}})
        return content, calls
