import cv2
import numpy as np


class BlockDetector:
    def __init__(self, min_area=100, logo_hist=None, logo_size=None):
        self.min_area = min_area
        self.logo_hist = logo_hist
        self.logo_size = logo_size  # (h, w)
        self.thresh = None

    def detect_rectangles(self, image):
        """
        Detect rectangles (blocks) from an image.
        Returns list of rectangles and the original image.
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Threshold
        _, thresh = cv2.threshold(gray, 250, 255, cv2.THRESH_BINARY_INV)
        self.thresh = thresh
        inverted = cv2.bitwise_not(thresh)

        tolerance = 5
        # Apply mask to keep only those regions
        lower = np.array([max(0, 225 - tolerance)], dtype=np.uint8)
        upper = np.array([min(255, 225 + tolerance)], dtype=np.uint8)

        mask = cv2.inRange(image, lower, upper)
        
        contours, _ = cv2.findContours(
            inverted, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        contours1, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                
        headers = []
        rectangles = []

        for contour in contours1:
            area = cv2.contourArea(contour)
            if area >= 15000:
                x, y, w, h = cv2.boundingRect(contour)
                headers.append({
                    'coordinates': (x, y, w, h),
                    'area': area,
                    'center': (x + w // 2, y + h // 2)
                })
                
        for contour in contours:
            area = cv2.contourArea(contour)
            if area >= self.min_area:
                x, y, w, h = cv2.boundingRect(contour)
                rectangles.append({
                    'coordinates': (x, y, w, h),
                    'area': area,
                    'center': (x + w // 2, y + h // 2)
                })

        # FIXED: Sort by y-coordinate (position in image)
        blocks = sorted(rectangles, key=lambda b: b['coordinates'][1])  # Sort by y-coordinate
        headers = sorted(headers, key=lambda h: h['coordinates'][1])    # Sort by y-coordinate
        
        return blocks, headers, image

    def get_top_n(self, rectangles, n=10):
        """
        Get top N rectangles sorted by area.
        """
        return sorted(rectangles, key=lambda x: x['area'], reverse=True)[:n]

    def check_logo_in_block(self, block_image, threshold=0.7):
        """
        Check if logo exists in left 30% of block.
        Returns (bool, best_score).
        """
        if self.logo_hist is None or self.logo_size is None:
            return False, 0.0

        lh, lw = self.logo_size
        h, w = block_image.shape[:2]
        left_part = block_image[:, :int(0.3 * w)]

        best_score = 0
        step_x = max(lw // 2, 10)
        step_y = max(lh // 2, 10)

        for x_off in range(0, left_part.shape[1] - lw, step_x):
            for y_off in range(0, left_part.shape[0] - lh, step_y):
                window = left_part[y_off:y_off + lh, x_off:x_off + lw]
                if window.shape[:2] != (lh, lw):
                    continue
                win_hsv = cv2.cvtColor(window, cv2.COLOR_BGR2HSV)
                win_hist = cv2.calcHist([win_hsv], [0, 1], None,
                                        [50, 60], [0, 180, 0, 256])
                win_hist = cv2.normalize(win_hist, win_hist, 0, 1, cv2.NORM_MINMAX)
                score = cv2.compareHist(self.logo_hist, win_hist, cv2.HISTCMP_CORREL)
                best_score = max(best_score, score)

        return best_score > threshold, best_score

    def visualize_results(self, image, top_rectangles, headers):
        """
        Draw rectangles with red (logo) / green (no logo).
        """
        result_image = image.copy()
        detected = []
        odds_blocks = []

        for rect in top_rectangles:
            x, y, w, h = rect['coordinates']
            block_crop = image[y:y + h, x:x + w]

            has_logo, score = self.check_logo_in_block(block_crop)
            odds_blocks = []

            if has_logo:
                color = (0, 0, 255)  # red if logo detected
                text = f"Logo {score:.2f}"
                detected.append(rect)
                odds_blocks = self.detect_odds_blocks(block_crop)

                for odds_block in odds_blocks:
                    tx, ty, tw, th = odds_block['coordinates']
                    cv2.rectangle(result_image, (x + tx, y + ty), (x + tx + tw, y + ty + th), (255, 0, 0), 3)
            else:
                color = (0, 255, 0)  # green if no logo
                text = f"NoLogo {score:.2f}"

            cv2.rectangle(result_image, (x, y), (x + w, y + h), color, 3)
            # cv2.putText(result_image, text, (x, y - 5),
            #             cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        for header in headers:
            x, y, w, h = header['coordinates']
            cv2.rectangle(result_image, (x, y), (x + w, y + h), (255,0,0), 3)

        return result_image, detected

    def detect_odds_blocks(self, image):
        # image should be row block image
        odds_blocks = []
        h, w = image.shape[:2]
        x_start = int(w * 0.4)
        cropped = image[:, x_start:w]
        gray = cv2.cvtColor(cropped, cv2.COLOR_BGR2GRAY)

        # Threshold
        _, thresh = cv2.threshold(gray, 250, 255, cv2.THRESH_BINARY_INV)
        cv2.imwrite("cropped.png", thresh)

        contours, _ = cv2.findContours(
            thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        for contour in contours:
            area = cv2.contourArea(contour)
            if area >= 50 * 30:
                tx, ty, tw, th = cv2.boundingRect(contour)
                x = x_start + tx
                y = ty
                odds_blocks.append({
                    'coordinates': (x, y, tw, th),
                    'area': area,
                })
        
        return odds_blocks