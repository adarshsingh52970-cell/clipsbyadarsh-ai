import os, re, json, uuid, shutil, subprocess
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

load_dotenv()
BASE = Path(__file__).resolve().parent
DATA = Path(os.getenv("DATA_DIR", "data"))
UPLOADS = DATA / "uploads"
OUTPUTS = DATA / "outputs"
for p in (UPLOADS, OUTPUTS): p.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="ClipForge AI Shorts Maker")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
MAX_MB = int(os.getenv("MAX_UPLOAD_MB", "1500"))
jobs = {}

def run(cmd):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return p.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise RuntimeError((e.stderr or str(e))[-2500:])

def ffmpeg_path():
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("FFmpeg was not found. Install FFmpeg and add it to Windows PATH.")
    return exe

def duration_of(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=noprint_wrappers=1:nokey=1", str(path)])
    return float(out)

def parse_srt(path):
    raw = path.read_text(encoding="utf-8-sig", errors="ignore").replace("\r", "")
    blocks = re.split(r"\n\s*\n", raw.strip())
    segments=[]
    for b in blocks:
        lines=b.splitlines()
        ts=next((x for x in lines if "-->" in x),None)
        if not ts: continue
        a,z=[x.strip().split()[0] for x in ts.split("-->")]
        def sec(t):
            h,m,s=t.replace(",",".").split(":")
            return int(h)*3600+int(m)*60+float(s)
        txt=" ".join(x for x in lines[lines.index(ts)+1:] if not x.strip().isdigit()).strip()
        if txt: segments.append({"start":sec(a),"end":sec(z),"text":txt})
    return segments

def transcribe(video):
    if not API_KEY: return []
    from openai import OpenAI
    client=OpenAI(api_key=API_KEY)
    with open(video,"rb") as f:
        result=client.audio.transcriptions.create(
            model=os.getenv("OPENAI_TRANSCRIBE_MODEL","whisper-1"),
            file=f, response_format="verbose_json", timestamp_granularities=["segment"]
        )
    return [{"start":float(s.start),"end":float(s.end),"text":s.text.strip()}
            for s in getattr(result,"segments",[]) if s.text.strip()]

def fallback_clips(duration, segments):
    # Fallback suggestions are transcript-window candidates, not AI-scored viral predictions.
    if segments:
        chunks=[]
        for s in segments:
            if len(s["text"])>18:
                start=max(0,s["start"]-3); end=min(duration,s["end"]+8)
                if end-start>=15: chunks.append((start,end,s["text"][:180]))
        if chunks:
            return [{"id":str(i+1),"start":round(a,2),"end":round(min(z,a+60),2),
                     "title":t[:65] or "Interesting moment","reason":"Transcript-based candidate",
                     "score":None} for i,(a,z,t) in enumerate(chunks[:12])]
    # no transcript: create evenly spaced review windows
    starts=[max(0, duration*x) for x in (0.08,0.28,0.48,0.68,0.84)]
    return [{"id":str(i+1),"start":round(s,2),"end":round(min(duration,s+45),2),
             "title":f"Review moment {i+1}","reason":"Preview this section and decide if it is a highlight",
             "score":None} for i,s in enumerate(starts) if min(duration,s+45)-s>=8]

def rank_with_ai(segments,duration):
    if not API_KEY or not segments: return []
    from openai import OpenAI
    client=OpenAI(api_key=API_KEY)
    compact=segments[:600]
    prompt=("Select up to 10 compelling short-video moments from this timestamped transcript. "
            "Each must be 15-60 seconds, fit within the video duration, and have a clear hook/payoff. "
            "Return JSON only: {\"clips\":[{\"start\":number,\"end\":number,\"title\":string,"
            "\"reason\":string,\"score\":integer}]} . Do not invent transcript content. "
            f"Video duration: {duration:.1f} seconds. Transcript: {json.dumps(compact,ensure_ascii=False)}")
    response=client.chat.completions.create(
        model=os.getenv("OPENAI_CHAT_MODEL","gpt-4o-mini"),
        messages=[{"role":"system","content":"You are a careful short-form video editor. Scores are estimates, not guarantees of virality."},
                  {"role":"user","content":prompt}],
        response_format={"type":"json_object"}, temperature=0.2)
    data=json.loads(response.choices[0].message.content)
    clips=[]
    for i,c in enumerate(data.get("clips",[])[:10]):
        try:
            a=max(0,float(c["start"])); z=min(duration,float(c["end"]))
            if 15 <= z-a <= 60:
                clips.append({"id":str(i+1),"start":round(a,2),"end":round(z,2),
                    "title":str(c.get("title","Highlight"))[:90],
                    "reason":str(c.get("reason",""))[:180],
                    "score":max(0,min(100,int(c.get("score",0))))})
        except (ValueError,TypeError,KeyError): pass
    return clips

@app.get("/", response_class=HTMLResponse)
def home():
    return (BASE/"static"/"index.html").read_text(encoding="utf-8")

@app.get("/api/health")
def health():
    return {"ok":True,"ffmpeg_available":bool(shutil.which("ffmpeg")),
            "ai_enabled":bool(API_KEY)}

@app.post("/api/analyze")
async def analyze(background_tasks: BackgroundTasks, video: UploadFile=File(...),
                  transcript: Optional[UploadFile]=File(None), source_url: str=Form("")):
    name=Path(video.filename or "video").name
    if not name.lower().endswith((".mp4",".mov",".mkv",".webm",".avi")):
        raise HTTPException(400,"Upload an MP4, MOV, MKV, WEBM, or AVI video.")
    job_id=uuid.uuid4().hex[:12]
    target=UPLOADS/f"{job_id}_{name}"
    size=0
    with target.open("wb") as out:
        while chunk:=await video.read(1024*1024):
            size+=len(chunk)
            if size>MAX_MB*1024*1024:
                target.unlink(missing_ok=True)
                raise HTTPException(413,f"File exceeds {MAX_MB} MB limit.")
            out.write(chunk)
    try:
        ffmpeg_path()
        duration=duration_of(target)
    except Exception as e:
        target.unlink(missing_ok=True)
        raise HTTPException(400,str(e))
    subpath=None
    if transcript and transcript.filename:
        if not transcript.filename.lower().endswith((".srt",".vtt")):
            raise HTTPException(400,"Transcript must be .srt or .vtt")
        subpath=UPLOADS/f"{job_id}_{Path(transcript.filename).name}"
        with subpath.open("wb") as f: shutil.copyfileobj(transcript.file,f)
    jobs[job_id]={"id":job_id,"file":str(target),"duration":duration,"status":"analysing",
                  "clips":[],"source_url":source_url,"message":"Video uploaded. Analysing moments..."}
    background_tasks.add_task(process_analysis,job_id,str(subpath) if subpath else None)
    return {"job_id":job_id,"duration":duration,"status":"analysing"}

def process_analysis(job_id, subtitle):
    job=jobs[job_id]
    try:
        segs=parse_srt(Path(subtitle)) if subtitle else transcribe(Path(job["file"]))
        clips=rank_with_ai(segs,job["duration"])
        if not clips: clips=fallback_clips(job["duration"],segs)
        job.update(status="ready",clips=clips,
            message=("AI-ranked suggestions ready." if API_KEY and segs and clips
                     else "Suggestions ready. Add an OpenAI API key and/or transcript for AI ranking."))
    except Exception as e:
        job.update(status="error",message=str(e))

@app.get("/api/jobs/{job_id}")
def get_job(job_id):
    if job_id not in jobs: raise HTTPException(404,"Job not found")
    j=jobs[job_id]
    return {k:v for k,v in j.items() if k not in ("file",)}

@app.post("/api/jobs/{job_id}/export")
def export(job_id: str, payload: dict):
    if job_id not in jobs: raise HTTPException(404,"Job not found")
    job=jobs[job_id]
    if job["status"]!="ready": raise HTTPException(409,"Analysis is not ready yet.")
    ids=set(str(x) for x in payload.get("clip_ids",[]))
    chosen=[c for c in job["clips"] if c["id"] in ids]
    if not chosen: raise HTTPException(400,"Choose at least one clip.")
    results=[]
    for c in chosen:
        out=OUTPUTS/f"{job_id}_clip_{c['id']}.mp4"
        start=float(c["start"]); length=min(60,float(c["end"])-start)
        # Center-crop landscape footage to vertical 9:16, scale to 1080x1920.
        vf="scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1"
        cmd=[ffmpeg_path(),"-y","-ss",str(start),"-i",job["file"],"-t",str(length),
             "-vf",vf,"-c:v","libx264","-preset","veryfast","-crf","23",
             "-c:a","aac","-b:a","128k","-movflags","+faststart",str(out)]
        try: run(cmd)
        except Exception as e: raise HTTPException(500,f"Export failed: {e}")
        results.append({"id":c["id"],"title":c["title"],"url":f"/api/download/{out.name}"})
    return {"exports":results}

@app.get("/api/download/{filename}")
def download(filename):
    safe=Path(filename).name
    path=OUTPUTS/safe
    if not path.exists(): raise HTTPException(404,"File not found")
    return FileResponse(path,media_type="video/mp4",filename=safe)

@app.get("/api/config")
def config():
    return {"ai_enabled":bool(API_KEY)}
