import streamlit as st
import pandas as pd
import requests

# --- CONFIGURAÇÕES ---
URL_PLANILHA = "https://docs.google.com/spreadsheets/d/1rH7Uz_BhlUMDJJXGrRWg7zuEQUCbRQCGAFbE0Pu9NwI/edit?usp=sharing"
URL_PONTE_SALVAR = "https://script.google.com/macros/s/AKfycbwjYRXjx47IlSiqrW3ZxB6GBmKmNROPYdyPS8QxCNMZYnuULuYKkRW4fmrnLNiaLe46/exec"
GID_CONFIG = "1701820250" # Ex: 123456

csv_lanc = URL_PLANILHA.replace('/edit?usp=sharing', '/export?format=csv&gid=0')
csv_cfg = URL_PLANILHA.replace('/edit?usp=sharing', f'/export?format=csv&gid={GID_CONFIG}')

st.set_page_config(page_title="Financeiro Pro", layout="wide")

# --- MEMÓRIA DO APP (SESSION STATE) ---
if 'df_lanc' not in st.session_state:
    try:
        df = pd.read_csv(csv_lanc)
        df['Data'] = pd.to_datetime(df['Data'], errors='coerce').dt.date
        st.session_state.df_lanc = df
        
        cfg = pd.read_csv(csv_cfg)
        st.session_state.saldo_inicial = float(cfg['Saldo Inicial'].iloc[0]) if not cfg.empty else 0.0
        st.session_state.df_cats = cfg[['Categoria', 'Sinal']].dropna()
    except:
        st.session_state.df_lanc = pd.DataFrame(columns=['Data', 'Categoria', 'Valor'])
        st.session_state.saldo_inicial = 0.0
        st.session_state.df_cats = pd.DataFrame({'Categoria': ['Salário'], 'Sinal': ['+']})

# --- BARRA LATERAL ---
with st.sidebar:
    st.header("⚙️ Configurações")
    st.session_state.saldo_inicial = st.number_input("Saldo Inicial em Conta (R$)", value=st.session_state.saldo_inicial)
    
    st.write("---")
    st.write("### Categorias e Sinais")
    # ITEM 3: Sinal inteligente com caixa de seleção (+ ou -)
    st.session_state.df_cats = st.data_editor(
        st.session_state.df_cats,
        num_rows="dynamic",
        column_config={
            "Sinal": st.column_config.SelectboxColumn("Operação", options=["+", "-"], required=True)
        },
        use_container_width=True
    )

# --- CORPO DO APP ---
st.title("💰 Extrato Financeiro Vivo")

# ITEM 2: Lógica para calcular a coluna de Saldo
def calcular_extrato(df_lanc, df_cats, saldo_ini):
    if df_lanc.empty:
        return df_lanc
    
    # Unir com as categorias para saber se é + ou -
    temp_df = df_lanc.merge(df_cats, on='Categoria', how='left')
    temp_df['Multiplicador'] = temp_df['Sinal'].map({'+': 1, '-': -1}).fillna(1)
    temp_df['Valor_Real'] = temp_df['Valor'] * temp_df['Multiplicador']
    
    # Ordenar por data para o saldo fazer sentido
    temp_df = temp_df.sort_values('Data')
    
    # Cálculo do saldo acumulado
    temp_df['Saldo_Acumulado'] = saldo_ini + temp_df['Valor_Real'].cumsum()
    return temp_df[['Data', 'Categoria', 'Valor', 'Saldo_Acumulado']]

# ITEM 1 e 2: Exibição da Grade Viva com a coluna de Saldo
st.write("Edite seus lançamentos abaixo. A coluna 'Saldo_Acumulado' é atualizada automaticamente.")

# Calculamos o extrato antes de mostrar
df_visualizacao = calcular_extrato(st.session_state.df_lanc, st.session_state.df_cats, st.session_state.saldo_inicial)

df_editado = st.data_editor(
    df_visualizacao,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
        "Categoria": st.column_config.SelectboxColumn("Categoria", options=st.session_state.df_cats['Categoria'].tolist()),
        "Valor": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f"),
        "Saldo_Acumulado": st.column_config.NumberColumn("Saldo Projetado", format="R$ %.2f", disabled=True)
    }
)

# Atualiza a memória se houver mudanças na tabela de lançamentos
if st.button("💾 Salvar e Sincronizar com Planilha"):
    # Removemos a coluna de saldo acumulado antes de salvar, pois ela é calculada
    df_para_salvar = df_editado[['Data', 'Categoria', 'Valor']]
    
    dados_totais = {
        "lancamentos": df_para_salvar.assign(Data=df_para_salvar['Data'].astype(str)).to_dict(orient='records'),
        "categorias": st.session_state.df_cats.to_dict(orient='records'),
        "saldo_inicial": st.session_state.saldo_inicial
    }
    
    with st.spinner("Sincronizando..."):
        res = requests.post(URL_PONTE_SALVAR, json=dados_totais)
        if res.status_code == 200:
            st.session_state.df_lanc = df_para_salvar # Atualiza memória local
            st.success("Dados protegidos e salvos na nuvem!")
            st.rerun()
