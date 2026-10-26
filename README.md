# Edge TTS Render Alternative R3 — isolated pilot

## Result & limits

- R2 source bridge is **retained**, with a Render-specific minimal Dockerfile and a Render Blueprint (`render.yaml`).
- `edge-tts` is not a licensed commercial TTS API. Commercial reuse on YouTube still requires a separate rights check.
- Offline contract QA is not a live Edge synthesis test. Never label synthetic fixtures as generated MP3.
- **NO live Render service or ChatGPT custom MCP registration is claimed.** Connecting/installing the Render plugin and authorizing a Render account is an explicit user step.
- Default service exposes a **protected REST interface only**, NOT the unfinished MCP OAuth implementation.

## Suggested deployment path (Render web service pilot)

1. Register or sign in at https://dashboard.render.com/register (Railway is not required).
2. Save this folder's non-secret source files to a Git repository. NEVER commit `EDGE_API_KEY`, `.env`, or generated audio/private data. The example article is public teaching demonstration text; use a private Git repository for sensitive content.
3. In Render Dashboard choose **New > Blueprint**, authorize GitHub or GitLab provider, select the repository containing `render.yaml`.
4. Confirm `plan: free` (subject to account availability). Set `EDGE_API_KEY` at the Blueprint prompt to a random secret of at least 24 characters. **Do not share this key in chat or screenshots.** A key can be generated with `python -c "import secrets;print(secrets.token_urlsafe(32))"`.
5. Deploy. Build command uses `requirements-rest.txt`; the `Dockerfile` installs the real `edge-tts` dependency on Render's network-enabled builders.
6. Service health: `https://<your-onrender-host>/healthz` shows web health only. Real Edge TTS can still fail.
7. On an authorized machine/environment, set the API secret as the `EDGE_API_KEY` environment variable. Run `python smoke_test_render.py --url https://<your-onrender-host>` for health + 188 word validation (no audio requested). Then use `--live --voice en-US-JennyNeural` after authorization for a true 22-sentence MP3 / SRT test. Repeat with `--voice en-US-AriaNeural`, `en-US-GuyNeural`, and `en-US-ChristopherNeural`, using a distinct `--out` ZIP path each time. It writes `edge_tts_narration.zip` only on verified success.
8. Use `assemble_r5_edge.py` with the live ZIP extracted and R4 source assets to update the reading section, keeping earlier ~70 s silent. Visually and audibly QA the final MP4 before treating it as approved.

### Free tier limitations

Render free web services may sleep after 15 minutes idle and take about a minute to spin up. Persistent storage is not assured and request timeouts and external TTS connectivity need live testing. The REST route returns a ZIP synchronously; on a free service long passages may require a paid instance or a durable asynchronous job pattern.

### ChatGPT integration limitations

A **Render plugin** helps deploy/manage infrastructure when connected, but that does not automatically register this protected REST `POST /v1/narrate` endpoint as a direct callable ChatGPT tool. For that, a separate supported custom MCP/plugin interface with proper OAuth and user/workspace permissions is needed. Do not expose your API key or put it in chat prompts to circumvent these requirements.

### Security

`/healthz` public by design; `/v1/validate` and `/v1/narrate` require a 24+ character bearer secret. Never use a shared public API key or unrestricted endpoint for unattended production. Use Render secret variables, secret rotation, abuse/rate limits, and logged operator approval; commercial usage rights unresolved.

## Status

- `R3_RENDER_BLUEPRINT_READY`
- `R3_LOCAL_CONTRACT_QA_PENDING` (updated in QA file after verification)
- `RENDER_ACCOUNT_NOT_CONNECTED`
- `LIVE_EDGE_MP3_NOT_TESTED`
- `CHATGPT_MCP_NOT_REGISTERED`
- `R5_FINAL_MP4_NOT_GENERATED`

## Commands (offline)

```bash
EDGE_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx PYTHONPATH=. python -m unittest discover -s tests -v
python -m py_compile core.py rest_api.py edge_tts_bridge.py smoke_test_render.py assemble_r5_edge.py
```
