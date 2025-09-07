import cv2
import numpy as np

def block_detect(image, logo_template, logo_hist, debug=False):
    """
    Detect row blocks in the image that contain the given logo.
    Args:
        image: BGR/NumPy image
        logo_template: preselected logo ROI
        logo_hist: precomputed HSV histogram of logo
        debug: whether to print debug info
    Returns:
        result_img: BGR image with rectangles drawn
        blocks: list of bounding boxes [(x, y, w, h)]
    """
    orig = image.copy()
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Threshold & morphological closing to get horizontal lines
    _, thresh = cv2.threshold(gray, 250, 255, cv2.THRESH_BINARY_INV)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)

    # Detect horizontal lines
    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (50, 1))
    horizontal_lines = cv2.morphologyEx(closed, cv2.MORPH_OPEN, horizontal_kernel)
    contours, _ = cv2.findContours(horizontal_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    blocks = []
    lh, lw = logo_template.shape[:2]
    height, width = orig.shape[:2]
    row_count = 0

    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        area = cv2.contourArea(cnt)
        if area < 1000:
            continue
        aspect_ratio = w / float(h)
        if w > 50 and w > 0.8*width and h > 20 and aspect_ratio > 2:
            row_count += 1
            row_crop = orig[y:y+h, x:x+w]
            left_part = row_crop[:, :int(0.3*row_crop.shape[1])]

            # ---- LOGO CHECK ----
            best_score = 0
            lp_h, lp_w = left_part.shape[:2]
            step_x = max(lw//2, 10)
            step_y = max(lh//2, 10)

            for x_off in range(0, lp_w - lw, step_x):
                for y_off in range(0, lp_h - lh, step_y):
                    window = left_part[y_off:y_off+lh, x_off:x_off+lw]
                    if window.shape[0] != lh or window.shape[1] != lw:
                        continue
                    win_hsv = cv2.cvtColor(window, cv2.COLOR_BGR2HSV)
                    win_hist = cv2.calcHist([win_hsv], [0,1], None, [50,60], [0,180,0,256])
                    win_hist = cv2.normalize(win_hist, win_hist, 0, 1, cv2.NORM_MINMAX)
                    score = cv2.compareHist(logo_hist, win_hist, cv2.HISTCMP_CORREL)
                    best_score = max(best_score, score)

            if best_score > 0.5:
                cv2.rectangle(orig, (x, y), (x+w, y+h), (0, 0, 255), 2)  # red if logo detected
                blocks.append((x,y,w,h))
            else:
                cv2.rectangle(orig, (x, y), (x+w, y+h), (0, 255, 0), 2)  # green if no logo

            if debug:
                print(f"Row {row_count}: score={best_score:.2f}")

    return orig, blocks
