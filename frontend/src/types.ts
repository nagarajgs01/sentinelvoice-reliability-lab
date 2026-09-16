export interface ModelInfo {
  id: string;
  name: string;
  provider: string;
  size: string;
  language?: string;
}

export interface ModelCatalog {
  stt: ModelInfo[];
  llm: ModelInfo[];
  tts: ModelInfo[];
}

export interface TTSResult {
  voice: string;
  text: string;
  round_trip_transcript: string;
  intelligibility_percent: number;
  word_error_rate: number;
  generation_ms: number;
  audio_seconds: number;
  real_time_factor: number;
  audio_base64: string;
  trace_id: string;
  error?: string;
}

export interface PipelineResult {
  configuration: { stt: string; llm: string; tts: string };
  transcript: string;
  response: string;
  stt_accuracy_percent: number;
  stt_ms: number;
  llm_ms: number;
  tts_ms: number;
  total_ms: number;
  response_audio_seconds: number;
  audio_base64: string;
  trace_id: string;
}

export interface BenchmarkResult {
  sampleId: string;
  sampleName: string;
  model: string;
  text: string;
  expected_text: string;
  word_error_rate: number;
  accuracy_percent: number;
  latency_ms: number;
  duration_seconds: number;
  language: string;
  passed: boolean;
  trace_id: string;
  error?: string;
}

export interface VoiceSample {
  id: string;
  name: string;
  expected: string;
  audio: Blob;
}

export interface ModelSummary {
  model: string;
  samples: number;
  passRate: number;
  averageAccuracy: number;
  averageWer: number;
  averageLatency: number;
}
