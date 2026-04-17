import streamlit as st
import pandas as pd
import requests

# --- CONFIGURAÇÕES ---
URL_PLANILHA = "https://docs.google.com/spreadsheets/d/1rH7Uz_BhlUMDJJXGrRWg7zuEQUCbRQCGAFbE0Pu9NwI/edit?usp=sharing"
URL_PONTE_SALVAR = "https://script.google.com/macros/s/AKfycbwjYRXjx47IlSiqrW3ZxB6GBmKmNROPYdyPS8QxCNMZYnuULuYKkRW4fmrnLNiaLe46/exec"
GID_CONFIG = "1701820250" 

csv_lanc = URL_PLANILHA.replace('/edit?usp=sharing', '/export?format=csv&gid=0')
csv_cfg = URL_PLANILHA.replace('/edit?usp=sharing', f'/export?format=csv&gid={GID_CONFIG}')

st.set_page_config(page_title="Financeiro Pro", layout="wide")

# --- MEMÓRIA DO APP (SESSION STATE) ---
if 'df_lanc' not in st.session_state:
    try:
        df = pd.read_csv(csv_lanc)
        # Força conversão inicial
        df['Data'] = pd.to_datetime(df['Data'], errors='coerce').dt.date
        df['Valor'] = pd.to_numeric(df['Valor'], errors='coerce').fillna(0.0)
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
    st.session_state.saldo_inicial = st.number_input("Saldo Inicial em Conta (R$)", value=float(st.session_state.saldo_inicial))
    
    st.write("---")
    st.write("### Categorias e Sinais")
    # Editando categorias sem perder os lançamentos
    st.session_state.df_cats = st.data_editor(
        st.session_state.df_cats,
        num_rows="dynamic",
        column_config={
            "Sinal": st.column_config.SelectboxColumn("Operação", options=["+", "-"], required=True)
        },
        use_container_width=True,
        key="editor_categorias"
    )

# --- CORPO DO APP ---
st.title("💰 Extrato Financeiro Vivo")

def calcular_extrato_blindado(df_lanc, df_cats, saldo_ini):
    # Se não houver dados, cria estrutura vazia com as colunas certas
    if df_lanc.empty:
        df_vazia = pd.DataFrame(columns=['Data', 'Categoria', 'Valor', 'Saldo_Acumulado'])
        df_vazia['Data'] = pd.to_datetime([]).date
        return df_vazia

    # Limpeza pré-merge
    df_lanc = df_lanc.copy()
    df_lanc['Valor'] = pd.to_numeric(df_lanc['Valor'], errors='coerce').fillna(0.0)
    
    # Merge para pegar o sinal (+ ou -)
    temp_df = df_lanc.merge(df_cats, on='Categoria', how='left')
    temp_df['Sinal'] = temp_df['Sinal'].fillna('+')
    
    # Cálculo do valor real
    temp_df['Mult'] = temp_df['Sinal'].map({'+': 1, '-': -1})
    temp_df['Valor_Real'] = temp_df['Valor'] * temp_df['Mult']
    
    # Ordenar e calcular saldo acumulado
    temp_df = temp_df.sort_values('Data')
    temp_df['Saldo_Acumulado'] = saldo_ini + temp_df['Valor_Real'].cumsum()
    
    # SELEÇÃO E FORÇAR TIPOS (Isso resolve o erro de compatibilidade)
    final_df = temp_df[['Data', 'Categoria', 'Valor', 'Saldo_Acumulado']].copy()
    
    # Forçar tipos finais explicitamente
    final_df['Data'] = pd.to_datetime(final_df['Data'], errors='coerce').dt.date
    final_df['Categoria'] = final_df['Categoria'].astype(str)
    final_df['Valor'] = final_df['Valor'].astype(float)
    final_df['Saldo_Acumulado'] = final_df['Saldo_Acumulado'].astype(float)
    
    return final_df

# Prepara a tabela para o editor
df_para_mostrar = calcular_extrato_blindado(
    st.session_state.df_lanc, 
    st.session_state.df_cats, 
    st.session_state.saldo_inicial
)

# GRADE VIVA
st.info("A coluna 'Saldo Projetado' é calculada automaticamente com base nas categorias da lateral.")
df_resultado = st.data_editor(
    df_para_mostrar,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY", required=True),
        "Categoria": st.column_config.SelectboxColumn(
            "Categoria", 
            options=st.session_state.df_cats['Categoria'].dropna().unique().tolist(),
            required=True
        ),
        "Valor": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f", min_value=0.0),
        "Saldo_Acumulado": st.column_config.NumberColumn("Saldo Projetado", format="R$ %.2f", disabled=True)
    },
    key="editor_principal"
)

# Botão Salvar
if st.button("💾 Sincronizar Tudo"):
    # Limpa antes de salvar (remove a coluna de saldo acumulado que é só visual)
    if df_resultado is not None:
        df_save = df_resultado[['Data', 'Categoria', 'Valor']].copy()
        df_save['Data'] = df_save['Data'].astype(str)
        
        dados_envio = {
            "lancamentos": df_save.to_dict(orient='records'),
            "categorias": st.session_state.df_cats.to_dict(orient='records'),
            "saldo_inicial": float(st.session_state.saldo_inicial)
        }
        
        with st.spinner("Enviando..."):
            res = requests.post(URL_PONTE_SALVAR, json=dados_envio)
            if res.status_code == 200:
                st.session_state.df_lanc = df_resultado[['Data', 'Categoria', 'Valor']]
                st.success("Salvo com sucesso!")
                st.rerun()
