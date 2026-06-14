import ctypes
from ctypes import wintypes

import pyautogui
import time
import cv2
import numpy as np
from PIL import ImageGrab
from functools import partial
import pygetwindow as gw
import pytesseract
import os
import sys
import base64
import subprocess
import winsound

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
ImageGrab.grab = partial(ImageGrab.grab, all_screens=True)

# Create debug folder if it doesn't exist
DEBUG_FOLDER = "debug"
os.makedirs(DEBUG_FOLDER, exist_ok=True)

print("Auto-Retry started... Press Ctrl+C to stop\n")

TARGET_WORDS = ["retry", "accept all", "accept", "allow"]
SUBMIT_WORDS = ["submit"]
PERMISSION_DIALOG_PHRASE = "allow write access"
IMPLEMENTATION_PLAN_PHRASE = "implementation plan"
# Window activation rules (first match wins). Antigravity often omits the app name from the title
# (e.g. "Fixing Job Application Er...") so process_name is used as a fallback.
WINDOW_MATCH_RULES = (
    {"keyword": "Antigravity", "process_name": "Antigravity"},
    {"keyword": "Cursor", "process_name": "Cursor"},
)
# For "Implementation Plan" the chat is often in a browser; activate that first so keys go to the chat, not the IDE.
IMPLEMENTATION_PLAN_WINDOW_RULES = (
    {"keyword": "Claude"},
    {"keyword": "ChatGPT"},
    {"keyword": "Chrome"},
    {"keyword": "Google Chrome"},
    {"keyword": "Edge"},
    {"keyword": "Firefox"},
    {"keyword": "Brave"},
    {"keyword": "Opera"},
    {"keyword": "Antigravity", "process_name": "Antigravity"},
    {"keyword": "Cursor", "process_name": "Cursor"},
)
CONTINUE_MESSAGE = "Continue"


def ocr_full_screen_text_lower(screenshot_cv):
    gray = cv2.cvtColor(screenshot_cv, cv2.COLOR_BGR2GRAY)
    return pytesseract.image_to_string(gray, config="--oem 3 --psm 11").lower()


def screen_has_implementation_plan(screenshot_cv):
    return IMPLEMENTATION_PLAN_PHRASE in ocr_full_screen_text_lower(screenshot_cv)


def _pids_for_process_names(process_names):
    """Return PIDs whose executable base name matches (case-insensitive, .exe optional)."""
    wanted = {name.lower().removesuffix(".exe") for name in process_names if name}
    if not wanted:
        return set()

    TH32CS_SNAPPROCESS = 0x00000002
    kernel32 = ctypes.windll.kernel32

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot in (0, -1):
        return set()

    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
    pids = set()
    try:
        if kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            while True:
                exe = entry.szExeFile.lower().removesuffix(".exe")
                if exe in wanted:
                    pids.add(entry.th32ProcessID)
                if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                    break
    finally:
        kernel32.CloseHandle(snapshot)
    return pids


def _window_process_id(win):
    pid = wintypes.DWORD()
    ctypes.windll.user32.GetWindowThreadProcessId(win._hWnd, ctypes.byref(pid))
    return pid.value


def _find_window_for_rule(rule, windows):
    keyword = rule["keyword"]
    keyword_lower = keyword.lower()
    matches = [w for w in windows if keyword_lower in (w.title or "").lower()]
    if matches:
        return matches[0], f"title:{keyword}"

    process_name = rule.get("process_name")
    if not process_name:
        return None, None

    target_pids = _pids_for_process_names((process_name,))
    if not target_pids:
        return None, None

    for win in windows:
        title = (win.title or "").strip()
        if title and _window_process_id(win) in target_pids:
            return win, f"process:{process_name}"

    return None, None


def activate_first_matching_window(rules, label_for_log):
    windows = gw.getAllWindows()
    for rule in rules:
        win, matched_by = _find_window_for_rule(rule, windows)
        if win is None:
            continue
        if win.isMinimized:
            win.restore()
        win.activate()
        time.sleep(0.5)
        print(f"✅ Window activated ({matched_by}) — {label_for_log}")
        print(f"   Title: {win.title[:120]}{'…' if len(win.title) > 120 else ''}")
        return win
    print(f"⚠️  No window matched: {label_for_log}")
    return None


def activate_target_window():
    return activate_first_matching_window(WINDOW_MATCH_RULES, "retry / IDE")


def activate_implementation_plan_window():
    return activate_first_matching_window(
        IMPLEMENTATION_PLAN_WINDOW_RULES,
        "browser or chat (Implementation Plan)",
    )


def set_clipboard_windows(text: str) -> None:
    """Set clipboard as Unicode text via PowerShell (avoids 64-bit ctypes GlobalAlloc/GlobalLock bugs)."""
    if not text:
        raise ValueError("empty clipboard text")
    b64 = base64.standard_b64encode(text.encode("utf-16-le")).decode("ascii")
    ps = (
        "$b=[Convert]::FromBase64String('%s'); "
        "Set-Clipboard -Value ([Text.Encoding]::Unicode.GetString($b))"
    ) % b64
    creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Sta", "-Command", ps],
        capture_output=True,
        text=True,
        creationflags=creation,
    )
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()
        raise OSError(f"Set-Clipboard failed (exit {r.returncode}): {err}")


def paste_text_then_enter(text):
    """Chromium / many apps ignore pyautogui.write(); Ctrl+V from clipboard is reliable."""
    if sys.platform == "win32":
        set_clipboard_windows(text)
    else:
        raise RuntimeError("Clipboard paste is only implemented for Windows in this script")
    time.sleep(0.12)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.25)
    pyautogui.press("enter")


def respond_to_implementation_plan():
    """When 'Implementation Plan' is visible: foreground browser/chat, paste Continue, Enter."""
    winsound.Beep(1000, 300)
    print("\n📋 Implementation Plan on screen — continuing in 5 seconds...", end="", flush=True)
    for i in range(5, 0, -1):
        print(f" {i}", end="", flush=True)
        time.sleep(1)
    print()

    if activate_implementation_plan_window() is None:
        return False

    time.sleep(0.4)
    paste_text_then_enter(CONTINUE_MESSAGE)
    print(f"✅ Pasted '{CONTINUE_MESSAGE}' (Ctrl+V) and pressed Enter")
    return True


def text_matches_target(text, target_words):
    text = text.strip().lower()
    for target in target_words:
        if target in text:
            return target
    return None


def screen_has_permission_dialog(screenshot_cv):
    return PERMISSION_DIALOG_PHRASE in ocr_full_screen_text_lower(screenshot_cv)


def grab_screenshot_cv():
    screenshot = ImageGrab.grab()
    screenshot_np = np.array(screenshot)
    return cv2.cvtColor(screenshot_np, cv2.COLOR_RGB2BGR)


def click_matching_button(screenshot_cv, target_words, label="button"):
    """Return True if a matching button was clicked (blue region or OCR fallback)."""
    hsv = cv2.cvtColor(screenshot_cv, cv2.COLOR_BGR2HSV)
    lower_blue = np.array([100, 120, 120])
    upper_blue = np.array([130, 255, 255])
    blue_mask = cv2.inRange(hsv, lower_blue, upper_blue)
    contours, _ = cv2.findContours(blue_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if 50 < w < 300 and 20 < h < 80:
            roi = screenshot_cv[y : y + h, x : x + w]
            roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            roi_inv = cv2.bitwise_not(roi_gray)
            roi_inv = cv2.resize(roi_inv, None, fx=3, fy=3)

            text = pytesseract.image_to_string(roi_inv, config="--oem 3 --psm 8").strip().lower()
            print(f"  Blue region at ({x},{y}) {w}x{h} → OCR: '{text}'")

            debug_blue_path = os.path.join(DEBUG_FOLDER, f"debug_blue_{x}_{y}.png")
            cv2.imwrite(debug_blue_path, roi)

            matched = text_matches_target(text, target_words)
            if matched:
                click_x = x + w // 2
                click_y = y + h // 2
                print(f"✅ Clicking '{matched}' {label} at ({click_x}, {click_y})")
                pyautogui.moveTo(click_x, click_y, duration=0.4)
                time.sleep(0.3)
                pyautogui.click()
                return True

    gray = cv2.cvtColor(screenshot_cv, cv2.COLOR_BGR2GRAY)
    data = pytesseract.image_to_data(
        gray, config="--oem 3 --psm 11", output_type=pytesseract.Output.DICT
    )
    words = [w.strip().lower() for w in data["text"]]

    for i, word in enumerate(words):
        matched = text_matches_target(word, target_words)
        if matched and int(data["conf"][i]) > 30:
            x = data["left"][i]
            y = data["top"][i]
            w_px = data["width"][i]
            h_px = data["height"][i]

            if matched == "accept" and i + 1 < len(words) and words[i + 1] == "all":
                x2 = data["left"][i + 1] + data["width"][i + 1]
                w_px = x2 - x
                matched = "accept all"

            click_x = x + w_px // 2
            click_y = y + h_px // 2
            print(f"✅ Fallback OCR found '{matched}' {label} at ({click_x}, {click_y})")
            pyautogui.moveTo(click_x, click_y, duration=0.4)
            time.sleep(0.3)
            pyautogui.click()
            return True

    return False


def click_submit_if_present(screenshot_cv=None):
    """Click Submit on permission dialogs (e.g. Allow write access)."""
    if screenshot_cv is None:
        screenshot_cv = grab_screenshot_cv()
    return click_matching_button(screenshot_cv, SUBMIT_WORDS, label="Submit button")


def find_and_click_retry():
    # Beep and wait before stealing focus
    winsound.Beep(1000, 300)
    print("\n🔔 Checking in 5 seconds...", end="", flush=True)
    for i in range(5, 0, -1):
        print(f" {i}", end="", flush=True)
        time.sleep(1)
    print()

    win = activate_target_window()
    if win is None:
        return False

    screenshot_cv = grab_screenshot_cv()

    debug_full_path = os.path.join(DEBUG_FOLDER, "debug_full.png")
    cv2.imwrite(debug_full_path, screenshot_cv)
    print(f"📸 Full screenshot saved to {debug_full_path}")

    permission_dialog = screen_has_permission_dialog(screenshot_cv)
    primary_clicked = click_matching_button(screenshot_cv, TARGET_WORDS, label="button")
    submit_clicked = False

    if primary_clicked or permission_dialog:
        time.sleep(0.6)
        submit_clicked = click_submit_if_present(grab_screenshot_cv())
        if submit_clicked:
            print("✅ Submit button clicked")
        elif permission_dialog:
            print("⚠️  Permission dialog visible but Submit not found")

    if primary_clicked or submit_clicked:
        return True

    # Strategy 3: "Implementation Plan" on screen → foreground chat/browser, paste Continue, Enter
    if screen_has_implementation_plan(screenshot_cv):
        print("✅ Strategy 3: 'Implementation Plan' found — sending Continue")
        if activate_implementation_plan_window() is None:
            return False
        time.sleep(0.4)
        paste_text_then_enter(CONTINUE_MESSAGE)
        print(f"✅ Strategy 3: Pasted '{CONTINUE_MESSAGE}' (Ctrl+V) and pressed Enter")
        return True

    return False

try:
    while True:
        screenshot = ImageGrab.grab()
        screenshot_np = np.array(screenshot)
        screenshot_cv = cv2.cvtColor(screenshot_np, cv2.COLOR_RGB2BGR)

        if screen_has_implementation_plan(screenshot_cv):
            done = respond_to_implementation_plan()
            if done:
                print("⏳ Waiting after continue...")
                time.sleep(120.0)
            else:
                print(".", end="", flush=True)
                time.sleep(60.0)
            continue

        clicked = find_and_click_retry()
        if clicked:
            print("✅ Button clicked, waiting...")
            time.sleep(120.0)
        else:
            print(".", end="", flush=True)
            time.sleep(60.0)

except KeyboardInterrupt:
    print("\nStopped.")
except Exception as e:
    print(f"\nError: {e}")