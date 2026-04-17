import streamlit as st
import pandas as pd
import requests
from datetime import datetime

# --- CONFIGURAÇÕES ---
URL_PLANILHA = "https://docs.google.com/spreadsheets/d/1rH7Uz_BhlUMDJJXGrRWg7zuEQUCbRQCGAFbE0Pu9NwI/edit?usp=sharing"
URL_PONTE_SALVAR = "https://script.google.com/macros/s/AKfycbxdQzVYaXshgvAdSQAtK-IQmM6aLEz-w58Z8LbezmyR5WCVwCWRCVlLnXUKlI4nXMoZ/exec"
GID_CONFIG = "1701820250"

csv_lanc = URL_PLANILHA.replace('/edit?usp=sharing', '/export?format=csv&gid=0')
csv_cfg = URL_PLANILHA.replace('/edit?usp=sharing', f'/export?format=csv&gid={GID_CONFIG}')

st.set_page_config(page_title="Controle Financeiro", layout="wide")

# --- FUNÇÃO DE CARGA DE DADOS ---
def carregar_dados_da_nuvem():
    try:
        df_l = pd.read_csv(csv_lanc)
        # Força o tipo Date imediatamente
        df_l['Data'] = pd.to_datetime(df_l['Data'], errors='coerce').dt.date
        df_l['Valor'] = pd.to_numeric(df_l['Valor'], errors='coerce').fillna(0.0).astype(float)
        
        cfg = pd.read_csv(csv_cfg)
        s_ini = float(cfg['Saldo Inicial'].iloc[0]) if 'Saldo Inicial' in cfg and not cfg.empty else 0.0
        d_ini_str = cfg['Data Inicial'].iloc[0] if 'Data Inicial' in cfg and not cfg.empty else str(datetime.now().date())
        d_ini = pd.to_datetime(d_ini_str).date()
        
        cats = cfg[['Categoria', 'Sinal']].dropna(subset=['Categoria']).copy()
        cats['Categoria'] = cats['Categoria'].astype(str)
        
        return df_l, s_ini, d_ini, cats
    except Exception as e:
        st.warning(f"Usando dados temporários. (Aviso: {e})")
        return None

# --- INICIALIZAÇÃO DO ESTADO ---
if 'dados_carregados' not in st.session_state:
    res = carregar_dados_da_nuvem()
    if res:
        st.session_state.df_lanc, st.session_state.saldo_ini, \
        st.session_state.data_ini, st.session_state.df_cats = res
    else:
        # CORREÇÃO CRÍTICA 1: Criar tabela vazia com tipos explícitos
        df_vazio = pd.DataFrame({
            'Data': pd.Series(dtype='datetime64[ns]'),
            'Categoria': pd.Series(dtype='str'),
            'Valor': pd.Series(dtype='float64')
        })
        df_vazio['Data'] = pd.to_datetime([]).date
        st.session_state.df_lanc = df_vazio
        
        st.session_state.saldo_ini = 0.0
        st.session_state.data_ini = datetime.now().date()
        st.session_state.df_cats = pd.DataFrame({'Categoria': ['Receita', 'Despesa'], 'Sinal': ['+', '-']})
    st.session_state.dados_carregados = True

# --- SIDEBAR: GESTÃO DE CATEGORIAS ---
with st.sidebar:
    st.header("⚙️ Configurações")
    st.subheader("Categorias")
    
    df_cats_input = st.session_state.df_cats[['Categoria', 'Sinal']].copy()
    
    st.session_state.df_cats = st.data_editor(
        df_cats_input,
        num_rows="dynamic",
        column_config={
            "Sinal": st.column_config.SelectboxColumn("Operação", options=["+", "-"], required=True)
        },
        use_container_width=True,
        key="editor_categorias_sidebar"
    )
    
    if st.button("🔄 Recarregar da Planilha"):
        st.session_state.pop('dados_carregados')
        st.rerun()

# --- CORPO PRINCIPAL ---
st.title("💰 Gestão Financeira")

c1, c2, c3, c4 = st.columns([2, 1, 1.5, 1.5])
with c3:
    st.session_state.data_ini = st.date_input("Data do Saldo Inicial", st.session_state.data_ini)
with c4:
    st.session_state.saldo_ini = st.number_input("Saldo Inicial (R$)", value=float(st.session_state.saldo_ini), format="%.2f")

# --- LÓGICA DE CÁLCULO DO EXTRATO ---
def gerar_extrato(lancamentos, categorias, saldo_inicial):
    # CORREÇÃO CRÍTICA 2: Se vazio, retorna uma estrutura perfeitamente tipada
    if lancamentos.empty:
        df_vazio_extrato = pd.DataFrame({
            'Data': pd.Series(dtype='datetime64[ns]'),
            'Categoria': pd.Series(dtype='str'),
            'Valor': pd.Series(dtype='float64'),
            'Saldo_Acumulado': pd.Series(dtype='float64')
        })
        df_vazio_extrato['Data'] = pd.to_datetime([]).date
        return df_vazio_extrato
    
    df = lancamentos[['Data', 'Categoria', 'Valor']].copy()
    
    # Forçar tipos antes do merge
    df['Data'] = pd.to_datetime(df['Data'], errors='coerce').dt.date
    df['Categoria'] = df['Categoria'].astype(str)
    df['Valor'] = pd.to_numeric(df['Valor'], errors='coerce').fillna(0.0).astype(float)
    
    df = df.merge(categorias[['Categoria', 'Sinal']], on='Categoria', how='left')
    df['Sinal'] = df['Sinal'].fillna('+')
    
    df['Valor_Real'] = df['Valor'] * df['Sinal'].map({'+': 1, '-': -1})
    
    df = df.sort_values('Data').reset_index(drop=True)
    df['Saldo_Acumulado'] = (saldo_inicial + df['Valor_Real'].cumsum()).astype(float)
    
    # Retornar garantindo a tipagem final
    df_final = df[['Data', 'Categoria', 'Valor', 'Saldo_Acumulado']]
    return df_final

lista_categorias = st.session_state.df_cats['Categoria'].dropna().astype(str).unique().tolist()

df_visualizacao = gerar_extrato(st.session_state.df_lanc, st.session_state.df_cats, st.session_state.saldo_ini)

st.write("### Lançamentos")
df_editado = st.data_editor(
    df_visualizacao,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY", required=True),
        "Categoria": st.column_config.SelectboxColumn("Categoria", options=lista_categorias, required=True),
        "Valor": st.column_config.NumberColumn("Valor", format="R$ %.2f", min_value=0.0),
        "Saldo_Acumulado": st.column_config.NumberColumn("Saldo Projetado", format="R$ %.2f", disabled=True)
    },
    key="editor_financeiro_main"
)

# --- BOTÃO SALVAR ---
if st.button("💾 Salvar e Sincronizar Tudo", use_container_width=True):
    df_para_google = df_editado[['Data', 'Categoria', 'Valor']].copy()
    df_para_google['Data'] = df_para_google['Data'].astype(str)
    
    cats_para_google = st.session_state.df_cats[['Categoria', 'Sinal']].dropna(subset=['Categoria']).copy()
    
    payload = {
        "lancamentos": df_para_google.to_dict(orient='records'),
        "categorias": cats_para_google.to_dict(orient='records'),
        "saldo_inicial": float(st.session_state.saldo_ini),
        "data_saldo_inicial": str(st.session_state.data_ini)
    }
    
    with st.spinner("Enviando para o Google Sheets..."):
        try:
            response = requests.post(URL_PONTE_SALVAR, json=payload, timeout=20)
            if response.status_code == 200:
                st.session_state.df_lanc = df_para_google
                st.success("Sincronização realizada com sucesso!")
                st.rerun()
            else:
                st.error(f"Erro no servidor Google (Status {response.status_code})")
        except Exception as e:
            st.error(f"Erro de conexão: {e}")
