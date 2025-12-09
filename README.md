# Snapchat Memories Recovery & Organization Pipeline

This project automates the full extraction, cleanup, merging, and organization of your Snapchat Memories export using a single Python script.

Snapchat **does not preserve original timestamps** if you download photos or videos directly from the export HTML page.  
Snaps with text, stickers, or drawings also export as **separate image layers**, not merged media.

This tool solves those issues by:
- Using the HTML export to recover the correct creation dates  
- Downloading the true underlying files  
- Merging image layers automatically  
- Organizing everything into clean year/month folders  

### What This Tool Supports

- Downloading all snaps (images, videos, zip bundles) directly from the HTML export  
- Automatically merging image ZIPs (base + overlay) into one final JPEG  
- Extracting video ZIPs into organized folders  
- Sorting everything into:
  ```
  Memories/YYYY/MM - MonthName/images/
  Memories/YYYY/MM - MonthName/videos/
  ```
- Keeping timestamps accurate  
- Producing a clean, browsable archive of your entire Snapchat history  

This README walks you through **everything from scratch**, including installing Python.  

<br>

# ⚙️ Requirements

- macOS or Windows  
- Python **3.9+**  
- A Snapchat Memories export containing:
  - `memories_history.html`  
  - A table of media entries with direct download links  

<br>

# 📥 Step 0 — Download Snapchat Memories

1. Go to https://accounts.snapchat.com
2. Open My Data
3. Check Export Your Memories
4. Click Request Only Memories
5. Set the date range to All Time
6. Submit the request and wait for Snapchat to email you a download link
(This usually takes a few hours — sometimes up to a day.)
7. When the email arrives, open it, click the download link, and save the export to your computer

You will receive a ZIP containing `memories_history.html`.
Place this file in the `src/` folder before running the script.

<br>

# 📥 Step 1 — Install Python

### macOS
1. Go to: https://www.python.org/downloads/
2. Download the latest macOS installer (e.g., Python 3.12.x)
3. Run the installer  
4. After installation, open Terminal and verify:

```bash
python3 --version
```

### Windows
1. Download the Windows installer from:  
   https://www.python.org/downloads/
2. Run installer  
3. Make sure to check **“Add Python to PATH”**
4. Verify in Command Prompt:

```bash
python --version
```

<br>

# 📦 Step 2 — Install Required Python Libraries

```bash
python3 -m pip install requests beautifulsoup4 pillow
```

If pip is missing on macOS:

```bash
xcode-select --install
```

<br>

# 📂 Step 3 — Set Up Folder Structure

```
Snapchat Memories/
  src/
    memories_history.html
    memories_download.py
```

Paste your `memories_history.html` file inside `src/`.

<br>

# ▶️ Step 4 — Run the Full Pipeline

In Terminal, navigate to `src/`:

```bash
cd "/path/to/Snapchat Memories/src"
python3 memories_download.py
```

Windows:

```bash
python memories_download.py
```

<br>

# 🧠 What the Script Does

### Stage 1 — Download
- Reads every row from `memories_history.html`
- Downloads all images/videos/zips into `../Memories/`
- Renames files and fixes timestamps

### Stage 2 — ZIP Handling
- **Image ZIPs** → Merge into single `_merged.jpg`, delete zip
- **Video ZIPs** → Extract into folder `Memories/<zip_stem>/`, delete zip

### Stage 3 — Organize
- Moves everything into:

```
Memories/YYYY/MM - MonthName/images/
Memories/YYYY/MM - MonthName/videos/
```

<br>

# ✔️ Example Final Output

```
Memories/
  2023/
    07 - July/
      images/
      videos/
  2024/
    01 - January/
      images/
      videos/
```

<br>

# 🛠️ Troubleshooting

### Pip missing (macOS)
```
xcode-select --install
```

### Pillow HEIC warnings  
Normal — HEIC decoding varies by OS. Output will still be generated.

### Permission issues  
Run Terminal/PowerShell as Administrator or adjust folder permissions.

<br>

# 🎉 Done!

You now have a complete automated Snapchat Memories recovery, merging, and organization system.

