import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
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
        # --- KPI's PREMIUM (Cards customizados em HTML) ---
        col1, col2, col3 = st.columns(3)
        
        col1.markdown(f"""
            <div style="background-color: rgba(128, 128, 128, 0.05); border: 1px solid rgba(128, 128, 128, 0.2); padding: 0.8rem 1rem; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); min-height: 115px;">
                <div style="font-weight: 600; color: gray; font-size: 0.95rem; padding-bottom: 0.25rem;">💰 Total em 12 Meses</div>
                <div style="font-size: 1.8rem; color: #00cc96;">{formata_br(total_12m)}</div>
            </div>
        """, unsafe_allow_html=True)
        
        col2.markdown(f"""
            <div style="background-color: rgba(128, 128, 128, 0.05); border: 1px solid rgba(128, 128, 128, 0.2); padding: 0.8rem 1rem; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); min-height: 115px;">
                <div style="font-weight: 600; color: gray; font-size: 0.95rem; padding-bottom: 0.25rem;">📅 Média Mensal</div>
                <div style="font-size: 1.8rem; color: #33b5e5;">{formata_br(media_mensal)}</div>
            </div>
        """, unsafe_allow_html=True)
        
        col3.markdown(f"""
            <div style="background-color: rgba(128, 128, 128, 0.05); border: 1px solid rgba(128, 128, 128, 0.2); padding: 0.8rem 1rem; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); min-height: 115px;">
                <div style="font-weight: 600; color: gray; font-size: 0.95rem; padding-bottom: 0.25rem;">🚀 Melhor Mês</div>
                <div style="font-size: 1.8rem; color: #ffbf00;">{formata_br(melhor_mes)}</div>
            </div>
        """, unsafe_allow_html=True)

        st.markdown("---")
        st.subheader("📈 Evolução da Renda Passiva (Últimos 12 Meses)")

        # --- Gráfico Premium Plotly (Substituindo st.bar_chart) ---
        fig = px.bar(
            resumo_mensal, 
            x='Mês', 
            y='Total Recebido',
            text='Total Recebido', # Exibe o valor em cima da barra
            color_discrete_sequence=['#00cc96']
        )
        
        fig.update_traces(
            texttemplate='R$ %{text:,.2f}', 
            textposition='outside',
            hovertemplate="<b>Mês:</b> %{x}<br><b>Recebido:</b> R$ %{y:,.2f}<extra></extra>"
        )
        
        fig.update_layout(
            height=380,
            margin=dict(l=0, r=0, t=30, b=0),
            xaxis_title="",
            yaxis_title="",
            xaxis=dict(showgrid=False),
            yaxis=dict(showgrid=True, gridcolor='rgba(128,128,128,0.2)', tickformat=",.2f"),
            plot_bgcolor='rgba(0,0,0,0)', # Fundo transparente
            paper_bgcolor='rgba(0,0,0,0)'
        )
        
        # Aumenta o eixo Y para o texto não ser cortado no topo
        if not resumo_mensal.empty:
            fig.update_yaxes(range=[0, resumo_mensal['Total Recebido'].max() * 1.15])
            
        st.plotly_chart(fig, use_container_width=True)

        # --- Tabela de Detalhamento ---
        st.markdown("### 📝 Quais ativos mais te pagaram?")
        
        col_tabela, col_vazia = st.columns([1.5, 1])
        
        with col_tabela:
            st.dataframe(
                resumo_ativo.style.format({
                    "Total 12 Meses / Cota": lambda x: formata_br(x),
                    "Total Recebido": lambda x: formata_br(x)
                })
                .bar(subset=['Total Recebido'], color='rgba(0, 204, 150, 0.4)', vmin=0),
                width='stretch', 
                hide_index=True
            )
        
        if ativos_com_erro:
            st.caption(f"⚠️ **Aviso:** Não foi possível encontrar dados de proventos para os seguintes ativos (eles podem ser de Renda Fixa ou não listados no Yahoo): {', '.join(ativos_com_erro)}")
