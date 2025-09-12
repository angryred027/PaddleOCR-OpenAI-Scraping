import unicodedata
import re
from fuzzywuzzy import fuzz, process

class TurkishTextMatcher:
    def __init__(self, headers):
        self.headers = headers
    
    def clean_turkish_text(self, text):
        """Clean Turkish text while preserving Turkish characters"""
        if not text:
            return ""
        
        # Remove extra whitespace and normalize case
        text = re.sub(r'\s+', ' ', text.strip())
        
        # Convert to lowercase for matching (Turkish-aware)
        text = text.lower()
        
        # Replace some common Turkish character variations if needed
        # (only if you're seeing inconsistent encoding)
        replacements = {
            'i̇': 'i',  # dotted i variations
            'İ': 'i',
            'I': 'ı',   # Turkish uppercase I becomes ı
        }
        
        for old, new in replacements.items():
            text = text.replace(old, new)
        
        return text
    
    def normalize_for_comparison(self, text):
        """Light normalization that preserves Turkish characters"""
        # Only normalize Unicode composition, don't remove characters
        text = unicodedata.normalize('NFC', text)
        return self.clean_turkish_text(text)
    
    def match_headers(self, extracted_text, threshold=70):
        if len(self.headers) == 0:
            return None
        
        # Clean the extracted text
        cleaned_extracted = self.normalize_for_comparison(extracted_text)
        print(f"Original extracted: {extracted_text}")
        print(f"Cleaned extracted: {cleaned_extracted}")
        
        # Normalize headers for comparison
        normalized_headers = [self.normalize_for_comparison(header) for header in self.headers]
        
        # Try multiple fuzzy matching strategies
        scorers = [
            fuzz.token_sort_ratio,    # Your original
            fuzz.ratio,               # Simple ratio
            fuzz.partial_ratio,       # Partial matching
            fuzz.token_set_ratio,     # Token set
        ]
        
        best_overall_match = None
        best_overall_score = 0
        
        for scorer in scorers:
            match = process.extractOne(cleaned_extracted, normalized_headers, scorer=scorer)
            if match and match[1] > best_overall_score:
                best_overall_match = match
                best_overall_score = match[1]
        
        if best_overall_match and best_overall_score >= threshold:
            # Return the original header (not normalized)
            matched_index = normalized_headers.index(best_overall_match[0])
            original_header = self.headers[matched_index]
            print(f"Best match: '{original_header}' with score {best_overall_score}")
            return original_header
        else:
            print(f"No match found (best score: {best_overall_score})")
            return None

# Example usage:
headers = [
    "Maç Sonucu",
    "Çifte Şans", 
    "MS ve 1,5 Alt/Üst",
    "MS ve 2,5 Alt/Üst",
    "MS ve 3,5 Alt/Üst",
    "MS ve Karşılıklı Gol",
    "1. Yarı Sonucu",
    "1. Yarı Çifte Şans",
    "0,5 Alt/Üst",
    "1,5 Alt/Üst",
    "2,5 Alt/Üst", 
    "3,5 Alt/Üst",
    "1.Yarı 0,5 Alt/Üst",
    "1.Yarı 1,5 Alt/Üst",
    "1.Yarı 2,5 Alt/Üst",
    "1.Yarı Karşılıklı Gol",
    "Karşılıklı Gol",
    "Toplam Gol Aralığı",
    "Tek/Çift",
    "Toplam Korner Aralığı",
    "1. Yarı Korner Aralığı",
    "İlk Yarı / Maç Skoru"
]

matcher = TurkishTextMatcher(headers)

# Test examples:
test_texts = [
    "Cifte Sans",      # Missing Turkish chars
    "Maç Sonucu",      # Exact match
    "Mac Sonucu",      # Missing ç
    "Çifte Şans",      # Correct Turkish
    "1. Yari Sonucu",  # Missing dot over i
]

for test_text in test_texts:
    print(f"\nTesting: '{test_text}'")
    result = matcher.match_headers(test_text)
    print("-" * 50)