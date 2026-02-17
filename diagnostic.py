import pdfplumber
import sys

pdf_path = r"c:\Users\Sergio\Documents\Apps-Contabilidade\integra\extratos\extrato-bradesco.pdf"

try:
    with pdfplumber.open(pdf_path) as pdf:
        print(f"Total pages: {len(pdf.pages)}")
        for i, page in enumerate(pdf.pages):
            print(f"--- Page {i+1} ---")
            text = page.extract_text()
            print(text)
            print("-" * 20)
            
            # Also print words to see positioning
            words = page.extract_words(use_text_flow=True, keep_blank_chars=False)
            if words:
                print(f"First 5 words: {words[:5]}")
            else:
                print("No words found on this page.")
except Exception as e:
    print(f"Error: {e}")
