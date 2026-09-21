#!/usr/bin/env python3
"""Generate a standalone HTML preview for an action/toolbar Safari Magic Extension.

Used by `scripts/generate_thumbnails.sh` when an extension has no `index.html` (e.g.
it operates as a background script or toolbar action like Video PiP).

Creates `<work_dir>/_action_preview.html` configured for 1280x800 rendering.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
import sys

COLOR_MAP = {
    "orange": {"accent": "#ff9500", "glow": "rgba(255, 149, 0, 0.35)"},
    "blue": {"accent": "#0a84ff", "glow": "rgba(10, 132, 255, 0.35)"},
    "purple": {"accent": "#bf5af2", "glow": "rgba(191, 90, 242, 0.35)"},
    "pink": {"accent": "#ff375f", "glow": "rgba(255, 55, 95, 0.35)"},
    "red": {"accent": "#ff453a", "glow": "rgba(255, 69, 58, 0.35)"},
    "yellow": {"accent": "#ffd60a", "glow": "rgba(255, 214, 10, 0.35)"},
    "green": {"accent": "#30d158", "glow": "rgba(48, 209, 88, 0.35)"},
    "gray": {"accent": "#98989d", "glow": "rgba(152, 152, 157, 0.35)"},
}

DEFAULT_COLOR = {"accent": "#0a84ff", "glow": "rgba(10, 132, 255, 0.35)"}

# Clean inline SVGs for common SF Symbols
SVG_ICONS = {
    "video.fill": '''<svg viewBox="0 0 24 24" width="48" height="48" fill="currentColor">
      <path d="M4 5a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2v-2.2l3.4 2.2a1 1 0 0 0 1.6-.8V7.8a1 1 0 0 0-1.6-.8L17 9.2V7a2 2 0 0 0-2-2H4z"/>
    </svg>''',
    "sparkles": '''<svg viewBox="0 0 24 24" width="48" height="48" fill="currentColor">
      <path d="M12 2l2.4 5.6L20 10l-5.6 2.4L12 18l-2.4-5.6L4 10l5.6-2.4L12 2zm7 13l1.2 2.8L23 19l-2.8 1.2L19 23l-1.2-2.8L15 19l2.8-1.2L19 15zM5 15l1.2 2.8L9 19l-2.8 1.2L5 23l-1.2-2.8L1 19l2.8-1.2L5 15z"/>
    </svg>''',
    "moon.stars.fill": '''<svg viewBox="0 0 24 24" width="48" height="48" fill="currentColor">
      <path d="M12.3 2a10 10 0 0 0 9.7 13.5 10 10 0 1 1-11.2-13.4c.5 0 1-.1 1.5-.1z"/>
      <polygon points="19 3 20 5.5 22.5 6.5 20 7.5 19 10 18 7.5 15.5 6.5 18 5.5 19 3"/>
    </svg>''',
    "newspaper.fill": '''<svg viewBox="0 0 24 24" width="48" height="48" fill="currentColor">
      <path d="M20 4H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2zM5 7h5v4H5V7zm14 10H5v-2h14v2zm0-4H12v-2h7v2zm0-4H12V7h7v2z"/>
    </svg>''',
    "cat.fill": '''<svg viewBox="0 0 24 24" width="48" height="48" fill="currentColor">
      <path d="M12 4c-4.4 0-8 3.6-8 8 0 2.2.9 4.2 2.3 5.7L4 20l4.3-1.4C9.5 19.4 10.7 20 12 20c4.4 0 8-3.6 8-8s-3.6-8-8-8zm-5-1L4 7l3 1V3zm10 0v5l3-1-3-4z"/>
    </svg>''',
    "pawprint.fill": '''<svg viewBox="0 0 24 24" width="48" height="48" fill="currentColor">
      <circle cx="4.5" cy="9.5" r="2.5"/><circle cx="9" cy="5.5" r="2.5"/><circle cx="15" cy="5.5" r="2.5"/><circle cx="19.5" cy="9.5" r="2.5"/>
      <path d="M17.3 12.3a7 7 0 0 0-10.6 0C5.3 13.8 5 15.5 5 17c0 2.2 2.2 4 7 4s7-1.8 7-4c0-1.5-.3-3.2-1.7-4.7z"/>
    </svg>''',
    "puzzlepiece.extension": '''<svg viewBox="0 0 24 24" width="48" height="48" fill="currentColor">
      <path d="M20.5 11H19V7a2 2 0 0 0-2-2h-4V3.5a2.5 2.5 0 0 0-5 0V5H4a2 2 0 0 0-2 2v4h1.5a2.5 2.5 0 0 1 0 5H2v4a2 2 0 0 0 2 2h4v-1.5a2.5 2.5 0 0 1 5 0V21h4a2 2 0 0 0 2-2v-4h1.5a2.5 2.5 0 0 0 0-5z"/>
    </svg>''',
}

DEFAULT_SVG = SVG_ICONS["puzzlepiece.extension"]


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
    prompt = (
        data.get("prompt")
        or manifest.get("browser_specific_settings", {}).get("safari", {}).get("prompt")
        or "Safari AI Magic Extension"
    )
    symbol = data.get("selected_symbol") or "puzzlepiece.extension"
    color_name = (data.get("symbol_color_name") or "blue").lower()
    description = (
        data.get("description")
        or manifest.get("description")
        or "Active Safari Toolbar Action Extension."
    )

    color_cfg = COLOR_MAP.get(color_name, DEFAULT_COLOR)
    accent_color = color_cfg["accent"]
    glow_color = color_cfg["glow"]

    icon_svg = SVG_ICONS.get(symbol, DEFAULT_SVG)

    # Optional mockup feature box (e.g. PiP demonstration)
    mockup_html = ""
    if "pip" in symbol or "video" in symbol or "pip" in name.lower():
        mockup_html = f"""
        <div class="pip-demo-frame">
          <div class="pip-main-screen">
            <div class="pip-ambient-play">
              <svg viewBox="0 0 24 24" width="32" height="32" fill="rgba(255,255,255,0.25)">
                <polygon points="5 3 19 12 5 21 5 3"/>
              </svg>
            </div>
            <div class="pip-scrubber-bar">
              <div class="pip-scrubber-progress" style="background: {accent_color};"></div>
            </div>
          </div>
          <div class="pip-floating-card" style="box-shadow: 0 12px 30px rgba(0,0,0,0.8), 0 0 20px {glow_color};">
            <div class="pip-card-head">
              <span class="pip-dot"></span>
              <span class="pip-label">Picture-in-Picture Active</span>
            </div>
            <div class="pip-card-video">
              <svg viewBox="0 0 24 24" width="28" height="28" fill="{accent_color}">
                <polygon points="5 3 19 12 5 21 5 3"/>
              </svg>
            </div>
          </div>
        </div>
        """
    else:
        mockup_html = f"""
        <div class="action-banner-strip">
          <div class="action-pulse-chip" style="color: {accent_color}; border-color: {accent_color};">
            ● Toolbar Action Ready
          </div>
        </div>
        """

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>{html.escape(name)} Preview</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    html, body {{
      width: 1280px;
      height: 800px;
      overflow: hidden;
      background: #141417;
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Space Grotesk", sans-serif;
      color: #E8E0C6;
      display: flex;
      align-items: center;
      justify-content: center;
      position: relative;
    }}
    /* Soft ambient background glow */
    .bg-radial {{
      position: absolute;
      width: 700px;
      height: 700px;
      border-radius: 50%;
      background: radial-gradient(circle, {glow_color} 0%, rgba(20, 20, 23, 0) 70%);
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      z-index: 0;
      opacity: 0.85;
    }}
    /* Subtle scanline grid texture */
    .bg-grid {{
      position: absolute;
      inset: 0;
      background-image: linear-gradient(rgba(232, 224, 198, 0.03) 1px, transparent 1px),
                        linear-gradient(90deg, rgba(232, 224, 198, 0.03) 1px, transparent 1px);
      background-size: 32px 32px;
      z-index: 1;
    }}
    /* macOS Safari Window Mockup */
    .window-card {{
      position: relative;
      z-index: 2;
      width: 1080px;
      height: 680px;
      background: #1c1d22;
      border: 1px solid rgba(232, 224, 198, 0.22);
      border-radius: 18px;
      box-shadow: 0 32px 80px rgba(0, 0, 0, 0.8), 0 0 1px rgba(255, 255, 255, 0.2);
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }}
    /* Titlebar */
    .window-titlebar {{
      height: 52px;
      background: #25262c;
      border-bottom: 1px solid rgba(232, 224, 198, 0.12);
      display: flex;
      align-items: center;
      padding: 0 18px;
      gap: 16px;
    }}
    .traffic-lights {{
      display: flex;
      gap: 8px;
    }}
    .traffic-dot {{
      width: 12px;
      height: 12px;
      border-radius: 50%;
    }}
    .dot-red {{ background: #ff5f56; }}
    .dot-yellow {{ background: #ffbd2e; }}
    .dot-green {{ background: #27c93f; }}

    .toolbar-url-box {{
      flex: 1;
      max-width: 480px;
      margin: 0 auto;
      height: 30px;
      background: rgba(0, 0, 0, 0.35);
      border: 1px solid rgba(232, 224, 198, 0.14);
      border-radius: 7px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 11px;
      font-family: "Space Mono", ui-monospace, monospace;
      color: #a6a49b;
      letter-spacing: 0.04em;
    }}
    .toolbar-actions {{
      display: flex;
      align-items: center;
      gap: 12px;
    }}
    .action-icon-chip {{
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 4px 10px;
      border-radius: 6px;
      background: rgba(0, 0, 0, 0.4);
      border: 1px solid {accent_color};
      color: {accent_color};
      font-family: "Space Mono", monospace;
      font-size: 11px;
      font-weight: 700;
      box-shadow: 0 0 12px {glow_color};
    }}
    /* Main Content Area */
    .window-body {{
      flex: 1;
      padding: 40px 60px;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: space-between;
      text-align: center;
    }}
    .hero-badge-pill {{
      font-family: "Space Mono", ui-monospace, monospace;
      font-size: 11px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: {accent_color};
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(232, 224, 198, 0.2);
      padding: 4px 14px;
      border-radius: 9999px;
      margin-bottom: 16px;
    }}
    .icon-stage {{
      width: 90px;
      height: 90px;
      border-radius: 24px;
      background: #25262c;
      border: 2px solid {accent_color};
      box-shadow: 0 12px 36px {glow_color};
      color: {accent_color};
      display: flex;
      align-items: center;
      justify-content: center;
      margin-bottom: 18px;
    }}
    .hero-title {{
      font-size: 38px;
      font-weight: 700;
      color: #E8E0C6;
      margin-bottom: 10px;
      letter-spacing: -0.01em;
    }}
    .hero-prompt-chip {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      background: #151619;
      border: 1px solid rgba(232, 224, 198, 0.22);
      border-radius: 9999px;
      padding: 8px 22px;
      font-family: "Space Mono", ui-monospace, monospace;
      font-size: 13px;
      color: #d0c8af;
      margin-bottom: 12px;
      max-width: 800px;
    }}
    .prompt-label {{
      color: {accent_color};
      font-weight: 700;
    }}
    .hero-description {{
      font-size: 15px;
      color: #a6a49b;
      max-width: 620px;
      line-height: 1.5;
      margin-bottom: 24px;
    }}
    /* PiP Mockup Graphics */
    .pip-demo-frame {{
      position: relative;
      width: 580px;
      height: 150px;
      background: #111215;
      border: 1px solid rgba(232, 224, 198, 0.16);
      border-radius: 12px;
      overflow: hidden;
      display: flex;
      align-items: center;
      justify-content: center;
    }}
    .pip-main-screen {{
      width: 100%;
      height: 100%;
      position: relative;
      display: flex;
      align-items: center;
      justify-content: center;
      background: linear-gradient(135deg, #18191e 0%, #0d0e11 100%);
    }}
    .pip-scrubber-bar {{
      position: absolute;
      bottom: 10px;
      left: 14px;
      right: 14px;
      height: 4px;
      background: rgba(255, 255, 255, 0.1);
      border-radius: 2px;
    }}
    .pip-scrubber-progress {{
      width: 45%;
      height: 100%;
      border-radius: 2px;
    }}
    .pip-floating-card {{
      position: absolute;
      top: 14px;
      right: 18px;
      width: 190px;
      height: 110px;
      background: #25262c;
      border: 1.5px solid {accent_color};
      border-radius: 10px;
      padding: 8px 10px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }}
    .pip-card-head {{
      display: flex;
      align-items: center;
      gap: 6px;
    }}
    .pip-dot {{
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: {accent_color};
      box-shadow: 0 0 6px {accent_color};
    }}
    .pip-label {{
      font-size: 8.5px;
      font-family: "Space Mono", monospace;
      color: #E8E0C6;
      letter-spacing: 0.02em;
    }}
    .pip-card-video {{
      display: flex;
      align-items: center;
      justify-content: center;
      flex: 1;
    }}
  </style>
</head>
<body>
  <div class="bg-radial"></div>
  <div class="bg-grid"></div>

  <div class="window-card">
    <div class="window-titlebar">
      <div class="traffic-lights">
        <span class="traffic-dot dot-red"></span>
        <span class="traffic-dot dot-yellow"></span>
        <span class="traffic-dot dot-green"></span>
      </div>
      <div class="toolbar-url-box">
        safari · magic extension · {html.escape(symbol)}
      </div>
      <div class="toolbar-actions">
        <div class="action-icon-chip">
          <span>●</span>
          <span>{html.escape(name)}</span>
        </div>
      </div>
    </div>

    <div class="window-body">
      <div>
        <div class="hero-badge-pill">Safari Action Extension</div>
        <div style="display: flex; justify-content: center;">
          <div class="icon-stage">
            {icon_svg}
          </div>
        </div>
        <h1 class="hero-title">{html.escape(name)}</h1>
        <div class="hero-prompt-chip">
          <span class="prompt-label">prompt:</span>
          <span>"{html.escape(prompt)}"</span>
        </div>
        <p class="hero-description">{html.escape(description)}</p>
      </div>

      {mockup_html}
    </div>
  </div>
</body>
</html>
"""

    out_file = work_dir / "_action_preview.html"
    out_file.write_text(html_content, encoding="utf-8")
    return out_file


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 generate_action_card.py <work_dir>")
        sys.exit(1)
    target_dir = Path(sys.argv[1])
    created = generate_preview(target_dir)
    print(f"Generated action card: {created}")
