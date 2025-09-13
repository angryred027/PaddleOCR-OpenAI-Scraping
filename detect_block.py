import cv2
import numpy as np


class BlockDetector:
    def __init__(self, min_area=10000, logo_hist=None, logo_size=None):
        self.min_area = min_area
        self.logo_hist = logo_hist
        self.logo_size = logo_size
        self.thresh = None

    def detect_rectangles(self, image):
        if image is None or image.size == 0:
            return [], [], image
        
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 250, 255, cv2.THRESH_BINARY_INV)
        self.thresh = thresh
        inverted = cv2.bitwise_not(thresh)

        tolerance = 5
        lower = np.array([max(0, 225 - tolerance)], dtype=np.uint8)
        upper = np.array([min(255, 225 + tolerance)], dtype=np.uint8)
        mask = cv2.inRange(image, lower, upper)
        
        contours, _ = cv2.findContours(inverted, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
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

        blocks = sorted(rectangles, key=lambda b: b['coordinates'][1])
        headers = sorted(headers, key=lambda h: h['coordinates'][1])
        
        return blocks, headers, image

    def get_top_n(self, rectangles, n=10):
        return sorted(rectangles, key=lambda x: x['area'], reverse=True)[:n]
    
    def get_biggest_rectangle(self, rectangles):
        return sorted(rectangles, key=lambda x: x['area'], reverse=True)[0]

    def check_logo_in_block(self, block_image, threshold=0.7):
        if self.logo_hist is None or self.logo_size is None or block_image is None or block_image.size == 0:
            return False, 0.0

        lh, lw = self.logo_size
        h, w = block_image.shape[:2]
        
        if w < lw or h < lh:
            return False, 0.0
            
        left_part = block_image[:, :int(0.3 * w)]

        best_score = 0
        step_x = max(lw // 2, 10)
        step_y = max(lh // 2, 10)

        for x_off in range(0, max(1, left_part.shape[1] - lw), step_x):
            for y_off in range(0, max(1, left_part.shape[0] - lh), step_y):
                window = left_part[y_off:y_off + lh, x_off:x_off + lw]
                if window.shape[:2] != (lh, lw):
                    continue
                    
                try:
                    win_hsv = cv2.cvtColor(window, cv2.COLOR_BGR2HSV)
                    win_hist = cv2.calcHist([win_hsv], [0, 1], None, [50, 60], [0, 180, 0, 256])
                    win_hist = cv2.normalize(win_hist, win_hist, 0, 1, cv2.NORM_MINMAX)
                    score = cv2.compareHist(self.logo_hist, win_hist, cv2.HISTCMP_CORREL)
                    best_score = max(best_score, score)
                except Exception:
                    continue

        return best_score > threshold, best_score

    def visualize_results(self, image, top_rectangles, headers):
        if image is None or image.size == 0:
            return image, []
            
        result_image = image.copy()
        detected = []
        
        count = 0
        for rect in top_rectangles:
            x, y, w, h = rect['coordinates']
            
            if x < 0 or y < 0 or x + w > image.shape[1] or y + h > image.shape[0]:
                continue
                
            block_crop = image[y:y + h, x:x + w]
            has_logo, score = self.check_logo_in_block(block_crop)

            if has_logo:                
                color = (0, 0, 255)
                detected.append(rect)
                odds_blocks = self.detect_odds_blocks(block_crop)
                for odds_block in odds_blocks:
                    tx, ty, tw, th = odds_block['coordinates']
                    cv2.rectangle(result_image, (x + tx, y + ty), (x + tx + tw, y + ty + th), (255, 0, 0), 3)
                    
            else:
                color = (0, 255, 0)

            cv2.rectangle(result_image, (x, y), (x + w, y + h), color, 3)

        count = 0
        for header in headers:
            count += 1
            x, y, w, h = header['coordinates']
            if x >= 0 and y >= 0 and x + w <= image.shape[1] and y + h <= image.shape[0]:
                cv2.rectangle(result_image, (x, y), (x + w, y + h), (255, 0, 0), 3)

        return result_image, detected

    def detect_odds_blocks(self, image):
        if image is None or image.size == 0:
            return []
            
        odds_blocks = []
        h, w = image.shape[:2]
        x_start = int(w * 0.4)
        
        if x_start >= w:
            return []
            
        cropped = image[:, x_start:w]
        gray = cv2.cvtColor(cropped, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 250, 255, cv2.THRESH_BINARY_INV)

        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

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
        
        odds_blocks.reverse()
        return odds_blocks