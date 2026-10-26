"""Cloud REST API. Requires EDGE_API_KEY; emits ZIP directly, no public storage."""
from __future__ import annotations
import hmac
import os

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict

from core import validate_job, render_bundle

class NarrationJob(BaseModel):
    model_config = ConfigDict(extra='allow')
    paragraphs: list[str]
    sentences: list[str]
    expected_word_count: int | None = None
    expected_sentence_count: int | None = None
    voice: str = 'en-US-JennyNeural'
    rate: str = '-5%'
    pitch: str = '+0Hz'
    volume: str = '+0%'
    audio_phase: str = 'FINAL_ARTICLE_READING_ONLY'
    prior_animation_must_be_silent: bool = True
    content_id: str = 'untitled'


def create_app(api_key: str | None = None) -> FastAPI:
    secret = api_key if api_key is not None else os.getenv('EDGE_API_KEY', '')
    if len(secret) < 24:
        raise RuntimeError('EDGE_API_KEY required: 24+ characters; DO NOT expose unauthenticated narration')
    app = FastAPI(title='Edge TTS Narration Pilot R2',
                  docs_url=None,redoc_url=None,openapi_url=None)

    @app.get('/healthz')
    def healthz():
        return {'status':'ready_for_auth_http', 'live_edge_test':'NOT_PERFORMED',
                'api':'r2', 'commercial_rights':'REQUIRES_SEPARATE_REVIEW'}

    @app.post('/v1/validate')
    async def validate(payload: NarrationJob, authorization: str | None = Header(None)):
        require_auth(authorization, secret)
        try:
            p = validate_job(payload.model_dump(exclude_none=True))
        except ValueError as err:
            raise HTTPException(status_code=422,detail=str(err)) from err
        return {k:v for k,v in p.items() if k not in ('text','sentences') } | {'status':'CONTRACT_VALID_NO_AUDIO'}

    @app.post('/v1/narrate')
    async def narrate(payload: NarrationJob, authorization: str | None = Header(None)):
        require_auth(authorization,secret)
        try:
            data, result = await render_bundle(payload.model_dump(exclude_none=True))
        except ValueError as err:
            raise HTTPException(status_code=422,detail=str(err)) from err
        except Exception:
            # Edge network stack exceptions are not leaked to public client.
            raise HTTPException(status_code=503,detail='EDGE_SYNTHESIS_OR_ALIGNMENT_UNAVAILABLE') from None
        return Response(data, media_type='application/zip',
                        headers={'Content-Disposition':'attachment; filename="edge_tts_narration.zip"',
                                 'X-Audio-SHA256': result['audio_sha256'],
                                 'Cache-Control':'no-store'})
    return app


def require_auth(header: str | None, key: str):
    token = header[7:] if header and header.startswith('Bearer ') else ''
    if not hmac.compare_digest(token,key):
        raise HTTPException(status_code=401,detail='UNAUTHORIZED',
                            headers={'WWW-Authenticate':'Bearer'})

# Gunicorn/uvicorn import fails closed when credentials missing.
app = create_app()
