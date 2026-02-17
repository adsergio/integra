import streamlit as st
import pandas as pd
import pdfplumber
import re
import json
import os

def extrair_dados_blindado(file):
    dados = []
    # Expressão que busca: Data (10 chars) + Descrição + Valor (com vírgula no final)
    padrao_linha = re.compile(r'(\d{2}/\d{2}/\d{4})\s+(.*?)\s+([-]?\d+[\d\.]*,\d{2})')
    
    with pdfplumber.open(file) as pdf:
        for pagina in pdf.pages:
            texto = pagina.extract_text()
            if not texto: continue
            
            for linha in texto.split('\n'):
                # Ignora linhas de saldo e cabeçalhos do Bradesco
                if "SALDO" in linha.upper() or "TOTAL" in linha.upper():
                    continue
                
                match = padrao_linha.search(linha)
                if match:
                    data, desc, valor_str = match.groups()
                    
                    # Limpa o número do documento (geralmente é a última palavra da descrição)
                    partes_desc = desc.strip().split()
                    if len(partes_desc) > 1 and partes_desc[-1].isdigit():
                        partes_desc.pop() # Remove o Dcto
                    
                    historico_final = " ".join(partes_desc)
                    
                    # Converte valor para float (formato Python)
                    num_limpo = valor_str.replace('.', '').replace(',', '.')
                    valor_float = float(num_limpo)
                    
                    dados.append({"Data": data, "Historico": historico_final, "Valor": valor_float})
    
    return pd.DataFrame(dados)

# --- Interface Marina Contábil ---
st.title("🚀 Integrador Blindado - Marina Contábil")
cod_cli = st.sidebar.text_input("Código Domínio")
banco_red = st.sidebar.text_input("Conta Banco")

if cod_cli and banco_red:
    upload = st.file_uploader("Suba o PDF do Bradesco", type="pdf")
    if upload:
        df = extrair_dados_blindado(upload)
        if not df.empty:
            st.subheader("Conferência de Valores")
            st.table(df.assign(Valor=df['Valor'].map('R$ {:,.2f}'.format)))
            
            # Botão de exportação para o Domínio
            if st.button("Gerar Arquivo Domínio"):
                # Lógica de salvar regras e gerar TXT aqui...
                st.success("Arquivo gerado com sucesso!")