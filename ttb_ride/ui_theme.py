def hero_css_base() -> str:
    return """
    .hero-wrap { 
      margin: 0 auto 10px;
      max-width: 1100px; 
      text-align: center;
    }
    .hero-img { 
      display: block; 
      margin: 0 auto;
      width: min(70%, 1100px); 
      max-height: 320px; 
      object-fit: cover; 
      object-position: center;
      border-radius: 18px; 
      box-shadow: 0 6px 22px rgba(0,0,0,.12); 
    }
    .hero-title { 
      color: #fff; 
      font-size: 42px; 
      font-weight: 800; 
      line-height: 1.12; 
      margin: 14px 4px 6px; 
      text-shadow: 0 1px 2px rgba(0,0,0,.5); 
    }
    .hero-sub { 
      color: #fff; 
      margin: 0 4px 14px; 
      opacity: .9; 
      text-shadow: 0 1px 2px rgba(0,0,0,.45);
      font-size: 18px;  
    }
    """

def bg_style_tag(r: int, g: int, b: int) -> str:
    r = max(0, min(255, int(r)))
    g = max(0, min(255, int(g)))
    b = max(0, min(255, int(b)))
    return f"""
    <style>
      body, .gradio-container {{
        background: rgb({r},{g},{b}) !important;
      }}
    </style>
    """

def layout_style_tag() -> str:
    return """
    <style>
      .main-chat, .bottom-row { max-width: 1100px; margin: 0 auto; }
      .bottom-row { gap: 16px; }

      /* White cards for Upload + Debug */
      .card{
        background: #ffffff !important;
        border: 1px solid rgba(2,6,23,.08);
        border-radius: 12px;
        padding: 12px;
        box-shadow: 0 4px 16px rgba(0,0,0,.05);
        color: #0f172a; /* dark text inside */
      }

      .card .gr-markdown, .card .gr-markdown *,
      .card .prose, .card .prose * { color:#0f172a !important; }

      .card pre, .card code {
        background: #ffffff !important;
        color: #0f172a !important;
        border: 1px solid rgba(2,6,23,.08);
        border-radius: 8px;
      }
    </style>
    """
