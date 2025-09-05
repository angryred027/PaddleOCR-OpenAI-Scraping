import cv2
import numpy as np

# Load image
img = cv2.imread('test0.png')
orig = img.copy()

# Convert to grayscale
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


# # Apply slight blur
# blur = cv2.GaussianBlur(gray, (5, 5), 0)
# Threshold to get binary image
_, thresh = cv2.threshold(gray, 250, 255, cv2.THRESH_BINARY_INV)

_, thresh = cv2.threshold(thresh, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

cv2.imshow("abcd", thresh)

# Create horizontal kernel for detecting horizontal lines/structures
horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (50, 1))

# Apply morphological operations to detect horizontal structures
horizontal_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, horizontal_kernel)

# Find contours of horizontal structures
contours, _ = cv2.findContours(horizontal_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

# Filter and sort contours by area and position
row_boxes = []
min_area = 1000  # Minimum area threshold for valid rows

row_count = 0
height, width = orig.shape[:2]
for cnt in contours:
    area = cv2.contourArea(cnt)
    if area < 2000:  # filter small noise
        continue

    # Get bounding box
    x, y, w, h = cv2.boundingRect(cnt)
    aspect_ratio = w / float(h)
    if w > 50 and w > 0.8 * width and h > 20 and aspect_ratio > 2:  # adjust thresholds for your rows
        row_count += 1
        cv2.rectangle(orig, (x, y), (x + w, y + h), (0, 255, 0), 2)

    # cv2.imwrite(f'detected.png', orig)    


# Show scaled result
cv2.imshow('Detected Rows (Scaled)', resized)
cv2.waitKey(0)
cv2.destroyAllWindows()
cv2.waitKey(0)
cv2.destroyAllWindows()
