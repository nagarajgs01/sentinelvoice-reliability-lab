import { useEffect, useState } from "react";
import type { ModelCatalog } from "./types";
import { STTPanel } from "./STTPanel";
import { TTSPanel } from "./TTSPanel";
import { PipelinePanel } from "./PipelinePanel";

export const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
type Tab = "stt" | "tts" | "pipeline";

export default function App() {
  const [tab, setTab] = useState<Tab>("stt");
  const [catalog, setCatalog] = useState<ModelCatalog>({ stt: [], llm: [], tts: [] });
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${API}/api/models`)
      .then((response) => response.ok ? response.json() : Promise.reject(new Error("Backend unavailable")))
      .then(setCatalog).catch((reason) => setError(String(reason)));
  }, []);

  return <main>
    <header><div><p className="eyebrow">VOICE AI RELIABILITY PLATFORM</p><h1>Sentinel<span>Voice</span> Lab</h1></div>
      <p className="subtitle">Compare speech and language models on identical inputs, measure quality and latency, and reproduce failures.</p></header>
    <nav>{(["stt", "tts", "pipeline"] as Tab[]).map((item) =>
      <button className={tab === item ? "active" : ""} onClick={() => setTab(item)} key={item}>
        {item === "pipeline" ? "Full Pipeline" : `${item.toUpperCase()} Lab`}
      </button>)}</nav>
    {error && <p className="banner">{error}. Start FastAPI on port 8000.</p>}
    {tab === "stt" && <STTPanel models={catalog.stt} />}
    {tab === "tts" && <TTSPanel voices={catalog.tts} sttModels={catalog.stt} />}
    {tab === "pipeline" && <PipelinePanel catalog={catalog} />}
    <footer>Local-first · repeatable datasets · model-level traces · no simulated infrastructure</footer>
  </main>;
}
