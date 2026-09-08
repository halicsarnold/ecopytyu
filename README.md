# EcoPytyu

EcoPytyu is a small utility to analyze a YouTube channel and calculate the total duration of its videos (normal videos + Shorts).

This repository was created for the 18th anniversary of the EcoPityu channel: https://www.youtube.com/@EcoPityu/

Features
- Separate counting for normal videos and Shorts
- Aggregates total duration and prints human-friendly output (in Hungarian)
- Retries video metadata fetches when yt-dlp fails due to JS/challenge issues (EJS), with a fallback extractor
- Console progress bar and structured logging

Quick start

1. Install dependencies (see INSTALL.md for full instructions)

2. Run:

```bash
python ecopytyu.py https://www.youtube.com/@EcoPityu/
```

or run without an argument and paste the channel or video URL when prompted.

License

This project is MIT licensed — see LICENSE in the repository.
