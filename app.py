import streamlit as st
import pandas as pd
import requests
from datetime import datetime

# --- CONFIGURAÇÕES ---
URL_PLANILHA = "https://docs.google.com/spreadsheets/d/1rH7Uz_BhlUMDJJXGrRWg7zuEQUCbRQCGAFbE0Pu9NwI/edit?usp=sharing"
URL_PONTE_SALVAR = "https://script.google.com/macros/s/AKfycbxB6L1arpuS__Ae68jWGuqignMKdtpYjo8pevP5qbmXRzNkUsYgd7ikg4o6WHcRn28/exec"
GID_CONFIG = "1701820250" 

csv_lanc = URL_PLANILHA.replace('/edit?usp=sharing', '/export?format=csv&gid=0')
csv_cfg = URL_PLANILHA.replace('/edit?usp=sharing', f'/export?format=csv&gid={GID_CONFIG}')

st.set_page_config(page_title="Financeiro Pro", layout="wide")

# --- MEMÓRIA DO APP ---
if 'df_lanc' not in st.session_state:
    try:
        df = pd.read_csv(csv_lanc)
        df['Data'] = pd.to_datetime(df['Data'], errors='coerce').dt.date
        st.session_state.df_lanc = df
        
        cfg = pd.read_csv(csv_cfg)
        st.session_state.saldo_inicial = float(cfg['Saldo Inicial'].iloc[0]) if not cfg.empty else 0.0
        # Carrega a data inicial da planilha
        data_str = cfg['Data Inicial'].iloc[0] if not cfg.empty else str(datetime.now().date())
        st.session_state.data_saldo_inicial = pd.to_datetime(data_str).date()
        
        st.session_state.df_cats = cfg[['Categoria', 'Sinal']].dropna()
    except:
        st.session_state.df_lanc = pd.DataFrame(columns=['Data', 'Categoria', 'Valor'])
        st.session_state.saldo_inicial = 0.0
        st.session_state.data_saldo_inicial = datetime.now().date()
        st.session_state.df_cats = pd.DataFrame({'Categoria': ['Salário'], 'Sinal': ['+']})

# --- BARRA LATERAL (Apenas Categorias agora) ---
with st.sidebar:
    st.header("⚙️ Configurações")
    st.write("### Categorias e Sinais")
    st.session_state.df_cats = st.data_editor(
        st.session_state.df_cats,
        num_rows="dynamic",
        column_config={"Sinal": st.column_config.SelectboxColumn("Operação", options=["+", "-"], required=True)},
        use_container_width=True,
        key="editor_cats"
    )

# --- CORPO DO APP ---
st.title("💰 Extrato Financeiro")

# LAYOUT DE CABEÇALHO (Saldo e Data em cima da planilha)
col1, col2, col3, col4 = st.columns([2, 2, 1.5, 1.5])

with col3:
    st.session_state.data_saldo_inicial = st.date_input("Data do Saldo Inicial", st.session_state.data_saldo_inicial)

with col4:
    st.session_state.saldo_inicial = st.number_input("Saldo Inicial (R$)", value=float(st.session_state.saldo_inicial), step=100.0, format="%.2f")

def calcular_extrato_blindado(df_lanc, df_cats, saldo_ini, data_ini):
    if df_lanc.empty:
        return pd.DataFrame(columns=['Data', 'Categoria', 'Valor', 'Saldo_Acumulado'])

    temp_df = df_lanc.copy()
    temp_df['Valor'] = pd.to_numeric(temp_df['Valor'], errors='coerce').fillna(0.0)
    
    # Merge com categorias
    temp_df = temp_df.merge(df_cats, on='Categoria', how='left')
    temp_df['Sinal'] = temp_df['Sinal'].fillna('+')
    temp_df['Mult'] = temp_df['Sinal'].map({'+': 1, '-': -1})
    temp_df['Valor_Real'] = temp_df['Valor'] * temp_df['Mult']
    
    # Ordenação cronológica
    temp_df = temp_df.sort_values('Data')
    
    # O saldo acumulado começa a partir do saldo_inicial
    temp_df['Saldo_Acumulado'] = saldo_ini + temp_df['Valor_Real'].cumsum()
    
    final_df = temp_df[['Data', 'Categoria', 'Valor', 'Saldo_Acumulado']].copy()
    final_df['Data'] = pd.to_datetime(final_df['Data']).dt.date
    return final_df

# Prepara os dados
df_para_mostrar = calcular_extrato_blindado(
    st.session_state.df_lanc, 
    st.session_state.df_cats, 
    st.session_state.saldo_inicial,
    st.session_state.data_saldo_inicial
)

# GRADE VIVA
df_resultado = st.data_editor(
    df_para_mostrar,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY", required=True),
        "Categoria": st.column_config.SelectboxColumn("Categoria", options=st.session_state.df_cats['Categoria'].unique().tolist(), required=True),
        "Valor": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f", min_value=0.0),
        "Saldo_Acumulado": st.column_config.NumberColumn("Saldo Projetado", format="R$ %.2f", disabled=True)
    },
    key="editor_main"
)

# BOTÃO SALVAR
if st.button("💾 Sincronizar Tudo"):
    if df_resultado is not None:
        df_save = df_resultado[['Data', 'Categoria', 'Valor']].copy()
        df_save['Data'] = df_save['Data'].astype(str)
        
        dados_envio = {
            "lancamentos": df_save.to_dict(orient='records'),
            "categorias": st.session_state.df_cats.to_dict(orient='records'),
            "saldo_inicial": float(st.session_state.saldo_inicial),
            "data_saldo_inicial": str(st.session_state.data_saldo_inicial)
        }
        
        with st.spinner("Salvando na Planilha..."):
            res = requests.post(URL_PONTE_SALVAR, json=dados_envio)
            if res.status_code == 200:
                st.session_state.df_lanc = df_resultado[['Data', 'Categoria', 'Valor']]
                st.success("Dados atualizados!")
                st.rerun()
