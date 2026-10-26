#!/usr/bin/env python3
"""Operator-run Render endpoint smoke test. Never prints the credential.

Runs health and validation by default. Pass --live only after explicit approval
for a real Edge TTS synthesis request (costs network/service resources).
"""
import argparse,hashlib,io,json,os,sys,urllib.error,urllib.request,zipfile
from pathlib import Path

def request(url, method='GET', body=None, token=''):
    data=json.dumps(body).encode('utf8') if body is not None else None
    headers={'Content-Type':'application/json'}
    if token: headers['Authorization']='Bearer '+token
    req=urllib.request.Request(url,data=data,method=method,headers=headers)
    with urllib.request.urlopen(req,timeout=110) as resp:
        return resp.status,resp.read(),resp.headers

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--url',required=True,help='https://yourservice.onrender.com')
    p.add_argument('--live',action='store_true',help='Also request real MP3 generation')
    p.add_argument('--voice',default='en-US-JennyNeural',choices=['en-US-JennyNeural','en-US-AriaNeural','en-US-GuyNeural','en-US-ChristopherNeural'])
    p.add_argument('--out',type=Path,default=Path('edge_tts_narration.zip'))
    args=p.parse_args()
    if not args.url.startswith('https://'):
        raise SystemExit('STOP: HTTPS URL is required')
    key=os.getenv('EDGE_API_KEY','')
    if len(key)<24:raise SystemExit('STOP: EDGE_API_KEY environment variable is missing or too short')
    job=json.loads((Path(__file__).parent/'fixtures/morning_routine_188words.json').read_text(encoding='utf8'))
    job['voice']=args.voice
    status,data,_=request(args.url.rstrip('/')+'/healthz')
    print('HEALTH',status,json.loads(data))
    status,data,_=request(args.url.rstrip('/')+'/v1/validate','POST',job,key)
    x=json.loads(data)
    assert status==200 and x['word_count']==188 and x['sentence_count']==22
    print('VALIDATE: PASS (188 words / 22 sentences)',args.voice)
    if not args.live:
        print('LIVE: NOT_PERFORMED (re-run with --live when authorized)')
        return
    status,data,headers=request(args.url.rstrip('/')+'/v1/narrate','POST',job,key)
    assert status==200
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        assert set(['article_voice.mp3','article_voice.srt','sentence_timings.json','result.json'])<=set(z.namelist())
        times=json.loads(z.read('sentence_timings.json'))
        result=json.loads(z.read('result.json'))
        audio=z.read('article_voice.mp3')
        assert len(times)==22 and result['boundary_events']==22 and len(audio)>500
        assert hashlib.sha256(audio).hexdigest()==result['audio_sha256']
    args.out.write_bytes(data)
    print('REAL_EDGE_AUDIO: FILE_DELIVERED_PENDING_HUMAN_LISTENING',args.out.resolve(),len(audio),'MP3 bytes')

if __name__=='__main__':
    try:main()
    except Exception as e:
        print('BLOCKED:',type(e).__name__,str(e)[:220],file=sys.stderr)
        sys.exit(2)
