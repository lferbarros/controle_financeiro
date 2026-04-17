import streamlit as st
import pandas as pd
import requests
from datetime import datetime

# --- CONFIGURAÇÕES ---
URL_PLANILHA = "https://docs.google.com/spreadsheets/d/1rH7Uz_BhlUMDJJXGrRWg7zuEQUCbRQCGAFbE0Pu9NwI/edit?usp=sharing"
URL_PONTE_SALVAR = "https://script.google.com/macros/s/AKfycbxKQwvKnNkKCasQNhSOSH44n2Wtxhm6metAPnWGySlDnybBRNFxZ7zHBP4k7wLKDvaq/exec"
GID_CONFIG = "1701820250"

csv_lanc = URL_PLANILHA.replace('/edit?usp=sharing', '/export?format=csv&gid=0')
csv_cfg = URL_PLANILHA.replace('/edit?usp=sharing', f'/export?format=csv&gid={GID_CONFIG}')

st.set_page_config(page_title="Controle Financeiro", layout="wide")

# --- CARGA DE DADOS ---
def carregar_dados_da_nuvem():
    try:
        df_l = pd.read_csv(csv_lanc)
        df_l['Data'] = pd.to_datetime(df_l['Data'], errors='coerce').dt.date
        df_l['Valor'] = pd.to_numeric(df_l['Valor'], errors='coerce').fillna(0.0).astype(float)
        # Se a coluna Meio_Pgto não existir na planilha ainda, criamos ela vazia
        if 'Meio_Pgto' not in df_l.columns: df_l['Meio_Pgto'] = ""
        
        cfg = pd.read_csv(csv_cfg)
        s_ini = float(cfg['Saldo Inicial'].iloc[0]) if 'Saldo Inicial' in cfg and not cfg.empty else 0.0
        d_ini = pd.to_datetime(cfg['Data Inicial'].iloc[0] if 'Data Inicial' in cfg else datetime.now()).date()
        
        # Carregar Categorias e Meios de Pagamento
        cats = cfg[['Categoria', 'Sinal']].dropna(subset=['Categoria']).copy()
        
        # Lógica para carregar Meios de Pagamento da coluna F (que o pandas lê como Meio_Pagamento se tiver cabeçalho)
        if 'Meio_Pagamento' in cfg.columns:
            meios = cfg[['Meio_Pagamento']].dropna().copy()
        else:
            meios = pd.DataFrame({'Meio_Pagamento': ["Pix", "Cartão de Crédito", "Débito em Conta"]})
            
        return df_l, s_ini, d_ini, cats, meios
    except:
        return None

# --- INICIALIZAÇÃO ---
if 'dados_carregados' not in st.session_state:
    res = carregar_dados_da_nuvem()
    if res:
        st.session_state.df_lanc, st.session_state.saldo_ini, \
        st.session_state.data_ini, st.session_state.df_cats, st.session_state.df_meios = res
    else:
        st.session_state.df_lanc = pd.DataFrame(columns=['Data', 'Categoria', 'Valor', 'Meio_Pgto'])
        st.session_state.df_cats = pd.DataFrame({'Categoria': ['Salário', 'Mercado'], 'Sinal': ['+', '-']})
        st.session_state.df_meios = pd.DataFrame({'Meio_Pagamento': ["Pix", "Cartão de Crédito", "Débito em Conta"]})
        st.session_state.saldo_ini, st.session_state.data_ini = 0.0, datetime.now().date()
    st.session_state.dados_carregados = True

# --- SIDEBAR: CONFIGURAÇÕES ---
with st.sidebar:
    st.header("⚙️ Configurações")
    
    st.subheader("Categorias")
    st.session_state.df_cats = st.data_editor(st.session_state.df_cats[['Categoria', 'Sinal']], num_rows="dynamic", key="ed_cats")
    
    st.subheader("Meios de Pagamento")
    st.session_state.df_meios = st.data_editor(st.session_state.df_meios[['Meio_Pagamento']], num_rows="dynamic", key="ed_meios")
    
    if st.button("🔄 Recarregar Dados"):
        st.session_state.pop('dados_carregados')
        st.rerun()

# --- CORPO PRINCIPAL ---
st.title("💰 Extrato Financeiro")

c1, c2, c3, c4 = st.columns([2, 1, 1.5, 1.5])
with c3: st.session_state.data_ini = st.date_input("Início", st.session_state.data_ini)
with c4: st.session_state.saldo_ini = st.number_input("Saldo Inicial", value=float(st.session_state.saldo_ini), format="%.2f")

# Lógica de Cálculo
def gerar_extrato(lanc, cats, saldo_ini):
    if lanc.empty: return pd.DataFrame(columns=['Data', 'Categoria', 'Meio_Pgto', 'Valor', 'Saldo_Acumulado'])
    df = lanc[['Data', 'Categoria', 'Valor', 'Meio_Pgto']].copy()
    df = df.merge(cats[['Categoria', 'Sinal']], on='Categoria', how='left')
    df['Sinal'] = df['Sinal'].fillna('+')
    df['Valor_Real'] = df['Valor'] * df['Sinal'].map({'+': 1, '-': -1})
    df = df.sort_values('Data').reset_index(drop=True)
    df['Saldo_Acumulado'] = (saldo_ini + df['Valor_Real'].cumsum()).astype(float)
    return df[['Data', 'Categoria', 'Meio_Pgto', 'Valor', 'Saldo_Acumulado']]

# Opções para os Selectboxes
lista_cats = st.session_state.df_cats['Categoria'].dropna().unique().tolist()
lista_meios = st.session_state.df_meios['Meio_Pagamento'].dropna().unique().tolist()

df_viz = gerar_extrato(st.session_state.df_lanc, st.session_state.df_cats, st.session_state.saldo_ini)

df_editado = st.data_editor(
    df_viz,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY", required=True),
        "Categoria": st.column_config.SelectboxColumn("Categoria", options=lista_cats, required=True),
        "Meio_Pgto": st.column_config.SelectboxColumn("Meio de Pagamento", options=lista_meios),
        "Valor": st.column_config.NumberColumn("Valor", format="R$ %.2f", min_value=0.0),
        "Saldo_Acumulado": st.column_config.NumberColumn("Saldo Projetado", format="R$ %.2f", disabled=True)
    },
    key="editor_main"
)

# --- SALVAR ---
if st.button("💾 Salvar e Sincronizar Tudo", use_container_width=True):
    df_envio = df_editado[['Data', 'Categoria', 'Valor', 'Meio_Pgto']].copy()
    df_envio['Data'] = df_envio['Data'].astype(str)
    
    payload = {
        "lancamentos": df_envio.to_dict(orient='records'),
        "categorias": st.session_state.df_cats.to_dict(orient='records'),
        "meios_pgto": st.session_state.df_meios.to_dict(orient='records'),
        "saldo_inicial": float(st.session_state.saldo_ini),
        "data_saldo_inicial": str(st.session_state.data_ini)
    }
    
    with st.spinner("Sincronizando..."):
        try:
            res = requests.post(URL_PONTE_SALVAR, json=payload, timeout=20)
            if res.status_code == 200:
                st.session_state.df_lanc = df_envio
                st.success("Tudo salvo!")
                st.rerun()
            else: st.error(f"Erro {res.status_code}")
        except Exception as e: st.error(f"Erro: {e}")
