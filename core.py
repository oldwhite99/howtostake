"""Strict synthesis and zip-artifact contract shared by REST and MCP transports."""
from __future__ import annotations
import io
import json
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from edge_tts_bridge import build_plan, execute_job

MAX_TEXT_CHARS = 10000


def validate_job(job: dict) -> dict:
    if not isinstance(job, dict):
        raise ValueError('Expected an object containing paragraphs and sentences')
    paragraphs = job.get('paragraphs', [])
    if not isinstance(paragraphs, list) or sum(len(x) if isinstance(x, str) else 0 for x in paragraphs) > MAX_TEXT_CHARS:
        raise ValueError('Article exceeds MAX_TEXT_CHARS=10000 or paragraphs is invalid')
    plan = build_plan(job)
    if plan['word_count'] > 2000 or plan['sentence_count'] > 300:
        raise ValueError('Article too long for the synchronous demo service')
    # Exact text fidelity including punctuation, capitalization and apostrophes.
    if ' '.join(plan['text'].split()) != ' '.join(' '.join(plan['sentences']).split()):
        raise ValueError('PUNCTUATION_OR_CASE_MISMATCH: sentence list is not verbatim article')
    if job.get('audio_phase', 'FINAL_ARTICLE_READING_ONLY') != 'FINAL_ARTICLE_READING_ONLY':
        raise ValueError('Only FINAL_ARTICLE_READING_ONLY is supported')
    if job.get('prior_animation_must_be_silent', True) is not True:
        raise ValueError('Prior animation must be silent')
    return plan


async def render_bundle(job: dict) -> tuple[bytes, dict]:
    """Returns ZIP bytes and verified metadata. Never returns synthetic audio."""
    validate_job(job)
    with TemporaryDirectory(prefix='edge-tts-r2-') as td:
        out = Path(td)
        result = await execute_job(job, out, dry_run=False)
        files = ['article_voice.mp3','article_voice.srt','sentence_timings.json','result.json']
        absent = [f for f in files if not (out/f).is_file()]
        if absent:
            raise ValueError('INCOMPLETE_SYNTHESIS: ' + ','.join(absent))
        # R1 must validate exact 1:1 boundaries, not estimate timings.
        if result.get('boundary_events') != validate_job(job)['sentence_count']:
            raise ValueError('ALIGNMENT_NOT_VERIFIED')
        mp3=(out/'article_voice.mp3').read_bytes()
        if len(mp3) < 100 or not (mp3[:3] == b'ID3' or (mp3[0] == 255 and (mp3[1] & 224) == 224)):
            raise ValueError('NO_VALID_MP3_FRAMING')
        timings=json.loads((out/'sentence_timings.json').read_text(encoding='utf-8'))
        for i,t in enumerate(timings):
            if t['start_sec'] < 0 or t['end_sec'] <= t['start_sec']:
                raise ValueError('INVALID_SENTENCE_TIMING')
            if i and t['start_sec'] < timings[i-1]['end_sec'] - 0.025:
                raise ValueError('OVERLAPPING_SENTENCE_TIMINGS')
        memory = io.BytesIO()
        with zipfile.ZipFile(memory,'w', compression=zipfile.ZIP_DEFLATED) as z:
            for f in files:
                z.write(out/f, arcname=f)
        return memory.getvalue(), result
