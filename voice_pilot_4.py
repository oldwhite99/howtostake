"""Real four-voice pilot, ONLY for network-enabled runtime. Never synthesizes offline mocks."""
import asyncio
import json
from pathlib import Path
import sys
from edge_tts_bridge import execute_job
from core import validate_job

VOICES = ('en-US-JennyNeural','en-US-AriaNeural','en-US-GuyNeural','en-US-ChristopherNeural')

async def main():
    base=Path(__file__).resolve().parent
    job=json.loads((base/'fixtures'/'morning_routine_188words.json').read_text(encoding='utf-8'))
    out=base/'real_voice_pilot_output'
    out.mkdir(exist_ok=True)
    report=[]
    for voice in VOICES:
        j={**job,'voice':voice}
        validate_job(j)
        try:
            r=await execute_job(j,out/voice)
            report.append({'voice':voice,'status':'REAL_AUDIO_PENDING_LISTENING_QA',
                           'audio_sha256':r['audio_sha256'],'sentence_count':r['sentence_count']})
        except Exception as e:
            report.append({'voice':voice,'status':'BLOCKED','error':f'{type(e).__name__}: {e}'})
    (out/'real_voice_pilot_manifest.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
    if any(x['status']=='BLOCKED' for x in report):sys.exit(2)

if __name__=='__main__':asyncio.run(main())
