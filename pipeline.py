"""Folder-of-videos -> one folder per video -> independent <100MB ZIP packages."""
import argparse
from datetime import timedelta
import hashlib
import io
import json
import math
import os
from pathlib import Path
import subprocess
import threading
import zipfile

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from algorithms import dsh_tile, encode_avif, encode_dsh

VIDEO_EXT={".mp4",".mkv",".mov",".avi",".webm",".m4v",".wmv",".ts"}
MAX_BYTES=90_000_000  # conservative below the user's strict 100,000,000 limit
GAP=24

def sec_label(i):
    return str(timedelta(seconds=i)).zfill(8)

def ffmpeg_exe():
    override=os.environ.get("FFMPEG_BINARY")
    return override if override else imageio_ffmpeg.get_ffmpeg_exe()

def video_meta(video):
    ff=ffmpeg_exe()
    proc=subprocess.run([ff,"-hide_banner","-i",str(video)],
       capture_output=True,text=True,encoding="utf-8",errors="replace")
    # ffmpeg always exits nonzero without an output. Parse exact stream dimensions.
    import re
    lines=proc.stderr.splitlines()
    match=None
    for line in lines:
        if "Video:" in line:
            match=re.search(r"(?<!\d)(\d{2,5})x(\d{2,5})(?!\d)",line)
            if match: break
    if not match:
        raise RuntimeError("Cannot detect video width/height: "+video.name)
    return int(match.group(1)),int(match.group(2))

def frames_1fps(video,w,h,stop_event=None):
    ff=ffmpeg_exe()
    args=[ff,"-nostdin","-hide_banner","-loglevel","error","-i",str(video),
       "-map","0:v:0","-vf","fps=1","-an","-sn","-f","rawvideo",
       "-pix_fmt","rgb24","pipe:1"]
    proc=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    framebytes=w*h*3
    try:
        sec=0
        while True:
            if stop_event is not None and stop_event.is_set():
                raise InterruptedError("Cancelled")
            data=proc.stdout.read(framebytes)
            if not data: break
            if len(data)!=framebytes:
                raise RuntimeError("Truncated ffmpeg raw frame")
            yield sec,np.frombuffer(data,dtype=np.uint8).reshape((h,w,3)).copy()
            sec+=1
        error=proc.stderr.read().decode("utf-8","replace")
        if proc.wait()!=0: raise RuntimeError("ffmpeg failed: "+error[-1500:])
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait()
        proc.stdout.close()
        proc.stderr.close()

def viewer_html(rows):
    # Viewer always runs offline from inside an extracted ZIP, no server.
    data=json.dumps(rows,ensure_ascii=False).replace("</","<\\/")
    return """<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<title>Chalkboard Video Mosaic</title>
<style>body{background:#131820;color:#eee;font:16px system-ui;margin:0;padding:14px}
header{position:sticky;top:0;background:#131820;padding:10px}
button,input{margin:4px;padding:7px}img{display:block;max-width:100%;margin:auto}
.note{color:#e1b889}#photo{overflow:auto;text-align:center}</style>
<header><b>Video board mosaic</b><span id="counter"></span>
<button onclick="go(-1)">Previous</button><button onclick="go(1)">Next</button>
<input id="seek" type="range" min="0" value="0" oninput="set(+this.value)">
<p class="note">DSH binary is a navigation aid; faint writing can disappear. Use original video for final transcription.</p></header>
<div id="photo"></div><script>const data=__DATA__;let i=0;
function set(n){i=Math.max(0,Math.min(data.length-1,n));show()}
function go(d){set(i+d)}function show(){const r=data[i];if(!r)return;
document.getElementById('photo').innerHTML='<img src="'+r.file+'" alt="board montage">';
document.getElementById('counter').textContent=' '+(i+1)+'/'+data.length+' | '+r.seconds.join(', ');
document.getElementById('seek').value=i}
document.getElementById('seek').max=Math.max(0,data.length-1);
document.onkeydown=e=>{if(e.key==='ArrowRight')go(1);if(e.key==='ArrowLeft')go(-1)};show();
</script></html>""".replace("__DATA__",data)

def safe_name(path):
    import re
    return re.sub(r'[^\\w. -]+','_',path.stem).strip(' .')[:70] or 'video'

def video_output_dir(video, root, output):
    # Hashed source-relative path prevents same-named files colliding.
    rel=str(video.relative_to(root)).replace("\\\\","/")
    return output/(safe_name(video)+"_"+hashlib.sha256(rel.encode()).hexdigest()[:8])

def process_video(video, root, output, algorithm="avif", adaptive=True,
                  max_bytes=MAX_BYTES, callback=print, stop_event=None):
    if max_bytes>=100_000_000 or max_bytes<100_000:
        raise ValueError("Max ZIP size must be >=100KB and <100,000,000 bytes")
    w,h=video_meta(video)
    target=video_output_dir(video,root,output)/algorithm
    target.mkdir(parents=True,exist_ok=True)
    (target/"manifest.json").unlink(missing_ok=True)
    # Never leave half a ZIP with a success-looking filename.
    for old in target.glob("*.zip.part"):
        old.unlink()
    frame_iter=frames_1fps(video,w,h,stop_event)
    part=0
    totalframes=0
    totalmos=0
    parts=[]
    current=None
    currentrows=[]
    size=0
    def finish_part():
        nonlocal current,currentrows,size
        if current is None:return
        current.writestr("manifest.json",json.dumps({"video":video.name,
            "algorithm":algorithm,"mosaics":currentrows},ensure_ascii=False))
        current.writestr("index.html",viewer_html(currentrows))
        current.writestr("README.txt","Each tile is 1 second apart; each mosaic is 2x2. "+
          ("DSH binary can delete faint mathematical writing; verify original video." if algorithm=="dsh" else
           "AVIF is lossy; verify unclear small mathematical symbols."))
        current.close()
        temp=Path(current.filename)
        if temp.stat().st_size>=100_000_000:
            temp.unlink()
            raise RuntimeError("ZIP exceeded absolute 100MB limit")
        final=temp.with_suffix("")
        temp.replace(final)
        parts.append({"file":final.name,"bytes":final.stat().st_size,
                      "mosaics":len(currentrows)})
        callback("Saved "+final.name+" ("+str(final.stat().st_size)+" bytes)")
        current=None;currentrows=[];size=0
    def start_part():
        nonlocal current,part,size
        part+=1
        current=zipfile.ZipFile(target/(f"part_{part:03}.zip.part"),
          "w",compression=zipfile.ZIP_STORED,allowZip64=True)
        size=0
    def write_mosaic(group):
        nonlocal size,totalmos,currentrows
        color=(algorithm=="avif") or any(t.mode!="1" for _,t,_ in group)
        canvas=Image.new("RGB" if color else "1",(w*2,(h+GAP)*2),
                         (0,0,0) if color else 0)
        draw=ImageDraw.Draw(canvas)
        seconds=[]
        for j,(sec,tile,kind) in enumerate(group):
            x=(j%2)*w; y=(j//2)*(h+GAP)
            if color:tile=tile.convert("RGB")
            canvas.paste(tile,(x,y+GAP))
            draw.text((x+8,y+4),f"[{j+1}] {sec_label(sec)}",
              fill=(255,255,255) if color else 1)
            seconds.append(sec)
        if algorithm=="avif":
            data,metric=encode_avif(canvas,adaptive=adaptive)
            ext="avif"
        else:
            data,metric=encode_dsh(canvas)
            ext="png"
        name=f"mosaics/m{totalmos:06d}_t{seconds[0]:06d}.{ext}"
        # Reserve 256KB for metadata and viewer. Each individual image must fit.
        if len(data)+256000>=max_bytes: raise RuntimeError("Single mosaic exceeds ZIP capacity")
        if current is None:start_part()
        if size+len(data)+256000>max_bytes:
            finish_part();start_part()
        current.writestr(name,data,compress_type=zipfile.ZIP_STORED)
        size+=len(data)+len(name)+100
        currentrows.append({"file":name,"seconds":seconds,"bytes":len(data),
                            "quality":metric})
        totalmos+=1
        if totalmos%50==0:
            callback(video.name+": "+str(totalframes)+" frames / "+str(totalmos)+" mosaics")
    group=[]
    try:
        for sec,rgb in frame_iter:
            if algorithm=="dsh":
                tile,kind=dsh_tile(rgb)
            else:
                tile,kind=Image.fromarray(rgb,"RGB"),"rgb"
            group.append((sec,tile,kind))
            totalframes+=1
            if len(group)==4:
                write_mosaic(group);group=[]
        if group:write_mosaic(group)
        finish_part()
    except Exception:
        if current is not None:
            temp=Path(current.filename);current.close();temp.unlink(missing_ok=True)
        raise
    if totalframes==0:raise RuntimeError("No frames: "+str(video))
    valid_names={part["file"] for part in parts}
    for stale in target.glob("part_*.zip"):
        if stale.name not in valid_names: stale.unlink()
    manifest={"source":str(video),"algorithm":algorithm,
      "sampling_seconds":1,"tile": [w,h],"mosaic":[2*w,2*(h+GAP)],
      "frames":totalframes,"mosaics":totalmos,"parts":parts,
      "warning":"DSH deletes faint marks; not a visual authority" if algorithm=="dsh" else
       "AVIF is lossy; review unclear fine details"}
    (target/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    return manifest

def find_videos(folder, out):
    return sorted(p for p in folder.rglob("*") if p.is_file() and
       p.suffix.lower() in VIDEO_EXT and out not in p.parents)

def run_folder(folder,algorithm="avif",output=None,adaptive=True,max_bytes=MAX_BYTES,
               callback=print,stop_event=None):
    folder=Path(folder).resolve()
    if not folder.is_dir():raise NotADirectoryError(str(folder))
    output=Path(output).resolve() if output else folder/"BoardPackages"
    if output==folder:raise ValueError("Output must be a subdirectory")
    videos=find_videos(folder,output)
    if not videos:raise ValueError("No supported videos under "+str(folder))
    output.mkdir(parents=True,exist_ok=True)
    summary={"algorithm":algorithm,"input":str(folder),"output":str(output),"results":[]}
    for index,video in enumerate(videos,1):
        callback(f"[{index}/{len(videos)}] {video.name}")
        try:
            m=process_video(video,folder,output,algorithm=algorithm,
                adaptive=adaptive,max_bytes=max_bytes,callback=callback,stop_event=stop_event)
            summary["results"].append({"video":str(video),"status":"ok","result":m})
        except Exception as exc:
            callback("ERROR "+video.name+": "+str(exc))
            summary["results"].append({"video":str(video),"status":"error","error":str(exc)})
            if stop_event is not None and stop_event.is_set():break
    (output/"batch_report.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    return summary

def main():
    p=argparse.ArgumentParser()
    p.add_argument("folder",type=Path)
    p.add_argument("--mode",choices=["avif","dsh"],default="avif")
    p.add_argument("--output",type=Path)
    p.add_argument("--fast-avif",action="store_true",help="Use fixed Q55 instead of decoded fidelity gates")
    p.add_argument("--max-zip-mb",type=int,default=90,help="Hard maximum per ZIP in decimal MB (<100)")
    a=p.parse_args()
    summary=run_folder(a.folder,algorithm=a.mode,output=a.output,
      adaptive=not a.fast_avif,max_bytes=a.max_zip_mb*1000000)
    if any(x["status"]!="ok" for x in summary["results"]):raise SystemExit(1)
if __name__=="__main__":main()
