import cv2
import numpy as np
import mss
import time

# Parameters
DIFF_THRESHOLD = 5000  # Change sensitivity
FPS = 10

# Initialize screen capture
sct = mss.mss()
monitor = sct.monitors[1]  # primary monitor

# Grab full screen for ROI selection
full_screen = np.array(sct.grab(monitor))

# Let user select ROI with mouse
roi = cv2.selectROI("Select ROI", full_screen, False, False)
cv2.destroyWindow("Select ROI")

x, y, w, h = roi
ROI = {'top': y, 'left': x, 'width': w, 'height': h}

def detect_scroll(prev_frame, curr_frame, threshold=DIFF_THRESHOLD):
    """Return True if scrolling detected, False if stopped"""
    diff = cv2.absdiff(prev_frame, curr_frame)
    gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
    non_zero_count = cv2.countNonZero(gray)
    return non_zero_count > threshold

# Capture initial frame
prev_frame = np.array(sct.grab(ROI))

while True:
    start_time = time.time()
    curr_frame = np.array(sct.grab(ROI))

    scrolling = detect_scroll(prev_frame, curr_frame)
    status_text = "Scrolling" if scrolling else "Stopped"
    
    # Visualize
    display_frame = curr_frame.copy()
    cv2.putText(display_frame, status_text, (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
    cv2.imshow("ROI Monitor", display_frame)

    prev_frame = curr_frame

    # Limit FPS
    if cv2.waitKey(max(1, int(1000/FPS))) & 0xFF == 27:  # ESC to quit
        break

cv2.destroyAllWindows()
