import streamlit as st
import pandas as pd
from utils import ler_planilha, registrar_novo_usuario

# A configuração da página DEVE ser a primeira linha do app
st.set_page_config(page_title="App Investimentos v2.0", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
        .block-container { padding-top: 2rem; padding-bottom: 2rem; }
        h1 { font-size: 1.8rem !important; padding-bottom: 0.5rem !important; }
        h2 { font-size: 1.5rem !important; }
        h3 { font-size: 1.2rem !important; }
        p { font-size: 0.95rem !important; }
    </style>
""", unsafe_allow_html=True)

# Importando as telas
from menu import resumo, saldo, aportes, configuracao, lancamentos, perfil, backup, dividendos, imposto

# Variáveis Globais de Sessão
if 'logado' not in st.session_state:
    st.session_state.logado = False
    st.session_state.email = ""
    st.session_state.nome = ""
    st.session_state.codigo_recuperacao = None
    st.session_state.email_recuperacao = None


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
                    df_usuarios = ler_planilha("Usuarios")
                    if not df_usuarios.empty:
                        df_usuarios['Email'] = df_usuarios['Email'].astype(str).str.strip().str.lower()
                        df_usuarios['Senha'] = df_usuarios['Senha'].astype(str).str.strip()
                        
                        usuario = df_usuarios[(df_usuarios['Email'] == email_input.strip().lower()) & (df_usuarios['Senha'] == senha_input.strip())]
                        
                        if not usuario.empty:
                            status_usuario = str(usuario.iloc[0]['Status']).strip()
                            if status_usuario == 'Ativo':
                                st.session_state.logado = True
                                st.session_state.email = email_input.strip().lower()
                                st.session_state.nome = usuario.iloc[0]['Nome']
                                st.rerun()
                            elif status_usuario == 'Pendente':
                                st.warning("⏳ Seu cadastro está em análise pelo administrador.")
                            else:
                                st.error("❌ Seu acesso foi revogado.")
                        else:
                            st.error("Usuário ou senha incorretos.")
                    else:
                        st.error("Erro ao acessar base de dados.")

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
                        if not esq_email:
                            st.warning("Preencha o campo de e-mail.")
                        else:
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
# ROTEAMENTO NATIVO (ST.NAVIGATION)
# ==========================================
if not st.session_state.logado:
    # Oculta o menu lateral enquanto não estiver logado
    st.markdown("""<style>[data-testid="collapsedControl"] {display: none;}</style>""", unsafe_allow_html=True)
    
    # Define o login como a única página existente
    pg = st.navigation([st.Page(tela_acesso, title="Acesso Restrito", url_path="login")])
    pg.run()
    
else:
    # 1. Mapeamento nativo ajustado para o fluxo Operacional
    pg = st.navigation({
        f"Usuário: {st.session_state.nome}": [
            st.Page(perfil.render, title="Meu Perfil", icon="👤", url_path="perfil")
        ],
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
    
    # 2. Executa a construção do menu lateral primeiro
    pg.run()

    # 3. Adiciona o botão de logout logo abaixo do menu nativo com a correção (if em vez de callback)
    st.sidebar.markdown("<br><br>", unsafe_allow_html=True) # Espaçamento para o botão não ficar colado
    if st.sidebar.button("🚪 Sair do App", use_container_width=True):
        st.session_state.clear()
        st.rerun()
