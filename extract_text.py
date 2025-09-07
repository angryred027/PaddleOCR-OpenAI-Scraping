from paddleocr import PaddleOCR

# Initialize PaddleOCR 
ocr = PaddleOCR(use_angle_cls=True, lang='tr', use_gpu=False)

def extract_team_name(image):
    result = ocr.ocr(image)
    texts = []
    team_names = ""
    for line in result:
        for word_info in line:
            text = word_info[1][0]   # the string
            team_names += " " + text
            texts.append(text)

    return texts, team_names