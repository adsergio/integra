import pandas as pd
import pdfplumber
import re
import unicodedata
from collections import defaultdict

DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")

def _norm(s) -> str:
    if s is None:
        return ""
    s = str(s).replace("\u00a0", " ").strip()
    s = unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('ASCII')
    return re.sub(r"\s+", " ", s).strip()

def _is_date(s: str) -> bool:
    return bool(DATE_RE.match(_norm(s)))

def _to_num_ptbr(s: str):
    s = _norm(s).replace("R$", "").strip()
    if not s:
        return None
    if not re.search(r"\d", s):
        return None
    try:
        return float(s.replace(".", "").replace(",", "."))
    except:
        return None

def _is_noise(desc: str) -> bool:
    u = _norm(desc).upper()
    if not u:
        return True
    if "SALDO ANTERIOR" in u or "SALDO INICIAL" in u or "SALDO DIA" in u:
        return True
    if u.startswith("EXTRATO"):
        return True
    if u in {"TOTAL", "VALOR DISPONIVEL", "VALOR DISPONÍVEL"}:
        return True
    return False

def parse(uploaded_file, debug=False):
    """
    Caixa Econômica PDF parser - Análise por posição de palavras.
    Detecta padrões de data, valor e tipo (C/D) sem depender de estrutura de tabela.
    """
    dados = []

    with pdfplumber.open(uploaded_file) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(use_text_flow=True, keep_blank_chars=False)
            if not words:
                continue
            
            # Agrupa palavras por linhas (Y)
            rows_by_y = defaultdict(list)
            for w in words:
                y_key = round(w['top'], 1)
                rows_by_y[y_key].append(w)
            
            # Encontra o cabeçalho (linha com "Data", "Mov", "Valor", "Saldo")
            header_y = None
            for y in sorted(rows_by_y.keys()):
                row_text = " ".join([w['text'].upper() for w in rows_by_y[y]])
                if all(keyword in row_text for keyword in ["DATA", "MOV", "VALOR"]):
                    header_y = y
                    if debug:
                        print(f"Página {page_num}: Cabeçalho encontrado em Y={y}")
                    break
            
            if header_y is None:
                if debug:
                    print(f"Página {page_num}: Cabeçalho não encontrado")
                continue
            
            # Processa linhas de dados (após o cabeçalho)
            sorted_ys = sorted(rows_by_y.keys())
            header_idx = sorted_ys.index(header_y)
            
            for y_idx in range(header_idx + 1, len(sorted_ys)):
                y = sorted_ys[y_idx]
                row_words = rows_by_y[y]
                row_sorted = sorted(row_words, key=lambda x: x['x0'])
                
                # Extrai texto de todas as palavras na linha
                row_text = " ".join([_norm(w['text']) for w in row_sorted])
                
                # Extrai data (primeira ou segunda palavra deve ser uma data)
                data = None
                for w in row_sorted[:3]:  # Procura nas 3 primeiras palavras
                    cell_text = _norm(w['text'])
                    if _is_date(cell_text):
                        data = cell_text
                        break
                
                if not data:
                    continue
                
                # Extrai valor numérico com tipo (C ou D)
                # Padrão: "XXX.XXX,XX C" ou "XXX.XXX,XX D"
                valor = None
                valor_tipo = None
                
                m = re.search(r'([\d\.]+,\d{2})\s+([CD])', row_text)
                if m:
                    valor = _to_num_ptbr(m.group(1))
                    valor_tipo = m.group(2)
                
                if valor is None:
                    continue
                
                # Converte C/D em sinal
                if valor_tipo == 'D':
                    valor = -abs(valor)
                else:
                    valor = abs(valor)
                
                # Filtra ruído
                if _is_noise(row_text):
                    continue
                
                # Extrai histórico (tudo que não é data, número de doc, ou valor)
                # Remove data, valor, números de doc muito grandes
                historico_parts = []
                for w in row_sorted:
                    text = _norm(w['text'])
                    
                    # Pula data
                    if _is_date(text):
                        continue
                    
                    # Pula valores pura e simples
                    if re.match(r'^[\d\.]+,\d{2}', text):
                        continue
                    
                    # Pula indicadores C/D sozinhos
                    if text in ['C', 'D']:
                        continue
                    
                    # Pula números de documento (6 dígitos)
                    if len(text) == 6 and text.isdigit():
                        continue
                    
                    historico_parts.append(text)
                
                historico = " ".join(historico_parts)
                historico = _norm(historico)
                
                if historico and not _is_noise(historico):
                    dados.append({
                        "Data": data,
                        "Historico": historico,
                        "Valor": valor,
                        "HistoricoBase": historico,
                        "HistoricoFinal": historico
                    })
    
    df = pd.DataFrame(dados)
    if df.empty:
        return df
    
    df = df.reset_index(drop=True)
    df.insert(0, "Nº", df.index + 1)
    return df
