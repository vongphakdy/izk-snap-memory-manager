import os
import re
import io
import zipfile
from pathlib import Path
from datetime import datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup
from PIL import Image


# ---------- PATHS / CONFIG ----------

BASE_DIR = Path(__file__).resolve().parent          # .../Snapchat Memories/src
HTML_FILE = BASE_DIR / "memories_history.html"      # input HTML
MEMORIES_DIR = BASE_DIR.parent / "Memories"         # .../Snapchat Memories/Memories

DATE_COL_INDEX = 0   # column index for date in HTML table
TYPE_COL_INDEX = 1   # column index for media type in HTML table

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".gif", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".avi", ".hevc", ".mkv"}


# ---------- STAGE 1: DOWNLOAD FROM HTML ----------

def parse_date(date_str: str) -> datetime:
    for fmt in (
        "%Y-%m-%d %H:%M:%S %Z",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue

    print(f"WARNING: could not parse date: {date_str!r}, using current time.")
    return datetime.now()


def guess_extension(media_type: str, url: str) -> str:
    media_type = media_type.lower()
    url_l = url.lower()

    for ext in (".zip", ".mp4", ".mov", ".jpg", ".jpeg", ".png", ".heic"):
        if url_l.endswith(ext):
            return ext

    if "zip" in media_type:
        return ".zip"
    if "video" in media_type:
        return ".mp4"
    if "image" in media_type or "photo" in media_type or "snap" in media_type:
        return ".jpg"

    return ""


def extract_url_from_row(row) -> Optional[str]:
    a = row.find("a")
    if not a:
        return None

    onclick = a.get("onclick")
    if onclick:
        m = re.search(r"downloadMemories\('([^']+)'", onclick)
        if m:
            return m.group(1)

    href = a.get("href")
    if href and href != "#":
        return href

    return None


def rewrite_zip_in_place(zip_path: Path, dt: datetime, row_index: int):
    """Rename contents inside ZIP with timestamped names, keep it as a single zip file."""
    if not zipfile.is_zipfile(zip_path):
        return

    print(f"  Rewriting ZIP internal names: {zip_path.name}")
    ts = dt.timestamp()
    temp_path = zip_path.with_suffix(zip_path.suffix + ".tmp")

    with zipfile.ZipFile(zip_path, "r") as zin, \
         zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:

        for inner_index, info in enumerate(zin.infolist(), start=1):
            if info.is_dir():
                continue

            data = zin.read(info.filename)
            inner_path = Path(info.filename)
            base = inner_path.stem or "file"
            ext = inner_path.suffix

            new_name = f"{dt.strftime('%Y-%m-%d_%H-%M-%S')}_{base}_{row_index}_{inner_index}{ext}"

            zi = zipfile.ZipInfo(new_name)
            zi.date_time = dt.timetuple()[:6]
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = info.external_attr

            zout.writestr(zi, data)

    os.replace(temp_path, zip_path)
    os.utime(zip_path, (ts, ts))


def stage1_download():
    """Download all memories from the HTML export into Memories/ (including zips)."""
    if not HTML_FILE.exists():
        print(f"HTML file not found: {HTML_FILE}")
        return

    MEMORIES_DIR.mkdir(exist_ok=True)

    print(f"\n[Stage 1] Loading HTML from {HTML_FILE}...")
    with HTML_FILE.open(encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    rows = soup.select("table tr")
    print(f"Found {len(rows) - 1} potential memories (excluding header).")

    downloaded = 0

    for i, row in enumerate(rows[1:], start=1):  # skip header row
        cols = row.find_all("td")
        if len(cols) <= max(DATE_COL_INDEX, TYPE_COL_INDEX):
            continue

        date_text = cols[DATE_COL_INDEX].get_text(strip=True)
        media_type = cols[TYPE_COL_INDEX].get_text(strip=True)

        url = extract_url_from_row(row)
        if not url:
            print(f"[{i}] No URL found, skipping.")
            continue

        dt = parse_date(date_text)
        ext = guess_extension(media_type, url)
        safe_media_type = media_type.replace(" ", "_").lower() or "media"

        filename = f"{dt.strftime('%Y-%m-%d_%H-%M-%S')}_{safe_media_type}_{i}{ext}"
        filepath = MEMORIES_DIR / filename

        print(f"[{i}] {date_text} | {media_type} -> {filepath.name}")

        try:
            resp = requests.get(url, stream=True)
            resp.raise_for_status()
        except Exception as e:
            print(f"  ERROR downloading: {e}")
            continue

        with filepath.open("wb") as f:
            for chunk in resp.iter_content(8192):
                if chunk:
                    f.write(chunk)

        ts = dt.timestamp()
        os.utime(filepath, (ts, ts))

        if zipfile.is_zipfile(filepath):
            if filepath.suffix.lower() != ".zip":
                new_zip_path = filepath.with_suffix(".zip")
                filepath.rename(new_zip_path)
                filepath = new_zip_path
            rewrite_zip_in_place(filepath, dt, i)

        downloaded += 1

    print(f"[Stage 1] Done. Downloaded {downloaded} items into {MEMORIES_DIR.resolve()}")


# ---------- STAGE 2: HANDLE ZIPS (MERGE / EXTRACT) ----------

def is_image_filename(name: str) -> bool:
    return Path(name).suffix.lower() in IMAGE_EXTS


def is_video_filename(name: str) -> bool:
    return Path(name).suffix.lower() in VIDEO_EXTS


def pick_base_and_overlay(names):
    image_names = [n for n in names if is_image_filename(n)]
    if not image_names:
        return None, None

    base_candidates = [n for n in image_names if "media" in n.lower()]
    if not base_candidates:
        non_png = [n for n in image_names if not n.lower().endswith(".png")]
        base_name = non_png[0] if non_png else image_names[0]
    else:
        base_name = base_candidates[0]

    overlay_candidates = [
        n for n in image_names
        if n.lower().endswith(".png") and n != base_name
    ]
    overlay_name = overlay_candidates[0] if overlay_candidates else None

    return base_name, overlay_name


def merge_image_zip(zip_path: Path):
    """
    For image-only zips:
      - read base + overlay directly from zip,
      - save a single merged JPG into Memories/,
      - delete the zip.
    """
    print(f"\n[IMAGE ZIP] {zip_path.name}")
    zip_mtime = zip_path.stat().st_mtime

    with zipfile.ZipFile(zip_path, "r") as z:
        names = z.namelist()
        base_name, overlay_name = pick_base_and_overlay(names)

        if not base_name:
            print("  No base image found, skipping.")
            return

        base_data = z.read(base_name)
        base_img = Image.open(io.BytesIO(base_data)).convert("RGBA")

        if overlay_name:
            overlay_data = z.read(overlay_name)
            overlay_img = Image.open(io.BytesIO(overlay_data)).convert("RGBA")

            if overlay_img.size != base_img.size:
                overlay_img = overlay_img.resize(base_img.size)

            merged = Image.alpha_composite(base_img, overlay_img)
        else:
            merged = base_img

        merged = merged.convert("RGB")
        out_name = zip_path.stem + "_merged.jpg"
        out_path = MEMORIES_DIR / out_name

        merged.save(out_path, format="JPEG", quality=95)
        os.utime(out_path, (zip_mtime, zip_mtime))

        print(f"  -> Wrote merged image: {out_path.name}")

    zip_path.unlink()
    print(f"  Deleted ZIP: {zip_path.name}")


def extract_video_zip_to_folder(zip_path: Path):
    """
    For zips containing any video:
      - extract all contents into Memories/<zip_stem>/,
      - delete the zip.
    """
    print(f"\n[VIDEO ZIP] {zip_path.name} (extracting to folder)")
    zip_mtime = zip_path.stat().st_mtime
    out_folder = MEMORIES_DIR / zip_path.stem
    out_folder.mkdir(exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            extracted_path_str = z.extract(info, path=out_folder)
            extracted_path = Path(extracted_path_str)
            os.utime(extracted_path, (zip_mtime, zip_mtime))
            print(f"  -> Extracted to {out_folder.name}/ {extracted_path.name}")

    zip_path.unlink()
    print(f"  Deleted ZIP: {zip_path.name}")


def stage2_merge_and_extract():
    """Process all zips in Memories/: merge image zips, extract video zips into subfolders."""
    if not MEMORIES_DIR.exists():
        print(f"[Stage 2] {MEMORIES_DIR} does not exist, nothing to do.")
        return

    zip_files = sorted(MEMORIES_DIR.glob("*.zip"))
    if not zip_files:
        print("[Stage 2] No .zip files found.")
        return

    print(f"\n[Stage 2] Found {len(zip_files)} zip(s), processing all...")

    for zip_path in zip_files:
        try:
            with zipfile.ZipFile(zip_path, "r") as z:
                names = z.namelist()

            has_video = any(is_video_filename(n) for n in names)

            if has_video:
                extract_video_zip_to_folder(zip_path)
            else:
                merge_image_zip(zip_path)

        except Exception as e:
            print(f"  ERROR processing {zip_path.name}: {e}")

    print("[Stage 2] Zip processing complete.")


# ---------- STAGE 3: ORGANIZE INTO YEAR / MONTH / TYPE ----------

def is_year_folder(p: Path) -> bool:
    return p.is_dir() and p.name.isdigit() and len(p.name) == 4


def get_target_date(path: Path) -> datetime:
    name = path.name
    try:
        date_str = name[:10]  # 'YYYY-MM-DD'
        return datetime.strptime(date_str, "%Y-%m-%d")
    except Exception:
        return datetime.fromtimestamp(path.stat().st_mtime)


def classify_item(path: Path) -> str:
    """Return 'images', 'videos', or 'other'."""
    if path.is_file():
        ext = path.suffix.lower()
        if ext in IMAGE_EXTS:
            return "images"
        if ext in VIDEO_EXTS:
            return "videos"
        return "other"

    has_video = False
    has_image = False
    for child in path.rglob("*"):
        if not child.is_file():
            continue
        ext = child.suffix.lower()
        if ext in VIDEO_EXTS:
            has_video = True
            break
        if ext in IMAGE_EXTS:
            has_image = True

    if has_video:
        return "videos"
    if has_image:
        return "images"
    return "other"


def stage3_organize():
    """Organize Memories/ into YYYY/MM - MonthName/images|videos/."""
    if not MEMORIES_DIR.exists():
        print(f"[Stage 3] {MEMORIES_DIR} does not exist, nothing to do.")
        return

    items = list(MEMORIES_DIR.iterdir())
    if not items:
        print(f"[Stage 3] No items found in {MEMORIES_DIR}")
        return

    print(f"\n[Stage 3] Organizing items into YYYY/MM - MonthName/images|videos...")

    for item in items:
        if is_year_folder(item):
            continue
        if item.name.startswith("."):
            continue

        dt = get_target_date(item)
        year_folder = MEMORIES_DIR / f"{dt.year:04d}"
        month_label = dt.strftime("%B")
        month_folder = year_folder / f"{dt.month:02d} - {month_label}"

        category = classify_item(item)
        if category == "images":
            dest_root = month_folder / "images"
        elif category == "videos":
            dest_root = month_folder / "videos"
        else:
            dest_root = month_folder / "other"

        dest_root.mkdir(parents=True, exist_ok=True)
        dest = dest_root / item.name

        if dest.exists():
            stem = dest.stem
            suffix = dest.suffix
            dest = dest_root / f"{stem}_dup{suffix}"

        print(f"  Moving {item.name} -> {year_folder.name}/{month_folder.name}/{dest_root.name}/{dest.name}")
        item.rename(dest)

    print("[Stage 3] Organization complete.")


# ---------- MAIN PIPELINE ----------

def main():
    print("Starting Snapchat memories pipeline...\n")
    stage1_download()
    stage2_merge_and_extract()
    stage3_organize()
    print("\nAll stages completed ✅")


if __name__ == "__main__":
    main()
