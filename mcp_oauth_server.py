"""OAuth-protected remote MCP tool (Business/Enterprise/Edu support gated).

Cloud Run port served via `python mcp_oauth_server.py`. Requires external
OIDC issuer supporting ChatGPT OAuth client registration / refresh tokens,
audience == MCP_RESOURCE_URL, plus a private GCS output bucket.
There is deliberately NO anonymous MCP mode.
"""
from __future__ import annotations
import asyncio
from datetime import timedelta
import io
import json
import os
import uuid

import jwt
from jwt import PyJWKClient
from mcp.server import MCPServer
from mcp.server.auth.provider import TokenVerifier, AccessToken
from mcp.server.auth.settings import AuthSettings
from pydantic import AnyHttpUrl

from core import render_bundle, validate_job

REQUIRED = ('MCP_ISSUER_URL','MCP_RESOURCE_URL','MCP_JWKS_URL','GCS_OUTPUT_BUCKET','GCS_SIGNER_EMAIL')
missing = [k for k in REQUIRED if not os.getenv(k)]
if missing:
    raise RuntimeError('MCP_NOT_DEPLOYABLE: missing ' + ', '.join(missing))

ISSUER = os.environ['MCP_ISSUER_URL']
RESOURCE = os.environ['MCP_RESOURCE_URL']
JWKS_URI = os.environ['MCP_JWKS_URL']
JWT_ALGS = ['RS256']  # no HS256, no alg=none

class JWKSVerifier(TokenVerifier):
    def __init__(self):
        self.keys = PyJWKClient(JWKS_URI)

    def _check(self, token: str):
        key = self.keys.get_signing_key_from_jwt(token).key
        data = jwt.decode(token,key,algorithms=JWT_ALGS,
                          audience=RESOURCE,issuer=ISSUER,
                          options={'require':['exp','iat','iss','aud','sub']})
        scopes = (data.get('scope') or '').split()
        if 'tts:narrate' not in scopes:
            return None
        return AccessToken(token=token,client_id=str(data.get('azp') or data.get('client_id') or data['sub']),
                           scopes=scopes,resource=RESOURCE,subject=str(data['sub']))

    async def verify_token(self,token:str) -> AccessToken | None:
        try:
            return await asyncio.to_thread(self._check,token)
        except Exception:
            return None

mcp = MCPServer('AI English Edge TTS', token_verifier=JWKSVerifier(),
                auth=AuthSettings(issuer_url=AnyHttpUrl(ISSUER),
                                  resource_server_url=AnyHttpUrl(RESOURCE),
                                  required_scopes=['tts:narrate'],
                                  validate_token_resource=True))


def _store_with_signed_url(blob_data:bytes) -> str:
    from google.cloud import storage
    from google.auth import default as google_auth_default
    from google.auth.transport.requests import Request
    bucket_name=os.environ['GCS_OUTPUT_BUCKET']
    signer=os.environ['GCS_SIGNER_EMAIL']
    credentials,_ = google_auth_default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
    if not credentials.valid:
        credentials.refresh(Request())
    bucket=storage.Client(credentials=credentials).bucket(bucket_name)
    object_name='edge-tts-pilot/' + uuid.uuid4().hex + '/narration.zip'
    blob=bucket.blob(object_name)
    blob.cache_control='private, no-store'
    blob.upload_from_file(io.BytesIO(blob_data),rewind=True,content_type='application/zip')
    # Cloud Run service account must have roles/iam.serviceAccountTokenCreator for signer.
    return blob.generate_signed_url(version='v4',expiration=timedelta(minutes=15),
                                    method='GET',response_disposition='attachment; filename="narration.zip"',
                                    service_account_email=signer,access_token=credentials.token)

@mcp.tool()
async def validate_article(job_json:str) -> str:
    """Validate exact article input, count and 22-sentence contract; no audio."""
    plan=validate_job(json.loads(job_json))
    return json.dumps({k:v for k,v in plan.items() if k not in ('text','sentences')},ensure_ascii=False)

@mcp.tool()
async def narrate_article(job_json:str) -> str:
    """Generate article MP3+SRT+sentence timings for FINAL_ARTICLE_READING_ONLY.

    Produces short-lived private signed ZIP URL, not large base64 in chat.
    Do not use for monetized publication without an explicit rights review.
    """
    job=json.loads(job_json)
    validate_job(job)
    data, result = await render_bundle(job)
    url = await asyncio.to_thread(_store_with_signed_url,data)
    return json.dumps({'status':'AUDIO_CREATED_PENDING_HUMAN_QA',
                       'temporary_download_url':url,'url_expiration_minutes':15,
                       'audio_sha256':result['audio_sha256'],
                       'sentence_count':result['sentence_count'],
                       'commercial_rights':'REQUIRES_SEPARATE_REVIEW'},ensure_ascii=False)

if __name__=='__main__':
    mcp.run(transport='streamable-http', host='0.0.0.0',port=int(os.getenv('PORT','8080')),
            stateless_http=True,json_response=True)
