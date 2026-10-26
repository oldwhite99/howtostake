#!/usr/bin/env python3
"""Re-render R4's existing intro + R5 reading frames using REAL Edge MP3 and
REAL verified Edge sentence timings. Does not synthesize audio or mutate R4.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import shlex


def run(cmd):
    print('>',shlex.join(str(x) for x in cmd),flush=True)
    subprocess.run([str(x) for x in cmd],check=True)


def duration(path):
    r=subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration',
                               '-of','default=noprint_wrappers=1:nokey=1',str(path)],text=True)
    return float(r.strip())


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--r4',type=Path,required=True,help='Existing 50Words_Article_Full_Motion_R4 directory')
    p.add_argument('--edge',type=Path,required=True,help='ZIP-extracted real Edge narration output directory')
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    r4=args.r4.resolve();src=(r4/'build_silent.mp4')
    frames=(r4/'reading_frames')
    audio=(args.edge/'article_voice.mp3').resolve()
    timings=(args.edge/'sentence_timings.json')
    if not src.is_file() or not frames.is_dir():
        raise SystemExit('BLOCKED: R4 build_silent.mp4 or reading_frames unavailable')
    if not audio.is_file() or not timings.is_file():
        raise SystemExit('BLOCKED: TRUE Edge MP3 and JSON timestamps are required')
    points=json.loads(timings.read_text(encoding='utf-8'))
    if len(points) != 22 or [x['index'] for x in points] != list(range(1,23)):
        raise SystemExit('BLOCKED: 22 exact sentence boundaries required')
    audio_len=duration(audio)
    last_end=points[-1]['end_sec']
    if last_end > audio_len+0.30:
        raise SystemExit('BLOCKED: sentence timestamps exceed audio duration; no guessed timings')
    gap=0.20
    for i,v in enumerate(points):
        if v['start_sec'] < 0 or v['end_sec'] <= v['start_sec']:
            raise SystemExit('BLOCKED: invalid sentence duration')
        if i and v['start_sec'] < points[i-1]['end_sec'] - .025:
            raise SystemExit('BLOCKED: overlapping sentence highlight timestamps')
    target=args.output.resolve();target.parent.mkdir(parents=True,exist_ok=True)
    work=target.parent / '_r5_edge_build'
    work.mkdir(exist_ok=True)
    ff=work/'reading.ffconcat'
    entries=[];t=0.0
    for pnt in points:
        st=pnt['start_sec'];en=pnt['end_sec']
        if st-t>1e-3:entries.append(('00_idle.png',st-t))
        entries.append((f"{pnt['index']:02d}_active.png",en-st));t=en
    # Fill trailing real audio + a short tail. No early cutoff.
    entries.append(('00_idle.png',max(0,audio_len-t)+gap))
    lines=['ffconcat version 1.0']
    for file_name,seconds in entries:
        png=(frames/file_name).resolve()
        if not png.is_file():raise SystemExit('Missing R4 reading PNG: '+str(png))
        lines.extend([f"file '{png}'",'option framerate 30',f'duration {seconds:.6f}'])
    lines.append(f"file '{(frames/entries[-1][0]).resolve()}'")
    ff.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    reading=work/'reading.mp4'
    run(['ffmpeg','-nostdin','-y','-loglevel','error','-safe','0','-f','concat','-i',ff,
         '-vf','fps=30,format=yuv420p','-t',str(audio_len+gap),'-an','-c:v','libx264',
         '-preset','veryfast','-crf','19','-movflags','+faststart',reading])
    joined=work/'two_sections.ffconcat'
    joined.write_text("ffconcat version 1.0\n"+f"file '{src}'\nfile '{reading}'\n",encoding='utf-8')
    lead=duration(src)
    video=work/'silent_full.mp4'
    run(['ffmpeg','-nostdin','-y','-loglevel','error','-safe','0','-f','concat','-i',joined,
         '-an','-c:v','copy','-movflags','+faststart',video])
    run(['ffmpeg','-nostdin','-y','-loglevel','error','-i',video,'-i',audio,
         '-filter_complex',f'[1:a]adelay={round(lead*1000)}:all=1[a]',
         '-map','0:v','-map','[a]','-c:v','copy','-c:a','aac','-b:a','160k',
         '-t',str(lead+audio_len+gap),'-movflags','+faststart',target])
    print(json.dumps({'status':'VIDEO_RENDERED_PENDING_HUMAN_AUDIO_QA',
                      'video':str(target),'lead_silent_seconds':lead,'voice_seconds':audio_len,
                      'sentences':22},indent=2))

if __name__=='__main__':main()
