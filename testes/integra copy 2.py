import streamlit as st
import pandas as pd
import pdfplumber
import json
import os

# --- 1. MOTORES DE PROCESSAMENTO ---

def processar_extrato_bradesco(file):
    dados = []
    with pdfplumber.open(file) as pdf:
        for pagina in pdf.pages:
            # Extração mais sensível para layouts variáveis
            tabela = pagina.extract_table({
                "vertical_strategy": "text", 
                "horizontal_strategy": "text"
            })
            
            if tabela:
                for linha in tabela:
                    # Limpa a linha de valores nulos
                    linha_limpa = [str(item).strip() if item else "" for item in linha]
                    
                    # Procura por algo que pareça uma data (DD/MM/AAAA) em qualquer lugar da linha
                    if any("/" in celula and len(celula) >= 8 for celula in linha_limpa):
                        # Tenta identificar qual coluna é a data e qual é o histórico
                        data = next((c for c in linha_limpa if "/" in c), "")
                        
                        # O histórico geralmente é a maior string da linha que não é valor
                        # Vamos pegar a segunda coluna por padrão, mas limpando o lixo
                        historico = linha_limpa[1].replace("\n", " ") if len(linha_limpa) > 1 else ""
                        
                        # Pega o último valor da linha (geralmente saldo ou valor do lançamento)
                        # No Bradesco, Crédito é a 4ª e Débito a 5ª coluna
                        credito = linha_limpa[3] if len(linha_limpa) > 3 else ""
                        debito = linha_limpa[4] if len(linha_limpa) > 4 else ""
                        
                        valor_str = credito if (credito and credito != "0,00") else debito
                        
                        if valor_str and valor_str not in ["Crédito (R$)", "Débito (R$)", "Saldo (R$)"]:
                            try:
                                # Limpa pontos e vírgulas para converter em número
                                valor_limpo = valor_str.replace(".", "").replace(",", ".")
                                # Se o valor termina com '-', é um débito
                                multiplicador = -1 if "-" in valor_limpo else 1
                                valor_final = float(valor_limpo.replace("-", "")) * multiplicador
                                
                                if "SALDO" not in historico.upper():
                                    dados.append([data, historico, valor_final])
                            except:
                                continue
    
    return pd.DataFrame(dados, columns=['Data', 'Historico', 'Valor'])

def formatar_valor_dominio(valor):
    """Formata o valor para o layout padrão do Domínio (ex: 150,50)"""
    return f"{abs(valor):.2f}".replace(".", ",")

def gerar_arquivo_dominio(df_processado, regras_cliente, conta_banco):
    """Cria a string no formato DATA|DEBITO|CREDITO|VALOR|HISTORICO"""
    linhas_txt = []
    for _, row in df_processado.iterrows():
        hist = row['Historico']
        conta_mapeada = regras_cliente.get(hist, "")
        
        data_formatada = row['Data'].replace("/", "")
        valor_str = formatar_valor_dominio(row['Valor'])
        
        # Lógica: Se valor for negativo (Débito no extrato), tira do banco 
        if row['Valor'] < 0:
            debito, credito = conta_mapeada, conta_banco
        else:
            debito, credito = conta_banco, conta_mapeada
            
        linha = f"{data_formatada}|{debito}|{credito}|{valor_str}|{hist}"
        linhas_txt.append(linha)
    return "\n".join(linhas_txt)

def gerenciar_memoria(codigo, novas_regras=None):
    """Carrega ou salva as regras de cada cliente em JSON """
    if not os.path.exists('clientes'): os.makedirs('clientes')
    caminho = f"clientes/regra_{codigo}.json"
    
    regras = {}
    if os.path.exists(caminho):
        with open(caminho, 'r', encoding='utf-8') as f:
            regras = json.load(f)
            
    if novas_regras:
        regras.update(novas_regras)
        with open(caminho, 'w', encoding='utf-8') as f:
            json.dump(regras, f, indent=4)
            
    return regras

# --- 2. INTERFACE WEB (STREAMLIT) ---

st.set_page_config(page_title="Marina Contábil - Integra Fácil", layout="wide")

# Barra Lateral
st.sidebar.image("https://cdn-icons-png.flaticon.com/512/2641/2641433.png", width=100)
st.sidebar.title("Configurações")
cod_dominio = st.sidebar.text_input("Código do Cliente (Domínio)", placeholder="Ex: 101")
empresa = st.sidebar.text_input("Nome da Empresa")
conta_banco = st.sidebar.text_input("Conta Reduzida do Banco", placeholder="Ex: 10")

# Corpo Principal
st.title("🚀 Integra Fácil - Marina Contábil")
st.markdown("Transforme extratos bancários em lançamentos contábeis para o **Sistema Domínio**.")

if cod_dominio and conta_banco:
    regras_atuais = gerenciar_memoria(cod_dominio)
    
    upload = st.file_uploader("Selecione o arquivo PDF do Bradesco", type="pdf")
    
    if upload:
        df_extrato = processar_extrato_bradesco(upload)
        
        st.subheader("🛠️ Mapeamento Contábil")
        st.info("O sistema memoriza suas escolhas. Na próxima vez, o mapeamento será automático.")
        
        novas_regras_mapeadas = {}
        
        # Exibe os lançamentos para conferência/mapeamento
        for i, row in df_extrato.iterrows():
            hist = row['Historico']
            col1, col2, col3 = st.columns([1, 2, 1])
            
            col1.text(row['Data'])
            col2.text(hist)
            
            if hist in regras_atuais:
                col3.success(f"Conta: {regras_atuais[hist]}")
            else:
                conta_digitada = col3.text_input("Conta Contábil", key=f"input_{i}", placeholder="Cód. Reduzido")
                if conta_digitada:
                    novas_regras_mapeadas[hist] = conta_digitada

        # Botões de Ação
        st.divider()
        c1, c2 = st.columns(2)
        
        if c1.button("💾 Salvar Memória do Cliente"):
            if novas_regras_mapeadas:
                gerenciar_memoria(cod_dominio, novas_regras_mapeadas)
                st.success("Cérebro do cliente atualizado com sucesso!")
                st.rerun()
            else:
                st.info("Nada novo para salvar.")

        if c2.button("📑 Gerar Arquivo para o Domínio"):
            # Atualiza regras_atuais com as novas digitadas para a exportação
            regras_atuais.update(novas_regras_mapeadas)
            txt_final = gerar_arquivo_dominio(df_extrato, regras_atuais, conta_banco)
            
            st.download_button(
                label="📥 Baixar .TXT de Importação",
                data=txt_final,
                file_name=f"importacao_dominio_{cod_dominio}.txt",
                mime="text/plain"
            )
else:
    st.warning("👈 Preencha os dados do cliente e a conta do banco na barra lateral para começar.")