import streamlit as st
import pandas as pd
import datetime
from dateutil.relativedelta import relativedelta
import requests

# Configuração da Página
st.set_page_config(page_title="Gestão Financeira Operacional", layout="wide")

# ==========================================
# 1. SEGURANÇA E CONFIGURAÇÃO (SECRETS)
# ==========================================
if "URL_SCRIPT" in st.secrets:
    url_planilha = st.secrets["URL_SCRIPT"]
else:
    url_planilha = st.sidebar.text_input("URL do App Script (Google Sheets)", type="password")

# ==========================================
# 2. GERENCIAMENTO DE ESTADO
# ==========================================
if 'categorias' not in st.session_state:
    st.session_state.categorias = pd.DataFrame(columns=["Categoria", "Tipo"])
if 'cartoes' not in st.session_state:
    st.session_state.cartoes = pd.DataFrame(columns=["Cartão", "Vencimento", "Fechamento"])
if 'lancamentos' not in st.session_state:
    st.session_state.lancamentos = pd.DataFrame(columns=["Data", "Categoria", "Cartao", "Tipo", "Valor", "Data_Efetiva"])

# ==========================================
# 3. LÓGICA DE DATAS E SALDO
# ==========================================
def calcular_data_efetiva(data_compra, nome_cartao):
    if nome_cartao == "Nenhum" or not nome_cartao:
        return data_compra
    
    cartao_info = st.session_state.cartoes[st.session_state.cartoes["Cartão"] == nome_cartao]
    if cartao_info.empty:
        return data_compra
        
    dia_fechamento = int(cartao_info.iloc[0]["Fechamento"])
    dia_vencimento = int(cartao_info.iloc[0]["Vencimento"])
    
    data_fechamento_mes = datetime.date(data_compra.year, data_compra.month, dia_fechamento)
    
    if data_compra > data_fechamento_mes:
        base_vencimento = data_compra + relativedelta(months=1)
    else:
        base_vencimento = data_compra
    
    try:
        data_venc = datetime.date(base_vencimento.year, base_vencimento.month, dia_vencimento)
    except ValueError:
        data_venc = datetime.date(base_vencimento.year, base_vencimento.month, 28)
        
    return data_venc

def processar_exibicao():
    if not st.session_state.lancamentos.empty:
        df = st.session_state.lancamentos.copy()
        df["Data_Efetiva"] = pd.to_datetime(df["Data_Efetiva"]).dt.date
        df = df.sort_values(by="Data_Efetiva").reset_index(drop=True)
        
        sinais = df['Tipo'].apply(lambda x: 1 if x == '+' else -1)
        df['Valor_Num'] = pd.to_numeric(df['Valor']) * sinais
        df['Saldo Acumulado'] = df['Valor_Num'].cumsum()
        return df.drop(columns=['Valor_Num'])
    return st.session_state.lancamentos

# ==========================================
# 4. INTERFACE - BARRA LATERAL
# ==========================================
with st.sidebar:
    st.header("⚙️ Cadastros Base")
    
    with st.expander("Categorias"):
        with st.form("form_cat", clear_on_submit=True):
            n_cat = st.text_input("Nova Categoria")
            t_cat = st.selectbox("Sinal", ["-", "+"])
            if st.form_submit_button("Salvar"):
                if n_cat:
                    nova_cat = pd.DataFrame([{"Categoria": n_cat, "Tipo": t_cat}])
                    st.session_state.categorias = pd.concat([st.session_state.categorias, nova_cat], ignore_index=True)

    with st.expander("Cartões de Crédito"):
        with st.form("form_cartao", clear_on_submit=True):
            n_cartao = st.text_input("Nome do Cartão")
            venc = st.number_input("Dia Vencimento", 1, 31, 10)
            fech = st.number_input("Dia Fechamento", 1, 31, 3)
            if st.form_submit_button("Cadastrar"):
                if n_cartao:
                    novo_c = pd.DataFrame([{"Cartão": n_cartao, "Vencimento": venc, "Fechamento": fech}])
                    st.session_state.cartoes = pd.concat([st.session_state.cartoes, novo_c], ignore_index=True)

# ==========================================
# 5. PAINEL PRINCIPAL - LANÇAMENTOS
# ==========================================
st.title("🏦 Fluxo de Caixa Operacional")

with st.container(border=True):
    st.subheader("Novo Lançamento")
    c1, c2, c3, c4 = st.columns(4)
    
    with c1:
        d_lanc = st.date_input("Data da Ocorrência")
    with c2:
        lista_c = st.session_state.categorias["Categoria"].tolist()
        cat_sel = st.selectbox("Categoria", lista_c if lista_c else ["Defina uma categoria"])
    with c3:
        lista_cart = ["Nenhum"] + st.session_state.cartoes["Cartão"].tolist()
        cart_sel = st.selectbox("Meio de Pagamento", lista_cart)
    with c4:
        valor = st.number_input("Valor (R$)", min_value=0.0, format="%.2f")

    if st.button("Confirmar Lançamento", use_container_width=True, type="primary"):
        if not st.session_state.categorias.empty and cat_sel != "Defina uma categoria":
            tipo = st.session_state.categorias.loc[st.session_state.categorias["Categoria"] == cat_sel, "Tipo"].values[0]
            data_efetiva = calcular_data_efetiva(d_lanc, cart_sel)
            
            novo = pd.DataFrame([{
                "Data": d_lanc, 
                "Categoria": cat_sel, 
                "Cartao": cart_sel,
                "Tipo": tipo, 
                "Valor": valor, 
                "Data_Efetiva": data_efetiva
            }])
            
            st.session_state.lancamentos = pd.concat([st.session_state.lancamentos, novo], ignore_index=True)
            
            if url_planilha:
                try:
                    payload = {
                        "Data": d_lanc.isoformat(),
                        "Categoria": cat_sel,
                        "Cartao": cart_sel,
                        "Tipo": tipo,
                        "Valor": valor,
                        "Data_Efetiva": data_efetiva.isoformat(),
                        "action": "insert"
                    }
                    requests.post(url_planilha, json=payload, timeout=5)
                    st.success("Sincronizado com a planilha!")
                except:
                    st.warning("Erro de conexão com o Google Sheets.")
            
            # A linha abaixo deve estar exatamente neste nível de indentação
            st.rerun()

st.divider()

# ==========================================
# 6. TABELA DINÂMICA
# ==========================================
st.subheader("Projeção de Saldo Bancário")
df_final = processar_exibicao()

if not df_final.empty:
    df_editado = st.data_editor(
        df_final,
        column_config={
            "Valor": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
            "Saldo Acumulado": st.column_config.NumberColumn("Saldo Previsto", format="R$ %.2f"),
            "Data_Efetiva": st.column_config.DateColumn("Data Efetiva", format="DD/MM/YYYY")
        },
        disabled=["Saldo Acumulado"],
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True
    )
    
    if len(df_editado) != len(st.session_state.lancamentos):
        st.session_state.lancamentos = df_editado.drop(columns=["Saldo Acumulado"], errors="ignore")
else:
    st.info("Aguardando lançamentos para projetar o fluxo de caixa.")
