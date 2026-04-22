import streamlit as st
import pandas as pd
import datetime
import uuid
from dateutil.relativedelta import relativedelta
import requests

st.set_page_config(page_title="Gestão Financeira", layout="wide")

# --- CONFIGURAÇÃO DE URL ---
if "URL_SCRIPT" in st.secrets:
    url_planilha = st.secrets["URL_SCRIPT"]
else:
    url_planilha = st.sidebar.text_input("URL do App Script", type="password")

# --- CARGA INICIAL DE DADOS ---
def buscar_dados_nuvem(url):
    if not url: return None
    try:
        # Sem cache aqui para garantir que tragamos sempre o dado novo
        return requests.get(url, timeout=10).json()
    except:
        return None

if 'inicializado' not in st.session_state:
    dados = buscar_dados_nuvem(url_planilha)
    if dados:
        st.session_state.categorias = pd.DataFrame(dados.get('categorias', []))
        st.session_state.cartoes = pd.DataFrame(dados.get('cartoes', []))
        st.session_state.lancamentos = pd.DataFrame(dados.get('lancamentos', []))
    else:
        st.session_state.categorias = pd.DataFrame(columns=["Categoria", "Tipo"])
        st.session_state.cartoes = pd.DataFrame(columns=["Cartão", "Vencimento", "Fechamento"])
        st.session_state.lancamentos = pd.DataFrame(columns=["ID", "Data", "Categoria", "Cartao", "Tipo", "Valor", "Data_Efetiva"])
    st.session_state.inicializado = True

# --- FUNÇÕES DE APOIO ---
def calcular_vencimento(data_c, nome_c):
    if nome_c == "Não" or st.session_state.cartoes.empty: return data_c
    c = st.session_state.cartoes[st.session_state.cartoes["Cartão"] == nome_c]
    if c.empty: return data_c
    f, v = int(c.iloc[0]["Fechamento"]), int(c.iloc[0]["Vencimento"])
    dt_f = datetime.date(data_c.year, data_c.month, f)
    base = data_c + relativedelta(months=1) if data_c > dt_f else data_c
    try: return datetime.date(base.year, base.month, v)
    except: return datetime.date(base.year, base.month, 28)

def obter_df_exibicao():
    if st.session_state.lancamentos.empty: 
        return st.session_state.lancamentos
    
    df = st.session_state.lancamentos.copy()
    
    # --- TRATAMENTO ROBUSTO DE DATAS ---
    # errors='coerce' transforma lixo/erros em NaT (Not a Time)
    df["Data_Efetiva"] = pd.to_datetime(df["Data_Efetiva"], errors='coerce')
    
    # Remove linhas onde a data é inválida (limpa o lixo vindo da planilha)
    df = df.dropna(subset=["Data_Efetiva"])
    
    # Agora sim convertemos para apenas data (sem horas)
    df["Data_Efetiva"] = df["Data_Efetiva"].dt.date
    
    # --- TRATAMENTO DE VALORES ---
    df["Valor"] = pd.to_numeric(df["Valor"], errors='coerce').fillna(0)
    
    # Ordenação
    df = df.sort_values(by="Data_Efetiva").reset_index(drop=True)
    
    # Cálculo de Saldo
    sinais = df['Tipo'].apply(lambda x: 1 if "+" in str(x) else -1)
    df['Saldo Acumulado'] = (df['Valor'] * sinais).cumsum()
    
    return df

# --- SIDEBAR (CADASTROS) ---
with st.sidebar:
    st.header("⚙️ Configurações")
    if st.button("🔄 Sincronizar Agora"):
        del st.session_state.inicializado
        st.rerun()

    with st.expander("Categorias"):
        with st.form("f_cat", clear_on_submit=True):
            nc = st.text_input("Nome")
            tc = st.selectbox("Tipo", ["-", "+"])
            if st.form_submit_button("Adicionar"):
                if nc and url_planilha:
                    new = pd.DataFrame([{"Categoria": nc, "Tipo": tc}])
                    st.session_state.categorias = pd.concat([st.session_state.categorias, new], ignore_index=True)
                    requests.post(url_planilha, json={"action": "add_categoria", "Categoria": nc, "Tipo": tc})
                    st.success("Salvo!")

# --- FORMULÁRIO DE LANÇAMENTO ---
st.title("🏦 Gestão Financeira")
with st.container(border=True):
    st.subheader("Novo Lançamento")
    col1, col2, col3, col4 = st.columns(4)
    with col1: dt_o = st.date_input("Data", key="ins_data")
    with col2:
        cats = st.session_state.categorias["Categoria"].tolist()
        c_sel = st.selectbox("Categoria", cats if cats else ["Cadastre uma categoria"])
    with col3:
        crts = ["Não"] + st.session_state.cartoes["Cartão"].tolist()
        r_sel = st.selectbox("Cartão", crts)
    with col4: v_val = st.number_input("Valor", min_value=0.0, format="%.2f", step=None)

    if st.button("🚀 Confirmar Lançamento", use_container_width=True, type="primary"):
        if not st.session_state.categorias.empty and c_sel in cats:
            t_sinal = st.session_state.categorias.loc[st.session_state.categorias["Categoria"] == c_sel, "Tipo"].values[0]
            dt_e = calcular_vencimento(dt_o, r_sel)
            uid = str(uuid.uuid4())
            
            # 1. ATUALIZAÇÃO LOCAL INSTANTÂNEA
            novo_lanc = {
                "ID": uid, "Data": dt_o.isoformat(), "Categoria": c_sel, 
                "Cartao": r_sel, "Tipo": t_sinal, "Valor": float(v_val), 
                "Data_Efetiva": dt_e.isoformat()
            }
            # Criamos um novo DataFrame e concatenamos
            st.session_state.lancamentos = pd.concat([st.session_state.lancamentos, pd.DataFrame([novo_lanc])], ignore_index=True)
            
            # 2. SINCRONIZAÇÃO EM SEGUNDO PLANO
            try:
                requests.post(url_planilha, json={
                    "action": "insert", "ID": uid, "Data": dt_o.isoformat(),
                    "Categoria": c_sel, "Cartao": r_sel, "Tipo": t_sinal,
                    "Valor": float(v_val), "Data_Efetiva": dt_e.isoformat()
                }, timeout=5)
            except: pass
            
            st.rerun()

# --- TABELA PRINCIPAL ---
st.subheader("Projeção de Fluxo de Caixa")
df_vis = obter_df_exibicao()

def destacar_negativo(row):
    color = 'background-color: rgba(255, 75, 75, 0.15)' if row['Saldo Acumulado'] < 0 else ''
    return [color] * len(row)

if not df_vis.empty:
    # Aplicar o Styler antes de passar para o editor
    styled_df = df_vis.style.apply(destacar_negativo, axis=1)
    
    # IMPORTANTE: Removido o 'key' fixo para evitar que o Streamlit trave no cache do widget
    df_editado = st.data_editor(
        styled_df,
        column_config={
            "ID": None,
            "Data": st.column_config.DateColumn("Ocorrência", format="DD/MM/YYYY"),
            "Data_Efetiva": st.column_config.DateColumn("Data Efetiva", format="DD/MM/YYYY"),
            "Valor": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
            "Saldo Acumulado": st.column_config.NumberColumn("Saldo Previsto", format="R$ %.2f")
        },
        disabled=df_vis.columns,
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic"
    )

    # LÓGICA DE EXCLUSÃO
    if len(df_editado) < len(st.session_state.lancamentos):
        id_vivo = set(df_editado["ID"])
        id_morto = list(set(st.session_state.lancamentos["ID"]) - id_vivo)[0]
        # Remove local
        st.session_state.lancamentos = st.session_state.lancamentos[st.session_state.lancamentos["ID"] != id_morto]
        # Remove nuvem
        requests.post(url_planilha, json={"action": "delete", "ID": id_morto})
        st.rerun()
else:
    st.info("Nenhum lançamento registrado.")
