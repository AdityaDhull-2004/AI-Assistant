"""The agent loop: take user text, let the LLM think + call tools, return a reply."""
import json

from . import tools
from .llm import LLM

MAX_STEPS = 8


def build_system_prompt():
    paths = "\n".join(f"  {k.capitalize()}: {v}" for k, v in tools.FOLDERS.items() if v)
    return (
        "You are a fast, capable voice/text assistant on the user's Windows laptop. "
        "Use tools to ACTUALLY perform requests in this turn; don't say you'll do it later. "
        "After acting, give a SHORT confirmation. Answer general questions directly and concisely. "
        "Replies may be spoken aloud, so keep them natural and brief; avoid markdown unless asked.\n"
        "- Use web_search / read_webpage for current or factual info you don't know; get_weather for weather.\n"
        "- To save text (note/poem/doc) use write_file directly; you cannot type into apps.\n"
        "- For files in Desktop/Documents/Downloads etc., first call get_special_folder for the real path.\n"
        "- When acting on existing files in a folder, list_directory first to see what's really there.\n"
        "- To rename/move/copy, call the matching tool directly with full paths.\n"
        "- Only claim you did something if the tool returned success.\n"
        "User's real folders on this machine:\n" + paths
    )


class Agent:
    def __init__(self):
        self.llm = LLM()
        self.history = [{"role": "system", "content": build_system_prompt()}]

    def reset(self):
        self.history = self.history[:1]

    def run(self, user_text, on_token=None, on_tool=None):
        self.history.append({"role": "user", "content": user_text})
        final = ""
        for _ in range(MAX_STEPS):
            content, calls = self.llm.chat(self.history, tools.TOOL_SCHEMAS, on_token=on_token)
            msg = {"role": "assistant", "content": content or ""}
            if calls:
                msg["tool_calls"] = calls
            self.history.append(msg)
            if not calls:
                final = content
                break
            for tc in calls:
                name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"] or "{}")
                except Exception:
                    args = {}
                if on_tool:
                    on_tool(name, args)
                result = tools.dispatch(name, args)
                self.history.append({"role": "tool", "tool_call_id": tc["id"], "content": str(result)})
        else:
            final = final or "I took several steps but couldn't finish that."
        # keep history from growing unbounded
        if len(self.history) > 40:
            self.history = self.history[:1] + self.history[-30:]
        return (final or "").strip()
