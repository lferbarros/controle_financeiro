import streamlit as st
import pandas as pd
import datetime
import uuid
from dateutil.relativedelta import relativedelta
import requests

st.set_page_config(page_title="Gestão Financeira Pro", layout="wide")

# --- CONEXÃO ---
URL_SCRIPT = st.secrets.get("URL_SCRIPT") or st.sidebar.text_input("URL do App Script", type="password")

def sync_api(payload):
    try:
        requests.post(URL_SCRIPT, json=payload, timeout=10)
        return True
    except:
        return False

def carregar_tudo():
    if not URL_SCRIPT: return
    try:
        res = requests.get(URL_SCRIPT, timeout=10).json()
        st.session_state.df_cat = pd.DataFrame(res.get('categorias', []))
        st.session_state.df_card = pd.DataFrame(res.get('cartoes', []))
        st.session_state.df_lan = pd.DataFrame(res.get('lancamentos', []))
        st.session_state.last_sync = datetime.datetime.now()
    except:
        st.error("Erro ao carregar dados da nuvem.")

if 'df_lan' not in st.session_state:
    carregar_tudo()

# --- LÓGICA DE DATAS ---
def calcular_vencimento(data_o, cartao_n):
    if cartao_n == "Não" or st.session_state.df_card.empty: return data_o
    c = st.session_state.df_card[st.session_state.df_card["Cartão"] == cartao_n]
    if c.empty: return data_o
    f, v = int(c.iloc[0]["Fechamento"]), int(c.iloc[0]["Vencimento"])
    dt_f = datetime.date(data_o.year, data_o.month, f)
    base = data_o + relativedelta(months=1) if data_o > dt_f else data_o
    try: return datetime.date(base.year, base.month, v)
    except: return datetime.date(base.year, base.month, 28)

# --- SIDEBAR (TABELAS VIVAS) ---
with st.sidebar:
    st.title("⚙️ Configurações")
    
    # Tabela de Categorias
    st.subheader("Categorias")
    cat_editada = st.data_editor(
        st.session_state.df_cat,
        column_config={
            "ID": None,
            "Categoria": st.column_config.TextColumn("Nome", help="Nome da categoria"),
            "Tipo": st.column_config.SelectboxColumn("Sinal", options=["+", "-"], required=True)
        },
        num_rows="dynamic",
        hide_index=True,
        key="editor_categorias"
    )

    # Sincronização Automática de Categorias
    if len(cat_editada) != len(st.session_state.df_cat):
        if len(cat_editada) > len(st.session_state.df_cat): # Inclusão
            nova_linha = cat_editada.iloc[-1].copy()
            nova_linha['ID'] = str(uuid.uuid4())
            sync_api({"action": "insert", "table": "Categorias", **nova_linha.to_dict()})
        else: # Exclusão
            id_removido = set(st.session_state.df_cat["ID"]) - set(cat_editada["ID"])
            if id_removido: sync_api({"action": "delete", "table": "Categorias", "ID": list(id_removido)[0]})
        st.session_state.df_cat = cat_editada
        st.rerun()

    st.divider()

    # Tabela de Cartões
    st.subheader("Cartões")
    card_editado = st.data_editor(
        st.session_state.df_card,
        column_config={
            "ID": None,
            "Cartão": st.column_config.TextColumn("Nome"),
            "Vencimento": st.column_config.NumberColumn("Venc.", min_value=1, max_value=31, format="%d"),
            "Fechamento": st.column_config.NumberColumn("Fech.", min_value=1, max_value=31, format="%d")
        },
        num_rows="dynamic",
        hide_index=True,
        key="editor_cartoes"
    )

    if len(card_editado) != len(st.session_state.df_card):
        if len(card_editado) > len(st.session_state.df_card):
            nova_linha = card_editado.iloc[-1].copy()
            nova_linha['ID'] = str(uuid.uuid4())
            sync_api({"action": "insert", "table": "Cartoes", **nova_linha.to_dict()})
        else:
            id_removido = set(st.session_state.df_card["ID"]) - set(card_editado["ID"])
            if id_removido: sync_api({"action": "delete", "table": "Cartoes", "ID": list(id_removido)[0]})
        st.session_state.df_card = card_editado
        st.rerun()

# --- ÁREA PRINCIPAL ---
st.title("🏦 Controle Financeiro Operacional")

# Formulário de Lançamento
with st.expander("➕ Novo Lançamento", expanded=True):
    col1, col2, col3, col4 = st.columns(4)
    with col1: data_o = st.date_input("Data Ocorrência")
    with col2:
        cats = st.session_state.df_cat["Categoria"].tolist()
        cat_s = st.selectbox("Categoria", cats if cats else ["Cadastre na lateral"])
    with col3:
        cards = ["Não"] + st.session_state.df_card["Cartão"].tolist()
        card_s = st.selectbox("Cartão", cards)
    with col4: valor_s = st.number_input("Valor", min_value=0.0, format="%.2f")

    if st.button("Confirmar Lançamento", use_container_width=True, type="primary"):
        if cat_s in cats:
            sinal = st.session_state.df_cat.loc[st.session_state.df_cat["Categoria"] == cat_s, "Tipo"].values[0]
            data_e = calcular_vencimento(data_o, card_s)
            uid = str(uuid.uuid4())
            
            payload = {
                "action": "insert", "table": "Lançamentos", "ID": uid,
                "Data": data_o.isoformat(), "Categoria": cat_s, "Cartao": card_s,
                "Tipo": sinal, "Valor": float(valor_s), "Data_Efetiva": data_e.isoformat()
            }
            if sync_api(payload):
                st.toast("Lançamento salvo!")
                carregar_tudo()
                st.rerun()

# --- TABELA PRINCIPAL COM FORMATAÇÃO ---
st.subheader("Projeção de Saldo e Fluxo")

def get_df_final():
    if st.session_state.df_lan.empty: return pd.DataFrame()
    df = st.session_state.df_lan.copy()
    df["Data_Efetiva"] = pd.to_datetime(df["Data_Efetiva"], errors='coerce')
    df = df.dropna(subset=["Data_Efetiva"]).sort_values("Data_Efetiva")
    df["Valor"] = pd.to_numeric(df["Valor"], errors='coerce').fillna(0)
    
    # Cálculo de saldo
    sinais = df['Tipo'].apply(lambda x: 1 if str(x).strip() == "+" else -1)
    df['Saldo Acumulado'] = (df['Valor'] * sinais).cumsum()
    return df

df_final = get_df_final()

def style_negative(row):
    return ['background-color: rgba(255, 75, 75, 0.15)' if row['Saldo Acumulado'] < 0 else '' for _ in row]

if not df_final.empty:
    # Aplicar Estilo
    df_styled = df_final.style.apply(style_negative, axis=1)
    
    # Editor Principal (Permite exclusão selecionando a linha e apertando Delete)
    lan_editado = st.data_editor(
        df_styled,
        column_config={
            "ID": None,
            "Data": st.column_config.DateColumn("Ocorrência", format="DD/MM/YYYY"),
            "Data_Efetiva": st.column_config.DateColumn("Vencimento", format="DD/MM/YYYY"),
            "Valor": st.column_config.NumberColumn("Valor (R$)", format="%.2f"),
            "Saldo Acumulado": st.column_config.NumberColumn("Saldo (R$)", format="%.2f")
        },
        disabled=["Data", "Categoria", "Cartao", "Tipo", "Valor", "Data_Efetiva", "Saldo Acumulado"],
        num_rows="dynamic", # Habilita a lixeira lateral para exclusão
        hide_index=True,
        use_container_width=True,
        key="editor_principal"
    )

    # Sincronizar Exclusão da Tabela Principal
    if len(lan_editado) < len(df_final):
        id_morto = set(df_final["ID"]) - set(lan_editado["ID"])
        if id_morto:
            sync_api({"action": "delete", "table": "Lançamentos", "ID": list(id_morto)[0]})
            carregar_tudo()
            st.rerun()
else:
    st.info("Aguardando lançamentos...")
