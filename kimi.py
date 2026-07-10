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

# Configure Tesseract path (adjust if needed)
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
ImageGrab.grab = partial(ImageGrab.grab, all_screens=True)

# Create debug folder if it doesn't exist
DEBUG_FOLDER = "debug_kimi"
os.makedirs(DEBUG_FOLDER, exist_ok=True)

print("🤖 Kimi Chat Auto-Refresher started...")
print("Press Ctrl+C to stop\n")

# Target words/phrases to detect
TARGET_POPUP = ["got it", "upgrade"]
UP_ARROW_IMAGE = None  # We'll use OCR instead of image matching

def load_up_arrow_template():
    """Try to load up arrow template from debug folder if exists"""
    global UP_ARROW_IMAGE
    template_path = os.path.join(DEBUG_FOLDER, "up_arrow_template.png")
    if os.path.exists(template_path):
        UP_ARROW_IMAGE = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
        return True
    return False

def text_matches_target(text):
    """Check if text matches any target word/phrase"""
    text = text.strip().lower()
    for target in TARGET_POPUP:
        if target in text:
            return target
    return None

def find_up_arrow_ocr(screenshot_cv):
    """Find up arrow using OCR on the chat interface"""
    # Focus on the chat area - assuming it's in the bottom half of screen
    height, width = screenshot_cv.shape[:2]
    chat_region = screenshot_cv[height//2:, :]
    
    # Convert to grayscale
    gray = cv2.cvtColor(chat_region, cv2.COLOR_BGR2GRAY)
    
    # Try to find arrow-like patterns using edge detection
    edges = cv2.Canny(gray, 50, 150)
    
    # Look for upward pointing arrow shape using contour detection
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    for cnt in contours:
        # Get bounding box
        x, y, w, h = cv2.boundingRect(cnt)
        
        # Filter by size - up arrow should be relatively small
        if 15 < w < 60 and 15 < h < 60:
            # Check aspect ratio (should be roughly square or slightly taller)
            aspect_ratio = w / h if h > 0 else 0
            if 0.5 < aspect_ratio < 2.0:
                # Extract ROI
                roi = chat_region[y:y+h, x:x+w]
                
                # Try to detect upward arrow shape using template matching or shape analysis
                # For simplicity, we'll use OCR on the region around where arrow typically is
                # Save debug image
                debug_arrow_path = os.path.join(DEBUG_FOLDER, f"arrow_candidate_{x}_{y}.png")
                cv2.imwrite(debug_arrow_path, roi)
                
                # The actual click position (adjust offset as needed)
                click_x = x + w // 2
                click_y = y + h // 2
                
                # Since OCR might not detect arrow well, we check if this region contains
                # any text - if it doesn't, it might be the arrow
                roi_text = pytesseract.image_to_string(roi, config='--oem 3 --psm 8')
                if len(roi_text.strip()) < 2:  # No text, likely an icon/arrow
                    return click_x, click_y + height//2  # Add back the offset
    
    # Fallback: Try to find by specific location (common chat UI layout)
    # Many chat apps have the up arrow on the right side of the input
    # Let's check the right side of the screen in the bottom region
    right_region = chat_region[:, width*3//4:]
    gray_right = cv2.cvtColor(right_region, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray_right, 200, 255, cv2.THRESH_BINARY_INV)
    
    # Look for small vertical features on the right side
    contours_right, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    for cnt in contours_right:
        x, y, w, h = cv2.boundingRect(cnt)
        # Arrow is typically on the right side, near the input box
        if 15 < w < 60 and 15 < h < 60:
            return width*3//4 + x + w//2, height//2 + y + h//2
    
    return None, None

def find_and_click_up_arrow():
    """Main function to find and click the up arrow"""
    
    # Activate Kimi window
    windows = [w for w in gw.getAllWindows() if "Kimi" in w.title]
    if windows:
        win = windows[0]
        if win.isMinimized:
            win.restore()
        win.activate()
        time.sleep(1.5)
        print("✅ Kimi window activated")
    else:
        print("⚠️ Kimi window not found")
        return False
    
    # Full screenshot
    screenshot = ImageGrab.grab()
    screenshot_np = np.array(screenshot)
    screenshot_cv = cv2.cvtColor(screenshot_np, cv2.COLOR_RGB2BGR)
    
    # Save debug screenshot
    debug_full_path = os.path.join(DEBUG_FOLDER, "debug_full.png")
    cv2.imwrite(debug_full_path, screenshot_cv)
    print(f"📸 Full screenshot saved to {debug_full_path}")
    
    # Strategy 1: Look for popup first
    # Check for "Got it" or "Upgrade" in the entire screen
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
            
            # Expand the bounding box to include the full button
            x -= 20
            y -= 10
            w_px += 40
            h_px += 20
            
            click_x = x + w_px // 2
            click_y = y + h_px // 2
            
            print(f"✅ Found popup '{matched}' at ({click_x}, {click_y})")
            
            # Save debug region
            roi = screenshot_cv[y:y+h_px, x:x+w_px]
            debug_popup_path = os.path.join(DEBUG_FOLDER, f"popup_{matched}_{x}_{y}.png")
            cv2.imwrite(debug_popup_path, roi)
            
            pyautogui.moveTo(click_x, click_y, duration=0.4)
            time.sleep(0.3)
            pyautogui.click()
            
            print(f"✅ Clicked '{matched}' button")
            
            # Return True with popup flag
            return True, True
    
    # Strategy 2: Find and click up arrow
    arrow_x, arrow_y = find_up_arrow_ocr(screenshot_cv)
    
    if arrow_x and arrow_y:
        print(f"✅ Found up arrow at ({arrow_x}, {arrow_y})")
        pyautogui.moveTo(arrow_x, arrow_y, duration=0.4)
        time.sleep(0.3)
        pyautogui.click()
        print("✅ Clicked up arrow")
        return True, False
    
    # If nothing found, return False
    print("❌ Could not find up arrow")
    return False, False

try:
    while True:
        found, is_popup = find_and_click_up_arrow()
        
        if found:
            if is_popup:
                # If we clicked "Got it", wait 2 seconds then continue looking
                print("✅ Clicked popup, waiting 2 seconds...")
                time.sleep(2.0)
                continue
            else:
                # Clicked up arrow, go to sleep
                print("✅ Up arrow clicked, sleeping for 120 seconds...")
                time.sleep(120.0)
                # After sleep, continue loop to check again
                continue
        else:
            # No popup and no up arrow found, exit
            print("❌ No popup or up arrow found. Exiting script.")
            break

except KeyboardInterrupt:
    print("\n🛑 Stopped by user.")
except Exception as e:
    print(f"\n❌ Error: {e}")
    sys.exit(1)

print("Script finished.")