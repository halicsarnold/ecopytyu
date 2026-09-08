#!/usr/bin/env python3
"""
EcoPytyu - YouTube channel analyzer

CLI: elfogad egy opcionális URL argumentumot; ha nincs megadva, interaktíven kéri be.
Elemzi egy YouTube csatorna videóit (normál videók + Shorts),
összegzi darabszámot és teljes időtartamot. Ha egy videó lekérése
hibába fut (pl. EJS / challenge solving failed warning), a hibás
tételeket újrapróbáljuk többször, vissoffal és alternatív extractor-beállítással.

Készült az EcoPityu csatorna 18. évfordulójára: https://www.youtube.com/@EcoPityu/
"""
from __future__ import annotations

import argparse
import logging
import shutil
import sys
import time
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import yt_dlp

# ============================================================
# BEÁLLÍTÁSOK
# ============================================================
UPDATE_INTERVAL = 0.1
RETRY_ATTEMPTS = 3
RETRY_BACKOFF = 2.0  # exponenciális visszavárás alap (másodperc)
PROGRESS_BAR_WIDTH = 35

# ============================================================
# LOGOLÁS
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ecopytyu")


# ============================================================
# SEGÉDFUNKCIÓK
# ============================================================

def format_time(seconds: Optional[float]) -> str:
    """Formázott óra:perc:másodperc (HH:MM:SS) - ha ismeretlen, '--:--:--'."""
    if seconds is None or seconds < 0:
        return "--:--:--"

    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return "{:02d}:{:02d}:{:02d}".format(hours, minutes, seconds)


def format_duration(seconds: int) -> str:
    """Formáz egy hosszúságot magyarul: 'X nap Y óra Z perc T másodperc'"""
    seconds = int(seconds or 0)
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)

    parts: List[str] = []
    if days:
        parts.append(f"{days} nap")
    if hours:
        parts.append(f"{hours} óra")
    if minutes:
        parts.append(f"{minutes} perc")
    if seconds or not parts:
        parts.append(f"{seconds} másodperc")
    return " ".join(parts)


# ============================================================
# PROGRESS BAR
# ============================================================
_last_progress_time = 0.0


def show_progress(current: int, total: int, start_time: float, total_seconds: int) -> None:
    """Konzolos progress bar egyszerű implementáció."""
    global _last_progress_time
    now = time.time()
    if now - _last_progress_time < UPDATE_INTERVAL and current < total:
        return
    _last_progress_time = now

    percent = (current / float(total)) if total > 0 else 0.0
    filled = int(PROGRESS_BAR_WIDTH * percent)
    bar = "█" * filled + "░" * (PROGRESS_BAR_WIDTH - filled)

    elapsed = now - start_time
    speed = (current / elapsed) if elapsed > 0 else 0.0
    remaining = total - current
    eta = (remaining / speed) if speed > 0 else 0.0

    terminal_width = shutil.get_terminal_size((120, 20)).columns

    text = (
        "[{}] {:6.2f}% | "
        "{:,}/{:,} | "
        "{:.2f} videó/mp | "
        "ETA {} | "
        "Össz: {}"
    ).format(
        bar,
        percent * 100,
        current,
        total,
        speed,
        format_time(eta),
        format_duration(total_seconds),
    )

    if len(text) >= terminal_width:
        text = text[: terminal_width - 1]

    sys.stdout.write("\r\033[2K" + text)
    sys.stdout.flush()


# ============================================================
# YTDLP HELPERS
# ============================================================

def _yt_dlp_extract_info(url: str, ydl_opts: Dict) -> Tuple[Optional[dict], Optional[str]]:
    """
    Köröljárja a yt_dlp.extract_info hívást, és visszaadja az info dict-et vagy (None, error_message).
    """
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        return info, None
    except Exception as exc:
        return None, str(exc)


def get_video_duration(video_id: str, force_generic_extractor: bool = False) -> Tuple[Optional[int], Optional[str]]:
    """
    Lekéri egy videó hosszát másodpercben. Ha sikertelen, (None, hibaüzenet) lesz az eredmény.

    force_generic_extractor=True esetén a yt-dlp-nek megadott opciók megpróbálják
    a 'generic' extractor-t használni, ami néha megkerüli a JS-challenge hibákat.
    """
    url = f"https://www.youtube.com/watch?v={video_id}"

    opts = {
        "quiet": True,
        "no_warnings": False,
        "ignoreerrors": True,
        "skip_download": True,
        # Fussunk valódi extract_flat=False mert részletes adatot kérünk
        "extract_flat": False,
        # timeout, cache kikapcsolás (stabilitás érdekében)
        "socket_timeout": 20,
        "cachedir": False,
    }

    if force_generic_extractor:
        opts["force_generic_extractor"] = True

    info, error = _yt_dlp_extract_info(url, opts)
    if error:
        return None, error
    if not info:
        return None, "no info returned"
    # Duration néha None; ha van, intbe alakítjuk.
    duration = info.get("duration")
    if duration is None:
        return None, "duration not found in info"
    try:
        return int(duration), None
    except Exception:
        return None, "duration present but couldn't convert to int"


def get_video_duration_with_retries(video_id: str, attempts: int = RETRY_ATTEMPTS) -> Tuple[Optional[int], Optional[str]]:
    """
    Megpróbálja lekérni a videó hosszát többször, felismerve a challenge/EJS hibákat.
    - első próba: alap beállítások
    - későbbi próbálkozások: force_generic_extractor=True
    """
    last_error: Optional[str] = None
    for attempt in range(1, attempts + 1):
        force_generic = attempt > 1
        duration, error = get_video_duration(video_id, force_generic_extractor=force_generic)
        if duration is not None:
            if attempt > 1:
                logger.info("Video %s: succeeded on retry #%d", video_id, attempt)
            return duration, None
        last_error = error
        # Ha specifikus EJS/challenge szöveg van az errorban, logoljuk és retry-oljuk
        err_lower = (error or "").lower()
        is_challenge = "challenge solving failed" in err_lower or "ejs" in err_lower or "challenge" in err_lower
        logger.debug("Video %s: attempt %d failed: %s", video_id, attempt, error or "<no error>")
        if attempt < attempts:
            wait = RETRY_BACKOFF ** (attempt - 1)
            logger.info(
                "Retrying video %s (attempt %d/%d) after %.1fs (challenge-like=%s)...",
                video_id,
                attempt + 1,
                attempts,
                wait,
                is_challenge,
            )
            time.sleep(wait)
            continue
    return None, last_error


# ============================================================
# CSATORNA ÉS LISTA LEKÉRÉSE
# ============================================================

def get_channel_url(url: str) -> Optional[str]:
    """
    Kapott URL-ből megpróbál csatorna-URL-t meghatározni.
    Ha a bemenet már csatorna/user/channel formát, azt visszaadja.
    Ha videó linket kap, megpróbálja a csatorna URL-jét a videó meta alapján lekérni.
    """
    if any(token in url for token in ("/@", "/channel/", "/c/", "/user/")):
        return url

    logger.info("Videó link felismerve. Megkeresem a videó csatornáját...")
    opts = {
        "quiet": True,
        "no_warnings": False,
        "skip_download": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        if not info:
            return None
        if info.get("channel_url"):
            return info["channel_url"]
        if info.get("channel_id"):
            return "https://www.youtube.com/channel/" + info["channel_id"]
        return None
    except Exception as e:
        logger.warning("Hiba a csatorna meghatározásakor: %s", e)
        return None


def _get_flat_list(url: str, description: str) -> List[dict]:
    """
    Közös rész a /videos és /shorts listák lekéréséhez (extract_flat=True).
    """
    logger.info("%s lekérése...", description)
    opts = {
        "quiet": True,
        "no_warnings": False,
        "ignoreerrors": True,
        "skip_download": True,
        "extract_flat": True,
        "playlistend": None,
        "cachedir": False,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        if not info:
            return []
        entries = info.get("entries") or []
        return [entry for entry in entries if entry]
    except Exception as e:
        logger.warning("%s lekérési hiba: %s", description, e)
        return []


def get_video_list(channel_url: str) -> List[dict]:
    url = channel_url.rstrip("/") + "/videos"
    return _get_flat_list(url, "Videólista")


def get_shorts_list(channel_url: str) -> List[dict]:
    url = channel_url.rstrip("/") + "/shorts"
    return _get_flat_list(url, "Shorts lista")


# ============================================================
# DUPLIKÁCIÓK KISZŰRÉSE
# ============================================================
def unique_entries(entries: Iterable[dict]) -> List[dict]:
    """Eltávolítja a duplikált bejegyzéseket (id alapján), megőrzi a sorrendet."""
    result: List[dict] = []
    seen = set()
    for entry in entries:
        if not entry:
            continue
        video_id = entry.get("id")
        if not video_id or video_id in seen:
            continue
        seen.add(video_id)
        result.append(entry)
    return result


# ============================================================
# FELDOLGOZÁS (LOGIKA)
# ============================================================

def process_channel(channel_url: str) -> None:
    videos = get_video_list(channel_url)
    shorts = get_shorts_list(channel_url)

    logger.info("Normál videólista: %s", "{:,}".format(len(videos)))
    logger.info("Shorts lista: %s", "{:,}".format(len(shorts)))

    videos = unique_entries(videos)
    shorts = unique_entries(shorts)

    shorts_ids = {entry.get("id") for entry in shorts if entry.get("id")}
    normal_videos = [entry for entry in videos if entry.get("id") not in shorts_ids]

    logger.info("=" * 70)
    logger.info("VIDEÓK FELDOLGOZÁSA")
    logger.info("=" * 70)
    logger.info("Normál videók: %s", "{:,}".format(len(normal_videos)))
    logger.info("Shorts: %s", "{:,}".format(len(shorts)))
    logger.info("Összesen: %s", "{:,}".format(len(normal_videos) + len(shorts)))

    all_entries: List[Tuple[dict, str]] = [(e, "video") for e in normal_videos] + [(e, "short") for e in shorts]
    total = len(all_entries)

    normal_count = short_count = 0
    normal_seconds = short_seconds = 0
    missing = 0
    processed = 0
    start_time = time.time()

    # Első passz: ha van duration a listából, használjuk; ha nincs, próbáljuk lekérni.
    failed_to_fetch: List[Tuple[str, str]] = []  # list of (video_id, type)

    for entry, video_type in all_entries:
        video_id = entry.get("id")
        duration = entry.get("duration")
        if duration is None and video_id:
            # próbálkozunk egyszer
            d, err = get_video_duration_with_retries(video_id, attempts=1)
            if d is None:
                # nem sikerült most, feljegyezzük a későbbi újrapróbáláshoz
                failed_to_fetch.append((video_id, video_type))
            else:
                duration = d

        if duration is None:
            missing += 1
        else:
            duration = int(duration)
            if video_type == "short":
                short_count += 1
                short_seconds += duration
            else:
                normal_count += 1
                normal_seconds += duration

        processed += 1
        total_seconds = normal_seconds + short_seconds
        show_progress(processed, total, start_time, total_seconds)

    # Progress után új sor
    print()
    print()

    # --------------------------------------------------------
    # ÚJRAPRÓBÁLÁS - azoké, amik az első körben hiányoztak
    # --------------------------------------------------------
    if failed_to_fetch:
        logger.info("Újrapróbálom az %d darab hibás tételt (EJS/challenge esetén is).", len(failed_to_fetch))
        # újrapróbáljuk failed listát többször (RETRY_ATTEMPTS)
        remaining = failed_to_fetch[:]
        attempt = 1
        while remaining and attempt <= RETRY_ATTEMPTS:
            logger.info("Retry pass %d/%d - tételek: %d", attempt, RETRY_ATTEMPTS, len(remaining))
            new_remaining: List[Tuple[str, str]] = []
            for video_id, video_type in remaining:
                d, err = get_video_duration_with_retries(video_id, attempts=1 if attempt == 1 else 2)
                if d is None:
                    logger.debug("Still failed %s on attempt %d: %s", video_id, attempt, err)
                    new_remaining.append((video_id, video_type))
                else:
                    # update counts
                    if video_type == "short":
                        short_count += 1
                        short_seconds += int(d)
                    else:
                        normal_count += 1
                        normal_seconds += int(d)
            remaining = new_remaining
            attempt += 1

        # ha maradt, ezek tényleg nem hatékonyan lekérhetők
        if remaining:
            logger.warning(
                "A következő videók hosszát nem sikerült meghatározni utánaprólás után sem: %s",
                ", ".join(v for v, _ in remaining[:50]),
            )
            missing = len(remaining)

    # --------------------------------------------------------
    # EREDMÉNY
    # --------------------------------------------------------
    logger.info("=" * 70)
    logger.info("EREDMÉNY")
    logger.info("=" * 70)
    logger.info("NORMÁL VIDEÓK")
    logger.info("-" * 70)
    logger.info("Darabszám: %s", "{:,}".format(normal_count))
    logger.info("Összhossz: %s", format_duration(normal_seconds))
    logger.info("")
    logger.info("SHORTS")
    logger.info("-" * 70)
    logger.info("Darabszám: %s", "{:,}".format(short_count))
    logger.info("Összhossz: %s", format_duration(short_seconds))
    logger.info("")
    logger.info("MINDEN VIDEÓ EGYÜTT")
    logger.info("-" * 70)
    logger.info("Darabszám: %s", "{:,}".format(normal_count + short_count))
    logger.info("Összhossz: %s", format_duration(normal_seconds + short_seconds))
    logger.info("")
    if missing:
        logger.info("Nem meghatározható hosszúság: %s", "{:,}".format(missing))
    elapsed = time.time() - start_time
    logger.info("Feldolgozási idő: %s", format_time(elapsed))
    logger.info("=" * 70)


# ============================================================
# MAIN
# ============================================================
def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="YouTube csatorna elemző (EcoPytyu)")
    parser.add_argument("url", nargs="?", help="YouTube videó vagy csatorna linkje")
    args = parser.parse_args(argv)

    if args.url:
        url = args.url.strip()
    else:
        url = input("YouTube videó vagy csatorna linkje: ").strip()

    if not url:
        logger.error("Nem adtál meg URL-t.")
        return 2

    logger.info("=" * 70)
    logger.info("YOUTUBE CSATORNA ELEMZŐ")
    logger.info("=" * 70)
    logger.info("Csatorna meghatározása...")
    channel_url = get_channel_url(url)
    if not channel_url:
        logger.error("Nem sikerült megtalálni a csatornát.")
        return 3

    logger.info("Csatorna: %s", channel_url)
    process_channel(channel_url)

    input("Enter a kilépéshez...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
