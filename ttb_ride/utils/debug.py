from typing import List

def dbg(state: dict, tag: str, **fields):
    line = f"[{tag}] " + " | ".join(f"{k}={repr(v)}" for k, v in fields.items())
    print(line, flush=True)
    logs: List[str] = state.get("debug_logs", [])
    logs.append(line)
    if len(logs) > 400:
        logs[:] = logs[-400:]
    state["debug_logs"] = logs

def get_debug_text(state: dict) -> str:
    logs: List[str] = state.get("debug_logs", [])
    if not logs:
        return "_(no debug logs yet)_"
    return "```\n" + "\n".join(logs[-120:]) + "\n```"
