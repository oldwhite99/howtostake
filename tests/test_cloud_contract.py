import asyncio
import io
import json
import os
import sys
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import core
from edge_tts_bridge import build_plan

class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.job=json.loads((ROOT/'fixtures'/'morning_routine_188words.json').read_text(encoding='utf8'))

    def test_188_word_source(self):
        plan=core.validate_job(self.job)
        self.assertEqual((plan['word_count'],plan['sentence_count'],plan['paragraph_count']),(188,22,6))

    def test_punctuation_mismatch_is_blocked(self):
        other=json.loads(json.dumps(self.job))
        other['sentences'][0]=other['sentences'][0].replace('.','!')
        with self.assertRaisesRegex(ValueError,'PUNCTUATION_OR_CASE_MISMATCH'):
            core.validate_job(other)

    def test_prior_animation_cannot_be_spoken(self):
        other={**self.job,'prior_animation_must_be_silent':False}
        with self.assertRaisesRegex(ValueError,'must be silent'):
            core.validate_job(other)

    def test_oversize_blocked(self):
        other=json.loads(json.dumps(self.job))
        other['paragraphs'][0]='a'*10001
        with self.assertRaisesRegex(ValueError,'MAX_TEXT_CHARS'):
            core.validate_job(other)

    def test_22_sentences_required(self):
        other=json.loads(json.dumps(self.job))
        other['sentences']=other['sentences'][:-1]
        with self.assertRaises(ValueError):core.validate_job(other)

    def test_4_voice_names(self):
        for voice in ('en-US-JennyNeural','en-US-AriaNeural','en-US-GuyNeural','en-US-ChristopherNeural'):
            self.assertEqual(core.validate_job({**self.job,'voice':voice})['voice'],voice)

    def test_mp3_not_available_without_live_tts(self):
        from edge_tts_bridge import synthesize
        if __import__('importlib').util.find_spec('edge_tts') is None:
            plan=build_plan(self.job)
            with self.assertRaisesRegex(RuntimeError,'EDGE_TTS_UNAVAILABLE'):
                asyncio.run(synthesize(plan))
        else:
            self.skipTest('Real network test is excluded from offline suite')

    def test_no_default_public_secret(self):
        with patch.dict(os.environ,{'EDGE_API_KEY':'g'*32}):
            from rest_api import create_app
        with self.assertRaisesRegex(RuntimeError,'EDGE_API_KEY required'):create_app(api_key='')

    def test_rest_api_auth_contract_and_zip(self):
        from rest_api import create_app
        from fastapi import HTTPException
        secret='g'*32
        app=create_app(api_key=secret)
        original=core.render_bundle
        async def fake(job):
            # This is synthetic contract data, not generated TTS.
            with io.BytesIO() as buf:
                with zipfile.ZipFile(buf,'w') as z:
                    z.writestr('article_voice.mp3',b'NOT_REAL_MP3_SYNTHETIC_TEST')
                    z.writestr('article_voice.srt','TEST_ONLY')
                    z.writestr('sentence_timings.json','[]')
                    z.writestr('result.json','{}')
                return buf.getvalue(),{'audio_sha256':'test-sha'}
        import rest_api
        async def test_calls():
            async with AsyncClient(transport=ASGITransport(app=app),base_url='http://testserver') as client:
                resp=await client.get('/healthz')
                self.assertEqual(resp.status_code,200)
                self.assertEqual(resp.json()['live_edge_test'],'NOT_PERFORMED')
                resp=await client.post('/v1/validate',json=self.job)
                self.assertEqual(resp.status_code,401)
                resp=await client.post('/v1/validate',json=self.job,headers={'Authorization':'Bearer '+secret})
                self.assertEqual(resp.status_code,200)
                self.assertEqual(resp.json()['sentence_count'],22)
                with patch.object(rest_api,'render_bundle',new=fake):
                    resp=await client.post('/v1/narrate',json=self.job,headers={'Authorization':'Bearer '+secret})
                self.assertEqual(resp.status_code,200)
                self.assertEqual(resp.headers['Content-Type'],'application/zip')
                with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
                    self.assertEqual(set(z.namelist()),set(['article_voice.mp3','article_voice.srt','sentence_timings.json','result.json']))
        asyncio.run(test_calls())

    def test_cloud_mcp_config_fail_closed(self):
        s=(ROOT/'mcp_oauth_server.py').read_text()
        self.assertIn("if missing:",s)
        self.assertIn('MCP_NOT_DEPLOYABLE',s)
        self.assertIn('validate_token_resource=True',s)
        self.assertIn('GCS_OUTPUT_BUCKET',s)

    def test_docker_requires_auth(self):
        s=(ROOT/'Dockerfile').read_text()
        self.assertIn('rest_api:app',s)
        self.assertIn('USER 65532',s)
        self.assertIn('EDGE_API_KEY', (ROOT/'rest_api.py').read_text())

if __name__=='__main__':unittest.main()
