import io, base64, mimetypes
from typing import Optional, Union
from PIL import Image

def _resize_max(img: Image.Image, max_side: int = 1024) -> Image.Image:
    w, h = img.size
    if max(w, h) <= max_side:
        return img
    if w >= h:
        nh = int(h * (max_side / float(w)))
        return img.resize((max_side, max(1, nh)))
    else:
        nw = int(w * (max_side / float(h)))
        return img.resize((max(1, nw), max_side))

def pil_to_jpeg_data_url(img: Image.Image, quality: int = 80, max_side: int = 1024) -> str:
    img = _resize_max(img.convert("RGB"), max_side=max_side)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{b64}"

def image_path_to_data_url(path: str) -> str:
    mime = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{b64}"

def path_from_gradio_file(f: Union[str, dict, None]) -> Optional[str]:
    if f is None:
        return None
    if isinstance(f, str):
        return f
    if isinstance(f, dict):
        return f.get("name") or f.get("path")
    return getattr(f, "name", None)
