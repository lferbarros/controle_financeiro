import streamlit as st
import pandas as pd
import datetime
import uuid
import requests
from dateutil.relativedelta import relativedelta

st.set_page_config(page_title="Gestor Financeiro", layout="wide")

# =========================================================
# 1. ACESSO MULTIUSUÁRIO (URL)
# =========================================================
if "url_base" not in st.session_state:
    st.session_state.url_base = ""

def logout():
    st.session_state.clear()
    st.rerun()

if not st.session_state.url_base:
    st.title("Bem-vindo ao Gestor Financeiro")
    url_input = st.text_input("Insira sua URL do Google Apps Script:", type="password")
    if st.button("Conectar e Iniciar"):
        if "script.google.com" in url_input:
            st.session_state.url_base = url_input
            st.rerun()
        else:
            st.error("URL inválida.")
    st.stop()

URL_SCRIPT = st.session_state.url_base

# =========================================================
# 2. FUNÇÕES DE SINCRONIZAÇÃO (SUA VERSÃO ESTÁVEL)
# =========================================================
def sync_api(payload):
    try:
        requests.post(URL_SCRIPT, json=payload, timeout=10)
        return True
    except:
        return False

def carregar_tudo():
    if not URL_SCRIPT: return
    try:
        res = requests.get(URL_SCRIPT, timeout=10).json()
        
        # 1. Blindagem Total: Categorias
        df_cat = pd.DataFrame(res.get('categorias', []))
        colunas_cat = ["Categoria", "Tipo", "ID"]
        for col in colunas_cat:
            if col not in df_cat.columns:
                df_cat[col] = None
        st.session_state.df_cat = df_cat

        # 2. Blindagem Total: Cartões (Onde dava o erro)
        df_card = pd.DataFrame(res.get('cartoes', []))
        colunas_card = ["Cartão", "Vencimento", "Fechamento", "ID"]
        for col in colunas_card:
            if col not in df_card.columns:
                df_card[col] = None
        st.session_state.df_card = df_card

# 3. Blindagem Total: Lançamentos
      
        # --- Trecho dentro de carregar_tudo() para Lançamentos ---
        df_lan = pd.DataFrame(res.get('lancamentos', []))

        # Correção do Bug: Mapeia os nomes da planilha para os nomes do código
        mapeamento = {
            "Data Lanc.": "Data",
            "Cartão": "Cartao"
        }
        df_lan = df_lan.rename(columns=mapeamento)

        # Garante que as colunas existam no DataFrame interno
        colunas_lan = ["Data", "Categoria", "Cartao", "Valor", "Data_Efetiva", "Tipo", "ID"]
        for col in colunas_lan:
            if col not in df_lan.columns:
                df_lan[col] = None
        st.session_state.df_lan = df_lan
        
        st.session_state.last_sync = datetime.datetime.now()
    except Exception as e:
        st.error(f"Erro de conexão: {e}")

if 'df_lan' not in st.session_state:
    carregar_tudo()

# =========================================================
# 3. LÓGICA DE NEGÓCIO
# =========================================================
def calcular_vencimento(data_o, cartao_n):
    if cartao_n == "Não" or st.session_state.df_card.empty: return data_o
    c = st.session_state.df_card[st.session_state.df_card["Cartao"] == cartao_n]
    if c.empty: return data_o
    f, v = int(c.iloc[0]["Fechamento"]), int(c.iloc[0]["Vencimento"])
    dt_f = datetime.date(data_o.year, data_o.month, f)
    base = data_o + relativedelta(months=1) if data_o.day > f else data_o
    try: return datetime.date(base.year, base.month, v)
    except: return datetime.date(base.year, base.month, 28)

# =========================================================
# 4. SIDEBAR (TABELAS VIVAS COM BLINDAGEM)
# =========================================================
with st.sidebar:
    st.title("Configurações")
    if st.button("Sair / Trocar Base"): logout()
    st.divider()

    # --- TABELA CATEGORIAS ---
    st.subheader("Categorias")
    cat_editada = st.data_editor(
        st.session_state.df_cat,
        column_config={
            "ID": None, 
            "id": None,
            "Tipo": st.column_config.SelectboxColumn("Sinal", options=["+", "-"], required=True)
        },
        num_rows="dynamic", hide_index=True, key="editor_categorias"
    )

    # Lógica de Sincronização Blindada para Categorias
    if len(cat_editada) != len(st.session_state.df_cat):
        if len(cat_editada) > len(st.session_state.df_cat): # Inclusão
            nova_linha = cat_editada.iloc[-1].copy()
            nova_linha['ID'] = str(uuid.uuid4())
            sync_api({"action": "insert", "table": "Categorias", **nova_linha.to_dict()})
        else: # Exclusão
            ids_antigos = set(st.session_state.df_cat["ID"].dropna())
            ids_novos = set(cat_editada["ID"].dropna())
            id_removido = list(ids_antigos - ids_novos)
            if id_removido:
                sync_api({"action": "delete", "table": "Categorias", "ID": id_removido[0]})
        carregar_tudo()
        st.rerun()

    st.divider()

    # --- TABELA CARTÕES (COM DIAS 1-31) ---
    st.subheader("Cartões")
    dias_mes = list(range(1, 32)) # Opções de 1 a 31
    
    card_editado = st.data_editor(
        st.session_state.df_card,
        column_config={
            "ID": None,
            "id": None,
            "Cartão": None,
            "cartão": None,
            "Cartao": st.column_config.TextColumn("Cartão", required=True),
            "Vencimento": st.column_config.SelectboxColumn("Venc.", options=dias_mes, required=True),
            "Fechamento": st.column_config.SelectboxColumn("Fech.", options=dias_mes, required=True)
        },
        num_rows="dynamic", hide_index=True, key="editor_cartoes"
    )

    # Lógica de Sincronização Blindada para Cartões
    if len(card_editado) != len(st.session_state.df_card):
        if len(card_editado) > len(st.session_state.df_card): # Inclusão
            nova_linha = card_editado.iloc[-1].copy()
            nova_linha['ID'] = str(uuid.uuid4())
            sync_api({"action": "insert", "table": "Cartoes", **nova_linha.to_dict()})
        else: # Exclusão
            ids_antigos = set(st.session_state.df_card["ID"].dropna())
            ids_novos = set(card_editado["ID"].dropna())
            id_removido = list(ids_antigos - ids_novos)
            if id_removido:
                sync_api({"action": "delete", "table": "Cartoes", "ID": id_removido[0]})
        carregar_tudo()
        st.rerun()

# =========================================================
# 5. ÁREA PRINCIPAL
# =========================================================
st.title("Gestor Financeiro")

# --- Trecho do Formulário de Lançamento ---
with st.expander("Incluir Lançamento", expanded=False):
    col1, col2, col3, col4 = st.columns(4)
    with col1: data_o = st.date_input("Data Lanç.", format="DD/MM/YYYY") # d_o -> data_o
    with col2:
        cats = st.session_state.df_cat["Categoria"].tolist() if not st.session_state.df_cat.empty else []
        cat_s = st.selectbox("Categoria", cats if cats else ["Cadastre na lateral"]) # cat_sel -> cat_s
    with col3:
        list_card = ["Não"] + (st.session_state.df_card["Cartao"].tolist() if not st.session_state.df_card.empty else [])
        card_s = st.selectbox("Cartão", list_card) # card_sel -> card_s
    with col4: valor_s = st.number_input("Valor", min_value=0.0, format="%.2f") # v_val -> valor_s

    if st.button("Confirmar Lançamento", use_container_width=True, type="primary"):
            # Agora 'cat_s' está definido acima
            # --- Trecho dentro do botão de Confirmação ---
        if cat_s in cats:
            sinal = st.session_state.df_cat.loc[st.session_state.df_cat["Categoria"] == cat_s, "Tipo"].values[0]
            data_e = calcular_vencimento(data_o, card_s)
            uid = str(uuid.uuid4())
            
            payload = {
                "action": "insert", 
                "table": "Lançamentos", 
                "ID": uid,
                "Data Lanc.": data_o.isoformat(), # Nome exato na planilha
                "Categoria": cat_s, 
                "Cartão": card_s,            # Nome exato na planilha com acento
                "Tipo": sinal, 
                "Valor": float(valor_s), 
                "Data_Efetiva": data_e.isoformat()
            }
            if sync_api(payload):
                st.toast("Lançamento salvo!")
                carregar_tudo()
                st.rerun()
        

# =========================================================
# 6. PROCESSAMENTO E VISUALIZAÇÃO (TABELA + RESUMO)
# =========================================================

def get_render_df():
    if st.session_state.df_lan.empty: return pd.DataFrame()
    df = st.session_state.df_lan.copy()
    df["Data_Efetiva"] = pd.to_datetime(df["Data_Efetiva"], errors='coerce')
    df = df.dropna(subset=["Data_Efetiva"]).sort_values("Data_Efetiva")
    df["Valor"] = pd.to_numeric(df["Valor"], errors='coerce').fillna(0)
    sinais = df['Tipo'].apply(lambda x: 1 if str(x).strip() == "+" else -1)
    df['Saldo Acumulado'] = (df['Valor'] * sinais).cumsum()
    return df

def get_resumo_semanal():
    df = st.session_state.df_lan.copy()
    
    # 1. Horizonte de 5 semanas
    hoje = datetime.date.today()
    segunda_atual = hoje - datetime.timedelta(days=hoje.weekday())
    datas_semanas = [segunda_atual + datetime.timedelta(weeks=i) for i in range(5)]
    
    # 2. Preparação de dados (Histórico Completo)
    if df.empty:
        return pd.DataFrame({'Semana': datas_semanas, '+': 0.0, '-': 0.0, 'Variacao': 0.0, 'Saldo_Acum': 0.0})

    df["Data_Efetiva"] = pd.to_datetime(df["Data_Efetiva"], errors='coerce').dt.date
    df = df.dropna(subset=["Data_Efetiva"]).sort_values("Data_Efetiva")
    df["Valor"] = pd.to_numeric(df["Valor"], errors='coerce').fillna(0)
    
    # Cálculo do saldo acumulado linha a linha no tempo
    sinais = df['Tipo'].apply(lambda x: 1 if str(x).strip() == "+" else -1)
    df['Acumulado_Historico'] = (df['Valor'] * sinais).cumsum()
    
    # Identificar a semana de cada lançamento
    df['Sem_Ref'] = df['Data_Efetiva'].apply(lambda x: x - datetime.timedelta(days=x.weekday()))
    
    # Agrupar variações semanais (Entradas e Saídas)
    resumo_vendas = df.groupby(['Sem_Ref', 'Tipo'])['Valor'].sum().unstack(fill_value=0)
    if '+' not in resumo_vendas.columns: resumo_vendas['+'] = 0.0
    if '-' not in resumo_vendas.columns: resumo_vendas['-'] = 0.0
    resumo_vendas['Variacao'] = resumo_vendas['+'] - resumo_vendas['-']
    
    # Pegar o último saldo acumulado de cada semana
    resumo_saldo = df.groupby('Sem_Ref')['Acumulado_Historico'].last()
    
    # Unir e reindexar para as 5 semanas do horizonte
    resumo_final = pd.merge(resumo_vendas, resumo_saldo, left_index=True, right_index=True).reset_index()
    resumo_final.rename(columns={'Sem_Ref': 'Semana', 'Acumulado_Historico': 'Saldo_Acum'}, inplace=True)
    
    df_base = pd.DataFrame({'Semana': datas_semanas})
    resumo_final = pd.merge(df_base, resumo_final, on='Semana', how='left')
    
    # Importante: Saldo acumulado deve persistir (ffill) e variações vazias são 0
    resumo_final[['+', '-', 'Variacao']] = resumo_final[['+', '-', 'Variacao']].fillna(0)
    resumo_final['Saldo_Acum'] = resumo_final['Saldo_Acum'].ffill().fillna(0)
    
    return resumo_final

# --- EXECUÇÃO DA INTERFACE ---
df_vis = get_render_df()

if not df_vis.empty:
    # 1. ESTILO
    def style_negative(row):
        return ['background-color: rgba(255, 75, 75, 0.15)' if row['Saldo Acumulado'] < 0 else '' for _ in row]

    # 2. BLOCO DA TABELA PRINCIPAL
    with st.expander("Fluxo Projetado", expanded=True):
        lan_edit = st.data_editor(
            df_vis.style.apply(style_negative, axis=1),
            
             column_config={
            "ID": None,
            "Tipo": None,
            "Cartao": st.column_config.TextColumn("Cartão"), # Volta o acento apenas na etiqueta
            "Data": st.column_config.DateColumn("Data Lanç.", format="DD/MM/YYYY"),
            "Data_Efetiva": st.column_config.DateColumn("Vencimento", format="DD/MM/YYYY"),
            "Valor": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
            "Saldo Acumulado": st.column_config.NumberColumn("Saldo Acumulado", format="R$ %.2f")
        },

            disabled=df_vis.columns, 
            num_rows="dynamic",
            hide_index=True,
            use_container_width=True,
            key="main_table"
    )

        # Lógica de Exclusão
        if len(lan_edit) < len(df_vis):
            ids_vivos = set(lan_edit["ID"].dropna())
            ids_antigos = set(df_vis["ID"].dropna())
            id_morto = list(ids_antigos - ids_vivos)
            if id_morto and sync_api({"action": "delete", "table": "Lançamentos", "ID": id_morto[0]}):
                carregar_tudo()
                st.rerun()

    # 3. BLOCO DO RESUMO SEMANAL (Compacto para Mobile)
    df_sem = get_resumo_semanal()
    
    # CSS Cirúrgico para comprimir métricas e fontes
    st.markdown("""
        <style>
            [data-testid="stMetricValue"] { font-size: 1.1rem !important; }
            [data-testid="stMetricLabel"] { font-size: 0.8rem !important; }
            [data-testid="stVerticalBlock"] > div { padding-top: 0rem !important; padding-bottom: 0rem !important; }
            .stExpander { border: none !important; }
        </style>
    """, unsafe_allow_html=True)

    with st.expander("📊 Resumo por Período", expanded=True):
        for _, row in df_sem.iterrows():
            sem_inicio = row['Semana']
            sem_fim = sem_inicio + datetime.timedelta(days=6)
            
            # Texto menor e em negrito para a data
            st.markdown(f"<p style='margin-bottom: -10px; font-size: 0.9rem;'><b>{sem_inicio.strftime('%d/%m')} a {sem_fim.strftime('%d/%m')}</b></p>", unsafe_allow_html=True)
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Entradas", f"R$ {row['+']:,.2f}")
            c2.metric("Saídas", f"R$ {row['-']:,.2f}")
            # Card 3: Saldo Final da Semana com Delta da Variação Semanal
            c3.metric("Saldo Acum.", f"R$ {row['Saldo_Acum']:,.2f}", delta=f"{row['Variacao']:,.2f}")
            
            st.markdown("<hr style='margin: 5px 0px; opacity: 0.2;'>", unsafe_allow_html=True)
            
else:
    st.info("Aguardando lançamentos.")
