import pdfplumber
import pandas as pd
import unicodedata
import re

def _norm(s) -> str:
    if s is None:
        return ""
    s = str(s).replace("\u00a0", " ").strip()
    s = unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('ASCII')
    return re.sub(r"\s+", " ", s).strip()

def _cluster_rows(words, y_tol=4.5):
    if not words:
        return []
    words = sorted(words, key=lambda w: (w["top"], w["x0"]))
    rows = []
    cur = [words[0]]
    cur_y = words[0]["top"]

    for w in words[1:]:
        if abs(w["top"] - cur_y) <= y_tol:
            cur.append(w)
        else:
            rows.append(cur)
            cur = [w]
            cur_y = w["top"]
    rows.append(cur)
    return rows

def _row_text(words_row):
    return " ".join(_norm(w["text"]) for w in sorted(words_row, key=lambda x: x["x0"]))

path = r"c:\Users\Sergio\Documents\Apps-Contabilidade\integra\extratos\extrato-bradesco-12-2025.pdf"

print(f"--- Diagnóstico para: {path} ---")

with pdfplumber.open(path) as pdf:
    page = pdf.pages[0]
    words = page.extract_words(use_text_flow=True, keep_blank_chars=False)
    
    print(f"Total de palavras na pág 1: {len(words)}")
    
    if not words:
        print("ALERTA: Nenhuma palavra encontrada. PDF pode ser imagem.")
    else:
        rows = _cluster_rows(words, y_tol=4.5)
        print(f"Total de linhas detectadas: {len(rows)}")
        
        print("\n--- Primeiras 20 linhas ---")
        for i, r in enumerate(rows[:20]):
            txt = _row_text(r)
            print(f"Linha {i}: {txt} (Y={r[0]['top']:.2f})")
            
        print("\n--- Procurando Header 'DATA' ---")
        found = False
        for i, r in enumerate(rows):
            txt = _row_text(r).upper()
            if "DATA" in txt:
                print(f"FOUND 'DATA' na Linha {i}: {txt}")
                found = True
        
        if not found:
            print("ALERTA: Token 'DATA' não encontrado nas linhas.")

