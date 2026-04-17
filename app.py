import streamlit as st
import pandas as pd
import requests
from datetime import datetime

# --- CONFIGURAÇÕES (PONTO DE MELHORIA: PROTEÇÃO DE DADOS) ---
# Dica: No futuro, substitua por st.secrets para maior segurança
URL_PLANILHA = "https://docs.google.com/spreadsheets/d/1rH7Uz_BhlUMDJJXGrRWg7zuEQUCbRQCGAFbE0Pu9NwI/edit?usp=sharing"
URL_PONTE_SALVAR = "https://script.google.com/macros/s/AKfycbxB6L1arpuS__Ae68jWGuqignMKdtpYjo8pevP5qbmXRzNkUsYgd7ikg4o6WHcRn28/exec"
GID_CONFIG = "1701820250" 

csv_lanc = URL_PLANILHA.replace('/edit?usp=sharing', '/export?format=csv&gid=0')
csv_cfg = URL_PLANILHA.replace('/edit?usp=sharing', f'/export?format=csv&gid={GID_CONFIG}')

st.set_page_config(page_title="Financeiro Pro", layout="wide")

# --- 1. MELHORIA NA CARGA DE DADOS (CACHE E CONSISTÊNCIA) ---
@st.cache_data(ttl=60)  # Cache de 1 minuto para evitar downloads excessivos
def carregar_dados_remotos(url_l, url_c):
    try:
        df_l = pd.read_csv(url_l)
        df_l['Data'] = pd.to_datetime(df_l['Data'], errors='coerce').dt.date
        
        cfg = pd.read_csv(url_c)
        s_ini = float(cfg['Saldo Inicial'].iloc[0]) if not cfg.empty else 0.0
        d_str = cfg['Data Inicial'].iloc[0] if not cfg.empty else str(datetime.now().date())
        d_ini = pd.to_datetime(d_str).date()
        cats = cfg[['Categoria', 'Sinal']].dropna()
        # Sanitização de strings para evitar erros de busca
        cats['Categoria'] = cats['Categoria'].str.strip()
        
        return df_l, s_ini, d_ini, cats
    except Exception as e:
        st.error(f"Erro na carga inicial: {e}")
        return None

# Inicialização da Memória (Session State)
if 'df_lanc' not in st.session_state:
    dados = carregar_dados_remotos(csv_lanc, csv_cfg)
    if dados:
        st.session_state.df_lanc, st.session_state.saldo_inicial, \
        st.session_state.data_saldo_inicial, st.session_state.df_cats = dados
    else:
        st.session_state.df_lanc = pd.DataFrame(columns=['Data', 'Categoria', 'Valor'])
        st.session_state.saldo_inicial = 0.0
        st.session_state.data_saldo_inicial = datetime.now().date()
        st.session_state.df_cats = pd.DataFrame({'Categoria': ['Salário'], 'Sinal': ['+']})

# --- 2. MELHORIA NA LÓGICA DE CÁLCULO (ORDENAÇÃO FORÇADA) ---
def calcular_extrato_otimizado(df_lanc, df_cats, saldo_ini):
    if df_lanc.empty:
        return pd.DataFrame(columns=['Data', 'Categoria', 'Valor', 'Saldo_Acumulado'])

    temp_df = df_lanc.copy()
    # Garantir integridade dos tipos antes do cálculo
    temp_df['Valor'] = pd.to_numeric(temp_df['Valor'], errors='coerce').fillna(0.0)
    temp_df['Data'] = pd.to_datetime(temp_df['Data']).dt.date
    
    # Ordenação Crítica: Garante que o saldo acumulado siga a linha do tempo
    temp_df = temp_df.sort_values(by=['Data'], ascending=True).reset_index(drop=True)
    
    # Merge sanitizado
    df_cats_clean = df_cats.copy()
    df_cats_clean['Categoria'] = df_cats_clean['Categoria'].str.strip()
    
    temp_df = temp_df.merge(df_cats_clean, on='Categoria', how='left')
    temp_df['Sinal'] = temp_df['Sinal'].fillna('+')
    temp_df['Mult'] = temp_df['Sinal'].map({'+': 1, '-': -1})
    temp_df['Valor_Real'] = temp_df['Valor'] * temp_df['Mult']
    
    # Cálculo Vetorizado (mais rápido que loops)
    temp_df['Saldo_Acumulado'] = saldo_ini + temp_df['Valor_Real'].cumsum()
    
    return temp_df[['Data', 'Categoria', 'Valor', 'Saldo_Acumulado']]

# --- INTERFACE ---
st.title("💰 Extrato Financeiro Inteligente")

with st.sidebar:
    st.header("⚙️ Configurações")
    st.session_state.df_cats = st.data_editor(
        st.session_state.df_cats,
        num_rows="dynamic",
        column_config={"Sinal": st.column_config.SelectboxColumn("Operação", options=["+", "-"], required=True)},
        use_container_width=True,
        key="editor_cats"
    )
    if st.button("Limpar Cache de Leitura"):
        st.cache_data.clear()
        st.rerun()

col1, col2, col3, col4 = st.columns([2, 2, 1.5, 1.5])
with col3:
    st.session_state.data_saldo_inicial = st.date_input("Data do Saldo Inicial", st.session_state.data_saldo_inicial)
with col4:
    st.session_state.saldo_inicial = st.number_input("Saldo Inicial (R$)", value=float(st.session_state.saldo_inicial), format="%.2f")

# Preparação da Tabela
df_para_mostrar = calcular_extrato_otimizado(
    st.session_state.df_lanc, 
    st.session_state.df_cats, 
    st.session_state.saldo_inicial
)

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

# --- 3. MELHORIA NO SALVAMENTO (RESILIÊNCIA E VALIDAÇÃO) ---
if st.button("💾 Sincronizar Tudo", use_container_width=True):
    if df_resultado is not None:
        # Ponto de Melhoria: Ordenar antes de enviar para a planilha do Google
        df_save = df_resultado[['Data', 'Categoria', 'Valor']].copy()
        df_save = df_save.sort_values(by='Data')
        df_save['Data'] = df_save['Data'].astype(str)
        
        # Validação: Impedir categorias vazias
        if df_save['Categoria'].isnull().any():
            st.error("Erro: Existem lançamentos sem categoria definida!")
        else:
            dados_envio = {
                "lancamentos": df_save.to_dict(orient='records'),
                "categorias": st.session_state.df_cats.to_dict(orient='records'),
                "saldo_inicial": float(st.session_state.saldo_inicial),
                "data_saldo_inicial": str(st.session_state.data_saldo_inicial)
            }
            
            with st.status("Sincronizando dados...", expanded=True) as status:
                try:
                    res = requests.post(URL_PONTE_SALVAR, json=dados_envio, timeout=20)
                    if res.status_code == 200:
                        st.session_state.df_lanc = df_save
                        st.cache_data.clear() # Limpa cache para ler o dado novo na próxima
                        status.update(label="✅ Sincronização concluída!", state="complete", expanded=False)
                        st.rerun()
                    else:
                        status.update(label="❌ Erro no Servidor Google", state="error")
                        st.error(f"Status: {res.status_code}")
                except requests.exceptions.Timeout:
                    status.update(label="❌ O servidor demorou muito a responder", state="error")
                except Exception as e:
                    status.update(label=f"❌ Erro crítico: {e}", state="error")
