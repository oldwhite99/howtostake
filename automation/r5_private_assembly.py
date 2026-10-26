#!/usr/bin/env python3
"""Private-repository-only, pinned-source R5 Aria video assembly.
Requires an already generated authenticated Render Aria.zip and a trusted
R5_ASSET_URL secret. Does NOT generate any voices locally.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit
import urllib.request
import zipfile

APPROVED_ASSET_SHA256 = "c7d50d8a6a277a9bb4c497096be654fce02aae5cd63aa7057c3938fea53dcc33"
APPROVED_FILES = {
    "assemble_r5_aria.py": "d1f80045f347d7187084bb228fcf3f8b06854e09d299736618650b71a50ca2fa",
    "article_contract_188words_22sentences.json": "6a435f8c000a17a0f329f9fc58387cdd7d2d990cb69de2e2e8858e3abdefc774",
    "R5_video_with_new_highlight_NO_AUDIO.mp4": "4e3fc3d5003b066ffc1f58aa47ddd4126bf068e407501e00856e504b5fef7a5d"
}
MAX_DOWNLOAD = 80 * 1024 * 1024
MAX_EXTRACTED = 60 * 1024 * 1024


def sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def die_if_not_private():
    if os.environ.get("R5_REPOSITORY_PRIVATE") != "true":
        raise ValueError("PRIVATE_REPOSITORY_REQUIRED_FOR_VIDEO_ARTIFACT")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise ValueError("FFMPEG_AND_FFPROBE_REQUIRED")


def download_assets():
    url=os.environ.get("R5_ASSET_URL","")
    if not url:
        raise ValueError("R5_ASSET_URL_SECRET_NOT_CONFIGURED")
    parsed=urlsplit(url)
    if parsed.scheme!="https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("ASSET_URL_MUST_USE_HTTPS")
    # Signed URLs remain in Actions Secrets; never print their values.
    try:
        req=urllib.request.Request(url,headers={"User-Agent":"AI-English-R5-PrivateRunner/1.0"})
        with urllib.request.urlopen(req,timeout=120) as resp:
            b=resp.read(MAX_DOWNLOAD+1)
    except Exception:
        raise ValueError("PRIVATE_ASSET_DOWNLOAD_FAILED") from None
    if len(b)>MAX_DOWNLOAD or sha_bytes(b)!=APPROVED_ASSET_SHA256:
        raise ValueError("APPROVED_R5_ASSET_SHA256_MISMATCH")
    return b


def safe_unpack(data,folder: Path):
    import io
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        if z.testzip() is not None:
            raise ValueError("R5_ASSET_ZIP_CRC_FAILURE")
        info=z.infolist()
        if sum(i.file_size for i in info)>MAX_EXTRACTED:
            raise ValueError("R5_ASSET_ZIP_UNPACKED_TOO_LARGE")
        root=folder.resolve()
        for item in info:
            name=item.filename
            # No absolute/parent escapes, symlinks or executable external files.
            dest=(root/name).resolve()
            if not dest.is_relative_to(root):
                raise ValueError("R5_ASSET_PATH_TRAVERSAL")
            if (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("R5_ASSET_SYMLINK_NOT_ALLOWED")
            if item.is_dir():
                dest.mkdir(parents=True,exist_ok=True)
                continue
            dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(z.read(item))
        for name,expected in APPROVED_FILES.items():
            p=root/name
            if not p.is_file() or sha_bytes(p.read_bytes())!=expected:
                raise ValueError("R5_SOURCE_FILE_SHA256_MISMATCH:"+name)
        framefiles=list((root/"frames").glob("*_active.png"))
        if len(framefiles)!=22 or not (root/"frames"/"00_idle.png").is_file():
            raise ValueError("R5_EXPECTED_23_FRAMES_MISSING")


def probe(path):
    return json.loads(subprocess.check_output(
        ["ffprobe","-v","error","-show_entries",
         "format=duration:stream=codec_type,codec_name,duration,width,height,r_frame_rate",
         "-of","json",str(path)],text=True))


def verify_movie(mp4,output,base_sha):
    p=probe(mp4)
    streams=p["streams"]
    vids=[s for s in streams if s["codec_type"]=="video"]
    aud=[s for s in streams if s["codec_type"]=="audio"]
    if len(vids)!=1 or len(aud)!=1 or vids[0]["width"]!=1920 or vids[0]["height"]!=1080:
        raise ValueError("MP4_STREAM_LAYOUT_INCORRECT")
    if vids[0]["codec_name"]!="h264" or aud[0]["codec_name"]!="aac":
        raise ValueError("MP4_CODEC_MISMATCH")
    dura=float(p["format"]["duration"])
    vd=float(vids[0]["duration"])
    if abs(dura-vd)>0.065 or not 140<dura<165:
        raise ValueError("MP4_DURATION_OR_VIDEO_END_MISMATCH")
    srt=output/"R5_Aria_Full_Timeline.srt"
    if not srt.is_file() or len(re.findall(r" --> ",srt.read_text("utf-8")) )!=22:
        raise ValueError("OUTPUT_SRT_NOT_22_SENTENCES")
    qa_file=output/"R5_Aria_Assembly_QA.json"
    qa=json.loads(qa_file.read_text("utf-8"))
    if qa.get("voice")!="en-US-AriaNeural" or qa.get("sentence_count")!=22:
        raise ValueError("R5_ASSEMBLER_QA_FAILED")
    report={
        "status":"CLOUD_VIDEO_TECHNICAL_QA_PASS_HUMAN_APPROVAL_PENDING",
        "source":"GITHUB_ACTIONS_PRIVATE_REPO_RENDER_ARIA",
        "source_r5_assets_sha256":base_sha,
        "voice":"en-US-AriaNeural",
        "article_words":188,"sentences":22,
        "duration_seconds":dura,"video_stream_seconds":vd,
        "video":"R5_Aria_Cloud.mp4",
        "video_sha256":sha_bytes(mp4.read_bytes()),
        "subtitle":"R5_Aria_Full_Timeline.srt",
        "commercial_rights":"REQUIRES_SEPARATE_REVIEW",
        "publication_approval":"NOT_APPROVED_FOR_PUBLICATION"
    }
    (output/"cloud_delivery_qa.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    return report


def main():
    die_if_not_private()
    audio=Path("Aria.zip").resolve()
    if not audio.is_file() or audio.stat().st_size < 10000:
        raise ValueError("AUTHENTIC_CLOUD_ARIA_ZIP_MISSING")
    assetbytes=download_assets()
    out=Path("r5_video_delivery").resolve()
    out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="r5_private_",dir="/tmp") as temp:
        root=Path(temp)
        safe_unpack(assetbytes,root)
        movie=out/"R5_Aria_Cloud.mp4"
        subprocess.run(
            [sys.executable,str(root/"assemble_r5_aria.py"),"--aria",str(audio),"--output",str(movie)],
            stdout=subprocess.DEVNULL,check=True,timeout=900)
    print(json.dumps(verify_movie(movie,out,APPROVED_ASSET_SHA256),indent=2))


if __name__=="__main__":
    try:
        main()
    except Exception as exc:
        # Never leak signed URLs into logs.
        print("BLOCKED:",str(exc).splitlines()[0][:260],file=sys.stderr)
        sys.exit(2)
