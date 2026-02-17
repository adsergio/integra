import streamlit as st
import pandas as pd
import json
import os
import database
import parsers

# Inicializa o banco ao abrir
if not os.path.exists(database.DB_NAME):
    database.init_db()

st.set_page_config(page_title="Integra Fácil", layout="wide")

# --- Sidebar: Seleção/Cadastro de Cliente ---
st.sidebar.title("⚙️ Configurações")

modo_cliente = st.sidebar.radio("Cliente", ["Selecionar Existente", "Cadastrar Novo"])
cliente_selecionado = None

if modo_cliente == "Cadastrar Novo":
    st.sidebar.subheader("Novo Cliente")
    novo_nome = st.sidebar.text_input("Nome da Empresa")
    novo_cod = st.sidebar.text_input("Código Domínio")
    novo_conta = st.sidebar.text_input("Conta Banco (Reduzida)")
    novo_parser = st.sidebar.selectbox("Layout do Banco", list(parsers.AVAILABLE_PARSERS.keys()))
    
    if st.sidebar.button("Salvar Cliente"):
        if novo_nome and novo_cod and novo_conta:
            if database.criar_cliente(novo_nome, novo_cod, novo_conta, novo_parser):
                st.sidebar.success("Cliente criado!")
                st.rerun()
            else:
                st.sidebar.error("Erro ao criar cliente.")
        else:
            st.sidebar.warning("Preencha todos os campos.")

else:
    clientes = database.listar_clientes()
    if not clientes:
        st.sidebar.warning("Nenhum cliente cadastrado.")
    else:
        # Cria dicionário {nome: id} para o selectbox
        # clientes agora retorna (id, nome, codigo, conta, parser)
        # Atenção: listar_clientes no database.py retorna: id, nome, codigo_sistema, conta_banco_padrao, banco_parser
        opcoes = {f"{c[1]} (Cód: {c[2]})": c[0] for c in clientes}
        nome_selecionado = st.sidebar.selectbox("Selecione a Empresa", list(opcoes.keys()))
        cliente_id = opcoes[nome_selecionado]
        
        # Carrega dados do cliente
        cliente_dados = database.get_cliente_by_id(cliente_id) # (id, nome, cnpj, cod, conta, parser)
        # O fetchall do database.py retorna * então a ordem depende do CREATE TABLE + ALTER TABLE
        # CREATE: id, nome, cnpj, codigo_sistema, conta_banco_padrao
        # ALTER ADD: banco_parser
        # Logo: 0:id, 1:nome, 2:cnpj, 3:codigo, 4:conta, 5:parser
        
        if cliente_dados:
            cliente_selecionado = {
                "id": cliente_dados[0],
                "nome": cliente_dados[1],
                "codigo": cliente_dados[3],
                "conta_banco": cliente_dados[4],
                "parser": cliente_dados[5] if len(cliente_dados) > 5 else "Bradesco (PDF)"
            }
            st.sidebar.info(f"Banco: {cliente_selecionado['parser']}")
            st.sidebar.info(f"Conta: {cliente_selecionado['conta_banco']}")


debug_mode = st.sidebar.checkbox("🔎 Debug (mostrar detalhes)", value=False)

st.title("🚀 Integra Fácil")

if cliente_selecionado:
    # Carrega regras do banco
    regras = database.listar_regras(cliente_selecionado["id"])
    
    # Identifica o parser correto
    parser_name = cliente_selecionado.get("parser", "Bradesco (PDF)")
    parser_module = parsers.get_parser(parser_name)
    
    upload = st.file_uploader(f"Selecione o arquivo ({parser_name})", type="pdf") # Futuro: aceitar OFX/XLSX dependendo do parser

    if upload:
        if parser_module:
            try:
                df = parser_module.parse(upload, debug=debug_mode)
            except Exception as e:
                st.error(f"Erro ao processar arquivo: {e}")
                df = pd.DataFrame()
        else:
            st.error(f"Parser '{parser_name}' não encontrado.")
            df = pd.DataFrame()

        if not df.empty:
            st.subheader("📊 Conferência de Lançamentos")
            df_view = df.copy()
            # Formatação visual apenas se for numérico
            if "Valor" in df_view.columns:
                df_view["Valor"] = df_view["Valor"].apply(lambda x: f"R$ {x:,.2f}" if isinstance(x, (int, float)) else x)
            
            cols_to_show = [c for c in ["Nº", "Data", "Lancamento", "Dcto", "Valor"] if c in df_view.columns]
            st.dataframe(df_view[cols_to_show], use_container_width=True, hide_index=True)

            st.subheader("🧠 Mapeamento Contábil")
            
            # --- Separação: Mapeados vs Pendentes ---
            pendentes = []
            mapeados = []
            
            for index, row in df.iterrows():
                hbase = row.get("HistoricoBase", "")
                if not hbase: continue
                
                if hbase in regras:
                     mapeados.append({
                         "Data": row["Data"],
                         "Historico": hbase,
                         "Conta": regras[hbase],
                         "Valor": row["Valor"]
                     })
                else:
                    # Adiciona à lista de pendentes
                    if hbase not in [p["Historico"] for p in pendentes]:
                         pendentes.append({"Historico": hbase, "Exemplo Valor": row["Valor"]})

            # Exibe Pendentes
            if pendentes:
                st.warning(f"⚠️ Existem {len(pendentes)} históricos novos para classificar.")
                
                with st.expander("📝 Classificar Pendências", expanded=True):
                    with st.form("form_regras"):
                        novas_regras = {}
                        for p in pendentes:
                            c1, c2 = st.columns([3, 1])
                            c1.markdown(f"**{p['Historico']}**")
                            conta = c2.text_input("Conta Reduzida", key=f"new_{p['Historico']}")
                            if conta:
                                novas_regras[p['Historico']] = conta
                        
                        if st.form_submit_button("💾 Salvar Novas Regras"):
                            for hist, cta in novas_regras.items():
                                database.salvar_regra(cliente_selecionado["id"], hist, cta)
                            st.success("Regras salvas! Recarregando...")
                            st.rerun()
            else:
                st.success("✅ Todos os lançamentos estão mapeados!")

            # --- Exportação ---
            if st.button("📥 Gerar Arquivo de Importação"):
                txt_final = []
                erro_count = 0
                
                regras_atualizadas = database.listar_regras(cliente_selecionado["id"])
                conta_banco = cliente_selecionado["conta_banco"]

                for _, r in df.iterrows():
                    hbase = r.get("HistoricoBase")
                    if not hbase: continue
                    
                    c_map = regras_atualizadas.get(hbase)
                    
                    if not c_map:
                        erro_count += 1
                        continue
                    
                    valor = r["Valor"]
                    c_deb, c_cre = (c_map, conta_banco) if valor < 0 else (conta_banco, c_map)

                    data_txt = r["Data"].replace("/", "")
                    val_txt = f"{abs(valor):.2f}".replace(".", ",")
                    hist_final = r.get("HistoricoFinal", hbase)

                    txt_final.append(f"{data_txt}|{c_deb}|{c_cre}|{val_txt}|{hist_final}")

                if erro_count > 0:
                    st.error(f"Impossível gerar: {erro_count} lançamentos sem conta definida.")
                else:
                    st.download_button("Baixar TXT", "\n".join(txt_final), file_name=f"dominio_{cliente_selecionado['codigo']}.txt")
                    
        else:
            st.warning("Nenhum lançamento encontrado ou erro na leitura.")
else:
    st.info("👈 Selecione ou cadastre uma empresa na barra lateral para começar.")
