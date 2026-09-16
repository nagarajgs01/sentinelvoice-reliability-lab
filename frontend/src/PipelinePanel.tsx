import { useRef, useState } from "react";
import { API } from "./App";
import type { ModelCatalog, PipelineResult } from "./types";

export function PipelinePanel({ catalog }: { catalog: ModelCatalog }) {
  const [audio, setAudio] = useState<Blob | null>(null);
  const [expected, setExpected] = useState("Explain why reliable voice agents need interruption handling.");
  const [stt, setStt] = useState("tiny.en"); const [llm, setLlm] = useState("llama3.2:latest"); const [tts, setTts] = useState("af_heart");
  const [result, setResult] = useState<PipelineResult | null>(null); const [status, setStatus] = useState("Record one end-to-end request."); const [running, setRunning] = useState(false);
  const recorder = useRef<MediaRecorder | null>(null); const chunks = useRef<Blob[]>([]);
  async function record() {
    if (recorder.current?.state === "recording") { recorder.current.stop(); return; }
    try { const stream = await navigator.mediaDevices.getUserMedia({ audio: true }); chunks.current = []; const type = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "audio/mp4"; const next = new MediaRecorder(stream, { mimeType: type }); recorder.current = next; next.ondataavailable = (event) => { if (event.data.size) chunks.current.push(event.data); }; next.onstop = () => { setAudio(new Blob(chunks.current, { type })); stream.getTracks().forEach((track) => track.stop()); setStatus("Voice request ready."); }; next.start(); setStatus("Recording—click again to stop."); } catch (reason) { setStatus(reason instanceof Error ? reason.message : "Microphone failed"); }
  }
  async function run() {
    if (!audio) return; setRunning(true); setResult(null); setStatus("Running STT → LLM → TTS…");
    try { const query = new URLSearchParams({ stt_model: stt, llm_model: llm, tts_voice: tts, expected_transcript: expected }); const response = await fetch(`${API}/api/benchmarks/pipeline?${query}`, { method: "POST", headers: { "Content-Type": audio.type, "X-Trace-ID": crypto.randomUUID() }, body: audio }); const data = await response.json(); if (!response.ok) throw new Error(data.detail); setResult(data); setStatus("Full pipeline completed."); } catch (reason) { setStatus(reason instanceof Error ? reason.message : "Pipeline failed"); } finally { setRunning(false); }
  }
  return <><section className="grid"><article className="panel"><div className="heading"><h2>1. Voice request</h2><span>{audio ? "READY" : "REQUIRED"}</span></div><label>Correct transcript</label><textarea value={expected} onChange={(event) => setExpected(event.target.value)} /><button onClick={record}>{recorder.current?.state === "recording" ? "Stop recording" : "Record request"}</button></article>
    <article className="panel"><div className="heading"><h2>2. Pipeline configuration</h2><span>LOCAL</span></div><label>STT</label><select value={stt} onChange={(event) => setStt(event.target.value)}>{catalog.stt.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select><label>LLM</label><select value={llm} onChange={(event) => setLlm(event.target.value)}>{catalog.llm.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select><label>TTS</label><select value={tts} onChange={(event) => setTts(event.target.value)}>{catalog.tts.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select><button className="run" disabled={!audio || running} onClick={run}>{running ? "Running…" : "Run full pipeline"}</button><p className="status">{status}</p></article></section>
    <section className="panel results"><div className="heading"><h2>End-to-end trace</h2><span>{result ? `${result.total_ms.toFixed(0)} MS` : "NO RUN"}</span></div>{!result ? <p className="empty">One run measures every component and returns spoken audio.</p> : <><div className="scores wide"><b>{result.stt_accuracy_percent}%<small>STT accuracy</small></b><b>{result.stt_ms.toFixed(0)} ms<small>STT</small></b><b>{result.llm_ms.toFixed(0)} ms<small>LLM</small></b><b>{result.tts_ms.toFixed(0)} ms<small>TTS</small></b><b>{result.total_ms.toFixed(0)} ms<small>end-to-end</small></b></div><div className="transcript"><p><strong>You:</strong> {result.transcript}</p><p><strong>Agent:</strong> {result.response}</p></div><audio controls src={`data:audio/wav;base64,${result.audio_base64}`} /></>}</section></>;
}
