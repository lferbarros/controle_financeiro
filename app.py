import streamlit as st
import pandas as pd
import datetime
import uuid
from dateutil.relativedelta import relativedelta
import requests

st.set_page_config(page_title="Gestão Financeira Operacional", layout="wide")

# ==========================================
# 1. SEGURANÇA E CARGA DE DADOS
# ==========================================
if "URL_SCRIPT" in st.secrets:
    url_planilha = st.secrets["URL_SCRIPT"]
else:
    url_planilha = st.sidebar.text_input("URL do App Script (Google Sheets)", type="password")

@st.cache_data(show_spinner="Carregando base de dados...")
def carregar_dados_iniciais(url):
    if not url: return None
    try:
        response = requests.get(url, timeout=10)
        return response.json()
    except:
        return None

# ==========================================
# 2. GERENCIAMENTO DE ESTADO
# ==========================================
dados_nuvem = carregar_dados_iniciais(url_planilha)

if 'categorias' not in st.session_state:
    if dados_nuvem and dados_nuvem.get('categorias'):
        st.session_state.categorias = pd.DataFrame(dados_nuvem['categorias'])
    else:
        st.session_state.categorias = pd.DataFrame(columns=["Categoria", "Tipo"])

if 'cartoes' not in st.session_state:
    if dados_nuvem and dados_nuvem.get('cartoes'):
        st.session_state.cartoes = pd.DataFrame(dados_nuvem['cartoes'])
    else:
        st.session_state.cartoes = pd.DataFrame(columns=["Cartão", "Vencimento", "Fechamento"])

if 'lancamentos' not in st.session_state:
    st.session_state.lancamentos = pd.DataFrame(columns=["ID", "Data", "Categoria", "Cartao", "Tipo", "Valor", "Data_Efetiva"])

# ==========================================
# 3. LÓGICA DE NEGÓCIO
# ==========================================
def calcular_data_efetiva(data_compra, nome_cartao):
    if nome_cartao == "Não" or not nome_cartao:
        return data_compra
    cartao_info = st.session_state.cartoes[st.session_state.cartoes["Cartão"] == nome_cartao]
    if cartao_info.empty: return data_compra
    dia_fechamento = int(cartao_info.iloc[0]["Fechamento"])
    dia_vencimento = int(cartao_info.iloc[0]["Vencimento"])
    data_fechamento_mes = datetime.date(data_compra.year, data_compra.month, dia_fechamento)
    base_vencimento = data_compra + relativedelta(months=1) if data_compra > data_fechamento_mes else data_compra
    try:
        return datetime.date(base_vencimento.year, base_vencimento.month, dia_vencimento)
    except:
        return datetime.date(base_vencimento.year, base_vencimento.month, 28)

def processar_exibicao():
    if not st.session_state.lancamentos.empty:
        df = st.session_state.lancamentos.copy()
        df["Data"] = pd.to_datetime(df["Data"]).dt.date
        df["Data_Efetiva"] = pd.to_datetime(df["Data_Efetiva"]).dt.date
        df = df.sort_values(by="Data_Efetiva").reset_index(drop=True)
        sinais = df['Tipo'].apply(lambda x: 1 if x == '+' else -1)
        df['Saldo Acumulado'] = (pd.to_numeric(df['Valor']) * sinais).cumsum()
        return df
    return st.session_state.lancamentos

# ==========================================
# 4. BARRA LATERAL (CADASTROS PERSISTENTES)
# ==========================================
with st.sidebar:
    st.header("⚙️ Cadastros Base")
    with st.expander("Categorias"):
        with st.form("form_cat", clear_on_submit=True):
            n_cat = st.text_input("Nova Categoria")
            t_cat = st.selectbox("Sinal", ["-", "+"])
            if st.form_submit_button("Salvar Categoria"):
                if n_cat and url_planilha:
                    requests.post(url_planilha, json={"action": "add_categoria", "Categoria": n_cat, "Tipo": t_cat})
                    st.session_state.categorias = pd.concat([st.session_state.categorias, pd.DataFrame([{"Categoria": n_cat, "Tipo": t_cat}])], ignore_index=True)
                    st.cache_data.clear()
                    st.rerun()

    with st.expander("Cartões de Crédito"):
        with st.form("form_cartao", clear_on_submit=True):
            n_cartao = st.text_input("Nome do Cartão")
            venc = st.number_input("Dia Vencimento", 1, 31, 10)
            fech = st.number_input("Dia Fechamento", 1, 31, 3)
            if st.form_submit_button("Cadastrar Cartão"):
                if n_cartao and url_planilha:
                    requests.post(url_planilha, json={"action": "add_cartao", "Cartao": n_cartao, "Vencimento": venc, "Fechamento": fech})
                    st.session_state.cartoes = pd.concat([st.session_state.cartoes, pd.DataFrame([{"Cartão": n_cartao, "Vencimento": venc, "Fechamento": fech}])], ignore_index=True)
                    st.cache_data.clear()
                    st.rerun()

# ==========================================
# 5. LANÇAMENTOS
# ==========================================
st.title("🏦 Fluxo de Caixa Operacional")
with st.container(border=True):
    st.subheader("Novo Lançamento")
    c1, c2, c3, c4 = st.columns(4)
    with c1: d_lanc = st.date_input("Data da Ocorrência")
    with c2:
        lista_c = st.session_state.categorias["Categoria"].tolist()
        cat_sel = st.selectbox("Categoria", lista_c if lista_c else ["Defina uma categoria"])
    with c3:
        lista_cart = ["Não"] + st.session_state.cartoes["Cartão"].tolist()
        cart_sel = st.selectbox("Cartão de Crédito", lista_cart)
    with c4: valor = st.number_input("Valor", min_value=0.0, format="%.2f", step=None)

    if st.button("Confirmar Lançamento", use_container_width=True, type="primary"):
        if not st.session_state.categorias.empty and cat_sel != "Defina uma categoria":
            tipo = st.session_state.categorias.loc[st.session_state.categorias["Categoria"] == cat_sel, "Tipo"].values[0]
            data_efetiva = calcular_data_efetiva(d_lanc, cart_sel)
            id_lanc = str(uuid.uuid4())
            novo = pd.DataFrame([{"ID": id_lanc, "Data": d_lanc, "Categoria": cat_sel, "Cartao": cart_sel, "Tipo": tipo, "Valor": valor, "Data_Efetiva": data_efetiva}])
            st.session_state.lancamentos = pd.concat([st.session_state.lancamentos, novo], ignore_index=True)
            if url_planilha:
                requests.post(url_planilha, json={"action": "insert", "ID": id_lanc, "Data": d_lanc.isoformat(), "Categoria": cat_sel, "Cartao": cart_sel, "Tipo": tipo, "Valor": valor, "Data_Efetiva": data_efetiva.isoformat()})
            st.rerun()

st.divider()

# ==========================================
# 6. TABELA DINÂMICA
# ==========================================
st.subheader("Projeção de Saldo Bancário")
df_final = processar_exibicao()

def colorir_saldo_negativo(row):
    return ['background-color: rgba(255, 75, 75, 0.2)'] * len(row) if row['Saldo Acumulado'] < 0 else [''] * len(row)

if not df_final.empty:
    styled_df = df_final.style.apply(colorir_saldo_negativo, axis=1)
    df_editado = st.data_editor(
        styled_df,
        column_config={
            "ID": None, "Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
            "Valor": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
            "Saldo Acumulado": st.column_config.NumberColumn("Saldo Previsto", format="R$ %.2f"),
            "Data_Efetiva": st.column_config.DateColumn("Data Efetiva", format="DD/MM/YYYY")
        },
        disabled=["Data", "Categoria", "Cartao", "Tipo", "Valor", "Data_Efetiva", "Saldo Acumulado"], 
        num_rows="dynamic", use_container_width=True, hide_index=True
    )
    
    if len(df_editado) < len(st.session_state.lancamentos):
        id_del = list(set(st.session_state.lancamentos["ID"]) - set(df_editado["ID"]))[0]
        if url_planilha: requests.post(url_planilha, json={"action": "delete", "ID": id_del})
        st.session_state.lancamentos = df_editado.drop(columns=["Saldo Acumulado"], errors="ignore")
        st.rerun()
else:
    st.info("Aguardando lançamentos.")
