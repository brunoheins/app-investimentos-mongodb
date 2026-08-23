import streamlit as st
from utils import atualizar_dados_perfil

def render():
    st.title("👤 Meu Perfil")
    st.markdown("Atualize seus dados cadastrais. Para garantir a segurança dos seus investimentos, **o e-mail de acesso não pode ser alterado.**")

    with st.form("form_perfil"):
        c1, c2 = st.columns(2)
        novo_nome = c1.text_input("Seu Nome", value=st.session_state.nome)
        
        # Mostra o email desativado só para visualização
        c2.text_input("E-mail (Não alterável)", value=st.session_state.email, disabled=True)
        
        st.markdown("---")
        st.subheader("Alterar Senha")
        st.info("Deixe em branco se não quiser alterar a sua senha atual.")
        
        c3, c4 = st.columns(2)
        nova_senha = c3.text_input("Nova Senha", type="password")
        confirma_senha = c4.text_input("Confirme a Nova Senha", type="password")
        
        submit = st.form_submit_button("💾 Salvar Alterações", use_container_width=True, type="primary")
        
        if submit:
            if nova_senha or confirma_senha:
                if nova_senha != confirma_senha:
                    st.error("⚠️ As senhas não conferem. Digite senhas idênticas.")
                    return
            
            # Chama o motor para atualizar no Google Sheets
            sucesso, msg = atualizar_dados_perfil(st.session_state.email, novo_nome, nova_senha)
            
            if sucesso:
                st.session_state.nome = novo_nome # Atualiza o nome ao vivo na barra lateral
                st.success(msg)
            else:
                st.error(msg)
