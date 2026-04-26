import streamlit as st
import pandas as pd
import datetime
import uuid
import requests
from dateutil.relativedelta import relativedelta

# Configuração da página para melhor visualização em mobile e desktop
st.set_page_config(page_title="Gestor Financeiro PRO", layout="wide", initial_sidebar_state="collapsed")

# =========================================================
# 1. ACESSO E CONEXÃO
# =========================================================# No bloco "if 'url_base' not in st.session_state:"
if "url_base" not in st.session_state:
    st.session_state.url_base = ""

# ADICIONE ESTAS LINHAS AQUI:
if "chat_step" not in st.session_state:
    st.session_state.chat_step = 0
if "chat_data" not in st.session_state:
    st.session_state.chat_data = {}

def logout():
    st.session_state.clear()
    st.rerun()

if not st.session_state.url_base:
    st.title("🚀 Gestor Financeiro")
    url_input = st.text_input("Insira sua URL do Google Apps Script:", type="password")
    if st.button("Conectar Sistema", use_container_width=True):
        if "script.google.com" in url_input:
            st.session_state.url_base = url_input
            st.rerun()
        else:
            st.error("URL inválida.")
    st.stop()

URL_SCRIPT = st.session_state.url_base

# =========================================================
# 2. MOTOR DE SINCRONIZAÇÃO (ANTI-LOOP)
# =========================================================
def sync_api(payload):
    try:
        # Padronização de nomes (Removendo acentos para o back-end)
        payload["table"] = payload["table"].replace("ç", "c").replace("õ", "o").replace("ã", "a")
        if "Cartao" in payload: payload["Cartao"] = payload.pop("Cartao")
        
        res = requests.post(URL_SCRIPT, json=payload, timeout=15)
        return res.status_code == 200 and "error" not in res.text.lower()
    except:
        return False

def carregar_tudo():
    try:
        res = requests.get(URL_SCRIPT, timeout=15).json()
        
        # Categorias
        df_cat = pd.DataFrame(res.get('categorias', []))
        for c in ["Categoria", "Tipo", "ID"]:
            if c not in df_cat.columns: df_cat[c] = None
        st.session_state.df_cat = df_cat

        # Cartões
        df_card = pd.DataFrame(res.get('cartoes', []))
        if "Cartão" in df_card.columns: df_card = df_card.rename(columns={"Cartão": "Cartao"})
        for c in ["Cartao", "Vencimento", "Fechamento", "ID"]:
            if c not in df_card.columns: df_card[c] = None
        st.session_state.df_card = df_card

        # Lançamentos
        df_lan = pd.DataFrame(res.get('lancamentos', []))
        # Mapeia colunas da planilha para o código
        df_lan = df_lan.rename(columns={"Data Lanc.": "Data", "Cartão": "Cartao"})
        for c in ["Data", "Categoria", "Cartao", "Valor", "Data_Efetiva", "Tipo", "ID"]:
            if c not in df_lan.columns: df_lan[c] = None
        st.session_state.df_lan = df_lan
        
        st.session_state.last_sync = datetime.datetime.now()
    except Exception as e:
        st.error(f"Erro ao carregar dados: {e}")

if 'df_lan' not in st.session_state:
    carregar_tudo()

# =========================================================
# 3. LÓGICA DE NEGÓCIO (VENCIMENTOS)
# =========================================================
def calcular_vencimento(data_o, cartao_n):
    if cartao_n == "Não" or st.session_state.df_card.empty: return data_o
    c = st.session_state.df_card[st.session_state.df_card["Cartao"] == cartao_n]
    if c.empty: return data_o
    try:
        f, v = int(c.iloc[0]["Fechamento"]), int(c.iloc[0]["Vencimento"])
        base = data_o + relativedelta(months=1) if data_o.day > f else data_o
        return datetime.date(base.year, base.month, v)
    except:
        return data_o + relativedelta(months=1)

# =========================================================

# =========================================================
# 4. SIDEBAR - CONFIGURAÇÕES (VERSÃO BLOQUEADA PARA EDIÇÃO)
# =========================================================
with st.sidebar:
    st.title("⚙️ Configurações")
    if st.button("🔄 Sincronizar Agora"): 
        carregar_tudo()
        st.rerun()
    if st.button("🚪 Sair"): logout()
    st.divider()

    # --- SEÇÃO: CATEGORIAS ---
    st.subheader("Categorias")
    
    # Formulário de Inclusão (Seguindo o padrão da tabela principal)
    with st.expander("🆕 Nova Categoria", expanded=False):
        new_cat = st.text_input("Nome da Categoria", key="input_new_cat")
        new_tipo = st.selectbox("Sinal", ["-", "+"], key="input_new_tipo")
        if st.button("Adicionar", key="btn_add_cat", use_container_width=True):
            if new_cat:
                payload = {
                    "action": "insert", "table": "Categorias", 
                    "Categoria": new_cat, "Tipo": new_tipo, "ID": str(uuid.uuid4())
                }
                if sync_api(payload):
                    st.toast("Categoria adicionada!")
                    carregar_tudo()
                    st.rerun()

    # Tabela de Visualização e Exclusão (Bloqueada para edição)
    edit_cat = st.data_editor(
        st.session_state.df_cat,
        column_config={"ID": None, "Tipo": "Sinal"},
        num_rows="dynamic", 
        hide_index=True, 
        disabled=["Categoria", "Tipo", "ID"], # Bloqueio cirúrgico de edição
        key="widget_cat"
    )
    
    if st.session_state.widget_cat["deleted_rows"]:
        with st.spinner("Removendo..."):
            for idx in st.session_state.widget_cat["deleted_rows"]:
                id_a = st.session_state.df_cat.iloc[idx]["ID"]
                sync_api({"action": "delete", "table": "Categorias", "ID": id_a})
            carregar_tudo()
            st.rerun()

    st.divider()

    # --- SEÇÃO: CARTÕES ---
    st.subheader("Cartões")
    lista_dias = list(range(1, 32))

    # Formulário de Inclusão
    with st.expander("🆕 Novo Cartão", expanded=False):
        new_card = st.text_input("Nome do Cartão", key="input_new_card")
        c_venc = st.selectbox("Vencimento (dia)", lista_dias, key="input_new_venc")
        c_fech = st.selectbox("Fechamento (dia)", lista_dias, key="input_new_fech")
        if st.button("Adicionar", key="btn_add_card", use_container_width=True):
            if new_card:
                payload = {
                    "action": "insert", "table": "Cartoes", 
                    "Cartao": new_card, "Vencimento": c_venc, 
                    "Fechamento": c_fech, "ID": str(uuid.uuid4())
                }
                if sync_api(payload):
                    st.toast("Cartão adicionado!")
                    carregar_tudo()
                    st.rerun()

    # Tabela de Visualização e Exclusão (Bloqueada para edição)
    edit_card = st.data_editor(
        st.session_state.df_card,
        column_config={
            "ID": None, 
            "Cartao": "Nome", 
            "Vencimento": "Venc", 
            "Fechamento": "Fech"
        },
        num_rows="dynamic", 
        hide_index=True,
        disabled=["Cartao", "Vencimento", "Fechamento", "ID"], # Bloqueio cirúrgico de edição
        key="widget_card"
    )

    if st.session_state.widget_card["deleted_rows"]:
        with st.spinner("Removendo..."):
            for idx in st.session_state.widget_card["deleted_rows"]:
                try:
                    id_a = str(st.session_state.df_card.iloc[idx]["ID"])
                    sync_api({"action": "delete", "table": "Cartoes", "ID": id_a})
                except Exception as e:
                    st.error(f"Erro ao excluir: {e}")
            carregar_tudo()
            st.rerun()
            
            
        # =========================================================
# 6. PROCESSAMENTO DOS DADOS (TABELAS E RESUMOS)
# =========================================================
def get_df_render():
    if st.session_state.df_lan.empty: return pd.DataFrame()
    df = st.session_state.df_lan.copy()
    df["Data_Efetiva"] = pd.to_datetime(df["Data_Efetiva"], errors='coerce').dt.date
    df = df.dropna(subset=["Data_Efetiva"]).sort_values("Data_Efetiva")
    df["Valor"] = pd.to_numeric(df["Valor"], errors='coerce').fillna(0)
    sinais = df['Tipo'].apply(lambda x: 1 if str(x).strip() == "+" else -1)
    df['Saldo_Acumulado'] = (df['Valor'] * sinais).cumsum()
    return df

def get_resumo_semanal():
    df = st.session_state.df_lan.copy()
    hoje = datetime.date.today()
    segunda_atual = hoje - datetime.timedelta(days=hoje.weekday())
    datas_semanas = [segunda_atual + datetime.timedelta(weeks=i) for i in range(5)]
    
    if df.empty:
        return pd.DataFrame({'Semana': datas_semanas, '+': 0.0, '-': 0.0, 'Var': 0.0, 'Acum': 0.0})

    df["Data_Efetiva"] = pd.to_datetime(df["Data_Efetiva"], errors='coerce').dt.date
    df = df.dropna(subset=["Data_Efetiva"]).sort_values("Data_Efetiva")
    
    # Cálculo histórico de saldo
    sinais = df['Tipo'].apply(lambda x: 1 if str(x).strip() == "+" else -1)
    df['Acum_Historico'] = (df['Valor'] * sinais).cumsum()
    df['Sem_Ref'] = df['Data_Efetiva'].apply(lambda x: x - datetime.timedelta(days=x.weekday()))
    
    resumo_v = df.groupby(['Sem_Ref', 'Tipo'])['Valor'].sum().unstack(fill_value=0)
    if '+' not in resumo_v.columns: resumo_v['+'] = 0.0
    if '-' not in resumo_v.columns: resumo_v['-'] = 0.0
    resumo_v['Var'] = resumo_v['+'] - resumo_v['-']
    
    resumo_s = df.groupby('Sem_Ref')['Acum_Historico'].last()
    resumo_final = pd.merge(resumo_v, resumo_s, left_index=True, right_index=True).reset_index()
    resumo_final.rename(columns={'Sem_Ref': 'Semana', 'Acum_Historico': 'Acum'}, inplace=True)
    
    df_base = pd.DataFrame({'Semana': datas_semanas})
    resumo_final = pd.merge(df_base, resumo_final, on='Semana', how='left')
    resumo_final[['+', '-', 'Var']] = resumo_final[['+', '-', 'Var']].fillna(0)
    resumo_final['Acum'] = resumo_final['Acum'].ffill().fillna(0)
    
    return resumo_final
    
# Funcao assistente virtual

def assistente_virtual():
    st.subheader("🤖 Assistente de Fluxo")
    
    # Passo 0: Início
    if st.session_state.chat_step == 0:
        st.chat_message("assistant").write("Olá! Vamos projetar um lançamento futuro? O que deseja fazer?")
        c1, c2 = st.columns(2)
        if c1.button("📝 Novo Lançamento", use_container_width=True):
            st.session_state.chat_step = 1
            st.rerun()
        if c2.button("🧹 Limpar", use_container_width=True):
            st.session_state.chat_step = 0
            st.session_state.chat_data = {}
            st.rerun()

    # Passo 1: Valor
    elif st.session_state.chat_step == 1:
        st.chat_message("assistant").write("Qual o **valor** previsto?")
        valor_chat = st.number_input("R$:", min_value=0.0, step=0.01, format="%.2f")
        if st.button("Próximo ➡️", use_container_width=True):
            st.session_state.chat_data["valor"] = valor_chat
            st.session_state.chat_step = 2 # Vai para a data
            st.rerun()

    # Passo 2: Data da Ocorrência (NOVO)
    elif st.session_state.chat_step == 2:
        st.chat_message("assistant").write("Para **quando** está planejado este lançamento?")
        # O calendário abre por padrão em hoje, mas permite escolher qualquer data futura
        data_chat = st.date_input("Selecione a data:", datetime.date.today(), format="DD/MM/YYYY")
        if st.button("Definir Data 📅", use_container_width=True):
            st.session_state.chat_data["data"] = data_chat
            st.session_state.chat_step = 3
            st.rerun()

    # Passo 3: Categoria
    elif st.session_state.chat_step == 3:
        st.chat_message("assistant").write("Qual a **categoria**?")
        lista_cat = st.session_state.df_cat["Categoria"].tolist()
        cat_chat = st.selectbox("Selecione:", [""] + lista_cat)
        if cat_chat != "" and st.button("Confirmar Categoria", use_container_width=True):
            st.session_state.chat_data["categoria"] = cat_chat
            st.session_state.chat_step = 4
            st.rerun()

    # Passo 4: Cartão / Forma de Pagamento
    elif st.session_state.chat_step == 4:
        st.chat_message("assistant").write("Como será feito o **pagamento**?")
        lista_card = ["Não"] + st.session_state.df_card["Cartao"].tolist()
        card_chat = st.selectbox("Selecione o cartão (se houver):", lista_card)
        if st.button("Definir Pagamento", use_container_width=True):
            st.session_state.chat_data["cartao"] = card_chat
            st.session_state.chat_step = 5
            st.rerun()

    # Passo 5: Confirmação e Salvamento
    elif st.session_state.chat_step == 5:
        resumo = st.session_state.chat_data
        data_formatada = resumo['data'].strftime('%d/%m/%Y')
        
        st.chat_message("assistant").write(f"""
            **Resumo do Lançamento Projetado:**
            * 💰 **Valor:** R$ {resumo['valor']:.2f}
            * 📅 **Data Prevista:** {data_formatada}
            * 📂 **Categoria:** {resumo['categoria']}
            * 💳 **Pagamento:** {resumo['cartao']}
            
            Posso confirmar o agendamento?
        """)
        
        col_sim, col_nao = st.columns(2)
        if col_sim.button("✅ Confirmar", use_container_width=True, type="primary"):
            # Busca o sinal (+ ou -) da categoria
            sinal = st.session_state.df_cat.loc[st.session_state.df_cat["Categoria"] == resumo['categoria'], "Tipo"].values[0]
            
            # CALCULA O VENCIMENTO: Se for cartão, joga para a data da fatura. Se não, mantém a data escolhida.
            dt_efetiva = calcular_vencimento(resumo['data'], resumo['cartao'])
            
            payload = {
                "action": "insert", "table": "Lancamentos", "ID": str(uuid.uuid4()),
                "Data": resumo['data'].isoformat(), 
                "Categoria": resumo['categoria'], 
                "Cartao": resumo['cartao'], 
                "Tipo": sinal, 
                "Valor": float(resumo['valor']), 
                "Data_Efetiva": dt_efetiva.isoformat()
            }
            
            if sync_api(payload):
                st.success("Lançamento agendado com sucesso!")
                st.session_state.chat_step = 0
                st.session_state.chat_data = {}
                carregar_tudo()
                st.rerun()
        
        if col_nao.button("❌ Cancelar", use_container_width=True):
            st.session_state.chat_step = 0
            st.session_state.chat_data = {}
            st.rerun()    
    
# =========================================================
# 5. INTERFACE PRINCIPAL
# =========================================================

st.title("💰 Gestor Inteligente")

# Criando as abas para organizar o espaço
tab_chat, tab_extrato = st.tabs(["🤖 Assistente Virtual", "📊 Extrato e Resumos"])

with tab_chat:
    assistente_virtual()

with tab_extrato:
#Formulario lancamento manual
    with st.expander("➕ Incluir Manualmente", expanded=False):
        pass
    c1, c2, c3, c4 = st.columns([2,2,2,1])
    data_compra = c1.date_input("Data Compra", format="DD/MM/YYYY")
    
    lista_cat = st.session_state.df_cat["Categoria"].dropna().tolist()
    cat_sel = c2.selectbox("Categoria", lista_cat if lista_cat else ["Nenhuma"])
    
    lista_card = ["Não"] + st.session_state.df_card["Cartao"].dropna().tolist()
    card_sel = c3.selectbox("Cartão", lista_card)
    
    valor = c4.number_input("Valor", min_value=0.0, step=0.01, format="%.2f")

    if st.button("Confirmar Lançamento", use_container_width=True, type="primary"):
        if not lista_cat:
            st.error("Cadastre uma categoria primeiro.")
        else:
            sinal = st.session_state.df_cat.loc[st.session_state.df_cat["Categoria"] == cat_sel, "Tipo"].values[0]
            dt_efetiva = calcular_vencimento(data_compra, card_sel)
            payload = {
                "action": "insert", "table": "Lancamentos", "ID": str(uuid.uuid4()),
                "Data": data_compra.isoformat(), "Categoria": cat_sel, "Cartao": card_sel,
                "Tipo": sinal, "Valor": float(valor), "Data_Efetiva": dt_efetiva.isoformat()
            }
            if sync_api(payload):
                st.toast("Lançamento salvo!")
                carregar_tudo()
                st.rerun()
    
    # --- EXIBIÇÃO ---
df_render = get_df_render()

# Estilo Mobile
st.markdown("""
    <style>
        [data-testid="stMetricValue"] { font-size: 1.2rem !important; }
        [data-testid="stMetricLabel"] { font-size: 0.8rem !important; }
        .stExpander { border: 1px solid rgba(255,255,255,0.1); border-radius: 10px; margin-bottom: 10px; }
        hr { margin: 10px 0 !important; }
    </style>
""", unsafe_allow_html=True)

if not df_render.empty:
    # 1. TABELA PRINCIPAL
    with st.expander("📉 Extrato Projetado", expanded=True):
        def color_negative(row):
            return ['background-color: rgba(255, 75, 75, 0.1)' if row['Saldo_Acumulado'] < 0 else '' for _ in row]
        
        main_edit = st.data_editor(
            df_render.style.apply(color_negative, axis=1),
            column_config={
                "ID": None, "Tipo": None,
                "Data": st.column_config.DateColumn("Compra", format="DD/MM"),
                "Data_Efetiva": st.column_config.DateColumn("Vencimento", format="DD/MM/YY"),
                "Valor": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
                "Saldo_Acumulado": st.column_config.NumberColumn("Saldo", format="R$ %.2f")
            },
            disabled=df_render.columns, num_rows="dynamic", hide_index=True, 
            use_container_width=True, key="widget_main"
        )
        
        if st.session_state.widget_main["deleted_rows"]:
            for idx in st.session_state.widget_main["deleted_rows"]:
                id_a = df_render.iloc[idx]["ID"]
                sync_api({"action": "delete", "table": "Lancamentos", "ID": id_a})
            carregar_tudo()
            st.rerun()

    # 2. RESUMO SEMANAL COM SELETOR (MOBILE FRIENDLY)
    st.subheader("🗓️ Resumo Semanal")
    df_s = get_resumo_semanal()

    if not df_s.empty:
        # Criamos uma coluna temporária de rótulos para o seletor (Ex: "27/04 a 03/05")
        df_s['Label'] = df_s.apply(
            lambda x: f"{x['Semana'].strftime('%d/%m')} a {(x['Semana'] + datetime.timedelta(days=6)).strftime('%d/%m')}", 
            axis=1
        )

        # Seletor de Semana
        semana_label = st.selectbox(
            "Escolha a semana para análise:", 
            options=df_s['Label'].tolist(),
            label_visibility="collapsed" # Deixa o visual mais limpo no mobile
        )

        # Filtramos a linha correspondente à escolha
        row = df_s[df_s['Label'] == semana_label].iloc[0]

        # Exibição dos Cards de Métrica (Apenas a semana selecionada)
        with st.container():
            col1, col2, col3 = st.columns(3)
            col1.metric("Entradas", f"R$ {row['+']:,.2f}")
            col2.metric("Saídas", f"R$ {row['-']:,.2f}")
            # O delta mostra a variação (Var) em relação ao saldo acumulado (Acum)
            col3.metric("Saldo", f"R$ {row['Acum']:,.2f}", delta=f"R$ {row['Var']:,.2f}")
            
            st.markdown("---")
    else:
        st.info("Nenhuma projeção disponível para as próximas semanas.")

