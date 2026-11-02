# Local deployment note: Muse Glimmer as the always-on watcher

For the open-weights bonus the local model has to be a real workload, not a token integration. This note says
what runs locally, how to start it, and how to prove nothing leaves the bench.

## What runs locally

| Component | Where | Notes |
|---|---|---|
| Event log, object graph, safety kernel, verifier, passport signing | on the bench machine | no network at all |
| Always-on watcher and reasoning (`CAIRN_AGENT=glimmer`) | local model server | `cairn/local_llm.py`, OpenAI-compatible chat API with tool calls |
| Perception | **not local yet** | SAM 3.1 is a cloud API; see "Honest limits" |

## Start it

```bash
docker compose --profile local up -d
docker compose exec ollama ollama pull <glimmer-model-tag>       # pull the Glimmer weights you were given
CAIRN_AGENT=glimmer CAIRN_LOCAL_MODEL=<glimmer-model-tag> CAIRN_PRIVACY=local docker compose up
```

`<glimmer-model-tag>` is whatever tag your runtime serves the weights under (Ollama, llama.cpp `llama-server`, or
vLLM all expose `/v1/chat/completions`). Set `CAIRN_LOCAL_URL` if it is not `http://ollama:11434/v1`.
Document, for the submission: the endpoint, the quantisation, the GPU or Mac you ran it on, and measured latency.

## Privacy mode

`CAIRN_PRIVACY=local` makes the server **refuse to start** if the configured agent is the cloud Wonder agent or the
perception backend is the cloud SAM API. Check it:

```bash
curl localhost:8000/health        # "privacy": "local", "agent": "SafeAgent"
```

If the local model is down, `SafeAgent` falls back to the deterministic graph agent, so the bench keeps working.
The model can explain a safety rule but has no tool that changes the graph, the kernel or the passport.

## Honest limits

- **Perception is the cloud dependency.** With `CAIRN_PRIVACY=local`, camera images are not sent anywhere, which
  means SAM perception is off and the bench runs on Manual input or on a locally hosted segmentation model you
  provide behind the `SamBackend` interface. Do not describe the full system as "video never leaves the bench"
  until a local perception backend exists. If you use the cloud SAM API, say so: only the images sent for
  segmentation leave the bench, and only planning prompts without video go to Wonder.
- **No Glimmer model has been run against this repo.** The client is tested against a fake chat endpoint only.
- Latency and memory numbers for the submission have to be measured on your hardware.
