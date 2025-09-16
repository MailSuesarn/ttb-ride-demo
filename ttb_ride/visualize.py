import io
from PIL import Image

def graph_png(compiled_app) -> Image.Image:
    """
    Return a PIL Image of the compiled LangGraph.
    Tries Mermaid first, then Graphviz PNG.
    """
    g = compiled_app.get_graph()
    # Prefer Mermaid (usually works out-of-the-box)
    try:
        data = g.draw_mermaid_png()      # bytes
        return Image.open(io.BytesIO(data)).convert("RGBA")
    except Exception as e1:
        # Fallback to Graphviz (requires graphviz installed)
        try:
            data = g.draw_png()          # bytes
            return Image.open(io.BytesIO(data)).convert("RGBA")
        except Exception as e2:
            raise RuntimeError(f"Graph rendering not available. Mermaid error: {e1}; Graphviz error: {e2}")
