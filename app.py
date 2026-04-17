import streamlit as st
import pandas as pd
import requests
from datetime import datetime

# --- CONFIGURAÇÕES ---
# 1. Cole aqui o link da planilha que você copiou no Passo 1
URL_PLANILHA = "https://docs.google.com/spreadsheets/d/1rH7Uz_BhlUMDJJXGrRWg7zuEQUCbRQCGAFbE0Pu9NwI/edit?usp=sharing"
# 2. Cole aqui o URL do Apps Script que você copiou no Passo 2
URL_PONTE_SALVAR = "https://script.google.com/macros/s/AKfycbzclG8Nsa_1FmCDn_4MJHIBHEbI4VmiSatKc2DTPbsvW2dr_81K7Sb_D09qh7_gwW5z/exec"

# Transforma o link da planilha em um link de download de dados
csv_url = URL_PLANILHA.replace('/edit?usp=sharing', '/export?format=csv')

st.title("💰 Meu Financeiro Mobile")

# --- LER DADOS ---
try:
    df = pd.read_csv(csv_url)
    df['Data'] = pd.to_datetime(df['Data'])
except:
    df = pd.DataFrame(columns=['Data', 'Categoria', 'Valor'])

# --- FORMULÁRIO ---
with st.form("novo_lancamento", clear_on_submit=True):
    st.write("### Novo Lançamento")
    data = st.date_input("Data", datetime.now()).strftime('%Y-%m-%d')
    cat = st.selectbox("Categoria", ["Salário", "Mercado", "Lazer", "Aluguel", "Outros"])
    valor = st.number_input("Valor (R$)", min_value=0.0, step=1.0)
    tipo = st.radio("Tipo", ["Receita (+)", "Despesa (-)"], horizontal=True)
    
    if st.form_submit_button("Salvar"):
        valor_final = valor if "Receita" in tipo else -valor
        # Envia para a "ponte" que salva na planilha
        dados = {"data": data, "categoria": cat, "valor": valor_final}
        res = requests.post(URL_PONTE_SALVAR, json=dados)
        
        if res.status_code == 200:
            st.success("Salvo com sucesso! Atualize a página.")
        else:
            st.error("Erro ao salvar.")

# --- EXIBIR ---
st.write("---")
st.write("### Extrato")
if not df.empty:
    st.dataframe(df.sort_values(by='Data', ascending=False), use_container_width=True)
    st.metric("Saldo Atual", f"R$ {df['Valor'].sum():.2f}")
