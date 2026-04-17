import streamlit as st
import pandas as pd
import requests

# --- CONFIGURAÇÕES ---
URL_PLANILHA = "https://docs.google.com/spreadsheets/d/1rH7Uz_BhlUMDJJXGrRWg7zuEQUCbRQCGAFbE0Pu9NwI/edit?usp=sharing"
URL_PONTE_SALVAR = "https://script.google.com/macros/s/AKfycbyML1R0f1goSCMTcltnWxxShr450SMmEQGcejXnMMLBjMLABHjRoShaiXwt-66UGYno/exec"

csv_url = URL_PLANILHA.replace('/edit?usp=sharing', '/export?format=csv')

st.title("📝 Grade Financeira Viva")

# --- LER E TRATAR DADOS ---
try:
    # Lemos o CSV
    df_original = pd.read_csv(csv_url)
    
    # CORREÇÃO CRUCIAL: Converter a coluna Data para o formato de data do Python
    # Se a coluna estiver vazia ou não existir, o 'errors=coerce' evita que o app quebre
    if 'Data' in df_original.columns:
        df_original['Data'] = pd.to_datetime(df_original['Data'], errors='coerce').dt.date
    else:
        df_original['Data'] = pd.to_datetime([]).date
        
    # Garantir que a coluna Valor seja numérica
    if 'Valor' in df_original.columns:
        df_original['Valor'] = pd.to_numeric(df_original['Valor'], errors='coerce').fillna(0.0)

except Exception as e:
    # Se a planilha estiver totalmente vazia, criamos um modelo padrão
    df_original = pd.DataFrame(columns=['Data', 'Categoria', 'Valor'])

# --- GRADE EDITÁVEL ---
st.info("Clique no '+' no final da tabela para adicionar ou selecione uma linha para deletar.")

df_editado = st.data_editor(
    df_original,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "Data": st.column_config.DateColumn(
            "Data", 
            format="DD/MM/YYYY", 
            required=True
        ),
        "Categoria": st.column_config.SelectboxColumn(
            "Categoria", 
            options=["Salário", "Venda", "Mercado", "Lazer", "Aluguel", "Combustível", "Outros"],
            required=True
        ),
        "Valor": st.column_config.NumberColumn(
            "Valor (R$)", 
            format="R$ %.2f",
            required=True
        )
    }
)

# --- BOTÃO PARA SALVAR ---
if st.button("💾 Salvar Alterações"):
    if df_editado is not None:
        # Preparar para o envio: converter datas para texto (string)
        df_para_enviar = df_editado.copy()
        df_para_enviar['Data'] = df_para_enviar['Data'].astype(str)
        
        lista_dados = df_para_enviar.to_dict(orient='records')
        
        with st.spinner("Sincronizando..."):
            try:
                res = requests.post(URL_PONTE_SALVAR, json=lista_dados, timeout=10)
                if res.status_code == 200:
                    st.success("Tabela sincronizada!")
                    st.rerun()
                else:
                    st.error(f"Erro no servidor: {res.status_code}")
            except Exception as e:
                st.error(f"Erro de conexão: {e}")

# --- RESUMO ---
if not df_editado.empty:
    saldo = df_editado['Valor'].sum()
    cor = "blue" if saldo >= 0 else "red"
    st.markdown(f"### Saldo Atual: <span style='color:{cor}'>R$ {saldo:,.2f}</span>", unsafe_allow_html=True)
