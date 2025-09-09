from paddleocr import PaddleOCR

# Initialize OCR only once to avoid threading issues
_ocr_instance = None

def get_ocr():
    global _ocr_instance
    if _ocr_instance is None:
        _ocr_instance = PaddleOCR(use_angle_cls=True, lang='tr', use_gpu=False)
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
    team_names = ""
    for line in result:
        for word_info in line:
            text = word_info[1][0]   # the string
            team_names += " " + text
            texts.append(text)
    
    return "".join(texts)