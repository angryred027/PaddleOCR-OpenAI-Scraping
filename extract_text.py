from paddleocr import PaddleOCR
import re
import cv2
import random
import threading

pattern = re.compile(r'^\d+\.\d{2}$')
_ocr_instance = None
_ocr_lock = threading.Lock()

def get_ocr():
    global _ocr_instance
    with _ocr_lock:
        if _ocr_instance is None:
            _ocr_instance = PaddleOCR(
                use_angle_cls=True, 
                lang='tr', 
                show_log=False, 
                cpu_threads=8,
                enable_mkldnn=True,
                det_db_score_mode="slow",
                det_limit_side_len=5880,
                det_db_box_thresh=0.1,
                det_db_thresh=0.1,
                rec_batch_num=16,
                det_db_unclip_ratio=2,
                max_text_length=200,
                drop_score=0.1,
            )
    return _ocr_instance

def extract_team_name(image):
    if image is None or image.size == 0:
        return [], ""
        
    try:
        ocr = get_ocr()
        result = ocr.ocr(image)
        
        if not result or not result[0]:
            return [], ""
            
        texts = []
        team_names = ""
        
        for line in result:
            if not line:
                continue
            for word_info in line:
                if len(word_info) >= 2 and word_info[1] and len(word_info[1]) >= 1:
                    text = word_info[1][0]
                    team_names += " " + text
                    texts.append(text)

        return texts, team_names
    except Exception as e:
        print(f"Extract team name error: {e}")
        return [], ""

def extract_block_data(block_image):
    if block_image is None or block_image.size == 0:
        return ""
        
    try:
        ocr = get_ocr()
        result = ocr.ocr(block_image)
        
        if not result or not result[0]:
            return ""
            
        texts = []
        for line in result:
            if not line:
                continue
            for word_info in line:
                if len(word_info) >= 2 and word_info[1] and len(word_info[1]) >= 1:
                    text = word_info[1][0] 
                    texts.append(text)
        
        return "".join(texts)
    except Exception as e:
        print(f"Extract block data error: {e}")
        return ""

def get_odds_data(odds_block):
    if odds_block is None or odds_block.size == 0:
        return ['-', '-']
        
    try:
        ocr = get_ocr()
        result = ocr.ocr(odds_block)
        
        if not result or not result[0]:
            num = random.randint(100000, 999999)
            cv2.imwrite(f"{num}.png", odds_block)
            return ['-', '-']
            
        texts = []
        for line in result:
            if not line:
                continue
            for word in line:
                if len(word) >= 2 and word[1] and len(word[1]) >= 1:
                    text = word[1][0] if word[1][0] else '-'
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
            if len(texts) > 1 and pattern.match(texts[1]):
                return texts[:2]
            else:
                return [texts[0], '-']
                
    except Exception as e:
        print(f"Get odds data error: {e}")
        return ['-', '-']