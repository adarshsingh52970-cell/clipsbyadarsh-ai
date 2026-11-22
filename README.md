# ClipForge AI — Local backend + website

This is a real local FastAPI backend with upload, optional AI transcription/ranking, clip selection, FFmpeg vertical rendering, and MP4 downloads.

## Important source-video note
The YouTube URL field is reference-only. The app does NOT download YouTube videos. Upload the original video file you own or have permission to edit. This avoids relying on unsupported downloading and respects creator rights.

## Windows 10/11 setup (beginner-friendly)

1. Install **Python 3.11 or 3.12** from https://www.python.org/downloads/ . During setup, tick **Add Python to PATH**.
2. Install **FFmpeg** and add its `bin` folder to Windows PATH. A common route is:
   - Open PowerShell and run: `winget install Gyan.FFmpeg`
   - Close and reopen PowerShell.
   - Check: `ffmpeg -version` and `ffprobe -version`
3. Extract this ZIP. Open the extracted `clipforge_backend` folder.
4. Click the folder address bar, type `powershell`, and press Enter.
5. Create a virtual environment:
   `py -3.11 -m venv .venv`
6. Activate it:
   `.\.venv\Scripts\Activate.ps1`
   If PowerShell blocks activation, run this once in that terminal:
   `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`
   Then activate again.
7. Install packages:
   `python -m pip install --upgrade pip`
   `pip install -r requirements.txt`
8. Optional AI setup:
   - Copy `.env.example` and rename the copy to `.env`
   - Put your own API key after `OPENAI_API_KEY=`
   - Keep this key private; never share it or put it in frontend files.
   Without a key, the app can still make basic review candidates, and an uploaded SRT/VTT transcript helps create better candidate windows. AI transcription and AI ranking require the key and may incur API charges.
9. Start the website:
   `uvicorn main:app --reload`
10. Open http://127.0.0.1:8000 in Chrome.

## Use
- Paste the YouTube URL as a reference if you want.
- Upload the authorized video file (MP4/MOV/MKV/WEBM/AVI).
- Optionally upload captions as `.srt` or `.vtt`.
- Wait for analysis, select clips, then export MP4.
- Outputs are saved locally in `data/outputs`.

## Notes / limitations
- The renderer center-crops to 9:16 at 1080x1920; landscape gameplay may lose HUD/action near the edges. A future version can add a crop-position preview or blurred-background layout.
- Scores are AI estimates, not guarantees of virality.
- Long videos and large uploads take time and API transcription has file-size/service limits.
- This local development server is intended for your own computer, not public internet deployment.
