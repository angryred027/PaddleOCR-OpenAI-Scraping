import cv2
import numpy as np

# Load image
img = cv2.imread('test/test3.png')
orig = img.copy()

# ---- SELECT LOGO ROI ----
logo_roi = cv2.selectROI("Select Logo", orig, fromCenter=False, showCrosshair=True)
x, y, w, h = logo_roi
logo_template = orig[y:y+h, x:x+w].copy()

# Compute histogram of selected logo ROI
logo_hsv = cv2.cvtColor(logo_template, cv2.COLOR_BGR2HSV)
logo_hist = cv2.calcHist([logo_hsv], [0, 1], None, [50, 60], [0, 180, 0, 256])
logo_hist = cv2.normalize(logo_hist, logo_hist, 0, 1, cv2.NORM_MINMAX)
cv2.destroyWindow("Select Logo")

# Convert to grayscale
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

# Threshold to get binary image
_, thresh = cv2.threshold(gray, 250, 255, cv2.THRESH_BINARY_INV)
_, thresh = cv2.threshold(thresh, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
thresh[-1, :] = 255  # avoid bottom merge
cv2.imshow("thresh", thresh)

# Horizontal kernel for detecting horizontal structures
horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (50, 1))
horizontal_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, horizontal_kernel)

# Find contours of horizontal structures
contours, _ = cv2.findContours(horizontal_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

# Get all line y-positions (top of each contour)
line_positions = []
for cnt in contours:
    x, y, w, h = cv2.boundingRect(cnt)
    line_positions.append(y)
line_positions = sorted(line_positions)

height, width = orig.shape[:2]

# Add top line if first line >50px from top
if line_positions and line_positions[0] > 50:
    line_positions.insert(0, 0)
# Add bottom line if last line < height-50
if line_positions and height - line_positions[-1] > 50:
    line_positions.append(height)

# Draw red lines
for y in line_positions:
    cv2.line(orig, (0, y), (width, y), (0, 0, 255), 1)

# Process blocks between consecutive lines
block_count = 0
for i in range(len(line_positions) - 1):
    top = line_positions[i]
    bottom = line_positions[i+1]
    block_height = bottom - top
    if block_height < 50:
        continue  # ignore small blocks

    block_count += 1
    cv2.rectangle(orig, (0, top), (width, bottom), (0, 255, 0), 2)  # optional green highlight

    # ---- LOGO CHECK ----
    row_crop = orig[top:bottom, :]
    left_part = row_crop[:, :int(0.3 * row_crop.shape[1])]

    lh, lw = logo_template.shape[:2]
    lp_h, lp_w = left_part.shape[:2]

    best_score = 0
    step_x = max(lw // 2, 10)
    step_y = max(lh // 2, 10)

    for x_off in range(0, lp_w - lw, step_x):
        for y_off in range(0, lp_h - lh, step_y):
            window = left_part[y_off:y_off+lh, x_off:x_off+lw]
            if window.shape[0] != lh or window.shape[1] != lw:
                continue
            win_hsv = cv2.cvtColor(window, cv2.COLOR_BGR2HSV)
            win_hist = cv2.calcHist([win_hsv], [0, 1], None, [50, 60], [0, 180, 0, 256])
            win_hist = cv2.normalize(win_hist, win_hist, 0, 1, cv2.NORM_MINMAX)
            score = cv2.compareHist(logo_hist, win_hist, cv2.HISTCMP_CORREL)
            best_score = max(best_score, score)

    if best_score > 0.5:
        print(f"Block {block_count}: NESINE logo detected (best={best_score:.2f})")
        cv2.rectangle(orig, (0, top), (width, bottom), (0, 0, 255), 2)  # red if logo
    else:
        print(f"Block {block_count}: No logo (best={best_score:.2f})")

# Output
print(f"Total red lines detected: {len(line_positions)}")
print(f"Total valid blocks detected: {block_count}")

# Show result
cv2.imshow('Detected Blocks', orig)
cv2.imwrite("detected.png", orig)
cv2.waitKey(0)
cv2.destroyAllWindows()
