import streamlit as st
import pandas as pd
import datetime
import uuid
from dateutil.relativedelta import relativedelta
import requests

st.set_page_config(page_title="Gestão Financeira", layout="wide")

# 1. URL E CONEXÃO
if "URL_SCRIPT" in st.secrets:
    url_planilha = st.secrets["URL_SCRIPT"]
else:
    url_planilha = st.sidebar.text_input("URL do App Script", type="password")

def carregar_dados_direto(url):
    if not url: return None
    try:
        # Removido cache para garantir sincronia total
        response = requests.get(url, timeout=10)
        return response.json()
    except:
        return None

# 2. ESTADO DA SESSÃO
if 'dados_financeiros' not in st.session_state:
    res = carregar_dados_direto(url_planilha)
    if res:
        st.session_state.categorias = pd.DataFrame(res.get('categorias', []))
        st.session_state.cartoes = pd.DataFrame(res.get('cartoes', []))
        st.session_state.lancamentos = pd.DataFrame(res.get('lancamentos', []))
        st.session_state.dados_financeiros = True
    else:
        st.session_state.categorias = pd.DataFrame(columns=["Categoria", "Tipo"])
        st.session_state.cartoes = pd.DataFrame(columns=["Cartão", "Vencimento", "Fechamento"])
        st.session_state.lancamentos = pd.DataFrame(columns=["ID", "Data", "Categoria", "Cartao", "Tipo", "Valor", "Data_Efetiva"])

# 3. LÓGICA DE NEGÓCIO (DATA EFETIVA)
def calcular_data_vencimento(data_o, cartao_n):
    if cartao_n == "Não" or st.session_state.cartoes.empty: return data_o
    info = st.session_state.cartoes[st.session_state.cartoes["Cartão"] == cartao_n]
    if info.empty: return data_o
    f, v = int(info.iloc[0]["Fechamento"]), int(info.iloc[0]["Vencimento"])
    dt_fech = datetime.date(data_o.year, data_o.month, f)
    base = data_o + relativedelta(months=1) if data_o > dt_fech else data_o
    try: return datetime.date(base.year, base.month, v)
    except: return datetime.date(base.year, base.month, 28)

# 4. TRATAMENTO DA TABELA
def preparar_df():
    if st.session_state.lancamentos.empty: return st.session_state.lancamentos
    df = st.session_state.lancamentos.copy()
    
    # Blindagem contra erros de data (ValueError)
    df["Data_Efetiva"] = pd.to_datetime(df["Data_Efetiva"], errors='coerce')
    df = df.dropna(subset=["Data_Efetiva"])
    df["Data_Efetiva"] = df["Data_Efetiva"].dt.date
    
    # Conversão de valores e ordenação
    df["Valor"] = pd.to_numeric(df["Valor"], errors='coerce').fillna(0)
    df = df.sort_values(by="Data_Efetiva").reset_index(drop=True)
    
    # Cálculo do saldo
    sinais = df['Tipo'].apply(lambda x: 1 if "+" in str(x) else -1)
    df['Saldo Acumulado'] = (df['Valor'] * sinais).cumsum()
    return df

# 5. INTERFACE (SIDEBAR)
with st.sidebar:
    st.header("⚙️ Sincronização")
    if st.button("🔄 Atualizar Dados da Planilha"):
        del st.session_state.dados_financeiros
        st.rerun()

# 6. NOVO LANÇAMENTO
st.title("🏦 Fluxo de Caixa Operacional")
with st.container(border=True):
    c1, c2, c3, c4 = st.columns(4)
    with c1: data_mov = st.date_input("Data da Compra")
    with c2:
        lista_cat = st.session_state.categorias["Categoria"].tolist()
        cat_escolhida = st.selectbox("Categoria", lista_cat if lista_cat else ["Nenhuma"])
    with c3:
        lista_cart = ["Não"] + st.session_state.cartoes["Cartão"].tolist()
        cart_escolhido = st.selectbox("Cartão de Crédito", lista_cart)
    with c4: valor_mov = st.number_input("Valor", min_value=0.0, format="%.2f")

    if st.button("🚀 Confirmar Lançamento", use_container_width=True, type="primary"):
        if cat_escolhida != "Nenhuma" and url_planilha:
            tipo_sinal = st.session_state.categorias.loc[st.session_state.categorias["Categoria"] == cat_escolhida, "Tipo"].values[0]
            data_venc = calcular_data_vencimento(data_mov, cart_escolhido)
            novo_id = str(uuid.uuid4())
            
            payload = {
                "action": "insert", "ID": novo_id, "Data": data_mov.isoformat(),
                "Categoria": cat_escolhida, "Cartao": cart_escolhido, "Tipo": tipo_sinal,
                "Valor": float(valor_mov), "Data_Efetiva": data_venc.isoformat()
            }
            
            # Envia para o Google
            with st.spinner("Enviando..."):
                try:
                    res_post = requests.post(url_planilha, json=payload, timeout=10)
                    if res_post.status_code == 200:
                        # Se o Google aceitou, atualizamos o estado local e forçamos recarga
                        st.toast("Sucesso!")
                        del st.session_state.dados_financeiros # Isso força recarregar tudo do Google no próximo rerun
                        st.rerun()
                except Exception as e:
                    st.error(f"Erro ao salvar: {e}")

# 7. EXIBIÇÃO DA TABELA
st.subheader("Projeção de Saldo")
df_display = preparar_df()

if not df_display.empty:
    st.data_editor(
        df_display,
        column_config={
            "ID": None,
            "Data": st.column_config.DateColumn("Ocorrência", format="DD/MM/YYYY"),
            "Data_Efetiva": st.column_config.DateColumn("Vencimento", format="DD/MM/YYYY"),
            "Valor": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
            "Saldo Acumulado": st.column_config.NumberColumn("Saldo Previsto", format="R$ %.2f")
        },
        disabled=df_display.columns,
        use_container_width=True,
        hide_index=True
    )
    
    # Lógica de exclusão rápida
    if st.button("🗑️ Excluir Último Lançamento"):
        ultimo_id = df_display.iloc[-1]["ID"]
        requests.post(url_planilha, json={"action": "delete", "ID": ultimo_id})
        del st.session_state.dados_financeiros
        st.rerun()
else:
    st.info("Nenhum lançamento encontrado.")
