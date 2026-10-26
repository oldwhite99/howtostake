# ChatGPT / Edge TTS R2 deployment and permission gates

## Decision

Recommended technical route: **REST first; protected remote MCP only after credentials/entitlements are resolved**. Do not assume deployment or permanent ChatGPT installation when code generation finishes.

## Ownership and capability gates

| Gate | Needed | Status in delivered package |
|---|---|---|
| R1 article and source fidelity | 188 words, 22 sentences, 6 paragraphs | PASS offline |
| REST program / validation / ZIP | FastAPI, authenticated | PASS offline synthetic |
| Live Edge connectivity | server outbound WebSocket | BLOCKED in current container |
| Production HTTPS URL | Cloud Run / Railway / another host | NOT DEPLOYED |
| Cloud credentials and account billing | user-authorized host project | NOT CONNECTED |
| MCP token issuer | OAuth/OIDC provider supporting ChatGPT OAuth | NOT CONFIGURED |
| MCP JWKS JWT signature / scopes / audience | independent issuer + HTTPS metadata | IMPLEMENTATION PROVIDED, NOT LIVE QA |
| Private GCS & signed URL permissions | bucket, service account, IAM signing | NOT CONFIGURED |
| ChatGPT custom *write/execute* tool access | eligible plan & workspace permissions | NOT VERIFIED / PLAN DEPENDENT |
| YouTube commercial rights | provider written terms | NOT CONFIRMED |

## REST service deployment to Google Cloud Run

1. Create or authorize a Google Cloud project with billing enabled, plus suitable permissions.
2. Create a secret in Secret Manager containing a random `EDGE_API_KEY` (at least 24 characters).
3. From your project's authorized Cloud Shell, upload/extract this code, configure `GOOGLE_CLOUD_PROJECT`, `CLOUD_RUN_REGION`, and `EDGE_API_KEY_SECRET_NAME`, and run `cloud_run_deploy_TEMPLATE.sh`.
4. Call `/healthz`, then `POST /v1/validate` with Authorization, then a single small true Edge TTS call.
5. Confirm WAV/MP3 playback yourself, 22 sentence boundary records, audio duration, and zero audio in the article-composition phase.
6. Apply rate limits, resource quotas, provider terms, and production security policies before broad exposure.

The deploy template marks Cloud Run as publicly INVOKABLE so that generic REST clients can reach it. **The `/v1/narrate` method is still protected by a secret bearer key**, but this alone is not the correct Auth mechanism for ChatGPT MCP. Never paste that secret into a chat prompt, and consider API Gateway/Cloud Armor/IAM as further protection.

## MCP deployment (only for authorized accounts)

1. Configure an OAuth 2.1/OIDC provider (such as Auth0/Entra) that supports ChatGPT OAuth client identification, refresh tokens / offline access as required, JWKS public keys, and audience matching the deployed `MCP_RESOURCE_URL`.
2. Prepare private Cloud Storage bucket and service-account permissions for upload and signing time-limited download links; configure lifecycle deletion.
3. Deploy `Dockerfile.mcp` behind public HTTPS only AFTER all required environment variables are set. The process fails closed without any of `MCP_ISSUER_URL`, `MCP_RESOURCE_URL`, `MCP_JWKS_URL`, `GCS_OUTPUT_BUCKET`, `GCS_SIGNER_EMAIL`.
4. Verify discovery and OAuth sign-in with a generic MCP client before registering in ChatGPT.
5. Where the user's workspace supports it, navigate ChatGPT Plugins → Add custom MCP server → public `https://HOST/mcp` → OAuth. Test `validate_article` first, then `narrate_article` with the small article fixture.
6. Verify no anonymous synthesizer tool is exposed and no token or MP3 content is logged. No claim of full ChatGPT support until this real test passes.

**Plan boundary:** OpenAI's currently documented full MCP including write/modify tools is Business/Enterprise/Edu. Pro has more limited custom MCP read/fetch; Plus write/execute availability must not be assumed. Merely upgrading cloud hosting won't change ChatGPT entitlement.

## Optional Railway path

A Railway plugin is available for deployment workflows and was suggested for explicit installation. It requires the user to connect it. The REST API can be hosted in Railway with the supplied `railway.json`, `Dockerfile`, and `EDGE_API_KEY` secret. Since no Railway connection is authorized in this session, no deployment can be claimed.

## Source precision and known implementation risks

- The Edge `SentenceBoundary` feature exists, but returned events are service-controlled. If the number/text of boundaries differs from source, the adapter must fail rather than fabricate timings.
- ChatGPT MCP tools can return short-lived signed ZIP URLs, but the Cloud Storage signing method and issuer may have cloud-specific IAM requirements; no real integration has been tested.
- Cloud provider limits, service blocking, voice names, latency and third-party terms can change. Validate actual behaviour in the target host.
- Existing R4 visual assets are unchanged. R5's new timings should come from the actual Edge-generated output, not recycled Flite/Descript SRT.
