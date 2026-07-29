"""
Konva Scene Engine.

Renders a single SceneEvent as a real video clip via a headless browser
recording an HTML page running actual Konva.js canvas code — the top
half content for the "split_demo" layout.

Every template is animated, never static:
  - shared animated gradient background (color stops shift continuously
    via Konva.Animation) + slow-drifting glowing particle shapes
  - "diagram": nodes bounce-scale in on reveal, with a glowing dot and
    label; connecting lines draw themselves (tweened points) with a
    glow stroke; nodes marked "focus" get a camera zoom-in + hand-drawn
    pencil-circle annotation
  - "counter": a big number, in one of three presentation styles
    (sweeping ring / filling bar / side-by-side compare) picked per
    scene based on what the stat represents
  - "dynamic": one of three moods (drifting abstract shapes / relevant
    animated icons / bold kinetic typography) picked per scene so
    consecutive moments don't all look identical

Uses real Konva capabilities: fillLinearGradientColorStops animation,
shadowBlur/shadowColor for glow, Konva.Easings (including Bounce),
Konva.Arc for rings, Konva.Tween for animation, a small self-contained
icon library built from plain Konva primitives (no external image
assets needed).
"""
import json
import logging
from pathlib import Path

from playwright.async_api import async_playwright

from app.core.config import get_settings
from app.models.timeline import SceneEvent

logger = logging.getLogger(__name__)

HALF_WIDTH = 1080
HALF_HEIGHT = 960
START_TRIM_SECONDS = 0.4  # skip this much off the start of every recording — hides the natural browser-startup flash

SHARED_JS = """
function hexToRgb(hex) {
  hex = hex.replace('#','');
  var bigint = parseInt(hex, 16);
  return [(bigint>>16)&255, (bigint>>8)&255, bigint&255];
}
function rgbStr(rgb, a) { return 'rgba(' + rgb[0] + ',' + rgb[1] + ',' + rgb[2] + ',' + a + ')'; }

function buildAnimatedBackground(layer, accentHex, W, H) {
  var accent = hexToRgb(accentHex);
  var dark = [10, 10, 16];
  var bg = new Konva.Rect({
    x: 0, y: 0, width: W, height: H,
    fillLinearGradientStartPoint: { x: 0, y: 0 },
    fillLinearGradientEndPoint: { x: W, y: H },
    fillLinearGradientColorStops: [0, rgbStr(dark, 1), 1, rgbStr(accent, 0.35)],
  });
  layer.add(bg);
  bg.moveToBottom();

  var t = 0;
  var bgAnim = new Konva.Animation(function (frame) {
    t += frame.timeDiff / 1000;
    var mix = (Math.sin(t * 0.6) + 1) / 2;
    bg.fillLinearGradientColorStops([
      0, rgbStr(dark, 1),
      1, rgbStr(accent, 0.25 + mix * 0.25),
    ]);
  }, layer);
  bgAnim.start();

  var particles = [];
  for (var i = 0; i < 5; i++) {
    var p = new Konva.Circle({
      x: Math.random() * W, y: Math.random() * H,
      radius: 40 + Math.random() * 60,
      fill: rgbStr(accent, 0.12),
      shadowColor: accentHex, shadowBlur: 40, shadowOpacity: 0.6,
    });
    layer.add(p);
    p.moveToBottom();
    particles.push({ node: p, phase: Math.random() * 10, speed: 0.15 + Math.random() * 0.2 });
  }
  var particleAnim = new Konva.Animation(function (frame) {
    particles.forEach(function (pt) {
      var dt = (frame.time / 1000) * pt.speed + pt.phase;
      pt.node.x(pt.node.x() + Math.sin(dt) * 0.6);
      pt.node.y(pt.node.y() + Math.cos(dt * 0.8) * 0.4);
    });
  }, layer);
  particleAnim.start();
  bg.moveToBottom();
}

// Draws one icon (returns a Konva.Group) at (x, y) with given size/color.
// Every icon is built from plain Konva primitives — no external image
// assets — so the whole library stays self-contained and fast to render.
function makeIcon(type, x, y, size, color) {
  var g = new Konva.Group({ x: x, y: y });
  var s = size;
  var opts = { stroke: color, strokeWidth: s * 0.09, lineCap: "round", lineJoin: "round" };

  if (type === "checkmark") {
    g.add(new Konva.Line({ points: [-s*0.3, 0, -s*0.08, s*0.25, s*0.35, -s*0.3], ...opts }));
  } else if (type === "clock") {
    g.add(new Konva.Circle({ radius: s*0.5, stroke: color, strokeWidth: s*0.08 }));
    g.add(new Konva.Line({ points: [0, 0, 0, -s*0.3], ...opts }));
    g.add(new Konva.Line({ points: [0, 0, s*0.22, s*0.08], ...opts }));
  } else if (type === "chat") {
    g.add(new Konva.Rect({ x: -s*0.5, y: -s*0.35, width: s, height: s*0.6, cornerRadius: s*0.12, stroke: color, strokeWidth: s*0.08 }));
    g.add(new Konva.Line({ points: [-s*0.15, s*0.25, -s*0.3, s*0.5, 0, s*0.25], closed: true, fill: color }));
  } else if (type === "arrow") {
    g.add(new Konva.Arrow({ points: [-s*0.4, 0, s*0.4, 0], stroke: color, fill: color, strokeWidth: s*0.1, pointerLength: s*0.25, pointerWidth: s*0.25 }));
  } else if (type === "folder") {
    g.add(new Konva.Rect({ x: -s*0.5, y: -s*0.25, width: s, height: s*0.55, cornerRadius: s*0.06, stroke: color, strokeWidth: s*0.08 }));
    g.add(new Konva.Line({ points: [-s*0.5, -s*0.25, -s*0.3, -s*0.4, -s*0.05, -s*0.4, s*0.05, -s*0.25], ...opts }));
  } else if (type === "person") {
    g.add(new Konva.Circle({ y: -s*0.22, radius: s*0.2, stroke: color, strokeWidth: s*0.08 }));
    g.add(new Konva.Arc({ y: s*0.15, innerRadius: 0, outerRadius: s*0.4, angle: 180, rotation: 180, stroke: color, strokeWidth: s*0.08 }));
  } else if (type === "warning") {
    g.add(new Konva.Line({ points: [0, -s*0.45, s*0.45, s*0.35, -s*0.45, s*0.35], closed: true, stroke: color, strokeWidth: s*0.08 }));
    g.add(new Konva.Line({ points: [0, -s*0.12, 0, s*0.1], ...opts }));
    g.add(new Konva.Circle({ y: s*0.22, radius: s*0.035, fill: color }));
  } else if (type === "money") {
    g.add(new Konva.Circle({ radius: s*0.5, stroke: color, strokeWidth: s*0.08 }));
    g.add(new Konva.Text({ text: "$", fontSize: s*0.6, fontStyle: "bold", fill: color, x: -s*0.16, y: -s*0.32 }));
  } else if (type === "phone") {
    g.add(new Konva.Rect({ x: -s*0.28, y: -s*0.5, width: s*0.56, height: s, cornerRadius: s*0.1, stroke: color, strokeWidth: s*0.08 }));
    g.add(new Konva.Line({ points: [-s*0.1, s*0.38, s*0.1, s*0.38], ...opts }));
  } else if (type === "gear") {
    g.add(new Konva.Circle({ radius: s*0.4, stroke: color, strokeWidth: s*0.08 }));
    g.add(new Konva.Circle({ radius: s*0.14, stroke: color, strokeWidth: s*0.08 }));
    for (var gi = 0; gi < 6; gi++) {
      var ang = (gi / 6) * Math.PI * 2;
      g.add(new Konva.Line({
        points: [Math.cos(ang)*s*0.4, Math.sin(ang)*s*0.4, Math.cos(ang)*s*0.55, Math.sin(ang)*s*0.55],
        ...opts,
      }));
    }
  } else if (type === "calendar") {
    g.add(new Konva.Rect({ x: -s*0.5, y: -s*0.4, width: s, height: s*0.8, cornerRadius: s*0.08, stroke: color, strokeWidth: s*0.08 }));
    g.add(new Konva.Line({ points: [-s*0.5, -s*0.15, s*0.5, -s*0.15], ...opts }));
  } else if (type === "bell") {
    g.add(new Konva.Arc({ innerRadius: 0, outerRadius: s*0.4, angle: 200, rotation: -100, stroke: color, strokeWidth: s*0.08 }));
    g.add(new Konva.Line({ points: [-s*0.2, s*0.28, s*0.2, s*0.28], ...opts }));
  } else {
    g.add(new Konva.Circle({ radius: s*0.3, fill: color }));
  }
  return g;
}
"""


def _build_diagram_html(scene: SceneEvent, duration: float) -> str:
    elements_json = json.dumps(
        [{"text": e.text, "x": e.x_pct / 100.0 * HALF_WIDTH,
          "y": e.y_pct / 100.0 * HALF_HEIGHT, "revealAt": e.reveal_at, "focus": e.focus}
         for e in scene.elements]
    )
    connections_json = json.dumps(scene.connections)
    duration_ms = int(max(duration, 0.5) * 1000)

    return f"""<!DOCTYPE html>
<html><head><style>
  body {{ margin:0; width:{HALF_WIDTH}px; height:{HALF_HEIGHT}px; overflow:hidden;
          font-family:'Arial', sans-serif; background:#0a0a10; }}
  #stage {{ position:absolute; top:0; left:0; }}
  .title {{ position:absolute; top:55px; left:60px; font-size:52px; font-weight:800;
             color:#fff; max-width:900px; z-index:2; text-shadow: 0 0 20px rgba(0,0,0,0.6); }}
</style></head>
<body>
  <div id="stage"></div>
  <div class="title">{scene.title}</div>
  <script src="file:///app/vendor/konva.min.js"></script>
  <script>{SHARED_JS}
    var stage = new Konva.Stage({{ container: 'stage', width: {HALF_WIDTH}, height: {HALF_HEIGHT} }});
    var layer = new Konva.Layer();
    var accent = "{scene.accent_color}";
    buildAnimatedBackground(layer, accent, {HALF_WIDTH}, {HALF_HEIGHT});

    var camera = new Konva.Group({{ x: 0, y: 0, scaleX: 1, scaleY: 1 }});
    layer.add(camera);

    var elements = {elements_json};
    var connections = {connections_json};
    var totalDuration = {duration_ms};
    var nodePositions = [];

    elements.forEach(function(el, i) {{
      var group = new Konva.Group({{ x: el.x, y: el.y, opacity: 0, scaleX: 0.3, scaleY: 0.3 }});
      var glow = new Konva.Circle({{
        radius: 16, fill: accent, shadowColor: accent, shadowBlur: 25, shadowOpacity: 0.9,
      }});
      var label = new Konva.Text({{
        text: el.text, fontSize: 32, fontStyle: "bold", fill: "#fff",
        x: 30, y: -16, width: 280, shadowColor: "#000", shadowBlur: 8, shadowOpacity: 0.6,
      }});
      group.add(glow);
      group.add(label);
      camera.add(group);
      nodePositions.push({{ x: el.x, y: el.y }});

      setTimeout(function() {{
        new Konva.Tween({{
          node: group, duration: 0.5, opacity: 1, scaleX: 1, scaleY: 1,
          easing: Konva.Easings.BackEaseOut,
        }}).play();
      }}, el.revealAt * totalDuration);
    }});

    connections.forEach(function(pair) {{
      var a = nodePositions[pair[0]];
      var b = nodePositions[pair[1]];
      if (!a || !b) return;
      var line = new Konva.Line({{
        points: [a.x, a.y, a.x, a.y], stroke: accent, strokeWidth: 4, opacity: 0,
        shadowColor: accent, shadowBlur: 15, shadowOpacity: 0.7, lineCap: "round",
      }});
      camera.add(line);
      line.moveToBottom();
      var revealAt = Math.max(elements[pair[0]].revealAt, elements[pair[1]].revealAt) * totalDuration + 250;
      setTimeout(function() {{
        line.opacity(0.8);
        new Konva.Tween({{
          node: line, duration: 0.5, points: [a.x, a.y, b.x, b.y],
          easing: Konva.Easings.EaseOut,
        }}).play();
      }}, revealAt);
    }});

    var lastRevealMs = elements.length
      ? Math.max.apply(null, elements.map(function(e) {{ return e.revealAt * totalDuration; }}))
      : 0;
    var focusStart = lastRevealMs + 500;
    var focusElements = elements.filter(function(e) {{ return e.focus; }});
    var focusWindow = Math.max(totalDuration - focusStart, 0);

    if (focusElements.length && focusWindow > 800) {{
      var perFocus = focusWindow / focusElements.length;
      var ZOOM_SCALE = 1.7;

      focusElements.forEach(function(el, i) {{
        var stepStart = focusStart + i * perFocus;
        var targetX = {HALF_WIDTH} / 2 - el.x * ZOOM_SCALE;
        var targetY = {HALF_HEIGHT} / 2 - el.y * ZOOM_SCALE;

        setTimeout(function() {{
          new Konva.Tween({{
            node: camera, duration: 0.5, scaleX: ZOOM_SCALE, scaleY: ZOOM_SCALE,
            x: targetX, y: targetY, easing: Konva.Easings.EaseInOut,
          }}).play();

          setTimeout(function() {{
            var pts = [];
            var steps = 24;
            var radius = 55;
            for (var s = 0; s <= steps; s++) {{
              var ang = (s / steps) * Math.PI * 2;
              var jitter = (Math.random() - 0.5) * 8;
              pts.push(el.x + Math.cos(ang) * (radius + jitter));
              pts.push(el.y + Math.sin(ang) * (radius + jitter));
            }}
            var mark = new Konva.Line({{
              points: pts, stroke: "#FF5C5C", strokeWidth: 5, opacity: 0,
              lineCap: "round", lineJoin: "round", closed: true, tension: 0.6,
              shadowColor: "#FF5C5C", shadowBlur: 10, shadowOpacity: 0.5,
            }});
            camera.add(mark);
            mark.to({{ opacity: 0.9, duration: 0.25 }});
          }}, 350);
        }}, stepStart);
      }});

      setTimeout(function() {{
        new Konva.Tween({{
          node: camera, duration: 0.5, scaleX: 1, scaleY: 1, x: 0, y: 0,
          easing: Konva.Easings.EaseInOut,
        }}).play();
      }}, Math.max(totalDuration - 500, focusStart));
    }}

    stage.add(layer);
  </script>
</body></html>"""


def _build_counter_html(scene: SceneEvent, duration: float) -> str:
    duration_ms = int(max(duration, 0.5) * 1000 * 0.65)
    style = scene.counter_style if scene.counter_style in ("ring", "bar", "compare") else "ring"

    if style == "bar":
        js_body = f"""
    var finalText = "{scene.counter_value}";
    var numMatch = finalText.match(/[0-9]+/);
    var finalNum = numMatch ? parseInt(numMatch[0], 10) : 0;
    var suffix = finalText.replace(/^[^0-9]*[0-9]+/, "");
    var prefix = finalText.match(/^[^0-9]*/)[0];

    var barX = 90, barY = {HALF_HEIGHT} / 2 - 20, barW = {HALF_WIDTH} - 180, barH = 60;

    var barBg = new Konva.Rect({{
      x: barX, y: barY, width: barW, height: barH, cornerRadius: barH / 2,
      fill: "rgba(255,255,255,0.1)",
    }});
    layer.add(barBg);

    var barFill = new Konva.Rect({{
      x: barX, y: barY, width: 0, height: barH, cornerRadius: barH / 2,
      fill: accent, shadowColor: accent, shadowBlur: 25, shadowOpacity: 0.8,
    }});
    layer.add(barFill);

    var counterText = new Konva.Text({{
      x: 0, y: barY - 130, width: {HALF_WIDTH}, align: "center",
      text: prefix + "0" + suffix, fontSize: 110, fontStyle: "800",
      fill: "#fff", shadowColor: accent, shadowBlur: 20, shadowOpacity: 0.8,
    }});
    layer.add(counterText);
    stage.add(layer);

    var start = null;
    var totalMs = {duration_ms};
    function step(ts) {{
      if (!start) start = ts;
      var progress = Math.min((ts - start) / totalMs, 1);
      var current = Math.round(finalNum * progress);
      counterText.text(prefix + current + suffix);
      barFill.width(barW * progress);
      layer.batchDraw();
      if (progress < 1) requestAnimationFrame(step);
    }}
    requestAnimationFrame(step);
"""
    elif style == "compare":
        js_body = f"""
    var leftVal = "{scene.compare_value}";
    var rightVal = "{scene.counter_value}";
    var leftLabel = "{scene.compare_label}";
    var rightLabel = "{scene.counter_label}";

    var leftX = {HALF_WIDTH} * 0.28, rightX = {HALF_WIDTH} * 0.72, cy = {HALF_HEIGHT} / 2;

    var leftText = new Konva.Text({{
      x: leftX - 150, y: cy - 90, width: 300, align: "center",
      text: leftVal, fontSize: 100, fontStyle: "800",
      fill: "rgba(255,255,255,0.5)", opacity: 0,
    }});
    layer.add(leftText);

    var rightText = new Konva.Text({{
      x: rightX - 150, y: cy - 90, width: 300, align: "center",
      text: rightVal, fontSize: 130, fontStyle: "800",
      fill: "#fff", shadowColor: accent, shadowBlur: 25, shadowOpacity: 0.9, opacity: 0, scaleX: 0.5, scaleY: 0.5,
    }});
    layer.add(rightText);

    var leftLbl = new Konva.Text({{
      x: leftX - 150, y: cy + 70, width: 300, align: "center",
      text: leftLabel, fontSize: 28, fill: "rgba(255,255,255,0.6)", opacity: 0,
    }});
    layer.add(leftLbl);

    var rightLbl = new Konva.Text({{
      x: rightX - 150, y: cy + 90, width: 300, align: "center",
      text: rightLabel, fontSize: 30, fill: "#fff", opacity: 0,
    }});
    layer.add(rightLbl);

    var arrow = new Konva.Arrow({{
      points: [leftX + 90, cy, rightX - 90, cy], stroke: accent, fill: accent,
      strokeWidth: 6, pointerLength: 22, pointerWidth: 22, opacity: 0,
      shadowColor: accent, shadowBlur: 15, shadowOpacity: 0.7,
    }});
    layer.add(arrow);
    stage.add(layer);

    leftText.to({{ opacity: 1, duration: 0.4 }});
    leftLbl.to({{ opacity: 1, duration: 0.4 }});
    setTimeout(function() {{
      arrow.to({{ opacity: 0.9, duration: 0.3 }});
    }}, 300);
    setTimeout(function() {{
      rightText.to({{ opacity: 1, scaleX: 1, scaleY: 1, duration: 0.5, easing: Konva.Easings.BackEaseOut }});
      rightLbl.to({{ opacity: 1, duration: 0.4 }});
    }}, 650);
"""
    else:  # ring
        js_body = f"""
    var finalText = "{scene.counter_value}";
    var numMatch = finalText.match(/[0-9]+/);
    var finalNum = numMatch ? parseInt(numMatch[0], 10) : 0;
    var suffix = finalText.replace(/^[^0-9]*[0-9]+/, "");
    var prefix = finalText.match(/^[^0-9]*/)[0];

    var cx = {HALF_WIDTH} / 2, cy = {HALF_HEIGHT} / 2 + 40, ringRadius = 210;

    var ringBg = new Konva.Arc({{
      x: cx, y: cy, innerRadius: ringRadius - 14, outerRadius: ringRadius,
      angle: 360, rotation: -90, fill: "rgba(255,255,255,0.08)",
    }});
    layer.add(ringBg);

    var ring = new Konva.Arc({{
      x: cx, y: cy, innerRadius: ringRadius - 14, outerRadius: ringRadius,
      angle: 0, rotation: -90, fill: accent,
      shadowColor: accent, shadowBlur: 30, shadowOpacity: 0.9,
    }});
    layer.add(ring);

    var counterText = new Konva.Text({{
      x: 0, y: cy - 100, width: {HALF_WIDTH}, align: "center",
      text: prefix + "0" + suffix, fontSize: 170, fontStyle: "800",
      fill: "#fff", shadowColor: accent, shadowBlur: 25, shadowOpacity: 0.8,
    }});
    layer.add(counterText);
    stage.add(layer);

    var start = null;
    var totalMs = {duration_ms};
    function step(ts) {{
      if (!start) start = ts;
      var progress = Math.min((ts - start) / totalMs, 1);
      var current = Math.round(finalNum * progress);
      counterText.text(prefix + current + suffix);
      ring.angle(progress * 360);
      layer.batchDraw();
      if (progress < 1) requestAnimationFrame(step);
    }}
    requestAnimationFrame(step);
"""

    return f"""<!DOCTYPE html>
<html><head><style>
  body {{ margin:0; width:{HALF_WIDTH}px; height:{HALF_HEIGHT}px; overflow:hidden;
          font-family:'Arial', sans-serif; background:#0a0a10; }}
  #stage {{ position:absolute; top:0; left:0; }}
  .title {{ position:absolute; top:50px; left:60px; font-size:48px; font-weight:800;
             color:#fff; max-width:900px; z-index:2; text-shadow: 0 0 20px rgba(0,0,0,0.6); }}
  .counter-label {{ position:absolute; top:0; left:0; width:{HALF_WIDTH}px; height:{HALF_HEIGHT}px;
                      display:flex; align-items:flex-end; justify-content:center;
                      padding-bottom: 90px; font-size:38px; opacity:0.9; z-index:2; color:#fff; }}
</style></head>
<body>
  <div id="stage"></div>
  <div class="title">{scene.title}</div>
  <div class="counter-label">{scene.counter_label if style != "compare" else ""}</div>
  <script src="file:///app/vendor/konva.min.js"></script>
  <script>{SHARED_JS}
    var stage = new Konva.Stage({{ container: 'stage', width: {HALF_WIDTH}, height: {HALF_HEIGHT} }});
    var layer = new Konva.Layer();
    var accent = "{scene.accent_color}";
    buildAnimatedBackground(layer, accent, {HALF_WIDTH}, {HALF_HEIGHT});
{js_body}
  </script>
</body></html>"""


def _build_dynamic_html(scene: SceneEvent, duration: float) -> str:
    bullets_html = "".join(f'<div class="bullet">{b}</div>' for b in scene.bullets[:3])
    duration_ms = int(max(duration, 0.5) * 1000)
    mood = scene.mood if scene.mood in ("illustration", "icons", "typography") else "illustration"
    icons_json = json.dumps(scene.icons[:3] if scene.icons else ["gear"])

    if mood == "icons":
        js_body = f"""
    var iconNames = {icons_json};
    var iconColor = accent;
    var positions = [
      {{ x: {HALF_WIDTH} * 0.72, y: {HALF_HEIGHT} * 0.42 }},
      {{ x: {HALF_WIDTH} * 0.85, y: {HALF_HEIGHT} * 0.68 }},
      {{ x: {HALF_WIDTH} * 0.60, y: {HALF_HEIGHT} * 0.75 }},
    ];
    iconNames.forEach(function(name, i) {{
      var pos = positions[i % positions.length];
      var icon = makeIcon(name, pos.x, pos.y, 90, iconColor);
      icon.opacity(0);
      icon.scale({{ x: 0.4, y: 0.4 }});
      layer.add(icon);
      (function(node, delay) {{
        setTimeout(function() {{
          node.to({{ opacity: 1, scaleX: 1, scaleY: 1, duration: 0.5, easing: Konva.Easings.BackEaseOut }});
          function pulseLoop() {{
            node.to({{
              scaleX: 1.12, scaleY: 1.12, duration: 1.0, easing: Konva.Easings.EaseInOut,
              onFinish: function() {{
                node.to({{ scaleX: 1, scaleY: 1, duration: 1.0, easing: Konva.Easings.EaseInOut, onFinish: pulseLoop }});
              }},
            }});
          }}
          setTimeout(pulseLoop, 500);
        }}, delay);
      }})(icon, 300 + i * 250);
    }});
    stage.add(layer);
"""
    elif mood == "typography":
        js_body = f"""
    var titleText = new Konva.Text({{
      x: 60, y: {HALF_HEIGHT} * 0.38, width: {HALF_WIDTH} - 120,
      text: "{scene.title}", fontSize: 88, fontStyle: "900", fill: "#fff",
      shadowColor: accent, shadowBlur: 30, shadowOpacity: 0.9,
      opacity: 0, scaleX: 0.85, scaleY: 0.85,
    }});
    layer.add(titleText);
    stage.add(layer);
    titleText.to({{
      opacity: 1, scaleX: 1, scaleY: 1, duration: 0.6, easing: Konva.Easings.BackEaseOut,
    }});
    var underline = new Konva.Rect({{
      x: 64, y: {HALF_HEIGHT} * 0.38 + 100, width: 0, height: 8,
      fill: accent, shadowColor: accent, shadowBlur: 15, shadowOpacity: 0.8,
    }});
    layer.add(underline);
    setTimeout(function() {{
      underline.to({{ width: 260, duration: 0.5, easing: Konva.Easings.EaseOut }});
    }}, 400);
"""
    else:  # illustration
        js_body = f"""
    var pulses = [];
    for (var i = 0; i < 3; i++) {{
      var pc = new Konva.Circle({{
        x: 750 + i * 60, y: 750 - i * 100, radius: 8, fill: accent,
        shadowColor: accent, shadowBlur: 30, shadowOpacity: 1,
      }});
      layer.add(pc);
      pulses.push(pc);
      (function(node, delay) {{
        setTimeout(function() {{
          function pulseLoop() {{
            node.to({{
              radius: 26, duration: 0.9, easing: Konva.Easings.EaseInOut,
              onFinish: function() {{
                node.to({{ radius: 8, duration: 0.9, easing: Konva.Easings.EaseInOut, onFinish: pulseLoop }});
              }},
            }});
          }}
          pulseLoop();
        }}, delay);
      }})(pc, i * 300);
    }}
    stage.add(layer);
"""

    title_html = "" if mood == "typography" else f'<div class="title">{scene.title}</div>'

    return f"""<!DOCTYPE html>
<html><head><style>
  body {{ margin:0; width:{HALF_WIDTH}px; height:{HALF_HEIGHT}px; overflow:hidden;
          font-family:'Arial', sans-serif; background:#0a0a10; }}
  #stage {{ position:absolute; top:0; left:0; }}
  .title {{ position:absolute; top:70px; left:60px; font-size:58px; font-weight:800;
             color:#fff; max-width:900px; z-index:2; text-shadow: 0 0 20px rgba(0,0,0,0.6);
             opacity:0; animation: fadeSlide 0.6s ease-out 0.1s forwards; }}
  .bullets {{ position:absolute; top:250px; left:70px; z-index:2; }}
  .bullet {{ font-size:36px; opacity:0; color:#fff; margin-top:16px;
              animation: fadeSlide 0.5s ease-out forwards; text-shadow: 0 0 12px rgba(0,0,0,0.6); }}
  .bullet:nth-child(1) {{ animation-delay: 0.35s; }}
  .bullet:nth-child(2) {{ animation-delay: 0.55s; }}
  .bullet:nth-child(3) {{ animation-delay: 0.75s; }}
  @keyframes fadeSlide {{
    from {{ opacity: 0; transform: translateX(-30px); }}
    to {{ opacity: 1; transform: translateX(0); }}
  }}
</style></head>
<body>
  <div id="stage"></div>
  {title_html}
  <div class="bullets">{bullets_html}</div>
  <script src="file:///app/vendor/konva.min.js"></script>
  <script>{SHARED_JS}
    var stage = new Konva.Stage({{ container: 'stage', width: {HALF_WIDTH}, height: {HALF_HEIGHT} }});
    var layer = new Konva.Layer();
    var accent = "{scene.accent_color}";
    buildAnimatedBackground(layer, accent, {HALF_WIDTH}, {HALF_HEIGHT});
{js_body}
  </script>
</body></html>"""


def _build_legacy_simple_html(scene: SceneEvent) -> str:
    """Renders any old scenes that still have layout_type='simple' saved
    from before this upgrade — kept only for backward compatibility with
    already-generated Timelines."""
    bullets_html = "".join(f'<div class="bullet">{b}</div>' for b in scene.bullets[:3])
    return f"""<!DOCTYPE html>
<html><head><style>
  body {{ margin:0; width:{HALF_WIDTH}px; height:{HALF_HEIGHT}px; background:#0e0e14;
          overflow:hidden; font-family:'Arial', sans-serif; color:#fff; }}
  #stage {{ position:absolute; top:0; left:0; }}
  .title {{ position:absolute; top:60px; left:60px; font-size:56px; font-weight:800; z-index:2; }}
  .bullets {{ position:absolute; top:220px; left:70px; z-index:2; }}
  .bullet {{ font-size:34px; opacity:0.9; margin-top:14px; }}
</style></head>
<body>
  <div id="stage"></div>
  <div class="title">{scene.title}</div>
  <div class="bullets">{bullets_html}</div>
  <script src="file:///app/vendor/konva.min.js"></script>
  <script>
    var stage = new Konva.Stage({{ container: 'stage', width: {HALF_WIDTH}, height: {HALF_HEIGHT} }});
    var layer = new Konva.Layer();
    var c = new Konva.Circle({{ x: 900, y: 780, radius: 90, fill: "{scene.accent_color}", opacity: 0.9 }});
    layer.add(c);
    stage.add(layer);
  </script>
</body></html>"""


def _build_html(scene: SceneEvent, duration: float) -> str:
    if scene.layout_type == "diagram" and scene.elements:
        return _build_diagram_html(scene, duration)
    if scene.layout_type == "counter" and scene.counter_value:
        return _build_counter_html(scene, duration)
    if scene.layout_type == "simple":
        return _build_legacy_simple_html(scene)
    return _build_dynamic_html(scene, duration)


class KonvaSceneEngine:
    name = "konva_scene"

    async def resolve_scene(self, scene: SceneEvent, project_id: str, duration_override: float | None = None) -> str:
        """duration_override, when given, is the ACTUAL final on-screen
        duration this scene will play for in the composited video
        (accounting for gap-closing between scenes) — recording for
        exactly this length means the clip never needs to be looped at
        render time. Looping was the cause of a real bug: every loop
        restart replayed the recording's own brief startup flash (blank
        white page, then black body background, before Konva's first
        paint), which showed up as a jarring flicker partway through a
        scene's display time."""
        settings = get_settings()
        out_dir = Path(settings.assets_dir) / project_id / "konva_scenes" / scene.segment_id
        out_dir.mkdir(parents=True, exist_ok=True)

        duration = duration_override if duration_override and duration_override > 0 else max(scene.end - scene.start, 0.5)
        html_path = out_dir / "scene.html"
        html_path.write_text(_build_html(scene, duration))

        logger.info(
            "Rendering Konva scene for segment=%s (layout_type=%s, %.1fs)",
            scene.segment_id, scene.layout_type, duration,
        )

        async with async_playwright() as p:
            browser = await p.chromium.launch()
            context = await browser.new_context(
                record_video_dir=str(out_dir),
                viewport={"width": HALF_WIDTH, "height": HALF_HEIGHT},
            )
            page = await context.new_page()
            console_errors = []
            page.on("console", lambda msg: console_errors.append(f"[{msg.type}] {msg.text}") if msg.type == "error" else None)
            page.on("pageerror", lambda exc: console_errors.append(f"[pageerror] {exc}"))
            # Record extra time at both ends: the first ~0.4s of any
            # fresh browser recording shows a natural startup sequence
            # (blank tab -> HTML/CSS loads -> Konva paints) that reads as
            # a flash if displayed — instead of fighting that timing, the
            # render step below always skips past START_TRIM_SECONDS of
            # every recording, so the flash is simply never shown.
            await page.goto(f"file://{html_path}")
            await page.wait_for_timeout(int((duration + START_TRIM_SECONDS + 0.4) * 1000))
            if console_errors:
                logger.warning(
                    "Konva scene segment=%s had %d browser console error(s): %s",
                    scene.segment_id, len(console_errors), console_errors[:5],
                )
            await context.close()
            await browser.close()

        video_files = sorted(out_dir.glob("*.webm"), key=lambda p: p.stat().st_mtime)
        if not video_files:
            raise RuntimeError(f"No video recorded for Konva scene segment={scene.segment_id}")
        return str(video_files[-1])
