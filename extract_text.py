from paddleocr import PaddleOCR
import re
import cv2
import random

pattern = re.compile(r'^\d+\.\d{2}$')

# Initialize OCR only once to avoid threading issues
_ocr_instance = None

def get_ocr():
    global _ocr_instance
    if _ocr_instance is None:
        _ocr_instance = PaddleOCR(use_angle_cls=True, lang='tr', show_log=False)
    return _ocr_instance

def extract_team_name(image):
    ocr = get_ocr()
    result = ocr.ocr(image)
    texts = []
    team_names = ""
    for line in result:
        for word_info in line:
            text = word_info[1][0]   # the string
            team_names += " " + text
            texts.append(text)

    return texts, team_names

def extract_block_data(block_image):
    ocr = get_ocr()
    result = ocr.ocr(block_image)
    texts = []
    for line in result:
        for word_info in line:
            text = word_info[1][0] 
            texts.append(text)
    
    return "".join(texts)

def get_odds_data(odds_block):
    ocr = get_ocr()
    result = ocr.ocr(odds_block)
    texts = []

    for line in result:
        for word in line:
            text = word[1][0] if word[1][0] else '-'
            text = text.upper()
            texts.append(text)
        
    if len(texts) == 0:
            num = random.randint(100000, 999999)
            cv2.imwrite(f"{num}.png", odds_block)
            return ['-', '-']
    elif len(texts) == 1:
        if pattern.match(texts[0]):
            num = random.randint(100000, 999999)
            cv2.imwrite(f"{num}.png", odds_block)
            return ['-', texts[0]]
        else:
            return [texts[0], '-']
    else:
        return texts[:2]