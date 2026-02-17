import streamlit as st
import pandas as pd
import json
import os
import pdfplumber

# --- 1. FUNÇÕES DE MEMÓRIA (JSON por Cliente) ---
def carregar_regras(codigo):
    caminho = f"clientes/regra_{codigo}.json"
    if os.path.exists(caminho):
        with open(caminho, 'r') as f:
            return json.load(f)
    return {}

def salvar_regras(codigo, regras):
    if not os.path.exists('clientes'):
        os.makedirs('clientes')
    with open(f"clientes/regra_{codigo}.json", 'w') as f:
        json.dump(regras, f)

# --- 2. INTERFACE E LÓGICA ---
st.sidebar.header("Configurações do Cliente")
cod_dominio = st.sidebar.text_input("Código no Domínio", placeholder="Ex: 123")
empresa = st.sidebar.text_input("Nome da Empresa")

if cod_dominio:
    st.title(f"📂 Integrador: {empresa}")
    regras = carregar_regras(cod_dominio)
    
    upload = st.file_uploader("Arraste o extrato em PDF", type="pdf")
    
    if upload:
        # Aqui simulamos a leitura do PDF
        with st.spinner("Lendo extrato..."):
            # Para o teste, vamos criar um DataFrame fictício 
            # (Em breve substituiremos pela extração real do seu PDF)
            dados = {
                'Data': ['01/02/2026', '02/02/2026'],
                'Historico': ['TARIFA BANCARIA', 'PAGTO FORNECEDOR'],
                'Valor': [15.50, 1200.00]
            }
            df = pd.DataFrame(dados)
            
            st.subheader("Mapeamento Contábil")
            
            novas_regras = {}
            for hist in df['Historico'].unique():
                if hist in regras:
                    st.success(f"✅ {hist} -> Já mapeado para conta {regras[hist]}")
                else:
                    st.warning(f"❓ {hist} - Não reconhecido")
                    conta = st.text_input(f"Informe a conta para: {hist}", key=hist)
                    if conta:
                        novas_regras[hist] = conta

            if st.button("Salvar Memória e Gerar Arquivo"):
                regras.update(novas_regras)
                salvar_regras(cod_dominio, regras)
                st.success("Regras atualizadas! O próximo extrato será automático.")
                # Lógica de exportação para Domínio virá aqui
else:
    st.info("👈 Comece inserindo o código do cliente na barra lateral.")