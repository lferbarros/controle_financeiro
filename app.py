import streamlit as st
import pandas as pd
import datetime
import uuid
import requests
from dateutil.relativedelta import relativedelta

st.set_page_config(page_title="Gestor Financeiro PRO", layout="wide")

# =========================================================
# 1. GERENCIAMENTO DE CONEXÃO
# =========================================================
if "url_base" not in st.session_state:
    st.session_state.url_base = ""

def logout():
    st.session_state.clear()
    st.rerun()

if not st.session_state.url_base:
    st.title("🚀 Gestor Financeiro")
    url_input = st.text_input("Insira sua URL do Google Apps Script:", type="password")
    if st.button("Conectar Sistema"):
        if "script.google.com" in url_input:
            st.session_state.url_base = url_input
            st.rerun()
        else:
            st.error("URL inválida. Certifique-se de usar o link de 'Execução Web'.")
    st.stop()

URL_SCRIPT = st.session_state.url_base

# =========================================================
# 2. MOTOR DE SINCRONIZAÇÃO (ROBUSTEZ TOTAL)
# =========================================================
def sync_api(payload):
    """Envia dados para o Google Sheets e valida o sucesso."""
    try:
        # Padronização de nomes de colunas para o Google Sheets
        if "Cartao" in payload: payload["Cartão"] = payload.pop("Cartao")
        if "Data" in payload: payload["Data Lanc."] = payload.pop("Data")
        
        response = requests.post(URL_SCRIPT, json=payload, timeout=15)
        return response.status_code == 200
    except Exception as e:
        st.error(f"Falha na comunicação: {e}")
        return False

def carregar_tudo():
    """Recarrega todas as abas da planilha para o estado local."""
    try:
        res = requests.get(URL_SCRIPT, timeout=15).json()
        
        # Categorias
        df_cat = pd.DataFrame(res.get('categorias', []))
        for c in ["Categoria", "Tipo", "ID"]:
            if c not in df_cat.columns: df_cat[c] = None
        st.session_state.df_cat = df_cat

        # Cartões
        df_card = pd.DataFrame(res.get('cartoes', []))
        # Normaliza nome da coluna vindo da planilha
        if "Cartão" in df_card.columns: df_card = df_card.rename(columns={"Cartão": "Cartao"})
        for c in ["Cartao", "Vencimento", "Fechamento", "ID"]:
            if c not in df_card.columns: df_card[c] = None
        st.session_state.df_card = df_card

        # Lançamentos
        df_lan = pd.DataFrame(res.get('lancamentos', []))
        mapeamento = {"Data Lanc.": "Data", "Cartão": "Cartao"}
        df_lan = df_lan.rename(columns=mapeamento)
        for c in ["Data", "Categoria", "Cartao", "Valor", "Data_Efetiva", "Tipo", "ID"]:
            if c not in df_lan.columns: df_lan[c] = None
        st.session_state.df_lan = df_lan
        
        st.session_state.last_sync = datetime.datetime.now()
        return True
    except Exception as e:
        st.error(f"Erro ao baixar dados: {e}")
        return False

# Inicialização única
if 'df_lan' not in st.session_state:
    carregar_tudo()

# =========================================================
# 3. CÁLCULOS E LÓGICA
# =========================================================
def calcular_vencimento(data_o, cartao_n):
    if cartao_n == "Não" or st.session_state.df_card.empty: return data_o
    c = st.session_state.df_card[st.session_state.df_card["Cartao"] == cartao_n]
    if c.empty: return data_o
    try:
        f, v = int(c.iloc[0]["Fechamento"]), int(c.iloc[0]["Vencimento"])
        base = data_o + relativedelta(months=1) if data_o.day > f else data_o
        return datetime.date(base.year, base.month, v)
    except:
        return data_o + relativedelta(months=1)

# =========================================================
# 4. SIDEBAR - CONFIGURAÇÕES (EDITORES ROBUSTOS)
# =========================================================
with st.sidebar:
    st.title("⚙️ Configurações")
    if st.button("🔄 Forçar Atualização"): 
        carregar_tudo()
        st.rerun()
    if st.button("🚪 Sair do Sistema"): logout()
    st.divider()

    # --- CATEGORIAS ---
    st.subheader("Categorias")
    editor_cat = st.data_editor(
        st.session_state.df_cat,
        column_config={
            "ID": None, "id": None,
            "Tipo": st.column_config.SelectboxColumn("Sinal", options=["+", "-"], required=True)
        },
        num_rows="dynamic", hide_index=True, key="edit_cat_widget"
    )

    # Detecção de mudança por estado (Mais estável que comparar len)
    if st.session_state.edit_cat_widget["edited_rows"] or \
       st.session_state.edit_cat_widget["added_rows"] or \
       st.session_state.edit_cat_widget["deleted_rows"]:
        
        changes = st.session_state.edit_cat_widget
        sucesso_total = True
        
        with st.spinner("Sincronizando..."):
            # Deletar
            for idx in changes["deleted_rows"]:
                id_alvo = st.session_state.df_cat.iloc[idx]["ID"]
                if not sync_api({"action": "delete", "table": "Categorias", "ID": id_alvo}): sucesso_total = False
            # Adicionar
            for row in changes["added_rows"]:
                row["ID"] = str(uuid.uuid4())
                if not sync_api({"action": "insert", "table": "Categorias", **row}): sucesso_total = False
            
            if sucesso_total:
                carregar_tudo()
                st.rerun()

    st.divider()

    # --- CARTÕES ---
    st.subheader("Cartões")
    editor_card = st.data_editor(
        st.session_state.df_card,
        column_config={
            "ID": None, "id": None,
            "Cartao": st.column_config.TextColumn("Nome Cartão", required=True),
            "Vencimento": st.column_config.NumberColumn("Dia Venc.", min_value=1, max_value=31),
            "Fechamento": st.column_config.NumberColumn("Dia Fech.", min_value=1, max_value=31)
        },
        num_rows="dynamic", hide_index=True, key="edit_card_widget"
    )

    if st.session_state.edit_card_widget["edited_rows"] or \
       st.session_state.edit_card_widget["added_rows"] or \
       st.session_state.edit_card_widget["deleted_rows"]:
        
        changes = st.session_state.edit_card_widget
        sucesso_total = True
        
        with st.spinner("Sincronizando Cartões..."):
            for idx in changes["deleted_rows"]:
                id_alvo = st.session_state.df_card.iloc[idx]["ID"]
                if not sync_api({"action": "delete", "table": "Cartoes", "ID": id_alvo}): sucesso_total = False
            for row in changes["added_rows"]:
                row["ID"] = str(uuid.uuid4())
                if not sync_api({"action": "insert", "table": "Cartoes", **row}): sucesso_total = False
            
            if sucesso_total:
                carregar_tudo()
                st.rerun()

# =========================================================
# 5. ÁREA PRINCIPAL - LANÇAMENTOS
# =========================================================
st.title("💰 Fluxo de Caixa Projetado")

with st.expander("➕ Novo Lançamento", expanded=False):
    c1, c2, c3, c4 = st.columns(4)
    data_l = c1.date_input("Data Compra", format="DD/MM/YYYY")
    
    cats = st.session_state.df_cat["Categoria"].dropna().tolist()
    cat_sel = c2.selectbox("Categoria", cats if cats else ["Cadastre uma categoria"])
    
    cards = ["Não"] + st.session_state.df_card["Cartao"].dropna().tolist()
    card_sel = c3.selectbox("Cartão", cards)
    
    valor_l = c4.number_input("Valor R$", min_value=0.0, step=10.0, format="%.2f")

    if st.button("Salvar Lançamento", use_container_width=True, type="primary"):
        if not cats:
            st.warning("Adicione categorias na barra lateral primeiro.")
        else:
            sinal = st.session_state.df_cat.loc[st.session_state.df_cat["Categoria"] == cat_sel, "Tipo"].values[0]
            dt_efetiva = calcular_vencimento(data_l, card_sel)
            
            payload = {
                "action": "insert", "table": "Lançamentos", "ID": str(uuid.uuid4()),
                "Data": data_l.isoformat(), "Categoria": cat_sel, "Cartao": card_sel,
                "Tipo": sinal, "Valor": float(valor_l), "Data_Efetiva": dt_efetiva.isoformat()
            }
            
            if sync_api(payload):
                st.toast("Sucesso!")
                carregar_tudo()
                st.rerun()

# =========================================================
# 6. PROCESSAMENTO E EXIBIÇÃO
# =========================================================
def get_render_df():
    if st.session_state.df_lan.empty: return pd.DataFrame()
    df = st.session_state.df_lan.copy()
    df["Data_Efetiva"] = pd.to_datetime(df["Data_Efetiva"], errors='coerce').dt.date
    df = df.dropna(subset=["Data_Efetiva"]).sort_values("Data_Efetiva")
    df["Valor"] = pd.to_numeric(df["Valor"], errors='coerce').fillna(0)
    sinais = df['Tipo'].apply(lambda x: 1 if str(x).strip() == "+" else -1)
    df['Saldo Acumulado'] = (df['Valor'] * sinais).cumsum()
    return df

df_vis = get_render_df()

if not df_vis.empty:
    # Estilo condicional
    def style_rows(row):
        return ['background-color: rgba(255, 75, 75, 0.1)' if row['Saldo Acumulado'] < 0 else '' for _ in row]

    with st.expander("📉 Extrato Detalhado", expanded=True):
        main_editor = st.data_editor(
            df_vis.style.apply(style_rows, axis=1),
            column_config={
                "ID": None, "Tipo": None,
                "Data": st.column_config.DateColumn("Compra", format="DD/MM/YYYY"),
                "Data_Efetiva": st.column_config.DateColumn("Vencimento", format="DD/MM/YYYY"),
                "Valor": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
                "Saldo Acumulado": st.column_config.NumberColumn("Saldo", format="R$ %.2f")
            },
            disabled=df_vis.columns, num_rows="dynamic", hide_index=True, 
            use_container_width=True, key="main_table_widget"
        )

        # Exclusão na Tabela Principal
        if st.session_state.main_table_widget["deleted_rows"]:
            with st.spinner("Excluindo registros..."):
                indices = st.session_state.main_table_widget["deleted_rows"]
                for idx in indices:
                    id_alvo = df_vis.iloc[idx]["ID"]
                    sync_api({"action": "delete", "table": "Lançamentos", "ID": id_alvo})
                carregar_tudo()
                st.rerun()

else:
    st.info("Nenhum dado encontrado. Comece inserindo um lançamento acima.")
