import streamlit as st
import pandas as pd
import requests
from datetime import datetime

# --- CONFIGURAÇÕES ---
# Substitua pelos seus links reais
URL_PLANILHA = "https://docs.google.com/spreadsheets/d/1rH7Uz_BhlUMDJJXGrRWg7zuEQUCbRQCGAFbE0Pu9NwI/edit?usp=sharing"
URL_PONTE_SALVAR = "https://script.google.com/macros/s/AKfycbxdQzVYaXshgvAdSQAtK-IQmM6aLEz-w58Z8LbezmyR5WCVwCWRCVlLnXUKlI4nXMoZ/exec"
GID_CONFIG = "1701820250" 

csv_lanc = URL_PLANILHA.replace('/edit?usp=sharing', '/export?format=csv&gid=0')
csv_cfg = URL_PLANILHA.replace('/edit?usp=sharing', f'/export?format=csv&gid={GID_CONFIG}')

st.set_page_config(page_title="Controle Financeiro", layout="wide")

# --- FUNÇÃO DE CARGA DE DADOS ---
def carregar_dados_da_nuvem():
    try:
        # Lendo lançamentos
        df_l = pd.read_csv(csv_lanc)
        df_l['Data'] = pd.to_datetime(df_l['Data'], errors='coerce').dt.date
        df_l['Valor'] = pd.to_numeric(df_l['Valor'], errors='coerce').fillna(0.0)
        
        # Lendo configurações
        cfg = pd.read_csv(csv_cfg)
        s_ini = float(cfg['Saldo Inicial'].iloc[0]) if 'Saldo Inicial' in cfg and not cfg.empty else 0.0
        d_ini_str = cfg['Data Inicial'].iloc[0] if 'Data Inicial' in cfg and not cfg.empty else str(datetime.now().date())
        d_ini = pd.to_datetime(d_ini_str).date()
        
        # Categorias (Garante que pegamos apenas as colunas certas da planilha)
        cats = cfg[['Categoria', 'Sinal']].dropna(subset=['Categoria']).copy()
        
        return df_l, s_ini, d_ini, cats
    except Exception as e:
        st.warning(f"Usando dados temporários (Erro ao ler planilha: {e})")
        return None

# --- INICIALIZAÇÃO DO ESTADO ---
if 'dados_carregados' not in st.session_state:
    res = carregar_dados_da_nuvem()
    if res:
        st.session_state.df_lanc, st.session_state.saldo_ini, \
        st.session_state.data_ini, st.session_state.df_cats = res
    else:
        st.session_state.df_lanc = pd.DataFrame(columns=['Data', 'Categoria', 'Valor'])
        st.session_state.saldo_ini = 0.0
        st.session_state.data_ini = datetime.now().date()
        st.session_state.df_cats = pd.DataFrame({'Categoria': ['Receita', 'Despesa'], 'Sinal': ['+', '-']})
    st.session_state.dados_carregados = True

# --- SIDEBAR: GESTÃO DE CATEGORIAS ---
with st.sidebar:
    st.header("⚙️ Configurações")
    st.subheader("Categorias")
    
    # IMPORTANTE: Filtrar colunas para evitar o bug de colunas extras
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

# Inputs de Saldo e Data (Alinhados acima da tabela)
c1, c2, c3, c4 = st.columns([2, 1, 1.5, 1.5])
with c3:
    st.session_state.data_ini = st.date_input("Data do Saldo Inicial", st.session_state.data_ini)
with c4:
    st.session_state.saldo_ini = st.number_input("Saldo Inicial (R$)", value=float(st.session_state.saldo_ini), format="%.2f")

# --- LÓGICA DE CÁLCULO DO EXTRATO ---
def gerar_extrato(lancamentos, categorias, saldo_inicial):
    if lancamentos.empty:
        return pd.DataFrame(columns=['Data', 'Categoria', 'Valor', 'Saldo_Acumulado'])
    
    # Criar cópia limpa
    df = lancamentos[['Data', 'Categoria', 'Valor']].copy()
    df['Valor'] = pd.to_numeric(df['Valor'], errors='coerce').fillna(0.0)
    
    # Cruzar com categorias para saber o sinal
    df = df.merge(categorias[['Categoria', 'Sinal']], on='Categoria', how='left')
    df['Sinal'] = df['Sinal'].fillna('+')
    
    # Calcular valor real (positivo ou negativo)
    df['Valor_Real'] = df['Valor'] * df['Sinal'].map({'+': 1, '-': -1})
    
    # Ordenar por data e calcular saldo acumulado
    df = df.sort_values('Data').reset_index(drop=True)
    df['Saldo_Acumulado'] = saldo_inicial + df['Valor_Real'].cumsum()
    
    return df[['Data', 'Categoria', 'Valor', 'Saldo_Acumulado']]

# Pegar categorias atualizadas para o dropdown da tabela
lista_categorias = st.session_state.df_cats['Categoria'].dropna().unique().tolist()

# Gerar dados para exibição
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
    # 1. Preparar Lançamentos (Remover coluna de saldo calculada)
    df_para_google = df_editado[['Data', 'Categoria', 'Valor']].copy()
    df_para_google['Data'] = df_para_google['Data'].astype(str)
    
    # 2. Preparar Categorias
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
