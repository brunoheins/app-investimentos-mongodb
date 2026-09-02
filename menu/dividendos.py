import streamlit as st
import pandas as pd
import yfinance as yf
from dateutil.relativedelta import relativedelta
import re
from utils import ler_planilha, extrair_numero_br, formata_br, buscar_historico_dividendos

def render():
    st.title("💸 Dashboard de Dividendos")
    st.markdown("Acompanhe os dividendos **reais** que caíram na sua conta nos últimos 12 meses, calculados de acordo com a data exata das suas compras.")

    email_usuario = st.session_state.email.strip().lower()
    sucesso_carregamento = False

    # ==========================================
    # 1. FASE DE EXTRAÇÃO E PROCESSAMENTO
    # ==========================================
    with st.status("Sincronizando histórico de proventos...", expanded=True) as status:
        st.write("Lendo carteira atual de investimentos...")
        df_invest = ler_planilha("Investimentos")
        
        # Limpa os cabeçalhos para evitar espaços ocultos que causam KeyError
        if not df_invest.empty:
            df_invest.columns = [str(c).strip() for c in df_invest.columns]

        if df_invest.empty or 'Email' not in df_invest.columns:
            status.update(label="Nenhum dado encontrado.", state="complete", expanded=False)
            st.info("Você ainda não possui investimentos cadastrados para calcular dividendos.")
            return

        df_invest['Email'] = df_invest['Email'].astype(str).str.strip().str.lower()
        meus_invest = df_invest[df_invest['Email'] == email_usuario].copy()

        if meus_invest.empty:
            status.update(label="Nenhum dado encontrado.", state="complete", expanded=False)
            st.info("Você ainda não possui investimentos cadastrados para calcular dividendos.")
            return

        # Prepara os dados (Mantemos as linhas individuais para cruzar com as datas)
        meus_invest['Ativo'] = meus_invest['Ativo'].astype(str).str.strip().str.upper()
        meus_invest['Quantidade'] = meus_invest['Quantidade'].apply(extrair_numero_br)

        st.write("Buscando histórico na B3 e no Exterior (isso pode levar alguns segundos)...")
        # Busca os dividendos usando a função com Cache
        df_divs, ativos_com_erro = buscar_historico_dividendos(meus_invest)

        if df_divs.empty:
            status.update(label="Nenhum pagamento localizado.", state="complete", expanded=False)
            st.warning("Nenhum pagamento de dividendos foi encontrado para a sua carteira (considerando as datas em que você possuía os ativos) nos últimos 12 meses.")
            return

        st.write("Consolidando métricas e agrupando por mês...")
        # Processar os dados para o Gráfico
        resumo_mensal = df_divs.groupby('Mês_Sort')['Total Recebido'].sum().reset_index()
        # Formata o mês para ficar bonito no gráfico (ex: 08/2023)
        resumo_mensal['Mês'] = pd.to_datetime(resumo_mensal['Mês_Sort']).dt.strftime('%m/%Y')
        
        total_12m = resumo_mensal['Total Recebido'].sum()
        media_mensal = total_12m / len(resumo_mensal) if not resumo_mensal.empty else 0
        melhor_mes = resumo_mensal['Total Recebido'].max()
        
        # Agrupa os dados por Ativo
        resumo_ativo = df_divs.groupby('Ativo').agg({
            'Valor por Cota': 'sum',
            'Total Recebido': 'sum'
        }).reset_index().sort_values('Total Recebido', ascending=False)
        
        resumo_ativo.rename(columns={'Valor por Cota': 'Total 12 Meses / Cota'}, inplace=True)

        sucesso_carregamento = True
        status.update(label="Histórico de dividendos processado com sucesso!", state="complete", expanded=False)


    # ==========================================
    # 2. RENDERIZAÇÃO DA INTERFACE (MÉTRICAS E GRÁFICOS)
    # ==========================================
    if sucesso_carregamento:
        # --- KPI's (Destaques no topo) ---
        col1, col2, col3 = st.columns(3)
        col1.metric("💰 Total em 12 Meses", formata_br(total_12m))
        col2.metric("📅 Média Mensal", formata_br(media_mensal))
        col3.metric("🚀 Melhor Mês", formata_br(melhor_mes))

        st.markdown("---")
        st.subheader("📈 Evolução da Renda Passiva (Últimos 12 Meses)")

        # Gráfico de Barras Nativo do Streamlit
        st.bar_chart(resumo_mensal.set_index('Mês')['Total Recebido'], color="#00C851")

        # --- Tabela de Detalhamento ---
        st.markdown("### 📝 Quais ativos mais te pagaram?")
        
        col_tabela, col_vazia = st.columns([1.5, 1])
        
        with col_tabela:
            st.dataframe(
                resumo_ativo.style.format({
                    "Total 12 Meses / Cota": lambda x: formata_br(x),
                    "Total Recebido": lambda x: formata_br(x)
                })
                .bar(subset=['Total Recebido'], color='#00C851', vmin=0),
                use_container_width=True, 
                hide_index=True
            )
        
        if ativos_com_erro:
            st.caption(f"⚠️ **Aviso:** Não foi possível encontrar dados de proventos para os seguintes ativos (eles podem ser de Renda Fixa ou não listados no Yahoo): {', '.join(ativos_com_erro)}")
