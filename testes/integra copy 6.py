import streamlit as st
import pandas as pd
import pdfplumber
import json
import os
import re
import unicodedata

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
    if "SALDO ANTERIOR" in u:
        return True
    if u.startswith("EXTRATO DE"):
        return True
    if "TOTAL DISPON" in u or u == "TOTAL":
        return True
    if u in {"VALOR DISPONIVEL", "VALOR DISPONÍVEL", "QUANDO DO REGISTRO"}:
        return True
    return False

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

def _row_has_tokens(text_upper: str) -> bool:
    # tokens mínimos do header (tolerante)
    has_data = "DATA" in text_upper
    has_lanc = ("LANC" in text_upper)  # pega LANCAMENTO/LANÇAMENTO
    has_dcto = ("DCT" in text_upper)   # DCTO / DCTO.
    has_cred = ("CRED" in text_upper)
    has_deb = ("DEB" in text_upper)
    has_saldo = ("SALDO" in text_upper)

    # aceita header mesmo se crédito/débito não estiverem na mesma linha (janela 2 linhas resolve)
    return has_data and has_lanc and has_dcto and has_saldo and (has_cred or has_deb)

def _find_header_and_boundaries(page, debug=False):
    """
    Detecta header numa janela de 2 linhas e monta os limites X.
    """
    words = page.extract_words(use_text_flow=True, keep_blank_chars=False)
    if not words:
        return None, None, None

    rows = _cluster_rows(words, y_tol=4.5)

    header_words = None
    header_y = None

    # tenta achar numa linha ou em 2 linhas combinadas
    for i in range(len(rows)):
        t1 = _row_text(rows[i]).upper()
        combined = rows[i]
        t_comb = t1

        if i + 1 < len(rows):
            t2 = _row_text(rows[i + 1]).upper()
            t_comb = (t1 + " " + t2).strip()
            combined = rows[i] + rows[i + 1]

        if debug:
             pass

        if _row_has_tokens(t1):
            header_words = rows[i]
            header_y = min(w["top"] for w in rows[i])
            break

        if _row_has_tokens(t_comb):
            header_words = combined
            header_y = min(w["top"] for w in combined)
            break

    if header_words is None:
        if debug:
            st.warning("DEBUG: Header não encontrado nesta página.")
        return None, None, None

    if debug:
        st.info(f"DEBUG: Header encontrado: {_row_text(header_words)}")

    # encontra X pelo primeiro word que contém o token
    def find_x_contains(token: str):
        token = token.upper()
        for w in sorted(header_words, key=lambda x: x["x0"]):
            if token in _norm(w["text"]).upper():
                return w["x0"]
        return None

    x_data = find_x_contains("DATA")
    x_lanc = find_x_contains("LANC")
    x_dcto = find_x_contains("DCT")
    x_cred = find_x_contains("CRED")
    x_deb = find_x_contains("DEB")
    x_saldo = find_x_contains("SALDO")

    # se algum não apareceu (às vezes o PDF não imprime "Débito" na mesma página),
    # usamos fallback por ordem esperada: Data, Lanc, Dcto, Cred, Deb, Saldo
    xs = [x_data, x_lanc, x_dcto, x_cred, x_deb, x_saldo]
    if x_data is None or x_lanc is None or x_dcto is None or x_saldo is None:
        if debug:
            st.warning(f"DEBUG: Falta token obrigatório. x_data={x_data}, x_lanc={x_lanc}, x_dcto={x_dcto}, x_saldo={x_saldo}")
        return None, None, None

    cols = [("Data", x_data), ("Lancamento", x_lanc), ("Dcto", x_dcto)]

    # crédito e débito podem falhar individualmente, mas se ambos existirem, usamos os dois
    if x_cred is not None:
        cols.append(("Credito", x_cred))
    if x_deb is not None:
        cols.append(("Debito", x_deb))

    cols.append(("Saldo", x_saldo))
    cols = sorted(cols, key=lambda c: c[1])

    # cria boundaries entre colunas
    boundaries = []
    for i in range(len(cols) - 1):
        boundaries.append((cols[i][1] + cols[i + 1][1]) / 2)

    col_names = [c[0] for c in cols]
    return header_y, boundaries, col_names

def _assign_to_columns(line_words, boundaries, col_names):
    buckets = {name: [] for name in col_names}

    for w in sorted(line_words, key=lambda x: x["x0"]):
        x = w["x0"]
        idx = 0
        while idx < len(boundaries) and x > boundaries[idx]:
            idx += 1
        col = col_names[idx]
        buckets[col].append(_norm(w["text"]))

    return {k: _norm(" ".join(v)) for k, v in buckets.items()}

def extrair_lancamentos_por_coordenadas(uploaded_file, debug=False):
    dados = []
    data_atual = ""
    lanc_corrente = None

    def flush():
        nonlocal lanc_corrente
        if not lanc_corrente:
            return
        if lanc_corrente.get("Valor") is None:
            lanc_corrente = None
            return

        hist = _norm(lanc_corrente.get("HistoricoBase", ""))
        if not hist or _is_noise(hist):
            lanc_corrente = None
            return

        dcto = _norm(lanc_corrente.get("Dcto", ""))
        lanc_corrente["HistoricoBase"] = hist
        lanc_corrente["HistoricoFinal"] = (f"{hist} Dcto:{dcto}".strip() if dcto else hist)

        dados.append(lanc_corrente)
        lanc_corrente = None

    with pdfplumber.open(uploaded_file) as pdf:
        for pi, page in enumerate(pdf.pages, start=1):
            y_header, boundaries, col_names = _find_header_and_boundaries(page, debug=debug)
            if y_header is None:
                continue

            words = page.extract_words(use_text_flow=True, keep_blank_chars=False)
            words = [w for w in words if w["top"] > y_header + 6]  # abaixo do header

            rows = _cluster_rows(words, y_tol=4.5)

            for r in rows:
                row = _assign_to_columns(r, boundaries, col_names)

                data = _norm(row.get("Data", ""))
                lanc = _norm(row.get("Lancamento", ""))
                dcto = _norm(row.get("Dcto", ""))

                cred = _norm(row.get("Credito", "")) if "Credito" in row else ""
                deb = _norm(row.get("Debito", "")) if "Debito" in row else ""

                if _is_date(data):
                    data_atual = data

                if _is_noise(lanc):
                    continue

                vcred = _to_num_ptbr(cred)
                vdeb = _to_num_ptbr(deb)
                tem_valor = (vcred is not None) or (vdeb is not None)

                if tem_valor:
                    # Se já temos um lançamento com valor, finaliza ele (flush)
                    if lanc_corrente and lanc_corrente.get("Valor") is not None:
                        flush()
                    
                    valor = vcred if vcred is not None else -abs(vdeb)

                    # Se já existe um parcial (descrição prévia sem valor), completamos ele
                    if lanc_corrente:
                         # Atualiza dados que vieram na linha de valor
                        if not lanc_corrente.get("Data") and data_atual:
                            lanc_corrente["Data"] = data_atual
                        if lanc:
                            lanc_corrente["Lancamento"] = _norm(lanc_corrente["Lancamento"] + " " + lanc)
                            lanc_corrente["HistoricoBase"] = lanc_corrente["Lancamento"]
                        if dcto:
                             lanc_corrente["Dcto"] = dcto
                        lanc_corrente["Valor"] = valor
                    
                    else:
                        # Novo lançamento iniciado pela linha de valor
                        lanc_corrente = {
                            "Data": data_atual,
                            "Lancamento": lanc,
                            "Dcto": dcto,
                            "HistoricoBase": lanc,
                            "Valor": valor
                        }
                    continue

                # --- Não tem valor (apenas texto/descrição) ---
                if not lanc_corrente:
                    if lanc:
                        # Inicia possível lançamento (ainda sem valor)
                        lanc_corrente = {
                            "Data": data_atual,
                            "Lancamento": lanc,
                            "Dcto": dcto,
                            "HistoricoBase": lanc,
                            "Valor": None
                        }
                    continue

                # Acumula texto no lançamento corrente (seja ele com valor já ou não)
                if lanc:
                    lanc_corrente["Lancamento"] = _norm(lanc_corrente["Lancamento"] + " " + lanc)
                    lanc_corrente["HistoricoBase"] = lanc_corrente["Lancamento"]

                if dcto and not lanc_corrente.get("Dcto"):
                    lanc_corrente["Dcto"] = dcto

    flush()

    df = pd.DataFrame(dados)
    if df.empty:
        return df

    df = df.reset_index(drop=True)
    df.insert(0, "Nº", df.index + 1)
    return df


# =========================
# STREAMLIT APP
# =========================
st.set_page_config(page_title="Integra Fácil - Bradesco (Coordenadas)", layout="wide")
st.sidebar.title("⚙️ Configurações")

cod_cli = st.sidebar.text_input("Código Domínio", placeholder="Ex: 101")
conta_banco = st.sidebar.text_input("Conta Banco (Reduzida)", placeholder="Ex: 10")

debug_mode = st.sidebar.checkbox("🔎 Debug (mostrar header detectado)", value=False)

st.title("🚀 Integra Fácil - Bradesco (PDF texto / Coordenadas)")

if cod_cli and conta_banco:
    if not os.path.exists("clientes"):
        os.makedirs("clientes")

    path_regra = f"clientes/regra_{cod_cli}.json"
    regras = json.load(open(path_regra, "r", encoding="utf-8")) if os.path.exists(path_regra) else {}

    upload = st.file_uploader("Selecione o PDF do Bradesco (PDF texto)", type="pdf")

    if upload:
        df = extrair_lancamentos_por_coordenadas(upload, debug=debug_mode)

        if not df.empty:
            st.subheader("📊 Conferência de Lançamentos (com numeração)")
            df_view = df.copy()
            df_view["Valor"] = df_view["Valor"].map(lambda x: f"R$ {x:,.2f}")
            st.dataframe(df_view[["Nº", "Data", "Lancamento", "Dcto", "Valor"]],
                         use_container_width=True, hide_index=True)

            st.subheader("🧠 Mapeamento Contábil (somente Histórico Base)")
            novas_regras = {}

            for hbase in df["HistoricoBase"].dropna().unique():
                if hbase in regras:
                    st.success(f"✅ {hbase} -> Conta {regras[hbase]}")
                else:
                    c1, c2 = st.columns([3, 1])
                    c1.warning(f"❓ Novo Histórico Base: **{hbase}**")
                    conta = c2.text_input("Cód. Conta Reduzido", key=f"in_{hbase}")
                    if conta:
                        novas_regras[hbase] = conta

            if st.button("💾 Salvar Memória e Gerar TXT"):
                regras.update(novas_regras)
                with open(path_regra, "w", encoding="utf-8") as f:
                    json.dump(regras, f, ensure_ascii=False, indent=2)

                txt_final = []
                for _, r in df.iterrows():
                    c_map = regras.get(r["HistoricoBase"], "ERRO")
                    c_deb, c_cre = (c_map, conta_banco) if r["Valor"] < 0 else (conta_banco, c_map)

                    data_txt = r["Data"].replace("/", "")
                    val_txt = f"{abs(r['Valor']):.2f}".replace(".", ",")

                    txt_final.append(f"{data_txt}|{c_deb}|{c_cre}|{val_txt}|{r['HistoricoFinal']}")

                st.download_button("📥 Baixar TXT para o Domínio",
                                   "\n".join(txt_final),
                                   file_name=f"dominio_{cod_cli}.txt")
                st.success("Tudo pronto! Mapeamento salvo para o próximo mês.")
        else:
            st.error("Não consegui extrair lançamentos. Ative o modo DEBUG para ver se o cabeçalho está sendo detectado.")
else:
    st.info("👈 Preencha o código do cliente e a conta do banco na barra lateral.")
