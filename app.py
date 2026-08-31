import streamlit as st
import pandas as pd
import time
from utils import ler_planilha, registrar_novo_usuario, db

# A configuração da página DEVE ser a primeira linha do app
st.set_page_config(page_title="App Investimentos v2.0", layout="wide", initial_sidebar_state="expanded")

# --- CSS INJETADO PARA SIMULAR ZOOM E COMPACTAR TUDO ---
st.markdown("""
    <style>
        /* 1. SIMULA O ZOOM (Reduz a fonte raiz de 16px para 14px) */
        html { font-size: 14px !important; }
        
        /* 2. COMPACTA O CORPO PRINCIPAL E TEXTOS */
        .block-container { padding-top: 1.5rem !important; padding-bottom: 1rem !important; }
        h1 { font-size: 1.7rem !important; padding-bottom: 0.3rem !important; }
        h2 { font-size: 1.4rem !important; }
        h3 { font-size: 1.15rem !important; }
        p, div, span, label { font-size: 0.95rem !important; }
        
        /* 3. ESPREME A BARRA LATERAL AO MÁXIMO E CORRIGE A LINHA */
        [data-testid="stSidebar"] { padding-top: 0.5rem !important; width: 17rem !important; min-width: 17rem !important; transition: background-color 0.3s ease; }
        [data-testid="stSidebarNav"] { padding-top: 0rem !important; padding-bottom: 0.5rem !important; }
        
        /* Reduz o espaço entre os botões de navegação */
        [data-testid="stSidebarNav"] ul { padding-top: 0rem !important; margin-bottom: 0rem !important; gap: 0px !important; }
        [data-testid="stSidebarNav"] a { padding-top: 0.15rem !important; padding-bottom: 0.15rem !important; }
        
        /* Ajusta o botão de Sair (Deixando apenas a linha nativa do Streamlit) */
        [data-testid="stSidebarUserContent"] { padding-top: 0.5rem !important; padding-bottom: 0.5rem !important; }
        [data-testid="stSidebarUserContent"] .stButton { margin-top: 0rem !important; }
        [data-testid="stSidebarUserContent"] .stButton button { min-height: 2rem !important; padding: 0rem !important; }
    </style>
""", unsafe_allow_html=True)

# Importando as telas
from menu import resumo, saldo, aportes, configuracao, lancamentos, perfil, backup, dividendos, imposto

# Variáveis Globais de Sessão e Defesas de Segurança
if 'logado' not in st.session_state:
    st.session_state.logado = False
    st.session_state.email = ""
    st.session_state.nome = ""
    st.session_state.codigo_recuperacao = None
    st.session_state.email_recuperacao = None
    st.session_state.last_login_time = 0.0
    st.session_state.last_email_time = 0.0
    st.session_state.email_autenticado = ""
    st.session_state.is_admin = False
    st.session_state.admin_email = ""


# ==========================================
# FUNÇÃO DA TELA DE ACESSO (LOGIN/CADASTRO)
# ==========================================
def tela_acesso():
    st.markdown("<h1 style='text-align: center;'>🔑 Acesso ao Sistema de Investimentos</h1>", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        tab_login, tab_cadastro, tab_esqueci = st.tabs(["Entrar", "Novo Cadastro", "Esqueci a Senha"])
        
        with tab_login:
            with st.form("form_login"):
                email_input = st.text_input("E-mail")
                senha_input = st.text_input("Senha", type="password")
                submit_login = st.form_submit_button("Entrar", use_container_width=True)
                
                if submit_login:
                    agora = time.time()
                    if agora - st.session_state.last_login_time < 3:
                        st.warning("⏳ Muitas tentativas seguidas. Aguarde alguns segundos para tentar novamente.")
                    else:
                        st.session_state.last_login_time = agora
                        email_formatado = email_input.strip().lower()
                        senha_formatada = senha_input.strip()
                        
                        usuario = db.usuarios.find_one({"_id": email_formatado, "senha": senha_formatada})
                        
                        if usuario:
                            status_usuario = str(usuario.get('status', 'Pendente')).strip().capitalize()
                            if status_usuario == 'Ativo':
                                st.session_state.logado = True
                                st.session_state.email = email_formatado
                                st.session_state.nome = usuario.get('nome', 'Usuário')
                                
                                st.session_state.email_autenticado = email_formatado
                                st.session_state.is_admin = usuario.get('admin', False)
                                st.session_state.admin_email = email_formatado if st.session_state.is_admin else ""
                                
                                st.cache_data.clear() 
                                st.rerun()
                            elif status_usuario == 'Pendente':
                                st.warning("⏳ Seu cadastro está em análise pelo administrador.")
                            else:
                                st.error("❌ Seu acesso foi revogado.")
                        else:
                            st.error("❌ Usuário ou senha incorretos.")

        with tab_cadastro:
            with st.form("form_cadastro", clear_on_submit=True):
                st.info("Preencha os dados abaixo. Seu acesso será liberado após a aprovação.")
                cad_nome = st.text_input("Seu Nome Completo")
                cad_email = st.text_input("Seu melhor E-mail")
                cad_senha = st.text_input("Crie uma Senha", type="password")
                
                if st.form_submit_button("Enviar Solicitação de Acesso", use_container_width=True):
                    if not cad_nome or not cad_email or not cad_senha:
                        st.warning("Preencha todos os campos.")
                    else:
                        with st.spinner("Registrando..."):
                            sucesso, msg = registrar_novo_usuario(cad_nome, cad_email, cad_senha)
                            if sucesso: st.success(msg)
                            else: st.error(msg)
                            
        with tab_esqueci:
            if not st.session_state.codigo_recuperacao:
                with st.form("form_pedir_codigo"):
                    st.info("Digite seu e-mail cadastrado. Enviaremos um código de 6 caracteres.")
                    esq_email = st.text_input("E-mail Cadastrado")
                    
                    if st.form_submit_button("Enviar Código", use_container_width=True):
                        agora = time.time()
                        tempo_restante = 60 - (agora - st.session_state.last_email_time)
                        
                        if tempo_restante > 0:
                            st.warning(f"⏳ Para sua segurança, aguarde {int(tempo_restante)} segundos antes de solicitar um novo código.")
                        elif not esq_email:
                            st.warning("Preencha o campo de e-mail.")
                        else:
                            st.session_state.last_email_time = agora
                            with st.spinner("Enviando e-mail..."):
                                from utils import verificar_email_cadastrado, enviar_codigo_email
                                import random, string
                                if verificar_email_cadastrado(esq_email):
                                    codigo_gerado = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
                                    sucesso, msg = enviar_codigo_email(esq_email, codigo_gerado)
                                    if sucesso:
                                        st.session_state.codigo_recuperacao = codigo_gerado
                                        st.session_state.email_recuperacao = esq_email.strip().lower()
                                        st.rerun()
                                    else: st.error(msg)
                                else: st.error("E-mail não encontrado.")
            else:
                with st.form("form_nova_senha"):
                    st.success(f"📧 O código foi enviado para **{st.session_state.email_recuperacao}**!")
                    codigo_digitado = st.text_input("Código de 6 caracteres")
                    st.markdown("---")
                    esq_nova_senha = st.text_input("Nova Senha", type="password")
                    esq_confirma_senha = st.text_input("Confirme a Nova Senha", type="password")
                    
                    c_btn1, c_btn2 = st.columns(2)
                    submit_validar = c_btn1.form_submit_button("Salvar Nova Senha", use_container_width=True)
                    if c_btn2.form_submit_button("Cancelar", use_container_width=True):
                        st.session_state.codigo_recuperacao = None
                        st.session_state.email_recuperacao = None
                        st.rerun()
                        
                    if submit_validar:
                        if codigo_digitado.strip().upper() != st.session_state.codigo_recuperacao:
                            st.error("❌ Código incorreto.")
                        elif esq_nova_senha != esq_confirma_senha:
                            st.error("❌ As senhas não conferem.")
                        else:
                            from utils import redefinir_senha_aprovada
                            sucesso, msg = redefinir_senha_aprovada(st.session_state.email_recuperacao, esq_nova_senha)
                            if sucesso:
                                st.success(msg)
                                st.session_state.codigo_recuperacao = None
                                st.session_state.email_recuperacao = None
                            else: st.error(msg)

# ==========================================
# FUNÇÃO DA TELA DE PAINEL ADMIN
# ==========================================
def painel_admin():
    st.title("🛠️ Painel do Administrador")
    
    tab_gestao, tab_personificar = st.tabs(["👥 Gestão de Acessos", "🎭 Visualizar Como (Personificar)"])
    
    with tab_gestao:
        st.markdown("Pesquise e gerencie a liberação ou revogação de acessos ao sistema.")
        usuarios = list(db.usuarios.find({}, {"_id": 1, "nome": 1, "status": 1}))
        
        if usuarios:
            df_users = pd.DataFrame(usuarios)
            df_users.rename(columns={"_id": "Email", "nome": "Nome", "status": "Status"}, inplace=True)
            
            # --- BLINDAGEM DO ERRO (NORMALIZAÇÃO DE TEXTO) ---
            if 'Status' not in df_users.columns:
                df_users['Status'] = 'Pendente'
            
            df_users['Status'] = df_users['Status'].fillna('Pendente').astype(str).str.strip().str.capitalize()
            df_users['Status'] = df_users['Status'].apply(lambda x: x if x in ["Ativo", "Revogado", "Pendente"] else "Pendente")
            
            # --- FERRAMENTAS DE PESQUISA E FILTRO ---
            col_busca, col_filtro = st.columns([2, 1])
            termo_busca = col_busca.text_input("🔎 Pesquisar por Nome ou E-mail:", "")
            filtro_status = col_filtro.selectbox("🏷️ Filtrar por Status:", ["Todos", "Pendente", "Ativo", "Revogado"])
            
            if filtro_status != "Todos":
                df_users = df_users[df_users['Status'] == filtro_status]
                
            if termo_busca:
                termo = termo_busca.lower()
                df_users = df_users[
                    df_users['Nome'].str.lower().str.contains(termo, na=False) | 
                    df_users['Email'].str.lower().str.contains(termo, na=False)
                ]
            
            st.markdown(f"**Resultados encontrados: {len(df_users)}**")
            st.markdown("---")
            
            # --- RENDERIZAÇÃO DA LISTA FILTRADA ---
            if df_users.empty:
                st.info("Nenhum usuário encontrado com os filtros atuais.")
            else:
                for _, row in df_users.iterrows():
                    c_info, c_status = st.columns([3, 2])
                    c_info.markdown(f"**{row['Nome']}** <br><span style='color:gray; font-size:0.85em;'>{row['Email']}</span>", unsafe_allow_html=True)
                    
                    if row['Email'] == st.session_state.get('admin_email'): 
                        c_status.info("Seu Usuário (Admin)")
                    else:
                        novo_status = c_status.selectbox(
                            "Status", 
                            options=["Ativo", "Revogado", "Pendente"], 
                            index=["Ativo", "Revogado", "Pendente"].index(row['Status']),
                            key=f"status_gestao_{row['Email']}",
                            label_visibility="collapsed"
                        )
                        
                        if novo_status != row['Status']:
                            db.usuarios.update_one({"_id": row['Email']}, {"$set": {"status": novo_status}})
                            st.toast(f"Status de {row['Nome']} alterado para {novo_status}!", icon="✅")
                            time.sleep(1) 
                            st.rerun()
                            
                    st.markdown("<hr style='margin: 0.5em 0; border: 0; border-top: 1px dashed #444;'>", unsafe_allow_html=True)
                    
    with tab_personificar:
        st.markdown("Selecione um usuário abaixo para visualizar o sistema como se fosse ele. Suas permissões de alteração continuarão bloqueadas.")
        st.info("💡 **Dica:** Clique na caixa e **comece a digitar** o nome ou e-mail.")
        
        from utils import listar_todos_usuarios
        lista_users = listar_todos_usuarios()
        
        if lista_users:
            opcoes = {u['email']: f"{u['nome']} ({u['email']})" for u in lista_users}
            emails_list = list(opcoes.keys())
            current_idx = emails_list.index(st.session_state.email) if st.session_state.email in emails_list else 0
            
            escolha = st.selectbox(
                "🔎 Buscar usuário para personificar:", 
                options=emails_list, 
                format_func=lambda x: opcoes[x],
                index=current_idx
            )
            
            if escolha != st.session_state.email:
                st.session_state.email = escolha
                st.session_state.nome = opcoes[escolha].split(' (')[0]
                st.rerun()


# ==========================================
# ROTEAMENTO NATIVO (ST.NAVIGATION)
# ==========================================
if not st.session_state.logado:
    st.markdown("""<style>[data-testid="collapsedControl"] {display: none;}</style>""", unsafe_allow_html=True)
    pg = st.navigation([st.Page(tela_acesso, title="Acesso Restrito", url_path="login")])
    pg.run()
    
else:
    if not st.session_state.get('is_admin', False):
        st.session_state.email = st.session_state.get('email_autenticado', st.session_state.email)

    # =========================================================
    # INJEÇÃO DINÂMICA DE ALERTA: MODO ADMIN / PERSONIFICAÇÃO
    # =========================================================
    if st.session_state.get('is_admin', False) and st.session_state.email != st.session_state.get('admin_email', ''):
        # Apenas muda a cor e a borda. Sem truques de altura ou teleporte!
        st.markdown("""
            <style>
                [data-testid="stSidebar"] {
                    background-color: #3b0a0a !important;
                    border-right: 2px solid #ff4444 !important;
                }
            </style>
        """, unsafe_allow_html=True)

    menu_usuario = [st.Page(perfil.render, title="Meu Perfil", icon="👤", url_path="perfil")]
    if st.session_state.get('is_admin', False):
        menu_usuario.append(st.Page(painel_admin, title="Painel Admin", icon="🛠️", url_path="admin"))

    pg = st.navigation({
        f"Usuário: {st.session_state.nome}": menu_usuario,
        "Visão Geral": [
            st.Page(resumo.render, title="Resumo da Aplicação", icon="💼", default=True, url_path="resumo"),
            st.Page(saldo.render, title="Evolução do Saldo", icon="📈", url_path="saldo"),
            st.Page(dividendos.render, title="Dashboard de Dividendos", icon="💸")
        ],
        "Operacional": [
            st.Page(aportes.render, title="Guia de Aportes", icon="🎯", url_path="aportes"),
            st.Page(lancamentos.render, title="Central de Lançamentos", icon="📝", url_path="lancamentos"),
            st.Page(configuracao.render, title="Configuração da Carteira", icon="⚙️", url_path="configuracao"),
            st.Page(imposto.render, title="Radar de Imposto", icon="🦁", url_path="imposto"),
            st.Page(backup.render, title="Importar/Exportar Dados", icon="💾", url_path="backup")
        ]
    })
    
    pg.run()

    # Aviso Renderizado Limpo e Estável (Exclusivo da Personificação)
    if st.session_state.get('is_admin', False) and st.session_state.email != st.session_state.get('admin_email', ''):
        st.sidebar.markdown(
            f"""
            <div style='background-color: #ff4444; color: white; padding: 0.8rem; border-radius: 5px; text-align: center; margin-bottom: 0.8rem;'>
                ⚠️ <b>MODO ADMIN</b><br>Vendo como: <b>{st.session_state.nome}</b>
            </div>
            """, 
            unsafe_allow_html=True
        )

    if st.sidebar.button("🚪 Sair do App", use_container_width=True):
        st.session_state.clear()
        st.rerun()
