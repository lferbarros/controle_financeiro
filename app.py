import streamlit as st
import pandas as pd
import requests

# --- CONFIGURAÇÕES ---
URL_PLANILHA = "https://docs.google.com/spreadsheets/d/1rH7Uz_BhlUMDJJXGrRWg7zuEQUCbRQCGAFbE0Pu9NwI/edit?usp=sharing"
URL_PONTE_SALVAR = "https://script.google.com/macros/s/AKfycbyML1R0f1goSCMTcltnWxxShr450SMmEQGcejXnMMLBjMLABHjRoShaiXwt-66UGYno/exec"

csv_url = URL_PLANILHA.replace('/edit?usp=sharing', '/export?format=csv')

st.title("📝 Grade Financeira Viva")
st.info("Dica: Clique duas vezes em uma célula para editar. Use a tecla 'Delete' ou o ícone de lixo para excluir.")

# --- LER DADOS ---
try:
    # O comando 'header=0' garante que ele entenda a primeira linha como título
    df_original = pd.read_csv(csv_url)
except:
    df_original = pd.DataFrame(columns=['Data', 'Categoria', 'Valor'])

# --- GRADE EDITÁVEL (O CORAÇÃO DO APP) ---
# Aqui criamos a "grade viva"
df_editado = st.data_editor(
    df_original,
    num_rows="dynamic", # Permite adicionar e deletar linhas
    use_container_width=True,
    column_config={
        "Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
        "Categoria": st.column_config.SelectboxColumn("Categoria", options=["Salário", "Mercado", "Lazer", "Aluguel", "Outros"]),
        "Valor": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f")
    }
)

# --- BOTÃO PARA SALVAR ALTERAÇÕES ---
if st.button("💾 Salvar todas as alterações na Planilha"):
    # Convertemos a tabela editada para um formato que o Google Sheets entende (JSON)
    # Primeiro, formatamos a data para texto para não dar erro no envio
    df_para_enviar = df_editado.copy()
    df_para_enviar['Data'] = df_para_enviar['Data'].astype(str)
    
    lista_dados = df_para_enviar.to_dict(orient='records')
    
    with st.spinner("Sincronizando com o Google Sheets..."):
        res = requests.post(URL_PONTE_SALVAR, json=lista_dados)
        
        if res.status_code == 200:
            st.success("Planilha atualizada com sucesso!")
            # Pequeno truque para recarregar a página e mostrar os dados salvos
            st.rerun()
        else:
            st.error("Erro ao salvar. Verifique a conexão.")

# --- RESUMO FINANCEIRO ---
if not df_editado.empty:
    saldo = df_editado['Valor'].sum()
    st.metric("Saldo Total Acumulado", f"R$ {saldo:,.2f}")
