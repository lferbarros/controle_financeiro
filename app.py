import streamlit as st
import pandas as pd
import datetime
import uuid
from dateutil.relativedelta import relativedelta
import requests

st.set_page_config(page_title="Gestão Financeira Operacional", layout="wide")

# ==========================================
# 1. COMUNICAÇÃO E CACHE INTELIGENTE
# ==========================================
if "URL_SCRIPT" in st.secrets:
    url_planilha = st.secrets["URL_SCRIPT"]
else:
    url_planilha = st.sidebar.text_input("URL do App Script (Google Sheets)", type="password")

@st.cache_data(show_spinner="Sincronizando com a nuvem...")
def carregar_dados_nuvem(url):
    if not url: return None
    try:
        response = requests.get(url, timeout=10)
        return response.json()
    except:
        return None

# ==========================================
# 2. ESTADO DA SESSÃO (LOCAL FIRST)
# ==========================================
# Carrega apenas uma vez ao abrir o app
if 'carregado' not in st.session_state:
    dados = carregar_dados_nuvem(url_planilha)
    if dados:
        st.session_state.categorias = pd.DataFrame(dados.get('categorias', []))
        st.session_state.cartoes = pd.DataFrame(dados.get('cartoes', []))
        st.session_state.lancamentos = pd.DataFrame(dados.get('lancamentos', []))
    else:
        st.session_state.categorias = pd.DataFrame(columns=["Categoria", "Tipo"])
        st.session_state.cartoes = pd.DataFrame(columns=["Cartão", "Vencimento", "Fechamento"])
        st.session_state.lancamentos = pd.DataFrame(columns=["ID", "Data", "Categoria", "Cartao", "Tipo", "Valor", "Data_Efetiva"])
    st.session_state.carregado = True

# ==========================================
# 3. FUNÇÕES DE APOIO
# ==========================================
def calcular_data_efetiva(data_compra, nome_cartao):
    if nome_cartao == "Não" or not nome_cartao or st.session_state.cartoes.empty:
        return data_compra
    cartao_info = st.session_state.cartoes[st.session_state.cartoes["Cartão"] == nome_cartao]
    if cartao_info.empty: return data_compra
    
    dia_f = int(cartao_info.iloc[0]["Fechamento"])
    dia_v = int(cartao_info.iloc[0]["Vencimento"])
    data_fechamento_mes = datetime.date(data_compra.year, data_compra.month, dia_f)
    base_venc = data_compra + relativedelta(months=1) if data_compra > data_fechamento_mes else data_compra
    try:
        return datetime.date(base_venc.year, base_venc.month, dia_v)
    except:
        return datetime.date(base_venc.year, base_venc.month, 28)

def processar_exibicao():
    if st.session_state.lancamentos.empty:
        return st.session_state.lancamentos
    
    df = st.session_state.lancamentos.copy()
    df["Data_Efetiva"] = pd.to_datetime(df["Data_Efetiva"]).dt.date
    df = df.sort_values(by="Data_Efetiva").reset_index(drop=True)
    
    # Cálculo de saldo robusto
    def conv_sinal(x): return 1 if "+" in str(x) else -1
    sinais = df['Tipo'].apply(conv_sinal)
    valores = pd.to_numeric(df['Valor'], errors='coerce').fillna(0)
    df['Saldo Acumulado'] = (valores * sinais).cumsum()
    return df

# ==========================================
# 4. INTERFACE - BARRA LATERAL
# ==========================================
with st.sidebar:
    st.header("⚙️ Cadastros Base")
    
    # Botão de atualização manual (caso queira forçar sincronia)
    if st.button("🔄 Forçar Sincronia com Planilha"):
        st.cache_data.clear()
        del st.session_state.carregado
        st.rerun()

    with st.expander("Categorias"):
        with st.form("form_cat", clear_on_submit=True):
            n_cat = st.text_input("Nova Categoria")
            t_cat = st.selectbox("Sinal", ["-", "+"])
            if st.form_submit_button("Salvar"):
                if n_cat and url_planilha:
                    nova_linha = pd.DataFrame([{"Categoria": n_cat, "Tipo": t_cat}])
                    st.session_state.categorias = pd.concat([st.session_state.categorias, nova_linha], ignore_index=True)
                    requests.post(url_planilha, json={"action": "add_categoria", "Categoria": n_cat, "Tipo": "'"+t_cat})
                    st.toast("Categoria Salva!")

    with st.expander("Cartões"):
        with st.form("form_cartao", clear_on_submit=True):
            n_cart = st.text_input("Nome do Cartão")
            v_dia = st.number_input("Vencimento (Dia)", 1, 31, 10)
            f_dia = st.number_input("Fechamento (Dia)", 1, 31, 3)
            if st.form_submit_button("Cadastrar"):
                if n_cart and url_planilha:
                    nova_linha = pd.DataFrame([{"Cartão": n_cart, "Vencimento": v_dia, "Fechamento": f_dia}])
                    st.session_state.cartoes = pd.concat([st.session_state.cartoes, nova_linha], ignore_index=True)
                    requests.post(url_planilha, json={"action": "add_cartao", "Cartao": n_cart, "Vencimento": v_dia, "Fechamento": f_dia})
                    st.toast("Cartão Salvo!")

# ==========================================
# 5. PAINEL PRINCIPAL
# ==========================================
st.title("🏦 Fluxo de Caixa Operacional")

with st.container(border=True):
    st.subheader("Novo Lançamento")
    c1, c2, c3, c4 = st.columns(4)
    with c1: d_lan = st.date_input("Data da Ocorrência")
    with c2:
        list_c = st.session_state.categorias["Categoria"].tolist()
        cat_s = st.selectbox("Categoria", list_c if list_c else ["Defina uma categoria"])
    with c3:
        list_cr = ["Não"] + st.session_state.cartoes["Cartão"].tolist()
        cart_s = st.selectbox("Cartão de Crédito", list_cr)
    with c4: val = st.number_input("Valor", min_value=0.0, format="%.2f", step=None)

    if st.button("Confirmar Lançamento", use_container_width=True, type="primary"):
        if not st.session_state.categorias.empty and cat_s != "Defina uma categoria":
            tipo = st.session_state.categorias.loc[st.session_state.categorias["Categoria"] == cat_s, "Tipo"].values[0]
            data_ef = calcular_data_efetiva(d_lan, cart_s)
            id_u = str(uuid.uuid4())
            
            # 1. Atualiza Localmente (Instantâneo)
            novo_item = {
                "ID": id_u, "Data": d_lan.isoformat(), "Categoria": cat_s, 
                "Cartao": cart_s, "Tipo": tipo, "Valor": val, "Data_Efetiva": data_ef.isoformat()
            }
            st.session_state.lancamentos = pd.concat([st.session_state.lancamentos, pd.DataFrame([novo_item])], ignore_index=True)
            
            # 2. Envia para Nuvem (Background)
            if url_planilha:
                try:
                    requests.post(url_planilha, json={
                        "action": "insert", "ID": id_u, "Data": d_lan.isoformat(),
                        "Categoria": cat_s, "Cartao": cart_s, "Tipo": "'"+str(tipo).replace("'",""),
                        "Valor": val, "Data_Efetiva": data_ef.isoformat()
                    }, timeout=5)
                except:
                    st.error("Erro ao sincronizar com a planilha, mas o dado foi salvo localmente.")
            
            st.rerun()

st.divider()

# ==========================================
# 6. TABELA COM DESTAQUE DE SALDO NEGATIVO
# ==========================================
st.subheader("Projeção de Saldo Bancário")
df_f = processar_exibicao()

def style_negative(row):
    color = 'background-color: rgba(255, 75, 75, 0.2)' if row['Saldo Acumulado'] < 0 else ''
    return [color] * len(row)

if not df_f.empty:
    styled = df_f.style.apply(style_negative, axis=1)
    
    # Editor de dados
    df_ed = st.data_editor(
        styled,
        column_config={
            "ID": None,
            "Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
            "Valor": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
            "Saldo Acumulado": st.column_config.NumberColumn("Saldo Previsto", format="R$ %.2f"),
            "Data_Efetiva": st.column_config.DateColumn("Data Efetiva", format="DD/MM/YYYY")
        },
        disabled=df_f.columns, # Bloqueia edição direta para evitar bugs de sync
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key="editor_principal"
    )

    # Lógica de Exclusão (Se o usuário deletar uma linha no editor)
    if len(df_ed) < len(st.session_state.lancamentos):
        ids_vivos = set(df_ed["ID"])
        # Encontra qual ID foi removido
        removido = st.session_state.lancamentos[~st.session_state.lancamentos["ID"].isin(ids_vivos)]
        if not removido.empty:
            id_para_deletar = removido.iloc[0]["ID"]
            # Atualiza local
            st.session_state.lancamentos = st.session_state.lancamentos[st.session_state.lancamentos["ID"] != id_para_deletar]
            # Atualiza nuvem
            if url_planilha:
                requests.post(url_planilha, json={"action": "delete", "ID": id_para_deletar}, timeout=5)
            st.rerun()
else:
    st.info("Nenhum lançamento para exibir.")
