"use client";

import { useEffect, useRef, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const STYLE_PRESETS = [
  { value: "minimal", label: "Minimal" },
  { value: "alex_hormozi", label: "Alex Hormozi" },
  { value: "ali_abdaal", label: "Ali Abdaal" },
  { value: "indian_ai_creator", label: "Indian AI Creator" },
  { value: "luxury", label: "Luxury" },
  { value: "podcast", label: "Podcast" },
];

const FONTS = [
  "Liberation-Sans",
  "Liberation-Sans-Bold",
  "Liberation-Serif-Bold",
];

const POSITIONS = ["top", "center", "bottom"];
const ANIMATIONS = [
  { value: "word_pop", label: "Word Pop" },
  { value: "karaoke", label: "Karaoke" },
  { value: "typewriter", label: "Typewriter" },
];

const PRESET_DEFAULTS: Record<
  string,
  { font: string; color: string; highlight_color: string; position: string; animation: string }
> = {
  alex_hormozi: { font: "Liberation-Sans-Bold", color: "#FFFFFF", highlight_color: "#F7C204", position: "bottom", animation: "word_pop" },
  ali_abdaal: { font: "Liberation-Sans-Bold", color: "#FFFFFF", highlight_color: "#4EA8FF", position: "bottom", animation: "karaoke" },
  indian_ai_creator: { font: "Liberation-Sans-Bold", color: "#FFFFFF", highlight_color: "#FF8A00", position: "center", animation: "word_pop" },
  luxury: { font: "Liberation-Serif-Bold", color: "#F5F0E6", highlight_color: "#D4AF37", position: "bottom", animation: "typewriter" },
  minimal: { font: "Liberation-Sans", color: "#FFFFFF", highlight_color: "#FFFFFF", position: "bottom", animation: "karaoke" },
  podcast: { font: "Liberation-Sans-Bold", color: "#FFFFFF", highlight_color: "#7CFF6B", position: "bottom", animation: "karaoke" },
};

const FONT_CSS_MAP: Record<string, string> = {
  "Liberation-Sans": "Arial, sans-serif",
  "Liberation-Sans-Bold": "Arial, sans-serif",
  "Liberation-Serif-Bold": "Georgia, serif",
};

interface Project {
  id: string;
  style_preset: string;
  status: string;
  created_at: string;
  updated_at: string;
  rendered_video_path: string | null;
  exported_video_path: string | null;
  error_message: string | null;
}

const PREVIEW_WORDS = ["This", "is", "how", "your", "captions", "will", "look"];

function CaptionPreview({
  font,
  color,
  highlightColor,
  position,
  animation,
}: {
  font: string;
  color: string;
  highlightColor: string;
  position: string;
  animation: string;
}) {
  const [activeWord, setActiveWord] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setActiveWord((w) => (w + 1) % PREVIEW_WORDS.length);
    }, 500);
    return () => clearInterval(interval);
  }, []);

  const justify =
    position === "top" ? "flex-start" : position === "bottom" ? "flex-end" : "center";

  return (
    <div
      style={{
        width: "100%",
        aspectRatio: "9 / 16",
        maxWidth: 220,
        background: "linear-gradient(160deg, #2a2a35, #14141a)",
        borderRadius: 12,
        display: "flex",
        flexDirection: "column",
        justifyContent: justify,
        alignItems: "center",
        padding: "16px 10px",
        overflow: "hidden",
        border: "1px solid #333",
      }}
    >
      {animation === "karaoke" ? (
        <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "center", gap: 4 }}>
          {PREVIEW_WORDS.map((w, i) => (
            <span
              key={i}
              style={{
                fontFamily: FONT_CSS_MAP[font] || "Arial, sans-serif",
                fontWeight: font.includes("Bold") ? 700 : 400,
                fontSize: 15,
                color: i <= activeWord ? highlightColor : color,
                opacity: i <= activeWord ? 1 : 0.5,
                transition: "opacity 0.2s, color 0.2s",
              }}
            >
              {w}
            </span>
          ))}
        </div>
      ) : animation === "typewriter" ? (
        <div
          style={{
            fontFamily: FONT_CSS_MAP[font] || "Arial, sans-serif",
            fontWeight: font.includes("Bold") ? 700 : 400,
            fontSize: 15,
            color,
            textAlign: "center",
          }}
        >
          {PREVIEW_WORDS.slice(0, activeWord + 1).join(" ")}
          <span style={{ opacity: 0.6 }}>|</span>
        </div>
      ) : (
        <div
          key={activeWord}
          style={{
            fontFamily: FONT_CSS_MAP[font] || "Arial, sans-serif",
            fontWeight: font.includes("Bold") ? 700 : 400,
            fontSize: 22,
            color: highlightColor,
            textAlign: "center",
            animation: "popIn 0.3s ease-out",
          }}
        >
          {PREVIEW_WORDS[activeWord]}
        </div>
      )}
      <style>{`
        @keyframes popIn {
          0% {
            transform: scale(0.6);
            opacity: 0;
          }
          60% {
            transform: scale(1.15);
            opacity: 1;
          }
          100% {
            transform: scale(1);
          }
        }
      `}</style>
    </div>
  );
}

const STATUS_COLORS: Record<string, string> = {
  uploaded: "#888",
  transcribing: "#e0a600",
  transcribed: "#888",
  generating_timeline: "#e0a600",
  timeline_ready: "#888",
  rendering: "#e0a600",
  rendered: "#3aa76d",
  exported: "#2d8fd6",
  failed: "#d64545",
};

const NEXT_ACTION: Record<string, { label: string; endpoint: (id: string) => string } | null> = {
  uploaded: { label: "Transcribe", endpoint: (id) => `/transcribe/${id}` },
  transcribed: { label: "Generate Timeline", endpoint: (id) => `/generate-timeline/${id}` },
  timeline_ready: { label: "Render", endpoint: (id) => `/render/${id}` },
  rendered: { label: "Export", endpoint: (id) => `/export/${id}` },
  transcribing: null,
  generating_timeline: null,
  rendering: null,
  exported: null,
  failed: null,
};

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [stylePreset, setStylePreset] = useState("minimal");
  const [useCustom, setUseCustom] = useState(false);
  const [font, setFont] = useState(PRESET_DEFAULTS.minimal.font);
  const [color, setColor] = useState(PRESET_DEFAULTS.minimal.color);
  const [highlightColor, setHighlightColor] = useState(PRESET_DEFAULTS.minimal.highlight_color);
  const [position, setPosition] = useState(PRESET_DEFAULTS.minimal.position);
  const [animation, setAnimation] = useState(PRESET_DEFAULTS.minimal.animation);

  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  function handlePresetChange(preset: string) {
    setStylePreset(preset);
    if (!useCustom) {
      const d = PRESET_DEFAULTS[preset] || PRESET_DEFAULTS.minimal;
      setFont(d.font);
      setColor(d.color);
      setHighlightColor(d.highlight_color);
      setPosition(d.position);
      setAnimation(d.animation);
    }
  }

  function toggleCustom(checked: boolean) {
    setUseCustom(checked);
    if (!checked) {
      const d = PRESET_DEFAULTS[stylePreset] || PRESET_DEFAULTS.minimal;
      setFont(d.font);
      setColor(d.color);
      setHighlightColor(d.highlight_color);
      setPosition(d.position);
      setAnimation(d.animation);
    }
  }

  async function fetchProjects() {
    try {
      const res = await fetch(`${API_URL}/projects`);
      if (!res.ok) return;
      const data = await res.json();
      setProjects(data);
    } catch {
      // network hiccup — next poll will retry
    }
  }

  useEffect(() => {
    fetchProjects();
    pollRef.current = setInterval(fetchProjects, 4000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  async function handleUpload() {
    if (!file) return;
    setUploading(true);
    setUploadError(null);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("style_preset", stylePreset);
    if (useCustom) {
      formData.append("caption_font", font);
      formData.append("caption_color", color);
      formData.append("caption_highlight_color", highlightColor);
      formData.append("caption_position", position);
      formData.append("caption_animation", animation);
    }

    try {
      const res = await fetch(`${API_URL}/upload`, { method: "POST", body: formData });
      const data = await res.json();
      if (!res.ok) {
        setUploadError(data.detail || "Upload failed — please retry.");
      } else {
        setFile(null);
        fetchProjects();
      }
    } catch {
      setUploadError("Upload failed — network error. Please retry.");
    } finally {
      setUploading(false);
    }
  }

  async function runAction(project: Project) {
    const action = NEXT_ACTION[project.status];
    if (!action) return;
    setActionLoading(project.id);
    try {
      await fetch(`${API_URL}${action.endpoint(project.id)}`, { method: "POST" });
      await fetchProjects();
    } finally {
      setActionLoading(null);
    }
  }

  function statusLabel(status: string) {
    return status.replace(/_/g, " ");
  }

  return (
    <main
      style={{
        maxWidth: 1000,
        margin: "40px auto",
        fontFamily: "system-ui, -apple-system, sans-serif",
        padding: "0 20px",
        color: "#1a1a1a",
      }}
    >
      <h1 style={{ fontSize: 32, marginBottom: 4 }}>NXT Reel AI</h1>
      <p style={{ color: "#666", marginBottom: 32 }}>
        Upload a talking-head video and let the AI Creative Director turn it into a viral reel.
      </p>

      <div style={{ display: "flex", gap: 32, flexWrap: "wrap", marginBottom: 48 }}>
        <div style={{ flex: "1 1 380px" }}>
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: "block", fontWeight: 600, marginBottom: 6 }}>Video file</label>
            <input
              type="file"
              accept="video/*"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              style={{ display: "block" }}
            />
          </div>

          <div style={{ marginBottom: 16 }}>
            <label style={{ display: "block", fontWeight: 600, marginBottom: 6 }}>Style preset</label>
            <select
              value={stylePreset}
              onChange={(e) => handlePresetChange(e.target.value)}
              style={{ padding: "8px 12px", borderRadius: 6, border: "1px solid #ccc", width: "100%" }}
            >
              {STYLE_PRESETS.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </select>
          </div>

          <div style={{ marginBottom: 16 }}>
            <label style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 600 }}>
              <input
                type="checkbox"
                checked={useCustom}
                onChange={(e) => toggleCustom(e.target.checked)}
              />
              Customize caption style
            </label>
          </div>

          {useCustom && (
            <div
              style={{
                background: "#f7f7f8",
                borderRadius: 8,
                padding: 16,
                marginBottom: 16,
                display: "flex",
                flexDirection: "column",
                gap: 12,
              }}
            >
              <div>
                <label style={{ display: "block", fontSize: 13, fontWeight: 600, marginBottom: 4 }}>
                  Font
                </label>
                <select
                  value={font}
                  onChange={(e) => setFont(e.target.value)}
                  style={{ padding: "6px 10px", borderRadius: 6, border: "1px solid #ccc", width: "100%" }}
                >
                  {FONTS.map((f) => (
                    <option key={f} value={f}>
                      {f}
                    </option>
                  ))}
                </select>
              </div>

              <div style={{ display: "flex", gap: 12 }}>
                <div style={{ flex: 1 }}>
                  <label style={{ display: "block", fontSize: 13, fontWeight: 600, marginBottom: 4 }}>
                    Text color
                  </label>
                  <input
                    type="color"
                    value={color}
                    onChange={(e) => setColor(e.target.value)}
                    style={{ width: "100%", height: 36 }}
                  />
                </div>
                <div style={{ flex: 1 }}>
                  <label style={{ display: "block", fontSize: 13, fontWeight: 600, marginBottom: 4 }}>
                    Highlight color
                  </label>
                  <input
                    type="color"
                    value={highlightColor}
                    onChange={(e) => setHighlightColor(e.target.value)}
                    style={{ width: "100%", height: 36 }}
                  />
                </div>
              </div>

              <div>
                <label style={{ display: "block", fontSize: 13, fontWeight: 600, marginBottom: 4 }}>
                  Position
                </label>
                <div style={{ display: "flex", gap: 8 }}>
                  {POSITIONS.map((p) => (
                    <button
                      key={p}
                      onClick={() => setPosition(p)}
                      style={{
                        flex: 1,
                        padding: "6px 0",
                        borderRadius: 6,
                        border: position === p ? "2px solid #333" : "1px solid #ccc",
                        background: position === p ? "#333" : "#fff",
                        color: position === p ? "#fff" : "#333",
                        cursor: "pointer",
                        textTransform: "capitalize",
                      }}
                    >
                      {p}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label style={{ display: "block", fontSize: 13, fontWeight: 600, marginBottom: 4 }}>
                  Animation
                </label>
                <select
                  value={animation}
                  onChange={(e) => setAnimation(e.target.value)}
                  style={{ padding: "6px 10px", borderRadius: 6, border: "1px solid #ccc", width: "100%" }}
                >
                  {ANIMATIONS.map((a) => (
                    <option key={a.value} value={a.value}>
                      {a.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          )}

          <button
            onClick={handleUpload}
            disabled={!file || uploading}
            style={{
              padding: "10px 20px",
              borderRadius: 6,
              border: "none",
              background: !file || uploading ? "#aaa" : "#1a1a1a",
              color: "#fff",
              cursor: !file || uploading ? "not-allowed" : "pointer",
              fontWeight: 600,
            }}
          >
            {uploading ? "Uploading…" : "Upload & Create Project"}
          </button>

          {uploadError && (
            <p style={{ color: "#d64545", marginTop: 10, fontSize: 14 }}>{uploadError}</p>
          )}
        </div>

        <div style={{ flex: "0 0 240px" }}>
          <label style={{ display: "block", fontWeight: 600, marginBottom: 6 }}>
            Live caption preview
          </label>
          <CaptionPreview
            font={font}
            color={color}
            highlightColor={highlightColor}
            position={position}
            animation={animation}
          />
        </div>
      </div>

      <h2 style={{ fontSize: 22, marginBottom: 12 }}>Your Projects</h2>
      {projects.length === 0 ? (
        <p style={{ color: "#888" }}>No projects yet — upload a video to get started.</p>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
            <thead>
              <tr style={{ textAlign: "left", borderBottom: "2px solid #eee" }}>
                <th style={{ padding: "8px 6px" }}>Project</th>
                <th style={{ padding: "8px 6px" }}>Style</th>
                <th style={{ padding: "8px 6px" }}>Status</th>
                <th style={{ padding: "8px 6px" }}>Created</th>
                <th style={{ padding: "8px 6px" }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {projects.map((p) => {
                const action = NEXT_ACTION[p.status];
                return (
                  <tr key={p.id} style={{ borderBottom: "1px solid #f0f0f0" }}>
                    <td style={{ padding: "8px 6px", fontFamily: "monospace", fontSize: 12 }}>
                      {p.id.slice(0, 8)}
                    </td>
                    <td style={{ padding: "8px 6px" }}>{p.style_preset}</td>
                    <td style={{ padding: "8px 6px" }}>
                      <span
                        style={{
                          display: "inline-block",
                          padding: "2px 10px",
                          borderRadius: 12,
                          background: STATUS_COLORS[p.status] || "#888",
                          color: "#fff",
                          fontSize: 12,
                          textTransform: "capitalize",
                        }}
                      >
                        {statusLabel(p.status)}
                      </span>
                      {p.error_message && (
                        <div style={{ color: "#d64545", fontSize: 11, marginTop: 4, maxWidth: 240 }}>
                          {p.error_message.slice(0, 80)}
                        </div>
                      )}
                    </td>
                    <td style={{ padding: "8px 6px", color: "#888" }}>
                      {new Date(p.created_at).toLocaleString()}
                    </td>
                    <td style={{ padding: "8px 6px" }}>
                      {p.status === "exported" || p.status === "rendered" ? (
                        <a
                          href={`${API_URL}/download/${p.id}`}
                          style={{
                            padding: "5px 12px",
                            borderRadius: 6,
                            background: "#2d8fd6",
                            color: "#fff",
                            textDecoration: "none",
                            fontSize: 13,
                          }}
                        >
                          Download
                        </a>
                      ) : action ? (
                        <button
                          onClick={() => runAction(p)}
                          disabled={actionLoading === p.id}
                          style={{
                            padding: "5px 12px",
                            borderRadius: 6,
                            border: "1px solid #333",
                            background: "#fff",
                            cursor: actionLoading === p.id ? "wait" : "pointer",
                            fontSize: 13,
                          }}
                        >
                          {actionLoading === p.id ? "…" : action.label}
                        </button>
                      ) : (
                        <span style={{ color: "#aaa", fontSize: 13 }}>in progress…</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
