import streamlit as st
import pandas as pd
import pdfplumber
import json
import os
import re

# --- 1. MOTOR DE EXTRAÇÃO RECALIBRADO ---

def extrair_dados_bradesco_completo(file):
    dados = []
    data_atual = "" # Memória para persistência da data
    
    with pdfplumber.open(file) as pdf:
        for pagina in pdf.pages:
            texto = pagina.extract_text()
            if not texto: continue
            
            linhas = texto.split('\n')
            for linha in linhas:
                linha = linha.strip()
                
                # Ignora cabeçalhos e linhas de saldo total
                if "SALDO ANTERIOR" in linha.upper() or "TOTAL" in linha.upper() or "DATA" in linha.upper():
                    continue
                
                # 1. Tenta identificar se a linha começa com uma nova data
                match_data = re.match(r'(\d{2}/\d{2}/\d{4})', linha)
                if match_data:
                    data_atual = match_data.group(1)
                
                # 2. Localiza os valores monetários (com vírgula) na linha
                # O Bradesco coloca o lançamento antes do saldo final
                valores = re.findall(r'([-]?\d+[\d\.]*,\d{2})', linha)
                
                # Se houver valores e já tivermos uma data na memória, processamos a linha
                if valores and data_atual:
                    # O valor do lançamento é o penúltimo (se houver saldo à direita) ou o primeiro
                    valor_str = valores[-2] if len(valores) >= 2 else valores[0]
                    
                    # 3. FUSÃO SOLICITADA: Lançamento + Dcto
                    # Pegamos tudo o que está entre a Data e o Valor do Lançamento
                    # Isso captura automaticamente o texto e o número do documento no meio
                    miolo = linha
                    if data_atual in miolo:
                        miolo = miolo.replace(data_atual, "").strip()
                    
                    # Remove todos os valores encontrados para sobrar apenas o histórico + dcto
                    for v in valores:
                        miolo = miolo.replace(v, "").strip()
                    
                    # Limpeza de ruídos e espaços duplos
                    historico_unificado = re.sub(r'(VALOR DISPONIVEL|QUANDO DO REGISTRO)', '', miolo, flags=re.IGNORECASE).strip()
                    historico_unificado = re.sub(r'\s+', ' ', historico_unificado)

                    try:
                        num = valor_str.replace('.', '').replace(',', '.')
                        valor_f = float(num)
                        
                        if valor_f != 0:
                            dados.append({
                                "Data": data_atual, 
                                "Historico": historico_unificado, 
                                "Valor": valor_f
                            })
                    except:
                        continue
                        
    return pd.DataFrame(dados)

# --- 2. INTERFACE MARINA CONTÁBIL ---

st.set_page_config(page_title="Marina Contábil - Integrador", layout="wide")
st.sidebar.title("⚙️ Configurações")
cod_cli = st.sidebar.text_input("Código Domínio", placeholder="Ex: 101")
conta_banco = st.sidebar.text_input("Conta Banco (Reduzida)", placeholder="Ex: 10")

st.title("🚀 Integra Fácil - Marina Contábil")

if cod_cli and conta_banco:
    if not os.path.exists('clientes'): os.makedirs('clientes')
    path_regra = f"clientes/regra_{cod_cli}.json"
    regras = json.load(open(path_regra, 'r')) if os.path.exists(path_regra) else {}

    upload = st.file_uploader("Suba o extrato PDF do Bradesco", type="pdf")
    
    if upload:
        df = extrair_dados_bradesco_completo(upload)
        
        if not df.empty:
            st.subheader(f"📋 Conferência de Lançamentos ({len(df)} encontrados)")
            # Exibe a tabela formatada com os históricos unificados (Lançamento + Dcto)
            st.table(df.assign(Valor=df['Valor'].map('R$ {:,.2f}'.format)))
            
            st.subheader("🧠 Mapeamento Contábil")
            novas_regras = {}
            for h in df['Historico'].unique():
                if h in regras:
                    st.success(f"✅ {h} -> Conta {regras[h]}")
                else:
                    c1, c2 = st.columns([3, 1])
                    c1.warning(f"❓ Novo: {h}")
                    conta = c2.text_input("Conta Contábil", key=f"in_{h}")
                    if conta: novas_regras[h] = conta

            if st.button("💾 Salvar Memória e Gerar Arquivo"):
                regras.update(novas_regras)
                with open(path_regra, 'w') as f: json.dump(regras, f)
                
                txt_final = []
                for _, r in df.iterrows():
                    c_map = regras.get(r['Historico'], "ERRO")
                    c_deb, c_cre = (c_map, conta_banco) if r['Valor'] < 0 else (conta_banco, c_map)
                    
                    data_txt = r['Data'].replace('/','')
                    val_txt = f"{abs(r['Valor']):.2f}".replace(".", ",")
                    
                    txt_final.append(f"{data_txt}|{c_deb}|{c_cre}|{val_txt}|{r['Historico']}")
                
                st.download_button("📥 Baixar TXT para o Domínio", "\n".join(txt_final), f"dominio_{cod_cli}.txt")
        else:
            st.error("Nenhum lançamento encontrado. Verifique se o PDF é um extrato original.")
else:
    st.info("👈 Preencha os dados na lateral para ativar o sistema.")