import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import type { ClusterState, Evidence, EvaluationReport, GPUNode, PreparedAction, RemediationOption, TraceRecord } from "./types";

const API = "http://localhost:8000";

function Metric({ label, value, warning = false }: { label: string; value: string; warning?: boolean }) {
  return (
    <article className={`metric ${warning ? "warning" : ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function NodeCard({ node }: { node: GPUNode }) {
  return (
    <article className={`node ${node.status}`}>
      <div className="node-title">
        <strong>{node.id}</strong>
        <span>{node.status}</span>
      </div>
      <div className="node-stats">
        <span>{node.temperature_c}°C</span>
        <span>{node.utilization_percent}% GPU</span>
        <span>{node.active_workloads} jobs</span>
      </div>
    </article>
  );
}

export default function App() {
  const [cluster, setCluster] = useState<ClusterState | null>(null);
  const [command, setCommand] = useState("Why is inference latency high?");
  const [agentText, setAgentText] = useState("Monitoring the inference cluster.");
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [recommendations, setRecommendations] = useState<RemediationOption[]>([]);
  const [preparedAction, setPreparedAction] = useState<PreparedAction | null>(null);
  const [busy, setBusy] = useState(false);
  const [recording, setRecording] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [voiceStatus, setVoiceStatus] = useState("Click Record and speak naturally.");
  const [activeTraceId, setActiveTraceId] = useState<string | null>(null);
  const [trace, setTrace] = useState<TraceRecord | null>(null);
  const [evaluation, setEvaluation] = useState<EvaluationReport | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const speechRequestRef = useRef(0);
  const audioTraceRef = useRef<string | null>(null);
  const playbackStartedRef = useRef(0);

  async function refreshTrace(traceId: string) {
    const [traceResponse, evaluationResponse] = await Promise.all([
      fetch(`${API}/api/traces/${traceId}`),
      fetch(`${API}/api/traces/${traceId}/evaluation`),
    ]);
    if (traceResponse.ok) setTrace(await traceResponse.json());
    if (evaluationResponse.ok) setEvaluation(await evaluationResponse.json());
  }

  async function recordClientEvent(
    traceId: string,
    name: string,
    durationMs?: number,
    metadata: Record<string, unknown> = {},
  ) {
    await fetch(`${API}/api/traces/${traceId}/events`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ component: "playback", name, duration_ms: durationMs, metadata }),
    });
    await refreshTrace(traceId);
  }

  function stopSpeaking() {
    speechRequestRef.current += 1;
    if (audioRef.current) {
      const traceId = audioTraceRef.current;
      const durationMs = playbackStartedRef.current
        ? performance.now() - playbackStartedRef.current
        : undefined;
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
      audioRef.current = null;
      audioTraceRef.current = null;
      if (traceId) void recordClientEvent(traceId, "playback_interrupted", durationMs);
    }
    setSpeaking(false);
  }

  async function speak(text: string, traceId = activeTraceId ?? crypto.randomUUID()) {
    stopSpeaking();
    const requestId = speechRequestRef.current;
    setSpeaking(true);
    setVoiceStatus("Kokoro is generating speech…");
    try {
      const response = await fetch(`${API}/api/voice/speak`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Trace-ID": traceId },
        body: JSON.stringify({ text }),
      });
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail ?? `Speech generation failed (${response.status})`);
      }
      const blob = await response.blob();
      if (requestId !== speechRequestRef.current) return;
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audioRef.current = audio;
      audioTraceRef.current = traceId;
      audio.onended = () => {
        const durationMs = performance.now() - playbackStartedRef.current;
        URL.revokeObjectURL(url);
        audioRef.current = null;
        audioTraceRef.current = null;
        setSpeaking(false);
        setVoiceStatus("Kokoro response completed.");
        void recordClientEvent(traceId, "playback_completed", durationMs);
      };
      audio.onerror = () => {
        URL.revokeObjectURL(url);
        audioRef.current = null;
        setSpeaking(false);
        setVoiceStatus("Audio playback failed.");
      };
      await audio.play();
      playbackStartedRef.current = performance.now();
      void recordClientEvent(traceId, "playback_started", undefined, { characters: text.length });
    } catch (error) {
      if (requestId === speechRequestRef.current) {
        setSpeaking(false);
        setVoiceStatus(error instanceof Error ? error.message : "Speech generation failed");
      }
    }
  }

  async function refresh() {
    const response = await fetch(`${API}/api/cluster`);
    setCluster(await response.json());
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function inject(scenario: string) {
    setBusy(true);
    const response = await fetch(`${API}/api/scenarios/${scenario}`, { method: "POST" });
    setCluster(await response.json());
    setAgentText(scenario === "reset" ? "Cluster returned to its healthy baseline." : "Anomaly detected. Ask me to investigate.");
    setEvidence([]);
    setRecommendations([]);
    setPreparedAction(null);
    setBusy(false);
  }

  async function ask(event: FormEvent) {
    event.preventDefault();
    if (!command.trim()) return;
    if (preparedAction) {
      const normalized = command.toLowerCase().trim().replace(/[.!?]+$/, "");
      if (normalized === "cancel action" || normalized === "cancel") {
        await cancelAction();
      } else {
        await voiceConfirmAction(command);
      }
      return;
    }
    setBusy(true);
    const traceId = activeTraceId ?? crypto.randomUUID();
    setActiveTraceId(traceId);
    const response = await fetch(`${API}/api/agent/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Trace-ID": traceId },
      body: JSON.stringify({ text: command }),
    });
    const data = await response.json();
    if (!response.ok) {
      setAgentText(data.detail ?? `Investigation failed (${response.status}).`);
      setBusy(false);
      return;
    }
    setAgentText(data.decision.spoken_response);
    setEvidence(data.evidence);
    setRecommendations(data.recommendations ?? []);
    setPreparedAction(null);
    setActiveTraceId(data.trace_id);
    await refreshTrace(data.trace_id);
    void speak(data.decision.spoken_response, data.trace_id);
    setBusy(false);
  }

  async function prepareAction(actionId: string) {
    setBusy(true);
    const response = await fetch(`${API}/api/remediation/prepare`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action_id: actionId }),
    });
    const data = await response.json();
    if (response.ok) {
      setPreparedAction(data);
      const message = `Action prepared. Say ${data.confirmation_phrase} within two minutes.`;
      setAgentText(message);
      setVoiceStatus(`Record and say exactly: “${data.confirmation_phrase}” — or say “cancel action.”`);
      void speak(message);
    } else {
      setAgentText(data.detail ?? "The action could not be prepared.");
    }
    setBusy(false);
  }

  async function confirmAction() {
    if (!preparedAction) return;
    setBusy(true);
    const response = await fetch(`${API}/api/remediation/confirm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action_id: preparedAction.action_id,
        confirmation_token: preparedAction.confirmation_token,
      }),
    });
    const data = await response.json();
    if (response.ok) {
      setCluster(data.cluster);
      setAgentText(data.result.summary);
      setRecommendations([]);
      setPreparedAction(null);
      void speak(data.result.summary);
      await refresh();
    } else {
      setAgentText(data.detail ?? "The action could not be executed.");
      setPreparedAction(null);
    }
    setBusy(false);
  }

  async function voiceConfirmAction(phrase: string) {
    if (!preparedAction) return;
    setBusy(true);
    const response = await fetch(`${API}/api/remediation/voice-confirm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action_id: preparedAction.action_id,
        confirmation_token: preparedAction.confirmation_token,
        phrase,
      }),
    });
    const data = await response.json();
    if (response.ok) {
      setCluster(data.cluster);
      setAgentText(data.result.summary);
      setRecommendations([]);
      setPreparedAction(null);
      setVoiceStatus("Spoken confirmation accepted. Recovery verification completed.");
      void speak(data.result.summary);
      await refresh();
    } else {
      setAgentText(data.detail ?? "Spoken confirmation was rejected.");
      setVoiceStatus("Confirmation rejected. Record the exact phrase or cancel the action.");
    }
    setBusy(false);
  }

  async function cancelAction() {
    if (!preparedAction) return;
    setBusy(true);
    const response = await fetch(`${API}/api/remediation/cancel`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirmation_token: preparedAction.confirmation_token }),
    });
    const data = await response.json();
    if (response.ok) {
      setPreparedAction(null);
      setAgentText("The pending remediation action was cancelled. No cluster changes were made.");
      setVoiceStatus("Action cancelled.");
      void speak("The pending remediation action was cancelled. No cluster changes were made.");
    } else {
      setAgentText(data.detail ?? "The pending action could not be cancelled.");
    }
    setBusy(false);
  }

  async function startRecording() {
    try {
      stopSpeaking();
      const traceId = crypto.randomUUID();
      setActiveTraceId(traceId);
      setTrace(null);
      setEvaluation(null);
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      chunksRef.current = [];

      const preferredType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/mp4";
      const recorder = new MediaRecorder(stream, { mimeType: preferredType });
      recorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = async () => {
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType });
        stream.getTracks().forEach((track) => track.stop());
        setVoiceStatus("Whisper is transcribing…");
        setBusy(true);
        try {
          const response = await fetch(`${API}/api/voice/transcribe`, {
            method: "POST",
            headers: { "Content-Type": recorder.mimeType, "X-Trace-ID": traceId },
            body: blob,
          });
          if (!response.ok) throw new Error(`Transcription failed (${response.status})`);
          const result = await response.json();
          setCommand(result.text);
          setActiveTraceId(result.trace_id);
          await refreshTrace(result.trace_id);
          setVoiceStatus(`Transcribed ${result.duration_seconds}s of ${result.language} audio.`);
        } catch (error) {
          setVoiceStatus(error instanceof Error ? error.message : "Transcription failed");
        } finally {
          setBusy(false);
          streamRef.current = null;
        }
      };
      recorder.start();
      setRecording(true);
      setVoiceStatus("Listening… click Stop when you finish.");
    } catch (error) {
      setVoiceStatus(error instanceof Error ? error.message : "Microphone access failed");
    }
  }

  function stopRecording() {
    if (recorderRef.current?.state === "recording") {
      recorderRef.current.stop();
      setRecording(false);
    }
  }

  const healthy = useMemo(
    () => cluster?.nodes.filter((node) => node.status === "healthy").length ?? 0,
    [cluster],
  );

  if (!cluster) return <main className="loading">Connecting to SentinelVoice…</main>;

  return (
    <main>
      <header>
        <div>
          <p className="eyebrow">LOCAL-FIRST VOICE AI SRE</p>
          <h1>Sentinel<span>Voice</span></h1>
          <p className="subtitle">Simulated GPU inference cluster · no production systems connected</p>
        </div>
        <div className="actions">
          <button onClick={() => inject("thermal_failure")} disabled={busy}>Inject thermal failure</button>
          <button className="secondary" onClick={() => inject("traffic_spike")} disabled={busy}>Inject traffic spike</button>
          <button className="ghost" onClick={() => inject("reset")} disabled={busy}>Reset</button>
        </div>
      </header>

      <section className="metrics">
        <Metric label="Healthy GPUs" value={`${healthy}/${cluster.nodes.length}`} warning={healthy < cluster.nodes.length} />
        <Metric label="Time to first token" value={`${cluster.inference.time_to_first_token_ms} ms`} warning={cluster.inference.time_to_first_token_ms > 1500} />
        <Metric label="Queue depth" value={`${cluster.inference.queue_depth}`} warning={cluster.inference.queue_depth > 100} />
        <Metric label="Error rate" value={`${cluster.inference.error_rate_percent}%`} warning={cluster.inference.error_rate_percent > 5} />
      </section>

      <section className="workspace">
        <div className="panel cluster-panel">
          <div className="panel-heading"><h2>GPU fleet</h2><span className="live">● LIVE</span></div>
          <div className="nodes">{cluster.nodes.map((node) => <NodeCard node={node} key={node.id} />)}</div>
        </div>

        <div className="panel agent-panel">
          <div className="panel-heading"><h2>Voice incident commander</h2><span>{busy ? "THINKING" : "READY"}</span></div>
          <div className="agent-message"><span className="orb" /><p>{agentText}</p></div>
          <form onSubmit={ask}>
            <input value={command} onChange={(event) => setCommand(event.target.value)} aria-label="Ask SentinelVoice" />
            <button
              type="button"
              className={recording ? "record stop" : "record"}
              onClick={recording ? stopRecording : startRecording}
              disabled={busy}
            >
              {recording ? "Stop" : "Record"}
            </button>
            <button disabled={busy}>Ask agent</button>
            <button type="button" className="voice-stop" onClick={stopSpeaking} disabled={!speaking}>Stop voice</button>
          </form>
          <p className="coming">{voiceStatus}</p>
        </div>

        <div className="panel evidence-panel">
          <div className="panel-heading"><h2>Evidence and tool calls</h2><span>{evidence.length} RESULTS</span></div>
          {evidence.length === 0 ? <p className="empty">No investigation has run yet.</p> : evidence.map((item) => (
            <article className="evidence" key={item.id}>
              <span>✓ {item.source}</span>
              <p>{item.summary}</p>
            </article>
          ))}
        </div>

        <div className="panel remediation-panel">
          <div className="panel-heading"><h2>Safe remediation</h2><span>{recommendations.length} OPTIONS</span></div>
          {recommendations.length === 0 ? (
            <p className="empty">Run an incident investigation to generate recovery options.</p>
          ) : recommendations.map((option) => (
            <article className={`remediation ${option.recommended ? "recommended" : ""}`} key={option.action_id}>
              <div>
                <strong>{option.title}</strong>
                {option.recommended && <span>RECOMMENDED</span>}
              </div>
              <p>{option.description}</p>
              <small>{option.risk.toUpperCase()} RISK · {option.reversible ? "REVERSIBLE" : "NOT REVERSIBLE"}</small>
              {option.blocked_reason && <p className="blocked">{option.blocked_reason}</p>}
              <button onClick={() => prepareAction(option.action_id)} disabled={busy || !option.available}>
                {option.available ? "Prepare action" : "Blocked"}
              </button>
            </article>
          ))}
          {preparedAction && (
            <div className="confirmation">
              <p>Confirmation required: <strong>{preparedAction.confirmation_phrase}</strong></p>
              <button onClick={confirmAction} disabled={busy}>Confirm and execute</button>
              <button className="cancel" onClick={cancelAction} disabled={busy}>Cancel action</button>
            </div>
          )}
        </div>

        <div className="panel trace-panel">
          <div className="panel-heading"><h2>Reliability trace</h2><span>{trace?.events.length ?? 0} EVENTS</span></div>
          {!trace ? <p className="empty">Run a voice turn to capture component-level telemetry.</p> : (
            <>
              {evaluation && (
                <div className={`quality-gate ${evaluation.status}`}>
                  <div>
                    <strong>{evaluation.status.toUpperCase()}</strong>
                    <span>QUALITY GATE · {evaluation.score}%</span>
                  </div>
                  <p>{evaluation.passed_metrics} passed · {evaluation.failed_metrics} failed · {evaluation.missing_metrics} not measured</p>
                </div>
              )}
              {evaluation && (
                <div className="metric-results">
                  {evaluation.metrics.map((metric) => (
                    <article className={metric.status} key={metric.key}>
                      <span>{metric.status === "pass" ? "PASS" : metric.status === "fail" ? "FAIL" : "N/A"}</span>
                      <strong>{metric.label}</strong>
                      <small>
                        {metric.value == null ? "Not measured" : `${metric.value.toFixed(1)} ${metric.unit}`}
                        {metric.threshold == null ? "" : ` / ≤ ${metric.threshold.toFixed(0)} ${metric.unit}`}
                      </small>
                    </article>
                  ))}
                </div>
              )}
              <div className="trace-summary">
                {Object.entries(trace.component_latency_ms).map(([component, latency]) => (
                  <span key={component}><strong>{component}</strong>{latency.toFixed(1)} ms</span>
                ))}
              </div>
              <div className="trace-events">
                {trace.events.map((event) => (
                  <article key={event.event_id}>
                    <span>{event.component}</span>
                    <strong>{event.name}</strong>
                    <small>{event.duration_ms == null ? `+${event.elapsed_ms.toFixed(0)} ms` : `${event.duration_ms.toFixed(1)} ms`}</small>
                  </article>
                ))}
              </div>
            </>
          )}
        </div>
      </section>
    </main>
  );
}
