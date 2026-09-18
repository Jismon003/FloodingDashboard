import asyncio
import os
import re
import shutil
from pyppeteer import launch
import urllib.request
from urllib.parse import urljoin, urlparse
from datetime import datetime, timedelta
import cv2
import numpy as np
import pytz
import json


FETCH_HOURS = 6
AZURE_PREFIX = ""

# ==========================
# LOGGER
# ==========================
DEBUG_FILE = r"C:\Users\simon\OneDrive\Documents\Sea Bright\Storm\debug.log"
_last_log_date = None

def log(message: str):
    global _last_log_date
    now = datetime.now()
    timestamp = now.strftime("[%H:%M:%S] ")
    log_date = now.strftime("%Y-%m-%d")
    new_day_header = ""
    if _last_log_date != log_date:
        new_day_header = f"\n----- {log_date} -----\n"
    _last_log_date = log_date

    print(new_day_header + timestamp + message)

    with open(DEBUG_FILE, "a", encoding="utf-8") as f:
        if new_day_header:
            f.write(new_day_header)
        f.write(timestamp + message + "\n")

def draw_x(img, x, y, color=(0, 0, 0), size=4, thickness=1):
    if x is None or y is None:
        return
    x, y = int(x), int(y)
    cv2.line(img, (x - size, y - size), (x + size, y + size), color, thickness)
    cv2.line(img, (x - size, y + size), (x + size, y - size), color, thickness)

# ==========================
# DATE FILTERING
# ==========================
today = datetime.now().date()
END_DATE = today + timedelta(days=5)

DATE_LIST = [
    (today + timedelta(days=i)).strftime("%Y-%m-%d")
    for i in range((END_DATE - today).days + 1)
]

def forecast_horizon_days():
    ny_tz = pytz.timezone("America/New_York")
    now_local = datetime.now(ny_tz)

    if now_local.hour < 14:
        return 4  # keep only 4 days before 2 PM local
    else:
        return 5  # after 2 PM local, allow Day 5

def filter_dates(date_list):
    today = datetime.now().date()
    horizon = forecast_horizon_days()
    cutoff = today + timedelta(days=horizon)
    valid = []
    for d in date_list:
        try:
            dt = datetime.strptime(d, "%Y-%m-%d").date()
            if today <= dt <= cutoff:
                valid.append(d)
        except ValueError:
            log(f"WARNING: Skipping invalid date format: {d}")
    log(f"Stevens Dates: {valid}")
    return valid

# ==========================
# STATION CONFIG
# ==========================
STATIONS = [
    # Monmouth
    (
        "Sea Bright",
        "U219",
        "https://water.noaa.gov/resources/hydrographs/sbin4_hg.png",
        "https://slosh.nws.noaa.gov/petss/fixed/images/all/mllw/8531804.png",
        "https://slosh.nws.noaa.gov/etsurge2.0/fixed/images/all/mllw/8531804.png",
        "https://slosh.nws.noaa.gov/petss_gefs/fixed/images/all/mllw/8531804.png"
    ),
    (
        "Sandy Hook",
        "N021",
        "https://water.noaa.gov/resources/hydrographs/sdhn4_hg.png",
        "https://slosh.nws.noaa.gov/petss/fixed/images/all/mllw/8531680.png",
        "https://slosh.nws.noaa.gov/etsurge2.0/fixed/images/all/mllw/8531680.png",
        "https://slosh.nws.noaa.gov/petss_gefs/fixed/images/all/mllw/8531680.png"
    ),
    (
        "Keansburg",
        "U218",
        "https://water.noaa.gov/resources/hydrographs/ksbn4_hg.png",
        "https://slosh.nws.noaa.gov/petss/fixed/images/all/mllw/8531592.png",
        "https://slosh.nws.noaa.gov/etsurge2.0/fixed/images/all/mllw/8531592.png",
        "https://slosh.nws.noaa.gov/petss_gefs/fixed/images/all/mllw/8531592.png"
    ),
    (
        "Manasquan",
        "U249",
        "https://water.noaa.gov/resources/hydrographs/msnn4_hg.png",
        "https://slosh.nws.noaa.gov/petss/fixed/images/all/mllw/8632591.png",
        "https://slosh.nws.noaa.gov/etsurge2.0/fixed/images/all/mllw/8632591.png",
        "https://slosh.nws.noaa.gov/petss_gefs/fixed/images/all/mllw/8632591.png"
    ),
    # Ocean
    (
        "Mantoloking",
        "U222",
        "https://water.noaa.gov/resources/hydrographs/mtln4_hg.png",
        "https://slosh.nws.noaa.gov/petss/fixed/images/all/mllw/8532786.png",
        "https://slosh.nws.noaa.gov/etsurge2.0/fixed/images/all/mllw/8532786.png",
        "https://slosh.nws.noaa.gov/petss_gefs/fixed/images/all/mllw/8532786.png"
    ),
    (
        "Barnaget Light",
        "U225",
        "https://water.noaa.gov/resources/hydrographs/bgln4_hg.png",
        "https://slosh.nws.noaa.gov/petss/fixed/images/all/mllw/8533615.png",
        "https://slosh.nws.noaa.gov/etsurge2.0/fixed/images/all/mllw/8533615.png",
        "https://slosh.nws.noaa.gov/petss_gefs/fixed/images/all/mllw/8533615.png"
    ),
    (
        "Ship Bottom",
        "U226",
        "https://water.noaa.gov/resources/hydrographs/sbtn4_hg.png",
        "https://slosh.nws.noaa.gov/petss/fixed/images/all/mllw/8533935.png",
        "https://slosh.nws.noaa.gov/etsurge2.0/fixed/images/all/mllw/8533935.png",
        "https://slosh.nws.noaa.gov/petss_gefs/fixed/images/all/mllw/8533935.png"
    ),
    (
        "Tuckerton",
        "U227",
        "https://water.noaa.gov/resources/hydrographs/tktn4_hg.png",
        "https://slosh.nws.noaa.gov/petss/fixed/images/all/mllw/8534319.png",
        "https://slosh.nws.noaa.gov/etsurge2.0/fixed/images/all/mllw/8534319.png",
        "https://slosh.nws.noaa.gov/petss_gefs/fixed/images/all/mllw/8534319.png"
    ),
]

SURGE_SKIP_FORECAST_OBS = ["Manasquan"]

DROPDOWN_VALUE = "MLLW"

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]

TEMP_DIR = r"C:\Users\simon\OneDrive\Documents\Sea Bright\Storm\Temp"
os.makedirs(TEMP_DIR, exist_ok=True)
TEMP_FILES = []


# ==========================
# TIDE MEASUREMENT CONFIG
# ==========================
PX_PER_FT = 25.0
SURGEPX_PER_FT = 34.0
MAGENTA = (255, 0, 255)
GRAY_TICK = (200, 200, 200)

hex_pattern = [
    ["#FFFFFF", "#FFFFFF", "#FFFFFF", "#FFFFFF", "#FFFFFF", "#FFFFFF"],
    ["#B6B6B6", "#B6B6B6", "#B6B6B6", "#B6B6B6", "#B6B6B6", "#B6B6B6"],
    ["#FFFFFF", "#FFFFFF", "#FFFFFF", "#B0C4E8", "#B0C4E8", "#B0C4E8"],
    ["#B6B6B6", "#B6B6B6", "#B6B6B6", "#B6B6B6", "#B6B6B6", "#B6B6B6"],
    ["#FFFFFF", "#FFFFFF", "#FFFFFF", "#FFFFFF", "#FFFFFF", "#FFFFFF"],
]

def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

pattern_rgb = np.array([[hex_to_rgb(h) for h in row] for row in hex_pattern], dtype=np.uint8)
baseline_template = cv2.cvtColor(pattern_rgb, cv2.COLOR_RGB2BGR)

# ==========================
# GITHUB REPOSITORY CONFIG
# ==========================
# The Python program lives in the cloned FloodingDashboard repository.
# All published data is stored under /Data/.
REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(REPO_ROOT, "Data")
os.makedirs(DATA_DIR, exist_ok=True)

def save_to_repository(local_file: str, remote_path: str):
    """Copy a downloaded/processed file into the GitHub repository."""
    try:
        safe_path = remote_path.replace("\\", "/").lstrip("/")
        destination = os.path.join(DATA_DIR, *safe_path.split("/"))

        # Create the complete folder tree automatically.
        os.makedirs(os.path.dirname(destination), exist_ok=True)

        with open(local_file, "rb") as source:
            with open(destination, "wb") as target:
                target.write(source.read())

        TEMP_FILES.append(local_file)
        log(f"Saved to repository: {os.path.relpath(destination, REPO_ROOT)}")

    except Exception as e:
        log(f"ERROR saving {local_file} to repository: {e}")


def git_publish_repository():
    """Commit and push changed /Data files to GitHub."""
    try:
        import subprocess

        def run_git(args):
            result = subprocess.run(
                ["git"] + args,
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace"
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip() or result.stdout.strip())
            return result.stdout.strip()

        run_git(["add", "Data"])
        status = run_git(["status", "--porcelain", "--", "Data"])

        if not status:
            log("No changes to publish to GitHub.")
            return

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        run_git(["commit", "-m", f"Update weather data {timestamp}"])
        run_git(["push"])

        log("Repository successfully pushed to GitHub.")

    except Exception as e:
        log(f"ERROR publishing repository to GitHub: {e}")


# ==========================
# CLEANUP HELPERS
# ==========================
def extract_date_from_path(path: str):
    path = path.replace("\\", "/")
    m = re.search(r"/(\d{8})/", path)
    if m:
        return m.group(1)
    m = re.search(r"/\d{2}_(\d{8})/", path)
    if m:
        return m.group(1)
    m = re.search(r"/(\d{10})/", path)
    if m:
        return m.group(1)[:8]
    return None


def build_keep_dates(stevens=False):
    today = datetime.now().date()
    back_days = 5 if stevens else 11
    fwd_days = 5

    start = today - timedelta(days=back_days)
    end = today + timedelta(days=fwd_days)

    return {
        (start + timedelta(days=i)).strftime("%Y%m%d")
        for i in range((end - start).days + 1)
    }


def cleanup_old_repository_files():
    """Delete files in /Data outside the existing retention windows."""
    stevens_keep = build_keep_dates(stevens=True)
    generic_keep = build_keep_dates(stevens=False)

    log(f"Stevens retention window: {sorted(stevens_keep)}")
    log(f"NWS/PETSS/Models retention window: {sorted(generic_keep)}")

    if not os.path.isdir(DATA_DIR):
        return

    for root, dirs, files in os.walk(DATA_DIR, topdown=False):
        for filename in files:
            full_path = os.path.join(root, filename)
            rel_path = os.path.relpath(full_path, DATA_DIR).replace("\\", "/")
            date_str = extract_date_from_path("/" + rel_path)

            if not date_str:
                continue

            if "Stevens/" in rel_path:
                keep_dates = (
                    generic_keep
                    if ("5_day" in rel_path or "5%20day" in rel_path)
                    else stevens_keep
                )
            else:
                keep_dates = generic_keep

            if date_str not in keep_dates:
                try:
                    os.remove(full_path)
                    log(f"Deleted old repository file: Data/{rel_path}")
                except Exception as e:
                    log(f"ERROR deleting {full_path}: {e}")

        # Remove empty folders left behind by retention cleanup.
        try:
            if root != DATA_DIR and not os.listdir(root):
                os.rmdir(root)
        except Exception:
            pass


# ==========================
# XPATHS & HELPERS
# ==========================
URL = "https://hudson.dl.stevens-tech.edu/sfas/d/index.shtml?station="
START_TIME = "/html/body/div[7]/div[2]/div/div[1]/div/div/div[2]/form/table/tbody/tr[2]/td[2]/input"
END_TIME = "/html/body/div[7]/div[2]/div/div[1]/div/div/div[2]/form/table/tbody/tr[3]/td[2]/input"
XPATH_DROPDOWN = "/html/body/div[7]/div[2]/div/div[1]/div/div/div[2]/form/table/tbody/tr[4]/td[2]/select"
XPATH_IMAGE_1 = "/html/body/div[7]/div[2]/div/div[2]/div[1]/img"
XPATH_IMAGE_2 = "/html/body/div[7]/div[2]/div/div[4]/div/img"

def find_browser():
    # Windows Chrome/Edge
    for path in CHROME_CANDIDATES:
        if os.path.exists(path):
            return path

    # Linux / GitHub Actions Chromium
    for browser in ["chromium", "chromium-browser", "google-chrome", "google-chrome-stable"]:
        path = shutil.which(browser)
        if path:
            return path

    raise FileNotFoundError("Could not find Chrome/Edge/Chromium.")

async def set_input_value(page, xpath, value):
    elem = await page.waitForXPath(xpath, {"timeout": 15000})
    await elem.click({"clickCount": 3})
    await elem.press("Backspace")
    await elem.type(value)

async def set_dropdown_value(page, xpath, value):
    await page.evaluate(
        """(xp, val) => {
            const node = document.evaluate(xp, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
            if (node) {
                let option = Array.from(node.options).find(o => o.value == val || o.text == val);
                if (option) {
                    node.value = option.value;
                    node.dispatchEvent(new Event('change', { bubbles: true }));
                }
            }
        }""",
        xpath,
        value,
    )
def analyze_and_annotate(img_path: str):
    error99_feet = None
    forecast_feet = None
    error1_feet = None
    observed_feet = None
    observed_feet_highest = None

    img = cv2.imread(img_path)
    if img is None:
        log(f"ERROR: Could not load image for analysis: {img_path}")
        return None

    # ---- Baseline (REQUIRED) ----
    res = cv2.matchTemplate(img, baseline_template, cv2.TM_CCOEFF_NORMED)
    _, _, _, max_loc = cv2.minMaxLoc(res)
    if max_loc is None:
        log(f"ERROR: Baseline not found in {img_path}")
        return None
    y0 = max_loc[1] + baseline_template.shape[0] // 2  # baseline

    # --- Dynamic pixel-to-foot calibration ---
    x_col = 47
    baseline_y = y0
    column_pixels = img[:baseline_y, x_col]
    black_indices = np.where(np.all(column_pixels == (0, 0, 0), axis=1))[0]

    if len(black_indices) == 0:
        log(f"[TIDE] No black tick above baseline; using default PX_PER_FT={PX_PER_FT}")
        px_per_ft_dynamic = PX_PER_FT
    else:
        top_tick_y = black_indices[-1]
        pixel_diff = baseline_y - top_tick_y
        px_per_ft_dynamic = float(pixel_diff)
    PX_PER_FT = px_per_ft_dynamic

    # ---- Forecast (magenta) ----
    mask_magenta = np.all(img == MAGENTA, axis=-1)
    coords_magenta = np.column_stack(np.where(mask_magenta))
    if len(coords_magenta) == 0:
        log(f"[TIDE] No magenta forecast pixels found.")
    else:
        y_peak = coords_magenta[:, 0].min()
        x_peak = coords_magenta[coords_magenta[:, 0].argmin(), 1]
        forecast_feet = (y0 - y_peak) / PX_PER_FT

    # ---- Error ticks (gray) ----
    mask_gray = np.all(img == GRAY_TICK, axis=-1)
    coords_gray = np.column_stack(np.where(mask_gray))
    if len(coords_gray) == 0:
        log(f"[TIDE] No gray error ticks found.")
    else:
        above_baseline = coords_gray[coords_gray[:, 0] < y0]
        if len(above_baseline) > 0:
            top_idx = np.argmin(above_baseline[:, 0])
            y_gray_top = above_baseline[top_idx, 0]
            x_gray_top = above_baseline[top_idx, 1]
            error99_feet = (y0 - y_gray_top) / PX_PER_FT
        else:
            log(f"[TIDE] No gray ticks above baseline.")

    # ---- Observed (red) ----
    mask_red = np.all(img == (0, 0, 255), axis=-1)
    coords_red = np.column_stack(np.where(mask_red))
    if len(coords_red) > 0:
        coords_red = coords_red[coords_red[:, 0] < y0]
        if len(coords_red) > 0:
            right_idx = np.argmax(coords_red[:, 1])
            y_obs, x_obs = coords_red[right_idx]
            observed_feet = (y0 - y_obs) / PX_PER_FT

            high_idx = np.argmin(coords_red[:, 0])
            y_high, x_high = coords_red[high_idx]
            observed_feet_highest = (y0 - y_high) / PX_PER_FT
        else:
            log(f"[TIDE] Red pixels found but none above baseline.")

    # ---- Annotation ----
    def fmt(v): return f"{v:.2f} ft" if v is not None else "N/A"

    annotated = img.copy()
    cv2.rectangle(annotated, (135, 340), (285, 395), (0, 0, 0), 1)
    font, scale, thickness = cv2.FONT_HERSHEY_SIMPLEX, 0.3, 1
    variablesX, valuesX = 145, 240

    cv2.putText(annotated, "Max 99% Error:", (variablesX, 355), font, scale, (0, 0, 0), thickness)
    cv2.putText(annotated, fmt(error99_feet), (valuesX, 355), font, scale, (0, 0, 255), thickness)
    cv2.putText(annotated, "Max Forecast Tide:", (variablesX, 370), font, scale, (0, 0, 0), thickness)
    cv2.putText(annotated, fmt(forecast_feet), (valuesX, 370), font, scale, (0, 0, 255), thickness)
    cv2.putText(annotated, "Max 1% Error:", (variablesX, 385), font, scale, (0, 0, 0), thickness)
    cv2.putText(annotated, fmt(error1_feet), (valuesX, 385), font, scale, (0, 0, 255), thickness)

    if observed_feet is not None or observed_feet_highest is not None:
        cv2.rectangle(annotated, (10, 340), (130, 395), (0, 0, 0), 1)
        cv2.putText(annotated, "Current:", (20, 355), font, scale, (0, 0, 0), thickness)
        cv2.putText(annotated, fmt(observed_feet), (80, 355), font, scale, (0, 0, 255), thickness)
        cv2.putText(annotated, "Max:", (20, 370), font, scale, (0, 0, 0), thickness)
        cv2.putText(annotated, fmt(observed_feet_highest), (80, 370), font, scale, (0, 0, 255), thickness)

    if 'x_peak' in locals() and forecast_feet is not None: draw_x(annotated, x_peak, y_peak)
    if 'x_gray_top' in locals() and error99_feet is not None: draw_x(annotated, x_gray_top, y_gray_top)
    if 'x_obs' in locals() and observed_feet is not None: draw_x(annotated, x_obs, y_obs)
    if 'x_high' in locals() and observed_feet_highest is not None: draw_x(annotated, x_high, y_high)
    cv2.imwrite(img_path, annotated)
    return True


def analyze_and_annotate_surge(img_path: str, station_name: str = ""):
    forecast_feet = None
    observed_feet = None
    observed_feet_highest = None
    error_feet = None
    observed_error_highest = None

    img = cv2.imread(img_path)
    if img is None:
        log(f"ERROR: Could not load surge image for analysis: {img_path}")
        return None

    img_masked = img.copy()
    img_masked[29:44, 267:309] = [255, 255, 255]

    res = cv2.matchTemplate(img_masked, baseline_template, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
    if max_val < 0.8:
        log(f"[SURGE] ERROR: Baseline not found in {img_path}")
        return None
    y0 = max_loc[1] + baseline_template.shape[0] // 2

    x_col = 47
    column_pixels = img[:y0, x_col]
    black_indices = np.where(np.all(column_pixels == (0, 0, 0), axis=1))[0]
    if len(black_indices) == 0:
        log(f"[SURGE] No black tick above baseline; using default SURGEPX_PER_FT={SURGEPX_PER_FT}")
        px_per_ft_dynamic = SURGEPX_PER_FT
    else:
        top_tick_y = black_indices[-1]
        px_per_ft_dynamic = float(y0 - top_tick_y)
    SURGEPX_PER_FT = px_per_ft_dynamic

    def fmt(v): return f"{v:.2f} ft" if v is not None else "N/A"

    # ---- Forecast (magenta) ----
    if station_name not in SURGE_SKIP_FORECAST_OBS:
        mask_magenta = np.all(img_masked == (255, 0, 255), axis=-1)
        if mask_magenta.any():
            coords_magenta = np.column_stack(np.where(mask_magenta))
            if len(coords_magenta) > 0:
                dy_all = y0 - coords_magenta[:, 0]
                forecast_feet = dy_all[np.argmax(np.abs(dy_all))] / SURGEPX_PER_FT
        else:
            log(f"[SURGE] No magenta forecast pixels found.")

    # ---- Observed (red) ----
    if station_name not in SURGE_SKIP_FORECAST_OBS:
        mask_red = np.all(img_masked == (0, 0, 255), axis=-1)
        if mask_red.any():
            coords_red = np.column_stack(np.where(mask_red))
            coords_red = coords_red[coords_red[:, 0] < y0]
            if len(coords_red) > 0:
                y_obs, x_obs = coords_red[np.argmax(coords_red[:, 1])]
                observed_feet = (y0 - y_obs) / SURGEPX_PER_FT
                y_high, x_high = coords_red[np.argmin(coords_red[:, 0])]
                observed_feet_highest = (y0 - y_high) / SURGEPX_PER_FT

    # ---- Error (green) ----
    mask_green = np.all(img_masked == (0, 255, 0), axis=-1)
    if mask_green.any():
        coords_green = np.column_stack(np.where(mask_green))
        if len(coords_green) > 0:
            y_err, x_err = coords_green[np.argmax(coords_green[:, 1])]
            error_feet = (y0 - y_err) / SURGEPX_PER_FT
            observed_error_highest = (y0 - coords_green[np.argmin(coords_green[:, 0]), 0]) / SURGEPX_PER_FT

    annotated = img.copy()
    cv2.rectangle(annotated, (425, 175), (575, 230), (0, 0, 0), 1)
    font, scale, thickness = cv2.FONT_HERSHEY_SIMPLEX, 0.3, 1

    cv2.putText(annotated, "Forecast Max:", (435, 185), font, scale, (0, 0, 0), thickness)
    cv2.putText(annotated, fmt(forecast_feet), (515, 185), font, scale, (0, 0, 255), thickness)
    cv2.putText(annotated, "Observed:", (435, 195), font, scale, (0, 0, 0), thickness)
    cv2.putText(annotated, fmt(observed_feet), (515, 195), font, scale, (0, 0, 255), thickness)
    cv2.putText(annotated, "Observed Max:", (435, 205), font, scale, (0, 0, 0), thickness)
    cv2.putText(annotated, fmt(observed_feet_highest), (515, 205), font, scale, (0, 0, 255), thickness)
    cv2.putText(annotated, "Error:", (435, 215), font, scale, (0, 0, 0), thickness)
    cv2.putText(annotated, fmt(error_feet), (515, 215), font, scale, (0, 0, 255), thickness)
    cv2.putText(annotated, "Error Max:", (435, 225), font, scale, (0, 0, 0), thickness)
    cv2.putText(annotated, fmt(observed_error_highest), (515, 225), font, scale, (0, 0, 255), thickness)

    if 'coords_magenta' in locals() and len(coords_magenta) > 0:
        max_idx = np.argmax(np.abs(y0 - coords_magenta[:, 0]))
        draw_x(annotated, coords_magenta[max_idx, 1], coords_magenta[max_idx, 0])
    if 'x_obs' in locals() and observed_feet is not None: draw_x(annotated, x_obs, y_obs)
    if 'x_high' in locals() and observed_feet_highest is not None: draw_x(annotated, x_high, y_high)
    if 'x_err' in locals() and error_feet is not None: draw_x(annotated, x_err, y_err)
    cv2.imwrite(img_path, annotated)
    return True


# ==========================
# STEVENS FETCH (per station, all dates)
# ==========================
async def fetch_stevens(browser, station_name, station_code, valid_dates, dropdown_value):
    page = await browser.newPage()
    try:
        await page.goto(URL + station_code, {"waitUntil": "networkidle2"})
        image_data = {"station": station_name, "tide": "", "surge": ""}
        for date_value in valid_dates:
            try:
                await set_input_value(page, START_TIME, date_value)
                await set_input_value(page, END_TIME, date_value)
                await set_dropdown_value(page, XPATH_DROPDOWN, dropdown_value)
                await asyncio.sleep(1)  # give page time to refresh graphs

                ts = datetime.now().strftime("%H%M%S_%Y%m%d")
                run_time = datetime.now().strftime("%H_%Y%m%d")
                date_str = date_value.replace("-", "")

                # Tide
                el1 = await page.waitForXPath(XPATH_IMAGE_1, {"timeout": 30000})
                src1 = await (await el1.getProperty("src")).jsonValue()
                if not urlparse(src1).scheme:
                    src1 = urljoin(page.url, src1)
                tide_file = os.path.join(TEMP_DIR, f"{ts} - {station_name} for {date_value}-Tide.png")
                urllib.request.urlretrieve(src1, tide_file)
                analyze_and_annotate(tide_file)
                save_to_repository(tide_file, f"{AZURE_PREFIX}{station_name}/Stevens/{date_str}/{run_time}/{os.path.basename(tide_file)}")

                # Surge
                el2 = await page.waitForXPath(XPATH_IMAGE_2, {"timeout": 30000})
                src2 = await (await el2.getProperty("src")).jsonValue()
                if not urlparse(src2).scheme:
                    src2 = urljoin(page.url, src2)
                surge_file = os.path.join(TEMP_DIR, f"{ts} - {station_name} for {date_value}-Surge.png")
                urllib.request.urlretrieve(src2, surge_file)
                analyze_and_annotate_surge(surge_file, station_name)
                save_to_repository(surge_file, f"{AZURE_PREFIX}{station_name}/Stevens/{date_str}/{run_time}/{os.path.basename(surge_file)}")

            except Exception as e:
                log(f"ERROR fetching Stevens for {station_name} on {date_value}: {e}")
        # ===== Fetch 5-day composite =====
        try:
            start_date = valid_dates[0]
            end_date = valid_dates[-1]
            await set_input_value(page, START_TIME, start_date)
            await set_input_value(page, END_TIME, end_date)
            await set_dropdown_value(page, XPATH_DROPDOWN, dropdown_value)
            await asyncio.sleep(1)

            ts = datetime.now().strftime("%H%M%S_%Y%m%d")
            run_time = datetime.now().strftime("%H_%Y%m%d")

            # Tide 5-day
            el1 = await page.waitForXPath(XPATH_IMAGE_1, {"timeout": 30000})
            src1 = await (await el1.getProperty("src")).jsonValue()
            if not urlparse(src1).scheme:
                src1 = urljoin(page.url, src1)
            tide_5day = os.path.join(TEMP_DIR, f"{ts} - {station_name} 5 day {start_date}-Tide.png")
            urllib.request.urlretrieve(src1, tide_5day)
            analyze_and_annotate(tide_5day)
            save_to_repository(
                tide_5day,
                f"{AZURE_PREFIX}{station_name}/Stevens/Composite/{run_time}/{os.path.basename(tide_5day)}"
            )

            # Surge 5-day
            el2 = await page.waitForXPath(XPATH_IMAGE_2, {"timeout": 30000})
            src2 = await (await el2.getProperty("src")).jsonValue()
            if not urlparse(src2).scheme:
                src2 = urljoin(page.url, src2)
            surge_5day = os.path.join(TEMP_DIR, f"{ts} - {station_name} 5 day {start_date}-Surge.png")
            urllib.request.urlretrieve(src2, surge_5day)
            analyze_and_annotate_surge(surge_5day, station_name)
            save_to_repository(
                surge_5day,
                f"{AZURE_PREFIX}{station_name}/Stevens/Composite/{run_time}/{os.path.basename(surge_5day)}"
            )

        except Exception as e:
            log(f"ERROR fetching 5-day composite for {station_name}: {e}")
    finally:
        await page.close()
# ==========================
# TROPICAL TIDBITS CONFIG
# ==========================
TROPICAL_MODELS = [
    {
        "name": "EC-AIFS",
        "model": "ec-aifs",
        "region": "neus",
        "product": "mslp_wind"
    },
    {
        "name": "ECMWF",
        "model": "ecmwf",
        "region": "neus",
        "product": "mslp_wind"
    },
    {
        "name": "ECMWF",
        "model": "ecmwf",
        "region": "neus",
        "product": "wavehgt"
    },
    {
        "name": "GFS",
        "model": "gfs",
        "region": "neus",
        "product": "wavehgt"
    },
    {
        "name": "GFS",
        "model": "gfs",
        "region": "neus",
        "product": "mslp_wind"
    },
]

def build_forecast_hours():
    base = [0, 24, 48, 72, 96, 120]
    if forecast_horizon_days() == 6:
        base.append(144)
    return base

FORECAST_HOURS = build_forecast_hours()

async def fetch_tropicaltidbits(browser, name, model, region, product):
    ny_tz = pytz.timezone("America/New_York")
    now = datetime.now(ny_tz)

    # figure out current cycle (00, 06, 12, 18)
    cycles = [0, 6, 12, 18]
    cycle_hour = max([ch for ch in cycles if ch <= now.hour], default=18)
    runtime = now.strftime("%Y%m%d") + f"{cycle_hour:02d}"

    # compute previous cycle (6h earlier)
    prev_time = now.replace(hour=cycle_hour) - timedelta(hours=6)
    prev_cycle_hour = (cycle_hour - 6) % 24
    prev_runtime = prev_time.strftime("%Y%m%d") + f"{prev_cycle_hour:02d}"

    page = await browser.newPage()
    try:
        for run_id in [runtime, prev_runtime]:
            base_url = f"https://www.tropicaltidbits.com/analysis/models/?model={model}&region={region}&pkg={product}&runtime={run_id}"
            for fh in FORECAST_HOURS:
                url = f"{base_url}&fh={fh}"
                await page.goto(url, {"waitUntil": "networkidle2"})
                img_xpath = "/html/body/div/div[2]/div[2]/div[1]/div[2]/img"

                el = await page.waitForXPath(img_xpath, {"timeout": 30000})
                src = await (await el.getProperty("src")).jsonValue()

                parts = src.split("/")
                model_dir = parts[5]
                run_date_hour = parts[6]
                base_filename = os.path.basename(src)
                filename = f"{run_date_hour}_{base_filename}"
                local_path = os.path.join(TEMP_DIR, filename)

                resp = await page.goto(src)
                img_bytes = await resp.buffer()
                with open(local_path, "wb") as f:
                    f.write(img_bytes)
                remote_path = f"{AZURE_PREFIX}Models/{run_date_hour}/{model_dir}/{filename}"
                save_to_repository(local_path, remote_path)
                #log(f"Saved {name} {model} {product} run={run_id} fh={fh} into {remote_path}")
    except Exception as e:
        log(f"ERROR fetching {name}: {e}")
    finally:
        await page.close()

async def fetch_all_tropicaltidbits(browser):
    for cfg in TROPICAL_MODELS:
        await fetch_tropicaltidbits(
            browser,
            cfg["name"],
            cfg["model"],
            cfg["region"],
            cfg["product"]
        )

# ==========================
# PIVOTAL WEATHER CONFIG
# ==========================
PIVOTAL_MODELS = [
    {
        "name": "ECMWF - Sfc Wind/MSLP",
        "model": "ecmwf",
        "product": "sfcwind_mslp",
        "region": "us_ne"
    },
]

# ==========================
# PIVOTAL WEATHER FETCH (formatted like TropicalTidbits)
# ==========================
def fetch_pivotalweather(name, model, product, region):
    try:
        ny_tz = pytz.timezone("America/New_York")
        now = datetime.now(ny_tz)

        # Determine current runtime (00, 06, 12, 18)
        cycles = [0, 6, 12, 18]
        cycle_hour = max([ch for ch in cycles if ch <= now.hour], default=18)
        runtime = now.strftime("%Y%m%d") + f"{cycle_hour:02d}"

        # Previous 6-hour cycle
        prev_time = now.replace(hour=cycle_hour) - timedelta(hours=6)
        prev_cycle_hour = (cycle_hour - 6) % 24
        prev_runtime = prev_time.strftime("%Y%m%d") + f"{prev_cycle_hour:02d}"

        runtimes = [runtime, prev_runtime]

        for run_id in runtimes:
            for fh in FORECAST_HOURS:
                try:
                    # Construct the URL
                    url = (
                        f"https://m1o.pivotalweather.com/maps/models/"
                        f"{model}_full/{run_id}/{fh:03d}/{product}.{region}.png"
                    )

                    # Build the desired filename and folder structure
                    filename = f"{run_id}_{model}_{product}_{region}_{fh}.png"
                    local_path = os.path.join(TEMP_DIR, filename)
                    remote_path = f"{AZURE_PREFIX}Models/{run_id}/{model}/{filename}"

                    # Download image directly
                    urllib.request.urlretrieve(url, local_path)

                    # Validate download size (skip empty PNGs)
                    if os.path.exists(local_path) and os.path.getsize(local_path) < 10000:
                        log(f"SKIPPED (empty file): {filename}")
                        os.remove(local_path)
                        continue
                    # Upload to Azure
                    save_to_repository(local_path, remote_path)
                except Exception as e:
                    log(f"ERROR fetching Pivotal {model} fh={fh} run={run_id}: {e}")
    except Exception as e:
        log(f"ERROR in fetch_pivotalweather({name}): {e}")

# ==========================
# PIVOTAL WEATHER FETCH (all configs)
# ==========================
def fetch_all_pivotalweather():
    for cfg in PIVOTAL_MODELS:
        fetch_pivotalweather(
            cfg["name"],
            cfg["model"],
            cfg["product"],
            cfg["region"]
        )


# ==========================
# NWS FETCH
# ==========================
def fetch_nws(station_name, nws_url):
    try:
        if not nws_url:
            return

        ts = datetime.now().strftime("%H%M%S_%Y%m%d")
        run_time = datetime.now().strftime("%H_%Y%m%d")
        filename = os.path.join(TEMP_DIR, f"{ts} - {station_name}-NWS.png")

        urllib.request.urlretrieve(nws_url, filename)

        remote_path = f"{AZURE_PREFIX}{station_name}/NWS/{run_time}/{os.path.basename(filename)}"
        save_to_repository(filename, remote_path)

    except Exception as e:
        log(f"ERROR in fetch_nws({station_name}): {e!r}")


# ==========================
# PETSS FETCH
# ==========================
def fetch_petss(station_name, urls):
    try:
        ts = datetime.now().strftime("%H%M%S_%Y%m%d")
        run_time = datetime.now().strftime("%H_%Y%m%d")

        for label, petss_url in urls.items():
            if not petss_url:
                continue

            try:
                filename = os.path.join(TEMP_DIR, f"{ts} - {station_name}-{label}.png")
                urllib.request.urlretrieve(petss_url, filename)

                try:
                    img = cv2.imread(filename)
                    if img is not None:
                        cv2.putText(
                            img,
                            label,
                            (10, 20),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.5,
                            (0, 0, 0),
                            2,
                            cv2.LINE_AA
                        )
                        cv2.imwrite(filename, img)
                except Exception as e:
                    log(f"WARNING: Could not annotate {station_name} {label}: {e}")

                remote_path = f"{AZURE_PREFIX}{station_name}/PETSS/{run_time}/{os.path.basename(filename)}"
                save_to_repository(filename, remote_path)

            except Exception as e:
                log(f"ERROR fetching PETSS {station_name} {label}: {e}")

    except Exception as e:
        log(f"ERROR in fetch_petss({station_name}): {e!r}")

# ==========================
# MAIN FETCH
# ==========================
async def fetch_once():
    log("Fetch cycle started.")
    browser_path = find_browser()
    browser = await launch(
        headless=True,
        executablePath=browser_path,
        args=["--disable-gpu", "--no-first-run", "--no-default-browser-check"]
    )

    try:
        valid_dates = filter_dates(DATE_LIST)
        if not valid_dates:
            log("No valid dates within the allowed window. Skipping cycle.")
            return

        for STATION_NAME, STATION_CODE, NWS_URL, PETSS_URL, ETSURGE_URL, PETSS_GEFS_URL in STATIONS:
            await fetch_stevens(browser, STATION_NAME, STATION_CODE, valid_dates, DROPDOWN_VALUE)
            #fetch_nws(STATION_NAME, NWS_URL)
            fetch_petss(STATION_NAME, {
                "PETSS": PETSS_URL,
                "ETSURGE": ETSURGE_URL,
                "PETSS_GEFS": PETSS_GEFS_URL
            })

        await fetch_all_tropicaltidbits(browser)
        fetch_all_pivotalweather()
        for fpath in TEMP_FILES[:]:
            try:
                os.remove(fpath)
            except Exception as e:
                log(f"WARNING: Could not delete {fpath}: {e}")
            finally:
                TEMP_FILES.remove(fpath)

        cleanup_old_repository_files()
        git_publish_repository()
        log("Fetch cycle completed.")

    except Exception as e:
        log(f"ERROR: {e!r}")
    finally:
        await browser.close()


# ==========================
# ENTRY POINT
# ==========================
if __name__ == "__main__":
    try:
        asyncio.run(fetch_once())
    except KeyboardInterrupt:
        log("Stopped by user.")
