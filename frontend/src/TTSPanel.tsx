import { useMemo, useRef, useState } from "react";
import { API } from "./App";
import type { ModelInfo, TTSResult } from "./types";

export function TTSPanel({ voices, sttModels }: { voices: ModelInfo[]; sttModels: ModelInfo[] }) {
  const [text, setText] = useState("Your appointment is confirmed for Thursday at three thirty PM.");
  const [selected, setSelected] = useState<string[]>(["af_heart"]);
  const [judge, setJudge] = useState("tiny.en");
  const [results, setResults] = useState<TTSResult[]>([]);
  const [running, setRunning] = useState(false);
  const [status, setStatus] = useState("Select voices and generate the same text.");
  const [interruptMs, setInterruptMs] = useState<number | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  async function run() {
    setRunning(true); setResults([]); const output: TTSResult[] = [];
    for (const voice of selected) {
      setStatus(`Generating and checking ${voice}…`);
      try {
        const response = await fetch(`${API}/api/benchmarks/tts`, { method: "POST", headers: { "Content-Type": "application/json", "X-Trace-ID": crypto.randomUUID() }, body: JSON.stringify({ text, voice, stt_model: judge }) });
        const data = await response.json(); if (!response.ok) throw new Error(data.detail);
        output.push(data);
      } catch (reason) { output.push({ voice, error: reason instanceof Error ? reason.message : "Failed" } as TTSResult); }
      setResults([...output]);
    }
    setRunning(false); setStatus("TTS comparison completed.");
  }
  const ranking = useMemo(() => [...results].filter((item) => !item.error).sort((a, b) => b.intelligibility_percent - a.intelligibility_percent || a.generation_ms - b.generation_ms), [results]);
  function play(result: TTSResult) {
    audioRef.current?.pause(); setInterruptMs(null);
    const audio = new Audio(`data:audio/wav;base64,${result.audio_base64}`); audioRef.current = audio;
    audio.play(); setStatus("Speaking—click Interrupt now while audio is playing.");
  }
  function interrupt() {
    if (!audioRef.current || audioRef.current.paused) return;
    const started = performance.now(); audioRef.current.pause(); audioRef.current.currentTime = 0;
    const elapsed = performance.now() - started; setInterruptMs(elapsed); setStatus(`Playback cancelled in ${elapsed.toFixed(2)} ms.`);
  }
  return <><section className="grid"><article className="panel"><div className="heading"><h2>1. TTS test text</h2><span>REFERENCE</span></div><label>Text every voice must speak</label><textarea value={text} onChange={(event) => setText(event.target.value)} /><label>Round-trip STT judge</label><select value={judge} onChange={(event) => setJudge(event.target.value)}>{sttModels.map((model) => <option value={model.id} key={model.id}>{model.name}</option>)}</select></article>
    <article className="panel"><div className="heading"><h2>2. TTS candidates</h2><span>{selected.length} SELECTED</span></div><div className="models">{voices.map((voice) => <label className={selected.includes(voice.id) ? "model selected" : "model"} key={voice.id}><input type="checkbox" checked={selected.includes(voice.id)} onChange={() => setSelected((items) => items.includes(voice.id) ? items.filter((id) => id !== voice.id) : [...items, voice.id])} /><span><strong>{voice.name}</strong><small>{voice.provider} · {voice.language}</small></span></label>)}</div><button className="run" disabled={!text.trim() || !selected.length || running} onClick={run}>{running ? "Testing…" : `Compare ${selected.length} voices`}</button><p className="status">{status}</p></article></section>
    <section className="panel results"><div className="heading"><h2>TTS ranking and interruption</h2><span>{results.length} RUNS</span></div>{!ranking.length ? <p className="empty">Results include intelligibility, generation latency and real-time factor.</p> : <div className="result-list">{ranking.map((result, index) => <article className={index === 0 ? "winner" : ""} key={result.voice}><div><strong>#{index + 1} {result.voice}</strong>{index === 0 && <span>BEST</span>}</div><div className="scores"><b>{result.intelligibility_percent}%<small>intelligibility</small></b><b>{result.generation_ms.toFixed(0)} ms<small>generation</small></b><b>{result.real_time_factor.toFixed(2)}<small>RTF</small></b></div><p>Round trip: “{result.round_trip_transcript}”</p><button onClick={() => play(result)}>Play test</button></article>)}</div>}
      {ranking.length > 0 && <div className="interrupt"><button className="danger" onClick={interrupt}>Interrupt now</button><span>{interruptMs === null ? "Play a result, then interrupt it." : `Playback stop latency: ${interruptMs.toFixed(2)} ms`}</span></div>}</section></>;
}
