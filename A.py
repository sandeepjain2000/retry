import pyautogui
import time
import cv2
import numpy as np
from PIL import ImageGrab
from functools import partial
import pygetwindow as gw
import pytesseract
import os
import winsound

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
ImageGrab.grab = partial(ImageGrab.grab, all_screens=True)

# Create debug folder if it doesn't exist
DEBUG_FOLDER = "debug"
os.makedirs(DEBUG_FOLDER, exist_ok=True)

print("Auto-Retry started... Press Ctrl+C to stop\n")

TARGET_WORDS = ["retry", "accept all", "accept", "allow"]

def text_matches_target(text):
    text = text.strip().lower()
    for target in TARGET_WORDS:
        if target in text:
            return target
    return None

def find_and_click_retry():
    # Beep and wait before stealing focus
    winsound.Beep(1000, 300)
    print("\n🔔 Checking in 5 seconds...", end="", flush=True)
    for i in range(5, 0, -1):
        print(f" {i}", end="", flush=True)
        time.sleep(1)
    print()

    # Activate Antigravity window
    windows = [w for w in gw.getAllWindows() if "Antigravity" in w.title]
    if windows:
        win = windows[0]
        if win.isMinimized:
            win.restore()
        win.activate()
        time.sleep(0.5)
        print("✅ Window activated")
    else:
        print("⚠️  Antigravity window not found")
        return False

    # Full screenshot
    screenshot = ImageGrab.grab()
    screenshot_np = np.array(screenshot)
    screenshot_cv = cv2.cvtColor(screenshot_np, cv2.COLOR_RGB2BGR)

    # --- Save debug screenshot to debug folder ---
    debug_full_path = os.path.join(DEBUG_FOLDER, "debug_full.png")
    cv2.imwrite(debug_full_path, screenshot_cv)
    print(f"📸 Full screenshot saved to {debug_full_path}")

    # Strategy 1: detect blue button pixels
    hsv = cv2.cvtColor(screenshot_cv, cv2.COLOR_BGR2HSV)
    lower_blue = np.array([100, 120, 120])
    upper_blue = np.array([130, 255, 255])
    blue_mask = cv2.inRange(hsv, lower_blue, upper_blue)

    # Find contours of blue regions
    contours, _ = cv2.findContours(blue_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if 50 < w < 300 and 20 < h < 80:
            # Crop and OCR just this region
            roi = screenshot_cv[y:y+h, x:x+w]
            roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            roi_inv = cv2.bitwise_not(roi_gray)
            roi_inv = cv2.resize(roi_inv, None, fx=3, fy=3)

            text = pytesseract.image_to_string(roi_inv, config='--oem 3 --psm 8').strip().lower()
            print(f"  Blue region at ({x},{y}) {w}x{h} → OCR: '{text}'")

            # Save blue region debug image to debug folder
            debug_blue_path = os.path.join(DEBUG_FOLDER, f"debug_blue_{x}_{y}.png")
            cv2.imwrite(debug_blue_path, roi)

            matched = text_matches_target(text)
            if matched:
                click_x = x + w // 2
                click_y = y + h // 2
                print(f"✅ Clicking '{matched}' button at ({click_x}, {click_y})")
                pyautogui.moveTo(click_x, click_y, duration=0.4)
                time.sleep(0.3)
                pyautogui.click()
                return True

    # Strategy 2: fallback full-screen OCR
    gray = cv2.cvtColor(screenshot_cv, cv2.COLOR_BGR2GRAY)
    data = pytesseract.image_to_data(gray, config='--oem 3 --psm 11',
                                      output_type=pytesseract.Output.DICT)

    words = [w.strip().lower() for w in data['text']]

    for i, word in enumerate(words):
        matched = text_matches_target(word)
        if matched and int(data['conf'][i]) > 30:
            x = data['left'][i]
            y = data['top'][i]
            w_px = data['width'][i]
            h_px = data['height'][i]

            if matched == "accept" and i + 1 < len(words) and words[i + 1] == "all":
                x2 = data['left'][i + 1] + data['width'][i + 1]
                w_px = x2 - x
                matched = "accept all"

            click_x = x + w_px // 2
            click_y = y + h_px // 2
            print(f"✅ Fallback OCR found '{matched}' at ({click_x}, {click_y})")
            pyautogui.moveTo(click_x, click_y, duration=0.4)
            time.sleep(0.3)
            pyautogui.click()
            return True

    return False

try:
    while True:
        clicked = find_and_click_retry()
        if clicked:
            print("✅ Button clicked, waiting...")
            time.sleep(240.0)
        else:
            print(".", end="", flush=True)
            time.sleep(180.0)

except KeyboardInterrupt:
    print("\nStopped.")
except Exception as e:
    print(f"\nError: {e}")