#!/usr/bin/env python3
"""Generate a rich, visual 1280x800 Safari preview for action/toolbar extensions.

Used by `scripts/generate_thumbnails.sh` when an extension has no `index.html` (e.g.
background scripts or toolbar actions like Video PiP, Greyscale Web, Browser Pet Cat).

Outputs `<work_dir>/_action_preview.html`.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
import re
import sys

COLOR_MAP = {
    "blue": {"hex": "#0a84ff", "gradient": "linear-gradient(135deg, #0a84ff, #0051d5)"},
    "purple": {"hex": "#bf5af2", "gradient": "linear-gradient(135deg, #bf5af2, #7d2ae8)"},
    "pink": {"hex": "#ff375f", "gradient": "linear-gradient(135deg, #ff375f, #d60036)"},
    "red": {"hex": "#ff453a", "gradient": "linear-gradient(135deg, #ff453a, #b31006)"},
    "orange": {"hex": "#ff9f0a", "gradient": "linear-gradient(135deg, #ff9f0a, #d46000)"},
    "yellow": {"hex": "#ffd60a", "gradient": "linear-gradient(135deg, #ffd60a, #d49b00)"},
    "green": {"hex": "#30d158", "gradient": "linear-gradient(135deg, #30d158, #158a32)"},
    "gray": {"hex": "#98989d", "gradient": "linear-gradient(135deg, #98989d, #545458)"},
    "graphite": {"hex": "#636366", "gradient": "linear-gradient(135deg, #636366, #3a3a3c)"},
}

SF_SYMBOLS = {
    "cat.fill": """<path d="M12 4c-1.2 0-2.3.4-3.2 1.1L5 3.5c-.5-.3-1.1 0-1.3.5-.2.5 0 1.1.5 1.3l2.8 1.4C5.7 8 5 9.9 5 12c0 4.4 3.1 8 7 8s7-3.6 7-8c0-2.1-.7-4-2-5.3l2.8-1.4c.5-.2.7-.8.5-1.3-.2-.5-.8-.8-1.3-.5l-3.8 1.6C14.3 4.4 13.2 4 12 4zm-3 8c.6 0 1 .4 1 1s-.4 1-1 1-1-.4-1-1 .4-1 1-1zm6 0c.6 0 1 .4 1 1s-.4 1-1 1-1-.4-1-1 .4-1 1-1zm-3 2.5c1.1 0 1.8.6 1.8.6-.2.4-.7.9-1.8.9s-1.6-.5-1.8-.9c0 0 .7-.6 1.8-.6z"/>""",
    "video.fill": """<path d="M19 11h-8v6h8v-6zm4 8V5c0-1.1-.9-2-2-2H3c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h18c1.1 0 2-.9 2-2zm-2 0H3V5h18v14z"/>""",
    "circle.fill": """<circle cx="12" cy="12" r="9"/>""",
    "pawprint.fill": """<path d="M12 12c-2.2 0-4 1.8-4 4 0 1.7 1.3 3 3 3h2c1.7 0 3-1.3 3-3 0-2.2-1.8-4-4-4zm-4.5-2c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm9 0c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm-6.5-3c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm4 0c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2z"/>""",
    "newspaper.fill": """<path d="M20 5H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm-9 3h7v2h-7V8zm0 4h7v2h-7v-2zm0 4h7v2h-7v-2zm-6-8h4v8H5V8z"/>""",
    "sparkles": """<path d="M12 2l2.4 5.6L20 10l-5.6 2.4L12 18l-2.4-5.6L4 10l5.6-2.4L12 2zm7 13l1.2 2.8L23 19l-2.8 1.2L19 23l-1.2-2.8L15 19l2.8-1.2L19 15z"/>""",
    "moon.stars.fill": """<path d="M12 3a9 9 0 1 0 9 9c0-.46-.04-.92-.1-1.36a5.389 5.389 0 0 1-4.4 2.26 5.403 5.403 0 0 1-3.14-9.79c-.44-.06-.9-.11-1.36-.11z"/>""",
    "puzzlepiece.extension": """<path d="M20.5 11H19V7c0-1.1-.9-2-2-2h-4V3.5C13 2.1 11.9 1 10.5 1S8 2.1 8 3.5V5H4c-1.1 0-1.99.9-1.99 2v3.8H3.5c1.4 0 2.5 1.1 2.5 2.5s-1.1 2.5-2.5 2.5H2v4c0 1.1.9 2 2 2h3.8v-1.5c0-1.4 1.1-2.5 2.5-2.5s2.5 1.1 2.5 2.5V22H17c1.1 0 2-.9 2-2v-4h1.5c1.4 0 2.5-1.1 2.5-2.5s-1.1-2.5-2.5-2.5z"/>""",
    "default": """<path d="M20.5 11H19V7c0-1.1-.9-2-2-2h-4V3.5C13 2.1 11.9 1 10.5 1S8 2.1 8 3.5V5H4c-1.1 0-1.99.9-1.99 2v3.8H3.5c1.4 0 2.5 1.1 2.5 2.5s-1.1 2.5-2.5 2.5H2v4c0 1.1.9 2 2 2h3.8v-1.5c0-1.4 1.1-2.5 2.5-2.5s2.5 1.1 2.5 2.5V22H17c1.1 0 2-.9 2-2v-4h1.5c1.4 0 2.5-1.1 2.5-2.5s-1.1-2.5-2.5-2.5z"/>"""
}


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "extension"


def infer_action_type(slug: str, manifest: dict) -> str:
    if "pip" in slug or "video" in slug:
        return "Picture-in-Picture Controller"
    if "grey" in slug or "gray" in slug or "monochrome" in slug:
        return "Monochrome Filter Controller"
    if "content_scripts" in manifest:
        return "Autonomous Content Script"
    if "action" in manifest or "browser_action" in manifest:
        return "1-Click Toolbar Action"
    return "Safari Action Controller"


def render_editorial_card(name: str, symbol: str, color_name: str, desc: str, action_type: str) -> str:
    color_info = COLOR_MAP.get(color_name.lower(), COLOR_MAP["blue"])
    accent = color_info["hex"]
    accent_grad = color_info["gradient"]
    svg_glyph = SF_SYMBOLS.get(symbol, SF_SYMBOLS["default"])
    slug = slugify(name)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>{html.escape(name)}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    html, body {{
      width: 1280px;
      height: 800px;
      overflow: hidden;
      background: #07080c;
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Helvetica Neue", sans-serif;
      -webkit-font-smoothing: antialiased;
      color: #fff;
    }}

    .showcase-canvas {{
      width: 1280px;
      height: 800px;
      position: relative;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      padding: 40px 56px 36px;
      background: 
        radial-gradient(ellipse 65% 55% at 75% 38%, {accent}22 0%, transparent 70%),
        radial-gradient(ellipse 50% 45% at 18% 75%, {accent}14 0%, transparent 65%),
        #07080c;
      overflow: hidden;
    }}

    .grid-overlay {{
      position: absolute;
      inset: 0;
      background-image: 
        linear-gradient(rgba(255, 255, 255, 0.03) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255, 255, 255, 0.03) 1px, transparent 1px);
      background-size: 36px 36px;
      mask-image: radial-gradient(ellipse 85% 75% at center, black 40%, transparent 85%);
      pointer-events: none;
    }}

    .ambient-flare {{
      position: absolute;
      width: 480px;
      height: 480px;
      border-radius: 50%;
      background: radial-gradient(circle, {accent}33 0%, transparent 65%);
      top: -120px;
      right: 120px;
      filter: blur(40px);
      pointer-events: none;
    }}

    /* Top: Floating Native Safari Toolbar */
    .safari-bar {{
      position: relative;
      z-index: 20;
      height: 48px;
      background: rgba(24, 26, 34, 0.82);
      border: 1px solid rgba(255, 255, 255, 0.11);
      border-radius: 12px;
      backdrop-filter: blur(28px);
      display: flex;
      align-items: center;
      padding: 0 16px;
      gap: 16px;
      box-shadow: 0 16px 36px rgba(0, 0, 0, 0.45);
    }}
    .traffic-lights {{
      display: flex;
      gap: 8px;
    }}
    .light {{
      width: 12px;
      height: 12px;
      border-radius: 50%;
    }}
    .light.red {{ background: #ff5f57; }}
    .light.yellow {{ background: #febc2e; }}
    .light.green {{ background: #28c840; }}

    .nav-arrows {{
      display: flex;
      gap: 12px;
      color: #636878;
      font-size: 15px;
      font-weight: 600;
    }}

    .url-capsule {{
      flex: 1;
      max-width: 520px;
      margin: 0 auto;
      height: 30px;
      background: rgba(0, 0, 0, 0.38);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      font-size: 12px;
      color: #8e92a4;
    }}
    .url-capsule .host {{ color: #ffffff; font-weight: 500; }}

    .safari-ext-pill {{
      display: flex;
      align-items: center;
      gap: 7px;
      background: {accent}22;
      border: 1px solid {accent}66;
      border-radius: 7px;
      padding: 4px 11px;
      font-size: 11.5px;
      font-weight: 600;
      color: {accent};
      box-shadow: 0 0 14px {accent}33;
    }}
    .safari-ext-pill svg {{ width: 13px; height: 13px; fill: currentColor; }}

    /* Center Stage */
    .stage-row {{
      position: relative;
      z-index: 10;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 60px;
      margin: auto 0;
    }}

    /* Left: Hero Editorial Typography */
    .hero-col {{
      max-width: 560px;
      display: flex;
      flex-direction: column;
      gap: 20px;
    }}

    .tag-badge {{
      align-self: flex-start;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      background: rgba(255, 255, 255, 0.07);
      border: 1px solid rgba(255, 255, 255, 0.12);
      border-radius: 9999px;
      padding: 6px 14px;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: #e2e8f0;
    }}
    .tag-dot {{
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: {accent};
      box-shadow: 0 0 10px {accent};
    }}

    .hero-name {{
      font-size: 54px;
      font-weight: 800;
      letter-spacing: -0.035em;
      line-height: 1.05;
      background: linear-gradient(180deg, #ffffff 40%, #a1a1aa 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }}

    .hero-summary {{
      font-size: 17.5px;
      line-height: 1.55;
      color: #94a3b8;
      font-weight: 400;
      max-width: 500px;
    }}

    .props-strip {{
      display: flex;
      gap: 12px;
      margin-top: 4px;
    }}
    .prop-chip {{
      display: flex;
      align-items: center;
      gap: 6px;
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 8px;
      padding: 6px 12px;
      font-size: 12px;
      font-weight: 500;
      color: #cbd5e1;
    }}
    .prop-chip span.ico {{ color: {accent}; font-weight: 700; }}

    /* Right: Realistic macOS Safari Extension Popover Card */
    .popover-card {{
      flex: 1;
      max-width: 500px;
      background: rgba(20, 22, 30, 0.82);
      border: 1px solid rgba(255, 255, 255, 0.15);
      border-radius: 24px;
      backdrop-filter: blur(36px);
      box-shadow: 
        0 32px 80px rgba(0, 0, 0, 0.75),
        0 0 0 1px rgba(255, 255, 255, 0.06),
        inset 0 1px 1px rgba(255, 255, 255, 0.2);
      padding: 32px;
      display: flex;
      flex-direction: column;
      gap: 24px;
      position: relative;
    }}

    .popover-head {{
      display: flex;
      align-items: center;
      justify-content: space-between;
    }}
    .popover-lead {{
      display: flex;
      align-items: center;
      gap: 16px;
    }}

    .squircle-icon {{
      width: 60px;
      height: 60px;
      border-radius: 15px;
      background: {accent_grad};
      border: 1px solid rgba(255, 255, 255, 0.35);
      box-shadow: 0 10px 24px {accent}44, inset 0 1px 1px rgba(255, 255, 255, 0.6);
      display: flex;
      align-items: center;
      justify-content: center;
    }}
    .squircle-icon svg {{
      width: 32px;
      height: 32px;
      fill: #ffffff;
    }}

    .popover-titles h3 {{
      font-size: 19px;
      font-weight: 700;
      color: #ffffff;
      margin-bottom: 3px;
      letter-spacing: -0.01em;
    }}
    .popover-titles p {{
      font-size: 12.5px;
      color: #8b92a5;
    }}

    .toggle-switch {{
      width: 50px;
      height: 30px;
      background: {accent};
      border-radius: 15px;
      padding: 2px;
      box-shadow: 0 0 16px {accent}55;
      display: flex;
      align-items: center;
      justify-content: flex-end;
    }}
    .toggle-thumb {{
      width: 26px;
      height: 26px;
      background: #ffffff;
      border-radius: 50%;
      box-shadow: 0 2px 5px rgba(0, 0, 0, 0.3);
    }}

    .popover-status-panel {{
      background: rgba(0, 0, 0, 0.45);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 14px;
      padding: 16px 20px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }}
    .status-item {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 13px;
    }}
    .status-label {{
      color: #7d8498;
      font-weight: 500;
    }}
    .status-val {{
      color: #f1f5f9;
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: 6px;
    }}
    .val-active-pulse {{
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: #30d158;
      box-shadow: 0 0 6px #30d158;
    }}

    .popover-action-btn {{
      background: rgba(255, 255, 255, 0.08);
      border: 1px solid rgba(255, 255, 255, 0.12);
      border-radius: 12px;
      padding: 12px 18px;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      font-size: 13px;
      font-weight: 600;
      color: #ffffff;
      box-shadow: inset 0 1px 1px rgba(255, 255, 255, 0.1);
    }}

    /* Bottom: Specs Strip */
    .footer-bar {{
      position: relative;
      z-index: 10;
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-top: 1px solid rgba(255, 255, 255, 0.07);
      padding-top: 16px;
      font-size: 12.5px;
      color: #64748b;
    }}
    .footer-features {{
      display: flex;
      gap: 16px;
      font-weight: 500;
    }}
    .footer-features span.bright {{ color: #cbd5e1; }}
  </style>
</head>
<body>
  <div class="showcase-canvas">
    <div class="grid-overlay"></div>
    <div class="ambient-flare"></div>

    <header class="safari-bar">
      <div class="traffic-lights">
        <span class="light red"></span>
        <span class="light yellow"></span>
        <span class="light green"></span>
      </div>
      <div class="nav-arrows">
        <span>‹</span>
        <span style="opacity:0.35">›</span>
      </div>
      <div class="url-capsule">
        <span>🔒</span>
        <span class="host">safari.apple.com</span>
        <span>/extensions/{slug}</span>
      </div>
      <div class="safari-ext-pill">
        <svg viewBox="0 0 24 24">
          {svg_glyph}
        </svg>
        <span>Active</span>
      </div>
    </header>

    <div class="stage-row">
      <div class="hero-col">
        <div class="tag-badge">
          <span class="tag-dot"></span>
          <span>Safari Action Extension</span>
        </div>
        <h1 class="hero-name">{html.escape(name)}</h1>
        <p class="hero-summary">{html.escape(desc)}</p>
        
        <div class="props-strip">
          <div class="prop-chip">
            <span class="ico">⚡</span>
            <span>1-Click Trigger</span>
          </div>
          <div class="prop-chip">
            <span class="ico">🔒</span>
            <span>Private &amp; Secure</span>
          </div>
          <div class="prop-chip">
            <span class="ico"></span>
            <span>Native Safari 18</span>
          </div>
        </div>
      </div>

      <div class="popover-card">
        <div class="popover-head">
          <div class="popover-lead">
            <div class="squircle-icon">
              <svg viewBox="0 0 24 24">
                {svg_glyph}
              </svg>
            </div>
            <div class="popover-titles">
              <h3>{html.escape(name)}</h3>
              <p>v1.0 · Active on this page</p>
            </div>
          </div>
          <div class="toggle-switch">
            <div class="toggle-thumb"></div>
          </div>
        </div>

        <div class="popover-status-panel">
          <div class="status-item">
            <span class="status-label">Extension State</span>
            <span class="status-val">
              <span class="val-active-pulse"></span>
              <span>Enabled</span>
            </span>
          </div>
          <div class="status-item">
            <span class="status-label">Execution Mode</span>
            <span class="status-val">{html.escape(action_type)}</span>
          </div>
        </div>

        <div class="popover-action-btn">
          <span>⚡</span>
          <span>Trigger Extension Action</span>
        </div>
      </div>
    </div>

    <footer class="footer-bar">
      <div class="footer-features">
        <span class="bright">✓ macOS Sequoia &amp; Sonoma</span>
        <span>·</span>
        <span>Apple Silicon Optimized</span>
        <span>·</span>
        <span>Zero Third-Party Tracking</span>
      </div>
      <div>Safari Magic Extensions</div>
    </footer>
  </div>
</body>
</html>"""


def generate_preview(work_dir: Path) -> Path:
    magic_file = work_dir / "magic.json"
    manifest_file = work_dir / "manifest.json"

    data = {}
    if magic_file.exists():
        try:
            with open(magic_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass

    manifest = {}
    if manifest_file.exists():
        try:
            with open(manifest_file, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception:
            pass

    name = data.get("name") or manifest.get("name") or "Safari Extension"
    symbol = data.get("selected_symbol") or "puzzlepiece.extension"
    color_name = (data.get("symbol_color_name") or "blue").lower()
    description = (
        data.get("description")
        or manifest.get("description")
        or "Native Safari Action Extension."
    )

    slug = slugify(name)
    action_type = infer_action_type(slug, manifest)
    content = render_editorial_card(name, symbol, color_name, description, action_type)

    out_file = work_dir / "_action_preview.html"
    out_file.write_text(content, encoding="utf-8")
    return out_file


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 generate_action_card.py <work_dir>")
        sys.exit(1)
    target_dir = Path(sys.argv[1])
    created = generate_preview(target_dir)
    print(f"Generated action card: {created}")
