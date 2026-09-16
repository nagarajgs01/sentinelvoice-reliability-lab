import { ChangeEvent, useMemo, useRef, useState } from "react";
import { API } from "./App";
import type { BenchmarkResult, ModelInfo, ModelSummary, VoiceSample } from "./types";

export function STTPanel({ models }: { models: ModelInfo[] }) {
  const [selected, setSelected] = useState<string[]>(["tiny.en"]);
  const [expected, setExpected] = useState("Please cancel my order number thirteen.");
  const [samples, setSamples] = useState<VoiceSample[]>([]);
  const [recording, setRecording] = useState(false);
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState<BenchmarkResult[]>([]);
  const [status, setStatus] = useState("Add at least one labeled voice sample.");
  const recorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);

  function addSample(audio: Blob, name: string) {
    if (!expected.trim()) return setStatus("Enter the correct transcript first.");
    setSamples((items) => [...items, { id: crypto.randomUUID(), name, expected: expected.trim(), audio }]);
    setResults([]); setStatus("Sample added.");
  }
  async function startRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      chunks.current = [];
      const type = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "audio/mp4";
      const next = new MediaRecorder(stream, { mimeType: type }); recorder.current = next;
      next.ondataavailable = (event) => { if (event.data.size) chunks.current.push(event.data); };
      next.onstop = () => { const blob = new Blob(chunks.current, { type }); stream.getTracks().forEach((track) => track.stop()); addSample(blob, `Recording ${samples.length + 1}`); };
      next.start(); setRecording(true); setStatus("Recording…");
    } catch (reason) { setStatus(reason instanceof Error ? reason.message : "Microphone failed"); }
  }
  function upload(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []); if (!expected.trim()) return;
    setSamples((items) => [...items, ...files.map((file) => ({ id: crypto.randomUUID(), name: file.name, expected: expected.trim(), audio: file }))]);
    setResults([]); event.target.value = "";
  }
  async function run() {
    setRunning(true); setResults([]); const output: BenchmarkResult[] = [];
    for (const model of selected) for (const sample of samples) {
      setStatus(`Running ${output.length + 1}/${selected.length * samples.length}: ${model}`);
      try {
        const query = new URLSearchParams({ model, expected_text: sample.expected });
        const response = await fetch(`${API}/api/benchmarks/stt?${query}`, { method: "POST", headers: { "Content-Type": sample.audio.type || "audio/webm", "X-Trace-ID": crypto.randomUUID() }, body: sample.audio });
        const data = await response.json(); if (!response.ok) throw new Error(data.detail);
        output.push({ ...data, sampleId: sample.id, sampleName: sample.name });
      } catch (reason) { output.push({ model, sampleId: sample.id, sampleName: sample.name, error: reason instanceof Error ? reason.message : "Failed" } as BenchmarkResult); }
      setResults([...output]);
    }
    setRunning(false); setStatus("Batch completed.");
  }
  const ranking = useMemo<ModelSummary[]>(() => selected.map((model) => {
    const runs = results.filter((result) => result.model === model && !result.error);
    const avg = (key: "accuracy_percent" | "word_error_rate" | "latency_ms") => runs.length ? runs.reduce((sum, item) => sum + item[key], 0) / runs.length : 0;
    return { model, samples: runs.length, passRate: runs.length ? runs.filter((item) => item.passed).length / runs.length * 100 : 0, averageAccuracy: avg("accuracy_percent"), averageWer: avg("word_error_rate"), averageLatency: avg("latency_ms") };
  }).filter((item) => item.samples).sort((a, b) => b.averageAccuracy - a.averageAccuracy || a.averageLatency - b.averageLatency), [results, selected]);

  return <><section className="grid"><article className="panel"><div className="heading"><h2>1. Labeled dataset</h2><span>{samples.length} SAMPLES</span></div>
    <label>Correct transcript for next sample</label><textarea value={expected} onChange={(event) => setExpected(event.target.value)} />
    <div className="controls"><button className={recording ? "danger" : ""} onClick={() => recording ? (recorder.current?.stop(), setRecording(false)) : startRecording()}>{recording ? "Stop recording" : "Record sample"}</button><label className="upload">Upload audio<input type="file" multiple accept="audio/*" onChange={upload} /></label></div>
    <div className="samples">{samples.map((sample, index) => <article key={sample.id}><span>{index + 1}</span><div><strong>{sample.name}</strong><small>{sample.expected}</small></div><button onClick={() => { setSamples((items) => items.filter((item) => item.id !== sample.id)); setResults([]); }}>Remove</button></article>)}</div></article>
    <article className="panel"><div className="heading"><h2>2. STT candidates</h2><span>{selected.length} SELECTED</span></div><div className="models">{models.map((model) => <label className={selected.includes(model.id) ? "model selected" : "model"} key={model.id}><input type="checkbox" checked={selected.includes(model.id)} onChange={() => setSelected((items) => items.includes(model.id) ? items.filter((id) => id !== model.id) : [...items, model.id])} /><span><strong>{model.name}</strong><small>{model.provider} · {model.size}</small></span></label>)}</div>
    <button className="run" disabled={!samples.length || !selected.length || running} onClick={run}>{running ? "Running…" : `Run ${samples.length * selected.length} comparisons`}</button><p className="status">{status}</p></article></section>
    <section className="panel results"><div className="heading"><h2>STT ranking</h2><span>{results.length} RUNS</span></div>{!ranking.length ? <p className="empty">Rankings appear after a batch.</p> : <div className="ranking">{ranking.map((item, index) => <article className={index === 0 ? "winner" : ""} key={item.model}><div><strong>#{index + 1} {item.model}</strong>{index === 0 && <span>BEST</span>}</div><div className="scores"><b>{item.averageAccuracy.toFixed(1)}%<small>accuracy</small></b><b>{item.averageWer.toFixed(2)}<small>WER</small></b><b>{item.averageLatency.toFixed(0)} ms<small>latency</small></b><b>{item.passRate.toFixed(0)}%<small>pass</small></b></div></article>)}</div>}</section></>;
}
