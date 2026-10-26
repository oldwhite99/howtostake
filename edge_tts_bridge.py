#!/usr/bin/env python3
"""Reusable Edge TTS tool for an LLM-driven English narration workflow.

The bridge is independently runnable but does NOT itself register tools with ChatGPT.
It needs `pip install edge-tts` and outbound WebSocket network access.
Dry-run and contract tests work offline.

Usage:
  python edge_tts_bridge.py --job example_job.json --out outputs --dry-run
  python edge_tts_bridge.py --job example_job.json --out outputs
"""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, AsyncIterable

TICKS_PER_SECOND = 10_000_000


def _normalized_words(text: str) -> list[str]:
    # Keeps contractions in one token, disregards punctuation and whitespace.
    return re.findall(r"[a-z0-9]+(?:['’][a-z0-9]+)*", text.lower())


def build_plan(job: dict[str, Any]) -> dict[str, Any]:
    paragraphs = job.get('paragraphs')
    sentences = job.get('sentences')
    if not isinstance(paragraphs, list) or not paragraphs or any(not isinstance(p, str) or not p.strip() for p in paragraphs):
        raise ValueError('paragraphs must be a nonempty list of nonempty English text')
    if not isinstance(sentences, list) or not sentences or any(not isinstance(s, str) or not s.strip() for s in sentences):
        raise ValueError('sentences must be an explicit nonempty list; never infer boundaries silently')
    text = '\n\n'.join(paragraphs)
    if _normalized_words(text) != _normalized_words(' '.join(sentences)):
        raise ValueError('exact word sequence differs between paragraphs and sentence list')
    if len(sentences) != job.get('expected_sentence_count', len(sentences)):
        raise ValueError('sentence count mismatch')
    wc = len(text.split())
    if wc != job.get('expected_word_count', wc):
        raise ValueError('article word count mismatch')
    sha = hashlib.sha256(text.encode('utf-8')).hexdigest()
    voice = job.get('voice', 'en-US-JennyNeural')
    rate = job.get('rate', '-5%')
    pitch = job.get('pitch', '+0Hz')
    volume = job.get('volume', '+0%')
    if not re.fullmatch(r'en-[A-Z]{2}-[\w-]+Neural', voice):
        raise ValueError('voice must be an English Neural voice name, e.g. en-US-JennyNeural')
    if not re.fullmatch(r'[+-]\d+%', rate) or not re.fullmatch(r'[+-]\d+Hz', pitch) or not re.fullmatch(r'[+-]\d+%', volume):
        raise ValueError('invalid rate, pitch or volume')
    return dict(schema='edge-tts-llm-bridge-r1', content_id=job.get('content_id','unnamed'),
                article_sha256=sha, word_count=wc, sentence_count=len(sentences),
                paragraph_count=len(paragraphs), voice=voice, rate=rate,
                pitch=pitch, volume=volume, phase='FINAL_ARTICLE_READING_ONLY',
                intro_must_be_silent=True, approval='NOT_APPROVED_FOR_PUBLICATION',
                commercial_rights='REQUIRES_SEPARATE_REVIEW', text=text, sentences=sentences)


def _srt_timestamp(seconds: float) -> str:
    ms=max(0,round(seconds*1000))
    hours,ms=divmod(ms,3_600_000); minutes,ms=divmod(ms,60_000); sec,ms=divmod(ms,1_000)
    return f'{hours:02d}:{minutes:02d}:{sec:02d},{ms:03d}'


def match_boundaries(sentences: list[str], events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Use real Edge onsets; resolve only modest metadata-duration overlaps.

    Edge returns both the sentence onset and a nominal duration. Occasionally
    an end computed from offset+duration extends past the next *real* onset.
    A subtitle cannot overlap the next speaking sentence, so clip that end to
    the next observed onset ONLY for bounded overlap and keep raw evidence.
    Severe overlap/non-monotonic onsets must fail, not be estimated.
    """
    boundaries = [e for e in events if e.get('type') == 'SentenceBoundary']
    if len(boundaries) != len(sentences):
        raise ValueError(f'REVIEW_REQUIRED: received {len(boundaries)} sentence boundaries for {len(sentences)} sentences')
    timings = []
    raw_durations = []
    for index, (source, event) in enumerate(zip(sentences, boundaries), 1):
        spoken = event.get('text', '')
        if _normalized_words(source) != _normalized_words(spoken):
            raise ValueError(f'REVIEW_REQUIRED: sentence {index} boundary text differs: expected {source!r}, received {spoken!r}')
        start = float(event['offset']) / TICKS_PER_SECOND
        duration = float(event['duration']) / TICKS_PER_SECOND
        if not (start >= 0 and duration > 0) or (timings and start <= timings[-1]['start_sec'] + 0.15):
            raise ValueError(f'REVIEW_REQUIRED: invalid/non-increasing sentence onset at {index}')
        timings.append(dict(index=index, text=source, start_sec=round(start, 4), end_sec=round(start + duration, 4)))
        raw_durations.append(duration)
    for i in range(len(timings) - 1):
        current, next_sentence = timings[i], timings[i+1]
        overlap = current['end_sec'] - next_sentence['start_sec']
        if overlap <= 0:
            continue
        # A large overrun could mean corrupted upstream timing or bad offsets;
        # never silently repair an arbitrary overlap.
        allowed_overlap = min(1.5, raw_durations[i] * 0.35)
        if overlap > allowed_overlap:
            raise ValueError(
                f'SENTENCE_DURATION_OVERLAP_REVIEW_REQUIRED: sentence={i+1}, '
                f'overlap_sec={overlap:.4f}, maximum_auto_adjust_sec={allowed_overlap:.4f}, '
                f'raw_end_sec={current["end_sec"]:.4f}, '
                f'next_observed_start_sec={next_sentence["start_sec"]:.4f}'
            )
        current['raw_end_sec'] = current['end_sec']
        current['end_sec'] = next_sentence['start_sec']
        current['end_clipped_to_observed_next_onset'] = True
        current['overlap_adjustment_sec'] = round(overlap, 4)
        if current['end_sec'] <= current['start_sec']:
            raise ValueError(f'REVIEW_REQUIRED: invalid normalized end on sentence {i+1}')
    return timings


def write_outputs(out: Path, plan: dict[str, Any], events: list[dict[str,Any]], mp3_bytes: bytes) -> dict[str,Any]:
    # Real audio must exist, and timestamps must be validated before issuing completed outputs.
    if not mp3_bytes:
        raise ValueError('NO_AUDIO: TTS produced zero audio bytes')
    timings = match_boundaries(plan['sentences'], events)
    out.mkdir(parents=True, exist_ok=True)
    (out/'article_voice.mp3').write_bytes(mp3_bytes)
    (out/'sentence_timings.json').write_text(json.dumps(timings,indent=2,ensure_ascii=False),encoding='utf-8')
    srt=[]
    for t in timings:
        srt.extend([str(t['index']),f"{_srt_timestamp(t['start_sec'])} --> {_srt_timestamp(t['end_sec'])}",t['text'],''])
    (out/'article_voice.srt').write_text('\n'.join(srt),encoding='utf-8')
    result={k:v for k,v in plan.items() if k not in ('text','sentences')}
    result.update(status='SYNTHESIS_AND_ALIGNMENT_COMPLETED_REVIEW_PENDING',
                  timing_adjustment_count=sum(1 for t in timings if t.get('end_clipped_to_observed_next_onset')),
                  max_timing_adjustment_sec=max((t.get('overlap_adjustment_sec', 0) for t in timings), default=0),
                  timing_alignment='OBSERVED_SENTENCE_ONSETS_WITH_BOUNDED_END_CLIPPING',
                  audio_bytes=len(mp3_bytes),boundary_events=len(timings),
                  audio_sha256=hashlib.sha256(mp3_bytes).hexdigest(),
                  outputs=['article_voice.mp3','article_voice.srt','sentence_timings.json','result.json'])
    (out/'result.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    return result


async def synthesize(plan:dict[str,Any]) -> tuple[bytes,list[dict[str,Any]]]:
    try:
        import edge_tts  # type: ignore
    except ImportError as e:
        raise RuntimeError('EDGE_TTS_UNAVAILABLE: install edge-tts in a network-enabled Python runtime') from e
    communication=edge_tts.Communicate(plan['text'], voice=plan['voice'],rate=plan['rate'],
                                       pitch=plan['pitch'],volume=plan['volume'],
                                       boundary='SentenceBoundary')
    audio=bytearray();events=[]
    async for event in communication.stream():
        if event['type']=='audio': audio.extend(event['data'])
        elif event['type'] in ('WordBoundary','SentenceBoundary'):events.append(event)
    return bytes(audio),events


async def execute_job(job: dict[str,Any], out: Path, dry_run:bool=False) -> dict[str,Any]:
    plan=build_plan(job)
    if dry_run:
        out.mkdir(parents=True,exist_ok=True)
        public={k:v for k,v in plan.items() if k not in ('text','sentences')}
        public.update(status='DRY_RUN_ONLY_NO_AUDIO_GENERATED')
        (out/'dry_run_plan.json').write_text(json.dumps(public,indent=2,ensure_ascii=False),encoding='utf-8')
        return public
    audio,events=await synthesize(plan)
    return write_outputs(out,plan,events,audio)


def main():
    ap=argparse.ArgumentParser(description='LLM-callable Edge TTS narration adapter')
    ap.add_argument('--job',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--dry-run',action='store_true')
    args=ap.parse_args()
    job=json.loads(args.job.read_text(encoding='utf-8'))
    try:
        result=asyncio.run(execute_job(job,args.out,args.dry_run))
    except Exception as e:
        print(json.dumps({'status':'BLOCKED','error':str(e)},ensure_ascii=False),file=sys.stderr)
        raise SystemExit(2)
    print(json.dumps(result,indent=2,ensure_ascii=False))

if __name__=='__main__':main()
