import streamlit as st
import pandas as pd
import requests
from datetime import datetime

# --- CONFIGURAÇÕES ---
URL_PLANILHA = "https://docs.google.com/spreadsheets/d/1rH7Uz_BhlUMDJJXGrRWg7zuEQUCbRQCGAFbE0Pu9NwI/edit?usp=sharing"
URL_PONTE_SALVAR = "https://script.google.com/macros/s/AKfycbz3ayt3DRFHAwSMfMoJtaa3ftRcw6ZRjNKGcUXn0CSzI9UQNnBNTLuKQ6_pQy3MZFK7/exec"
GID_CONFIG = "1701820250" 

csv_lanc = URL_PLANILHA.replace('/edit?usp=sharing', '/export?format=csv&gid=0')
csv_cfg = URL_PLANILHA.replace('/edit?usp=sharing', f'/export?format=csv&gid={GID_CONFIG}')

st.set_page_config(page_title="Financeiro Pro", layout="wide")

# --- CARGA DE DADOS ---
# Removemos o cache aqui para garantir que a sincronização seja imediata
def carregar_tudo():
    try:
        df_l = pd.read_csv(csv_lanc)
        df_l['Data'] = pd.to_datetime(df_l['Data'], errors='coerce').dt.date
        
        cfg = pd.read_csv(csv_cfg)
        s_ini = float(cfg['Saldo Inicial'].iloc[0]) if not cfg.empty else 0.0
        d_str = cfg['Data Inicial'].iloc[0] if not cfg.empty else str(datetime.now().date())
        d_ini = pd.to_datetime(d_str).date()
        # Selecionamos APENAS as colunas que importam para limpar colunas fantasmas
        cats = cfg[['Categoria', 'Sinal']].dropna(subset=['Categoria'])
        return df_l, s_ini, d_ini, cats
    except:
        return None

if 'df_lanc' not in st.session_state:
    dados = carregar_tudo()
    if dados:
        st.session_state.df_lanc, st.session_state.saldo_inicial, \
        st.session_state.data_saldo_inicial, st.session_state.df_cats = dados
    else:
        st.session_state.df_lanc = pd.DataFrame(columns=['Data', 'Categoria', 'Valor'])
        st.session_state.saldo_inicial = 0.0
        st.session_state.data_saldo_inicial = datetime.now().date()
        st.session_state.df_cats = pd.DataFrame({'Categoria': ['Salário'], 'Sinal': ['+']})

# --- SIDEBAR (CATEGORIAS) ---
with st.sidebar:
    st.header("⚙️ Configurações")
    # ITEM 2: Garantir que apenas 'Categoria' e 'Sinal' apareçam
    st.session_state.df_cats = st.data_editor(
        st.session_state.df_cats[['Categoria', 'Sinal']], 
        num_rows="dynamic",
        use_container_width=True,
        column_config={"Sinal": st.column_config.SelectboxColumn("Op.", options=["+", "-"])},
        key="editor_categorias"
    )

# --- CABEÇALHO ---
st.title("💰 Extrato Financeiro")
col1, col2, col3, col4 = st.columns([2, 2, 1.5, 1.5])
with col3:
    st.session_state.data_saldo_inicial = st.date_input("Data Inicial", st.session_state.data_saldo_inicial)
with col4:
    st.session_state.saldo_inicial = st.number_input("Saldo Inicial", value=float(st.session_state.saldo_inicial), format="%.2f")

# --- CÁLCULO DO EXTRATO ---
def processar_visualizacao(df_l, df_c, s_ini):
    if df_l.empty:
        return pd.DataFrame(columns=['Data', 'Categoria', 'Valor', 'Saldo_Acumulado'])
    
    df = df_l.copy()
    df['Valor'] = pd.to_numeric(df['Valor'], errors='coerce').fillna(0.0)
    
    # Merge limpo
    df = df.merge(df_c[['Categoria', 'Sinal']], on='Categoria', how='left')
    df['Sinal'] = df['Sinal'].fillna('+')
    df['Real'] = df['Valor'] * df['Sinal'].map({'+': 1, '-': -1})
    
    df = df.sort_values('Data')
    df['Saldo_Acumulado'] = s_ini + df['Real'].cumsum()
    
    return df[['Data', 'Categoria', 'Valor', 'Saldo_Acumulado']]

# ITEM 1: Atualização em tempo real das opções da caixa de categorias
opcoes_categorias = sorted(st.session_state.df_cats['Categoria'].unique().tolist())

df_viz = processar_visualizacao(st.session_state.df_lanc, st.session_state.df_cats, st.session_state.saldo_inicial)

df_editado = st.data_editor(
    df_viz,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
        "Categoria": st.column_config.SelectboxColumn("Categoria", options=opcoes_categorias),
        "Valor": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
        "Saldo_Acumulado": st.column_config.NumberColumn("Saldo Projetado", format="R$ %.2f", disabled=True)
    },
    key="editor_principal"
)

# --- SALVAMENTO (ITEM 3: CORREÇÃO GOOGLE SHEETS) ---
if st.button("💾 Sincronizar com Google Sheets", use_container_width=True):
    # Pegamos apenas os dados editados (sem a coluna de saldo acumulado)
    df_final = df_editado[['Data', 'Categoria', 'Valor']].copy()
    df_final['Data'] = df_final['Data'].astype(str)
    
    pacote = {
        "lancamentos": df_final.to_dict(orient='records'),
        "categorias": st.session_state.df_cats.to_dict(orient='records'),
        "saldo_inicial": float(st.session_state.saldo_inicial),
        "data_saldo_inicial": str(st.session_state.data_saldo_inicial)
    }
    
    with st.spinner("Enviando..."):
        try:
            res = requests.post(URL_PONTE_SALVAR, json=pacote, timeout=20)
            if res.status_code == 200:
                # IMPORTANTE: Atualizar o session_state ANTES do rerun
                st.session_state.df_lanc = df_final
                st.success("Sincronizado!")
                st.rerun()
            else:
                st.error(f"Erro no Google: {res.status_code}")
        except Exception as e:
            st.error(f"Erro de conexão: {e}")
