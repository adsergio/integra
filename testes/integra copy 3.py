import streamlit as st
import pandas as pd
import pdfplumber
import json
import os
import re

# --- 1. MOTOR DE EXTRAÇÃO POR TEXTO (Mais robusto para Bradesco) ---

def extrair_dados_texto_bradesco(file):
    dados = []
    # Expressão regular para encontrar: Data, Histórico e Valor
    # Exemplo: 13/03/2018 LIQUIDACAO DE COBRANCA 6009084 36,00
    padrao_linha = re.compile(r'(\d{2}/\d{2}/\d{4})\s+(.*?)\s+(\d+\.?\d*,\d{2}[-]?)$')
    
    with pdfplumber.open(file) as pdf:
        for pagina in pdf.pages:
            texto = pagina.extract_text()
            if not texto: continue
            
            linhas = texto.split('\n')
            for linha in linhas:
                linha = linha.strip()
                
                # Ignora saldos e cabeçalhos
                if "SALDO" in linha.upper() or "TOTAL" in linha.upper() or "DATA" in linha.upper():
                    continue
                
                match = padrao_linha.search(linha)
                if match:
                    data, hist, valor_str = match.groups()
                    
                    # Limpa o histórico de números de documento no final
                    hist_limpo = re.sub(r'\s+\d+$', '', hist).strip()
                    
                    # Ignora ruídos do Bradesco
                    if "VALOR DISPONIVEL" in hist_limpo.upper() or "REGISTRO" in hist_limpo.upper():
                        continue
                        
                    try:
                        # Trata formato: 3.972,00- ou 36,00
                        num = valor_str.replace(".", "").replace(",", ".")
                        mult = -1 if "-" in num else 1
                        valor_final = float(num.replace("-", "")) * mult
                        
                        dados.append({"Data": data, "Historico": hist_limpo, "Valor": valor_final})
                    except:
                        continue
                        
    return pd.DataFrame(dados)

# --- 2. INTERFACE E LÓGICA DE NEGÓCIO ---

st.set_page_config(page_title="Marina Contábil", layout="wide")
st.sidebar.title("⚙️ Configurações")
cod_cli = st.sidebar.text_input("Código Domínio", placeholder="Ex: 101")
banco_red = st.sidebar.text_input("Conta Banco (Reduzida)", placeholder="Ex: 10")

st.title("🚀 Integra Fácil - Marina Contábil")

if cod_cli and banco_red:
    if not os.path.exists('clientes'): os.makedirs('clientes')
    path_regra = f"clientes/regra_{cod_cli}.json"
    regras = json.load(open(path_regra)) if os.path.exists(path_regra) else {}

    upload = st.file_uploader("Suba o PDF do Bradesco", type="pdf")
    
    if upload:
        df = extrair_dados_texto_bradesco(upload)
        
        if not df.empty:
            st.subheader("📊 Conferência de Lançamentos")
            # Estilização para facilitar a visão da Marina
            st.dataframe(df.style.format({"Valor": "R$ {:.2f}"}), use_container_width=True)
            
            st.subheader("🧠 Mapeamento Contábil")
            novas_regras = {}
            
            # Mostra apenas o que ainda NÃO está na memória
            pendentes = df[~df['Historico'].isin(regras.keys())]
            
            if pendentes.empty:
                st.success("✅ Todos os lançamentos já estão mapeados na memória!")
            else:
                for h in pendentes['Historico'].unique():
                    c1, c2 = st.columns([3, 1])
                    c1.write(f"**Novo Histórico:** {h}")
                    conta = c2.text_input("Conta Débito/Crédito", key=f"h_{h}")
                    if conta: novas_regras[h] = conta
            
            st.divider()
            if st.button("💾 Salvar Memória e Gerar Arquivo"):
                regras.update(novas_regras)
                with open(path_regra, 'w') as f: json.dump(regras, f)
                
                # Gera o TXT para o Sistema Domínio
                txt_linhas = []
                for _, r in df.iterrows():
                    c_map = regras.get(r['Historico'], "999") # 999 se esquecer de mapear
                    c_deb, c_cre = (c_map, banco_red) if r['Valor'] < 0 else (banco_red, c_map)
                    
                    valor_dom = f"{abs(r['Valor']):.2f}".replace(".", ",")
                    data_dom = r['Data'].replace("/", "")
                    
                    txt_linhas.append(f"{data_dom}|{c_deb}|{c_cre}|{valor_dom}|{r['Historico']}")
                
                st.download_button("📥 Baixar Arquivo Domínio", "\n".join(txt_linhas), f"dominio_{cod_cli}.txt")
        else:
            st.error("Não encontrei lançamentos no texto desse PDF. O arquivo pode estar protegido ou em formato de imagem (foto).")
else:
    st.info("👈 Preencha o código do cliente e a conta do banco para ativar o sistema.")