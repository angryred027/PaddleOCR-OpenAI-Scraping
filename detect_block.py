import cv2
import numpy as np


# Load image
img = cv2.imread('test/test2.png')
orig = img.copy()

logo_roi = cv2.selectROI("Select Logo", orig, fromCenter=False, showCrosshair=True)
x, y, w, h = logo_roi
logo_template = orig[y:y+h, x:x+w].copy()
# Compute histogram of selected logo ROI
logo_hsv = cv2.cvtColor(logo_template, cv2.COLOR_BGR2HSV)
logo_hist = cv2.calcHist([logo_hsv], [0, 1], None, [50, 60], [0, 180, 0, 256])
logo_hist = cv2.normalize(logo_hist, logo_hist, 0, 1, cv2.NORM_MINMAX)

cv2.destroyWindow("Select Logo")

# Save logo ROI (optional)
cv2.imwrite("logo_template.png", logo_template)

# Convert to grayscale
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


# # Apply slight blur
# blur = cv2.GaussianBlur(gray, (5, 5), 0)
# Threshold to get binary image
_, thresh = cv2.threshold(gray, 250, 255, cv2.THRESH_BINARY_INV)

_, thresh = cv2.threshold(thresh, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

thresh[-1, :] = 255

cv2.imshow("thresh", thresh)

# Create horizontal kernel for detecting horizontal lines/structures
horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (50, 1))

# Apply morphological operations to detect horizontal structures
horizontal_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, horizontal_kernel)

# Find contours of horizontal structures
contours, _ = cv2.findContours(horizontal_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

# Filter and sort contours by area and position
row_boxes = []
line_positions = []
min_area = 1000  # Minimum area threshold for valid rows

row_count = 0
height, width = orig.shape[:2]
for cnt in contours:
    x, y, w, h = cv2.boundingRect(cnt)  # bounding box of the line
    line_top = y
    line_bottom = y + h
    line_center = y + h // 2
    line_positions.append((line_top, line_bottom, line_center))
    # Sort by vertical position
    line_positions = sorted(line_positions, key=lambda x: x[0])
    cv2.line(orig, (0, line_top), (orig.shape[1], line_top), (0, 0, 255), 1)  # red line
    cv2.line(orig, (0, line_bottom), (orig.shape[1], line_bottom), (0, 0, 255), 1)  # red line

    area = cv2.contourArea(cnt)
    if area > 1000:  # filter small noise
        continue

    # Get bounding box
    x, y, w, h = cv2.boundingRect(cnt)
    aspect_ratio = w / float(h)
    if w > 50 and w > 0.8 * width and h > 20 and aspect_ratio > 2:  # adjust thresholds for your rows
        row_count += 1
        cv2.rectangle(orig, (x, y), (x + w, y + h), (0, 255, 0), 2)
        row_crop = orig[y:y+h, x:x+w]
        left_part = row_crop[:, :int(0.3 * row_crop.shape[1])]

        # ---- LOGO CHECK START ----
        left_part = row_crop[:, :int(0.3 * row_crop.shape[1])]

        # Precompute logo histogram once (outside loop)
        # logo_hist is defined globally after ROI selection
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

        if best_score > 0.5:  # threshold
            print(f"Row {row_count}: NESINE logo detected (best={best_score:.2f})")
            cv2.rectangle(orig, (x, y), (x + w, y + h), (0, 0, 255), 2)  # red if logo detected
        else:
            print(f"Row {row_count}: No logo (best={best_score:.2f})")
            cv2.rectangle(orig, (x, y), (x + w, y + h), (0, 255, 0), 2)  # green if no logo
        # ---- LOGO CHECK END ----

    # cv2.imwrite(f'detected.png', orig)    


# Show scaled result
cv2.imshow('Detected Rows (Scaled)', orig)
cv2.imwrite("detected.png", orig)
cv2.waitKey(0)
cv2.destroyAllWindows()
cv2.waitKey(0)
cv2.destroyAllWindows()
