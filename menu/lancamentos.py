import streamlit as st
import pandas as pd
import time
from datetime import datetime
from utils import registrar_deposito, registrar_compra, obter_ativos_por_categoria, formata_br, ler_planilha, atualizar_historico_usuario
from menu.aportes import motor_de_aportes

# ==========================================
# ARMADURA NUMÉRICA E FORMATADORES PT-BR
# ==========================================
def limpa_numero_seguro(val):
    """Lê com segurança números americanos ou strings brasileiras (ex: 1.234,56 ou 0,3065) e transforma em float puro"""
    if pd.isna(val) or str(val).strip() == '': return 0.0
    if isinstance(val, (int, float)): return float(val)
    
    v = str(val).strip().replace('R$', '').replace(' ', '')
    if '.' in v and ',' in v:
        v = v.replace('.', '').replace(',', '.')
    elif ',' in v:
        v = v.replace(',', '.')
    
    try:
        return float(v)
    except:
        return 0.0

def formata_qtd(val):
    """Corta os zeros em excesso no final de frações e coloca vírgula"""
    s = f"{val:.8f}"
    if '.' in s: s = s.rstrip('0').rstrip('.')
    if not s: s = '0'
    return s.replace('.', ',')

def formata_preco(val):
    """Sempre 4 casas decimais com vírgula"""
    return f"{val:.4f}".replace('.', ',')

def formata_valor(val):
    """Sempre 2 casas decimais com vírgula"""
    return f"{val:.2f}".replace('.', ',')


def render():
    st.title("📝 Central de Lançamentos")
    st.markdown("Registre a movimentação de dinheiro na corretora e as suas ordens de compra e venda.")

    if 'dicas_salvas' not in st.session_state:
        st.session_state.dicas_salvas = None

    if 'aba_lancamento' not in st.session_state:
        st.session_state.aba_lancamento = "Depósitos"

    def mudar_aba_lancamento(nova_aba):
        st.session_state.aba_lancamento = nova_aba

    st.markdown("<br>", unsafe_allow_html=True)
    c_aba1, c_aba2 = st.columns(2)
    
    c_aba1.button(
        "💰 1. Aporte / Saque de Caixa", 
        width='stretch', 
        on_click=mudar_aba_lancamento, args=("Depósitos",),
        type="primary" if st.session_state.aba_lancamento == "Depósitos" else "secondary"
    )

    c_aba2.button(
        "🛒 2. Lançamento de Ativos", 
        width='stretch', 
        on_click=mudar_aba_lancamento, args=("Compras",),
        type="primary" if st.session_state.aba_lancamento == "Compras" else "secondary"
    )
    
    st.markdown("---")

    # ==========================================
    # 1. DEPÓSITO / SAQUE DE DINHEIRO
    # ==========================================
    if st.session_state.aba_lancamento == "Depósitos":
        st.subheader("Registrar Movimentação de Caixa")
        st.info("Lance aqui o dinheiro que entrou (Aporte) ou que você retirou (Saque) da corretora.")
        
        tipo_mov_caixa = st.radio(
            "Tipo de Movimentação:",
            options=["Aporte (Entrada 💰)", "Saque (Saída 💸)"],
            horizontal=True
        )

        with st.form("form_deposito", clear_on_submit=True):
            col1, col2 = st.columns(2)
            data_deposito = col1.date_input("Data da Operação", value=datetime.today(), format="DD/MM/YYYY")
            valor_deposito = col2.number_input("Valor (R$)", min_value=0.00, value=1000.00, step=100.0, format="%.2f")
            
            submit = st.form_submit_button("💾 Salvar Movimentação", width='stretch', type="primary")
            if submit:
                data_str = data_deposito.strftime("%d/%m/%Y")
                
                valor_final = valor_deposito if "Aporte" in tipo_mov_caixa else -valor_deposito
                
                if registrar_deposito(st.session_state.email, data_str, valor_final):
                    st.session_state.dicas_salvas = None 
                    
                    acao_texto = "Aporte" if "Aporte" in tipo_mov_caixa else "Saque"
                    st.success(f"✅ {acao_texto} de R$ {formata_valor(abs(valor_deposito))} em {data_str} salvo com sucesso!")
                    
                    time.sleep(1.5)
                    st.rerun()

    # ==========================================
    # 2. COMPRA / VENDA / EVENTOS CORPORATIVOS
    # ==========================================
    elif st.session_state.aba_lancamento == "Compras":
        st.subheader("Registrar Movimentação de Ativos")
        st.info("O sistema garante que você só registre ativos que pertençam à categoria correta.")
        
        painel_aberto = True if st.session_state.dicas_salvas else False
        
        with st.expander("💡 Precisa de ajuda? Consultar Guia de Aportes Rápido", expanded=painel_aberto):
            st.markdown("Descubra qual é o ativo mais atrasado na sua carteira neste momento:")
            c_val, c_num, c_btn = st.columns([2, 2, 1.2])
            val_simul = c_val.number_input("💵 Qual valor você tem para investir?", min_value=0.00, value=1000.00, step=100.00)
            
            opcao_est = c_num.selectbox("Estratégia do Aporte:", ["Dividir pelo Objetivo", "Aporte Integral (1 Ativo)"])
            dividir = "Dividir" in opcao_est
            
            if c_btn.button("Gerar Dica Rápida", width='stretch', type="primary"):
                with st.spinner("Calculando defasagem..."):
                    compras, resto, df_macro, erro = motor_de_aportes(st.session_state.email, val_simul, dividir)
                    st.session_state.dicas_salvas = {'compras': compras, 'resto': resto, 'erro': erro}
            
            if st.session_state.dicas_salvas:
                st.markdown("---")
                d = st.session_state.dicas_salvas
                if d['erro']:
                    st.error(d['erro'])
                elif not d['compras']:
                    st.warning("Nenhuma sugestão gerada.")
                else:
                    for c in d['compras']:
                        st.success(f"🎯 **Sugerido:** Comprar **{c['Ativo']}** ({c['Categoria']}) — Alocar **{formata_br(c['Valor'])}** (Aprox. {c['Qtd_Sugerida']})")
                    if d['resto'] > 0.05:
                        st.caption(f"⚠️ O sistema recomendou segurar **{formata_br(d['resto'])}** na conta para não ultrapassar suas metas.")
                
                if st.button("🧹 Limpar Dicas"):
                    st.session_state.dicas_salvas = None
                    st.rerun()
        
        st.markdown("<br>", unsafe_allow_html=True)

        cat_ativos_dict = obter_ativos_por_categoria(st.session_state.email)
        categorias_disp = list(cat_ativos_dict.keys())

        tipo_op = st.radio(
            "Tipo de Movimentação:",
            options=["Entrada (Compra / Bonificação 📈)", "Saída (Venda / Grupamento 📉)"],
            horizontal=True
        )
        
        c_cat, c_atv = st.columns(2)
        cat_compra = c_cat.selectbox("1. Escolha a Categoria", categorias_disp)
        
        ativos_da_categoria = cat_ativos_dict.get(cat_compra, [])
        
        if not ativos_da_categoria:
            c_atv.error(f"Nenhum ativo preenchido para '{cat_compra}' na aba Cotacao.")
            ativo_compra = None
        else:
            ativo_compra = c_atv.selectbox("2. Escolha o Ativo (Digite para buscar)", options=ativos_da_categoria)
            
            st.markdown("---")
            
            is_exterior = cat_compra in ["Stocks", "REITs", "ETFs"]
            
            if is_exterior:
                st.markdown("**🇺🇸 Lançamento Internacional**")
                c1, c2, c3, c4 = st.columns(4)
                data_compra = c1.date_input("Data da Operação", value=datetime.today(), format="DD/MM/YYYY")
                qtd_compra = c2.number_input("Quantidade (Frac.)", min_value=0.00000001, step=1.0, format="%.8f")
                preco_usd = c3.number_input("Preço Unit. (US$)", min_value=0.00, step=1.0, format="%.2f")
                valor_total_brl = c4.number_input("Total Debitado (R$)", min_value=0.00, step=10.0, format="%.2f", help="O valor exato em Reais que saiu da sua conta.")
                
                observacao_user = st.text_input("Anotações (Opcional)", placeholder="Ex: Remessa Nomad, Dividendo reinvestido...")
                
                total_usd = qtd_compra * preco_usd
                dolar_efetivo = (valor_total_brl / total_usd) if total_usd > 0 else 0.0
                
                if total_usd > 0 and valor_total_brl > 0:
                    st.caption(f"ℹ️ **Resumo da Ordem:** Total em Dólar: **US$ {formata_valor(total_usd)}** | Custo do Dólar (com taxas): **R$ {formata_preco(dolar_efetivo)}**")
                
                preco_unitario_brl = (valor_total_brl / qtd_compra) if qtd_compra > 0 else 0.0
                obs_final = f"[US$ {formata_valor(preco_usd)} | Câmbio: R$ {formata_preco(dolar_efetivo)}] {observacao_user}".strip()

            else:
                st.markdown("**🇧🇷 Lançamento Nacional**")
                c1, c2, c3 = st.columns(3)
                data_compra = c1.date_input("Data da Operação", value=datetime.today(), format="DD/MM/YYYY")
                qtd_compra = c2.number_input("Quantidade (Cotas)", min_value=0.0001, step=1.0, format="%.4f")
                preco_unitario_brl = c3.number_input("Preço Unitário (R$)", min_value=0.00, step=1.0, format="%.2f")
                
                observacao_user = st.text_input("Anotações (Opcional)", placeholder="Ex: Subscrição, Bonificação...")
                
                valor_total_brl = qtd_compra * preco_unitario_brl
                obs_final = observacao_user

            st.info("💡 **Dica corporativa:** Para Bonificação ou Grupamento, lance o valor como **R$ 0,00** para não alterar o capital investido.")

            if st.button("💾 Registrar Operação", width='stretch', type="primary"):
                data_str = data_compra.strftime("%d/%m/%Y")
                qtd_final = qtd_compra if "Entrada" in tipo_op else -qtd_compra
                
                if registrar_compra(st.session_state.email, data_str, cat_compra, ativo_compra, qtd_final, preco_unitario_brl, obs_final):
                    st.session_state.dicas_salvas = None 
                    
                    if preco_unitario_brl == 0:
                        st.success(f"✅ Evento de {formata_qtd(qtd_compra)} cotas salvo com sucesso para {ativo_compra}!")
                    else:
                        acao = "Compra" if "Entrada" in tipo_op else "Venda"
                        st.success(f"✅ {acao} de {ativo_compra} salva! Total da Ordem: R$ {formata_valor(valor_total_brl)}")
                    
                    time.sleep(2)
                    st.rerun()

    # ==========================================
    # AUDITORIA E EDIÇÃO DE LANÇAMENTOS
    # ==========================================
    st.markdown("---")
    
    with st.expander("🔍 Histórico, Edição e Auditoria de Lançamentos"):
        st.markdown("Consulte seu histórico abaixo. Para **editar**, dê um duplo clique na célula. Para **excluir**, clique na linha e aperte a tecla `Delete`. Depois, clique no botão de salvar.")
        
        col_hist1, col_hist2 = st.columns(2)
        
        with col_hist1:
            st.subheader("💰 Editar Aportes / Saques")
            df_depositos = ler_planilha("Depositos") 
            if not df_depositos.empty and 'Email' in df_depositos.columns:
                df_depositos['Email'] = df_depositos['Email'].astype(str).str.strip().str.lower()
                meus_depositos = df_depositos[df_depositos['Email'] == st.session_state.email].copy()
                
                if not meus_depositos.empty:
                    meus_depositos = meus_depositos.drop(columns=['Email'])
                    
                    # Converte para string com vírgula para visualização perfeita
                    if 'Valor' in meus_depositos.columns:
                        meus_depositos['Valor'] = meus_depositos['Valor'].apply(limpa_numero_seguro).apply(formata_valor)
                    
                    df_depositos_editado = st.data_editor(
                        meus_depositos, 
                        num_rows="dynamic",
                        width='stretch', 
                        hide_index=True,
                        key="editor_depositos",
                        column_config={
                            "Valor": st.column_config.TextColumn("Valor (R$)") # Força a ser texto para o Streamlit não quebrar
                        }
                    )
                    
                    if st.button("💾 Salvar Alterações de Caixa", width='stretch', type="primary"):
                        with st.spinner("Atualizando caixa..."):
                            df_save_depositos = df_depositos_editado.copy()
                            # Converte a string pt-br editada de volta para o padrão salvo no Google Sheets
                            if 'Valor' in df_save_depositos.columns:
                                df_save_depositos['Valor'] = df_save_depositos['Valor'].apply(limpa_numero_seguro).apply(formata_valor)
                                
                            if atualizar_historico_usuario(st.session_state.email, "Depositos", df_save_depositos):
                                st.success("Caixa atualizado com sucesso!")
                                time.sleep(1.5)
                                st.rerun()
                else:
                    st.info("Nenhum aporte registrado.")
            else:
                st.info("Banco de dados vazio.")

        with col_hist2:
            st.subheader("🛒 Editar Movimentações")
            df_compras = ler_planilha("Investimentos") 
            if not df_compras.empty and 'Email' in df_compras.columns:
                df_compras['Email'] = df_compras['Email'].astype(str).str.strip().str.lower()
                minhas_compras = df_compras[df_compras['Email'] == st.session_state.email].copy()
                
                if not minhas_compras.empty:
                    minhas_compras = minhas_compras.drop(columns=['Email'])
                    
                    col_preco = next((c for c in minhas_compras.columns if 'prec' in str(c).lower() or 'custo' in str(c).lower()), None)
                    col_qtd = 'Quantidade' if 'Quantidade' in minhas_compras.columns else None

                    # Transforma para string visual brasileira
                    if col_preco:
                        minhas_compras[col_preco] = minhas_compras[col_preco].apply(limpa_numero_seguro).apply(formata_preco)
                    if col_qtd:
                        minhas_compras[col_qtd] = minhas_compras[col_qtd].apply(limpa_numero_seguro).apply(formata_qtd)
                    
                    # Força a coluna a ser texto para blindar a exibição da vírgula
                    colunas_format = {}
                    if col_preco:
                        colunas_format[col_preco] = st.column_config.TextColumn(col_preco)
                    if col_qtd:
                        colunas_format[col_qtd] = st.column_config.TextColumn(col_qtd)

                    df_compras_editado = st.data_editor(
                        minhas_compras, 
                        num_rows="dynamic", 
                        width='stretch', 
                        hide_index=True,
                        key="editor_compras",
                        column_config=colunas_format
                    )
                    
                    if st.button("💾 Salvar Alterações de Ativos", width='stretch', type="primary"):
                        with st.spinner("Atualizando carteira..."):
                            df_save_compras = df_compras_editado.copy()
                            
                            # Limpa os números digitados na tela e formata para o banco de dados
                            if col_preco in df_save_compras.columns:
                                df_save_compras[col_preco] = df_save_compras[col_preco].apply(limpa_numero_seguro).apply(formata_preco)
                            if col_qtd in df_save_compras.columns:
                                df_save_compras[col_qtd] = df_save_compras[col_qtd].apply(limpa_numero_seguro).apply(formata_qtd)
                                
                            if atualizar_historico_usuario(st.session_state.email, "Investimentos", df_save_compras):
                                st.success("Movimentações atualizadas com sucesso!")
                                time.sleep(1.5)
                                st.rerun()
                else:
                    st.info("Nenhuma movimentação registrada.")
            else:
                st.info("Banco de dados de movimentações vazio.")
