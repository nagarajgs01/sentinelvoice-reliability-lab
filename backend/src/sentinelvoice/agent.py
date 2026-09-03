from __future__ import annotations

import json
from collections.abc import Sequence

import httpx

from .config import settings
from .domain import AgentDecision, Evidence, ToolCall


SYSTEM_PROMPT = """You are SentinelVoice, a voice SRE for a simulated GPU inference cluster.
Return JSON only with keys: spoken_response, tool_calls, requires_confirmation.
tool_calls is a list of {name, arguments}. Use these exact tool names without parentheses:
- get_cluster_summary with arguments {}
- get_inference_metrics with arguments {}
- get_node_health with arguments {"node_id": "gpu-node-03"}
Never invent telemetry. Query tools before making factual claims. Use the supplied tool evidence to
continue the investigation. Do not repeat a tool call whose result is already supplied. When the
evidence identifies the cause, return no tool calls and give a concise evidence-backed diagnosis.
"""


class OllamaTimeoutError(RuntimeError):
    """Raised when the local model does not respond within the configured limit."""


class OllamaAgent:
    def __init__(self, base_url: str = settings.ollama_url, model: str = settings.ollama_model) -> None:
        self.base_url = base_url
        self.model = model

    async def decide(
        self,
        transcript: str,
        evidence: Sequence[Evidence] = (),
        *,
        allow_tools: bool = True,
    ) -> AgentDecision:
        evidence_payload = [item.model_dump(mode="json") for item in evidence]
        context = (
            f"Engineer request: {transcript}\n"
            f"Tool evidence collected so far: {json.dumps(evidence_payload)}"
        )
        if not allow_tools:
            context += (
                "\nInvestigation limit reached. Do not request more tools. "
                "Return your best supported conclusion and clearly state any uncertainty."
            )
        payload = {
            "model": self.model,
            "stream": False,
            "think": False,
            "format": "json",
            "keep_alive": "10m",
            "options": {
                "temperature": 0,
                "num_predict": 256,
            },
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": context},
            ],
        }
        timeout = httpx.Timeout(180.0, connect=10.0)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(f"{self.base_url}/api/chat", json=payload)
                response.raise_for_status()
        except httpx.TimeoutException as error:
            raise OllamaTimeoutError(
                f"Ollama model {self.model} did not respond within 180 seconds"
            ) from error
        content = response.json()["message"]["content"]
        return AgentDecision.model_validate(json.loads(content))


class DevelopmentAgent:
    async def decide(
        self,
        transcript: str,
        evidence: Sequence[Evidence] = (),
        *,
        allow_tools: bool = True,
    ) -> AgentDecision:
        if evidence or not allow_tools:
            return AgentDecision(
                spoken_response="The requested cluster evidence has been collected.",
            )
        lowered = transcript.lower()
        if "node 3" in lowered or "node 03" in lowered:
            calls = [ToolCall(name="get_node_health", arguments={"node_id": "gpu-node-03"})]
        else:
            calls = [ToolCall(name="get_cluster_summary"), ToolCall(name="get_inference_metrics")]
        return AgentDecision(spoken_response="I will inspect the cluster before answering.", tool_calls=calls)
