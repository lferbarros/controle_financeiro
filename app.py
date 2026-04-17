import streamlit as st
import pandas as pd
import requests

# --- CONFIGURAÇÕES ---
URL_PLANILHA = "https://docs.google.com/spreadsheets/d/1rH7Uz_BhlUMDJJXGrRWg7zuEQUCbRQCGAFbE0Pu9NwI/edit?usp=sharing"
URL_PONTE_SALVAR = "https://script.google.com/macros/s/AKfycbxmLE4LgLuN1tOxC1sMn55aXTQlJRdjg0MOtGHoZZ3Rx0eXRQSbmSGa3LAHSZdtHg-T/exec"

# Links para baixar as duas abas
csv_lancamentos = URL_PLANILHA.replace('/edit?usp=sharing', '/export?format=csv&gid=0')
# Dica: O 'gid' da aba Config você encontra no link do navegador ao clicar nela (ex: gid=12345)
csv_config = URL_PLANILHA.replace('/edit?usp=sharing', '/export?format=csv&gid=COLE_O_ID_DA_ABA_CONFIG')

st.title("💰 Gestor Financeiro Inteligente")

# --- LER DADOS ---
try:
    df_lanc = pd.read_csv(csv_lancamentos)
    df_lanc['Data'] = pd.to_datetime(df_lanc['Data'], errors='coerce').dt.date
    
    df_cfg = pd.read_csv(csv_config)
    saldo_ini_valor = float(df_cfg['Saldo Inicial'].iloc[0]) if not df_cfg.empty else 0.0
    # Pega apenas as colunas de categoria e sinal, removendo linhas vazias
    df_cats = df_cfg[['Categoria', 'Sinal']].dropna()
except:
    df_lanc = pd.DataFrame(columns=['Data', 'Categoria', 'Valor'])
    saldo_ini_valor = 0.0
    df_cats = pd.DataFrame({'Categoria': ['Salário', 'Mercado'], 'Sinal': ['+', '-']})

# --- BARRA LATERAL: CONFIGURAÇÕES ---
with st.sidebar:
    st.header("⚙️ Configurações")
    saldo_inicial = st.number_input("Saldo Inicial (R$)", value=saldo_ini_valor)
    
    st.write("---")
    st.write("### Gerenciar Categorias")
    df_cats_editado = st.data_editor(df_cats, num_rows="dynamic", use_container_width=True)

# --- GRADE VIVA DE LANÇAMENTOS ---
st.subheader("📝 Extrato de Lançamentos")

# Criamos uma cópia para o editor
df_para_editar = df_lanc.copy()

# Cálculo do Saldo Acumulado (Lógica de Negócio)
# 1. Cruzamos os lançamentos com o sinal da categoria
df_com_sinal = df_para_editar.merge(df_cats_editado, on='Categoria', how='left')
df_com_sinal['Sinal'] = df_com_sinal['Sinal'].map({'+': 1, '-': -1}).fillna(1)
df_com_sinal['Valor_Real'] = df_com_sinal['Valor'] * df_com_sinal['Sinal']

# 2. Calculamos o saldo linha a linha
df_com_sinal = df_com_sinal.sort_values('Data')
df_com_sinal['Saldo'] = saldo_inicial + df_com_sinal['Valor_Real'].cumsum()

# Exibimos a grade principal (sem mostrar as colunas de cálculo interno)
df_editado = st.data_editor(
    df_para_editar,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
        "Categoria": st.column_config.SelectboxColumn("Categoria", options=df_cats_editado['Categoria'].tolist()),
        "Valor": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f")
    }
)

# Exibição do Saldo Final em destaque
if not df_com_sinal.empty:
    saldo_final = df_com_sinal['Saldo'].iloc[-1]
    st.metric("Saldo Final Calculado", f"R$ {saldo_final:,.2f}")

# --- BOTÃO SALVAR TUDO ---
if st.button("💾 Sincronizar tudo com a Planilha"):
    dados_totais = {
        "lancamentos": df_editado.assign(Data=df_editado['Data'].astype(str)).to_dict(orient='records'),
        "categorias": df_cats_editado.to_dict(orient='records'),
        "saldo_inicial": saldo_inicial
    }
    with st.spinner("Salvando..."):
        res = requests.post(URL_PONTE_SALVAR, json=dados_totais)
        if res.status_code == 200:
            st.success("Tudo salvo!")
            st.rerun()
