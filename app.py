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

# --- BOTÃO SALVAR E SINCRONIZAR ---
if st.button("💾 Salvar e Sincronizar com Planilha"):
    if df_editado is not None:
        # 1. Fazemos uma cópia para não mexer no que você está vendo na tela
        df_para_salvar = df_editado[['Data', 'Categoria', 'Valor']].copy()
        
        # 2. LIMPEZA DE SEGURANÇA: Preenche campos vazios para não dar erro no JSON
        # Se o valor estiver vazio, vira 0.0. Se a data estiver vazia, vira a data de hoje.
        df_para_salvar['Valor'] = pd.to_numeric(df_para_salvar['Valor']).fillna(0.0)
        df_para_salvar['Categoria'] = df_para_salvar['Categoria'].fillna("Outros")
        
        # Garante que as datas sejam textos válidos
        df_para_salvar['Data'] = pd.to_datetime(df_para_salvar['Data'], errors='coerce')
        df_para_salvar['Data'] = df_para_salvar['Data'].fillna(pd.Timestamp.now())
        df_para_salvar['Data'] = df_para_salvar['Data'].dt.strftime('%Y-%m-%d')
        
        # 3. Limpeza na tabela de categorias também
        df_cats_save = st.session_state.df_cats.copy().dropna(subset=['Categoria'])
        df_cats_save['Sinal'] = df_cats_save['Sinal'].fillna('+')

        dados_totais = {
            "lancamentos": df_para_salvar.to_dict(orient='records'),
            "categorias": df_cats_save.to_dict(orient='records'),
            "saldo_inicial": float(st.session_state.saldo_inicial)
        }
        
        with st.spinner("Sincronizando com a nuvem..."):
            try:
                # O segredo aqui é o timeout e garantir que o dado é serializável
                res = requests.post(URL_PONTE_SALVAR, json=dados_totais, timeout=15)
                
                if res.status_code == 200:
                    # Atualizamos a memória do app com os dados limpos
                    st.session_state.df_lanc = df_para_salvar
                    st.success("Tudo salvo e sincronizado!")
                    st.rerun()
                else:
                    st.error(f"O Google respondeu com erro: {res.status_code}")
            except Exception as e:
                st.error(f"Erro de conexão: Verifique se o link do Apps Script está correto. Detalhe: {e}")
