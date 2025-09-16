import os, re
from pathlib import Path

# ===== Models =====
MODEL_VLM  = os.getenv("MODEL_VLM",  "gpt-4o-mini")
MODEL_TEXT = os.getenv("MODEL_TEXT", "gpt-4o-mini")

# ===== Project & assets =====
PROJECT_ROOT = Path(__file__).resolve().parents[1]  # .../TTB_RIDE
ASSETS_DIR = Path(os.getenv("ASSETS_DIR", "assets"))
if not ASSETS_DIR.is_absolute():
    ASSETS_DIR = PROJECT_ROOT / ASSETS_DIR

def _resolve_asset(var_name: str, default_filename: str) -> str:
    """
    If env var is set, use it (relative -> PROJECT_ROOT / value).
    Otherwise fall back to ASSETS_DIR/default_filename.
    Returns an absolute path as a string.
    """
    val = os.getenv(var_name)
    if val:
        p = Path(val)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        return str(p)
    return str(ASSETS_DIR / default_filename)

CONGRATS_IMAGE_PATH = _resolve_asset("CONGRATS_IMAGE_PATH", "congrats.png")
COVER_IMAGE_PATH    = _resolve_asset("COVER_IMAGE_PATH",    "cover.png")

# ===== Theme background color =====
def _parse_bg_rgb_env():
    raw = os.getenv("BG_RGB", "16,44,92")
    nums = [int(x) for x in re.findall(r"\d+", raw)][:3]
    while len(nums) < 3:
        nums.append(245)
    r, g, b = [max(0, min(255, n)) for n in nums[:3]]
    return r, g, b

DEFAULT_BG_R, DEFAULT_BG_G, DEFAULT_BG_B = _parse_bg_rgb_env()
