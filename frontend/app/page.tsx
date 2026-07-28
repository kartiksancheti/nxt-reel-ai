"use client";

import { useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [stylePreset, setStylePreset] = useState("minimal");
  const [projectId, setProjectId] = useState<string | null>(null);
  const [status, setStatus] = useState<string>("");

  async function handleUpload() {
    if (!file) return;
    const formData = new FormData();
    formData.append("file", file);
    formData.append("style_preset", stylePreset);

    const res = await fetch(`${API_URL}/upload`, { method: "POST", body: formData });
    const data = await res.json();
    setProjectId(data.id);
    setStatus(data.status);
  }

  return (
    <main style={{ maxWidth: 480, margin: "80px auto", fontFamily: "sans-serif" }}>
      <h1>NXT Reel AI</h1>
      <p>Upload a talking-head video to generate a viral reel.</p>

      <input type="file" accept="video/*" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />

      <select value={stylePreset} onChange={(e) => setStylePreset(e.target.value)} style={{ display: "block", marginTop: 12 }}>
        <option value="minimal">Minimal</option>
        <option value="alex_hormozi">Alex Hormozi</option>
        <option value="ali_abdaal">Ali Abdaal</option>
        <option value="indian_ai_creator">Indian AI Creator</option>
        <option value="luxury">Luxury</option>
        <option value="podcast">Podcast</option>
      </select>

      <button onClick={handleUpload} style={{ marginTop: 16 }}>
        Upload
      </button>

      {projectId && (
        <p style={{ marginTop: 24 }}>
          Project <code>{projectId}</code> — status: <strong>{status}</strong>
        </p>
      )}
    </main>
  );
}
