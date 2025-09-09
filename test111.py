
import cv2
import numpy as np

class RectangleDetector:
    def __init__(self, min_area=100):
        self.min_area = min_area
        
    def detect_rectangles(self, image_path):
        image = cv2.imread(image_path)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Threshold & morphological closing to get horizontal lines
        # Binary threshold (inverse for light background)
        _, thresh = cv2.threshold(gray, 250, 255, cv2.THRESH_BINARY)

        tolerance = 5
        # Apply mask to keep only those regions
        lower = np.array([max(0, 225 - tolerance)], dtype=np.uint8)
        upper = np.array([min(255, 225 + tolerance)], dtype=np.uint8)

        mask = cv2.inRange(image, lower, upper)

        inverted = cv2.bitwise_not(image)
        # Preprocessing
        blur = cv2.GaussianBlur(thresh, (5, 5), 0)
        # _, thresh = cv2.threshold(gray, 250, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        cv2.imshow("inverted", blur)
        
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        rectangles = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if area >= self.min_area:
                x, y, w, h = cv2.boundingRect(contour)
                rectangles.append({
                    'coordinates': (x, y, w, h),
                    'area': area,
                    'center': (x + w//2, y + h//2)
                })
        
        return rectangles, image
    
    def get_top_n(self, rectangles, n=10):
        return sorted(rectangles, key=lambda x: x['area'], reverse=True)[:n]
    
    def visualize_results(self, image, top_rectangles):
        result_image = image.copy()
        colors = [(0, 255, 0), (255, 0, 0), (0, 0, 255), (255, 255, 0), 
                 (255, 0, 255), (0, 255, 255), (128, 0, 0), (0, 128, 0), 
                 (0, 0, 128), (128, 128, 0)]
        
        for i, rect in enumerate(top_rectangles):
            x, y, w, h = rect['coordinates']
            color = colors[i % len(colors)]
            
            # Draw rectangle
            cv2.rectangle(result_image, (x, y), (x + w, y + h), color, 3)
            
            # Draw rank and area
            cv2.putText(result_image, f"#{i+1}", (x, y-30), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.putText(result_image, f"{rect['area']:.0f}", (x, y-10), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        return result_image

# Usage example
detector = RectangleDetector(min_area=15000)
all_rectangles, original_image = detector.detect_rectangles('test/test2.png')
top_10_rectangles = detector.get_top_n(all_rectangles, 10)
result_image = detector.visualize_results(original_image, top_10_rectangles)

# Display
cv2.imshow('Top 10 Rectangles by Area', result_image)
cv2.waitKey(0)
cv2.destroyAllWindows()