import streamlit as st
import pandas as pd
import datetime
import uuid
from dateutil.relativedelta import relativedelta
import requests

st.set_page_config(page_title="Gestão Financeira", layout="wide")

# 1. CONFIGURAÇÃO DE ACESSO
if "URL_SCRIPT" in st.secrets:
    url_planilha = st.secrets["URL_SCRIPT"]
else:
    url_planilha = st.sidebar.text_input("URL do App Script", type="password")

# 2. CARGA DE DADOS (SEM CACHE PARA EVITAR TRAVAMENTOS)
def carregar_dados(url):
    if not url: return None
    try:
        r = requests.get(url, timeout=10)
        return r.json()
    except Exception as e:
        st.error(f"Erro de conexão: {e}")
        return None

if 'inicializado' not in st.session_state:
    dados = carregar_dados(url_planilha)
    if dados:
        st.session_state.categorias = pd.DataFrame(dados.get('categorias', []))
        st.session_state.cartoes = pd.DataFrame(dados.get('cartoes', []))
        st.session_state.lancamentos = pd.DataFrame(dados.get('lancamentos', []))
        st.session_state.inicializado = True
    else:
        # Fallback para evitar erro de variável inexistente
        st.session_state.categorias = pd.DataFrame(columns=["Categoria", "Tipo"])
        st.session_state.cartoes = pd.DataFrame(columns=["Cartão", "Vencimento", "Fechamento"])
        st.session_state.lancamentos = pd.DataFrame(columns=["ID", "Data", "Categoria", "Cartao", "Tipo", "Valor", "Data_Efetiva"])

# 3. LÓGICA DE DATAS
def calcular_vencimento(dt_compra, nome_cartao):
    if nome_cartao == "Não" or st.session_state.cartoes.empty: return dt_compra
    c = st.session_state.cartoes[st.session_state.cartoes["Cartão"] == nome_cartao]
    if c.empty: return dt_compra
    f, v = int(c.iloc[0]["Fechamento"]), int(c.iloc[0]["Vencimento"])
    dt_fech = datetime.date(dt_compra.year, dt_compra.month, f)
    base = dt_compra + relativedelta(months=1) if dt_compra > dt_fech else dt_compra
    try: return datetime.date(base.year, base.month, v)
    except: return datetime.date(base.year, base.month, 28)

# 4. PROCESSAMENTO DA TABELA (COM FILTRO ANTI-ERRO)
def get_df_limpo():
    if st.session_state.lancamentos.empty: return st.session_state.lancamentos
    df = st.session_state.lancamentos.copy()
    
    # Converte datas e remove lixo
    df["Data_Efetiva"] = pd.to_datetime(df["Data_Efetiva"], errors='coerce')
    df = df.dropna(subset=["Data_Efetiva"])
    df["Data_Efetiva"] = df["Data_Efetiva"].dt.date
    
    # Converte valores
    df["Valor"] = pd.to_numeric(df["Valor"], errors='coerce').fillna(0)
    df = df.sort_values(by="Data_Efetiva").reset_index(drop=True)
    
    # Saldo
    sinais = df['Tipo'].apply(lambda x: 1 if "+" in str(x) else -1)
    df['Saldo Acumulado'] = (df['Valor'] * sinais).cumsum()
    return df

# 5. INTERFACE - BARRA LATERAL
with st.sidebar:
    st.header("⚙️ Painel de Controle")
    if st.button("🔄 Sincronizar Tudo"):
        st.session_state.clear()
        st.rerun()

    with st.expander("Cadastrar Categoria"):
        with st.form("form_cat", clear_on_submit=True):
            n_c = st.text_input("Nome")
            t_c = st.selectbox("Tipo", ["-", "+"])
            if st.form_submit_button("Salvar"):
                if n_c and url_planilha:
                    requests.post(url_planilha, json={"action": "add_categoria", "Categoria": n_c, "Tipo": t_c})
                    st.session_state.categorias = pd.concat([st.session_state.categorias, pd.DataFrame([{"Categoria": n_c, "Tipo": t_c}])], ignore_index=True)
                    st.rerun()

# 6. LANÇAMENTOS
st.title("🏦 Fluxo de Caixa")
with st.container(border=True):
    col1, col2, col3, col4 = st.columns(4)
    with col1: data_o = st.date_input("Data")
    with col2:
        cat_list = st.session_state.categorias["Categoria"].tolist()
        cat_s = st.selectbox("Categoria", cat_list if cat_list else ["Vazio"])
    with col3:
        cart_list = ["Não"] + st.session_state.cartoes["Cartão"].tolist()
        cart_s = st.selectbox("Cartão", cart_list)
    with col4: valor_s = st.number_input("Valor", min_value=0.0, format="%.2f")

    if st.button("✅ Confirmar Lançamento", use_container_width=True, type="primary"):
        if not st.session_state.categorias.empty and cat_s != "Vazio":
            sinal = st.session_state.categorias.loc[st.session_state.categorias["Categoria"] == cat_s, "Tipo"].values[0]
            data_e = calcular_vencimento(data_o, cart_s)
            uid = str(uuid.uuid4())
            
            payload = {
                "action": "insert", "ID": uid, "Data": data_o.isoformat(),
                "Categoria": cat_s, "Cartao": cart_s, "Tipo": sinal,
                "Valor": float(valor_s), "Data_Efetiva": data_e.isoformat()
            }
            
            # Tenta enviar para o Google
            try:
                resp = requests.post(url_planilha, json=payload, timeout=8)
                if resp.status_code == 200:
                    # Só adiciona localmente se o Google aceitar (ou para ser rápido)
                    st.session_state.lancamentos = pd.concat([st.session_state.lancamentos, pd.DataFrame([payload])], ignore_index=True)
                    st.toast("Lançamento incluído com sucesso!")
                    st.rerun()
                else:
                    st.error(f"Erro no Google Sheets: {resp.text}")
            except Exception as e:
                st.error(f"Falha na rede: {e}")

# 7. EXIBIÇÃO
df_exibir = get_df_limpo()
if not df_exibir.empty:
    st.data_editor(
        df_exibir,
        column_config={
            "ID": None, "Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
            "Data_Efetiva": st.column_config.DateColumn("Vencimento", format="DD/MM/YYYY"),
            "Valor": st.column_config.NumberColumn("Valor (R$)", format="%.2f"),
            "Saldo Acumulado": st.column_config.NumberColumn("Saldo (R$)", format="%.2f")
        },
        disabled=True, use_container_width=True, hide_index=True
    )
    
    # Botão de limpeza de emergência
    if st.button("🗑️ Deletar último lançamento local (apenas emergência)"):
        st.session_state.lancamentos = st.session_state.lancamentos[:-1]
        st.rerun()
else:
    st.info("Nenhum dado encontrado.")
