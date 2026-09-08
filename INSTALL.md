# INSTALLATION

This document describes how to set up a Python environment and install dependencies for running `ecopytyu.py` on Windows, macOS or Linux.

Prerequisites
- Python 3.8+ installed (recommended: 3.10 or 3.11)
- pip

Optional (only if you experience JS/challenge errors frequently):
- Node.js (provides a JS runtime used by some extractors)

Windows (recommended using a virtual environment)

1. Open PowerShell or CMD.
2. Create and activate a virtual environment:

```powershell
python -m venv venv
# PowerShell
venv\Scripts\Activate.ps1
# CMD
venv\Scripts\activate
```

3. Upgrade pip and install dependencies:

```powershell
python -m pip install --upgrade pip
python -m pip install --upgrade yt-dlp
```

4. Verify installation:

```powershell
python -c "import yt_dlp; print('yt_dlp OK', yt_dlp.__version__)"
```

macOS / Linux

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install --upgrade yt-dlp
```

Notes about EJS / challenge solving failed warnings

If you see warnings like:

```
WARNING: [youtube] ...: n challenge solving failed: Some formats may be missing. Ensure you have a supported JavaScript runtime and challenge solver script distribution installed.
```

then:
- Install Node.js (https://nodejs.org/) — some extractors require a JS runtime to execute page JavaScript.
- The script includes retry logic that will try a fallback generic extractor on retries. If the problem persists, enabling a JS runtime and updating yt-dlp to the latest version usually helps.

Running the script

- With a channel or video URL as argument:

```bash
python ecopytyu.py https://www.youtube.com/@EcoPityu/
```

- Without an argument (interactive):

```bash
python ecopytyu.py
# then paste the URL when prompted
```

Troubleshooting

- If `ModuleNotFoundError: No module named 'yt_dlp'` appears, ensure you installed yt-dlp into the same Python interpreter you run the script with (use `python -m pip install yt-dlp`).
- If you have multiple Python versions installed, use the `python` (or `python3`) that you intend to run. Check with `python -V` and `where python` / `which python`.

