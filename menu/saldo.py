import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
import yfinance as yf
from utils import ler_planilha, obter_cotacoes, extrair_numero_br, formata_br, obter_historico_benchmarks

# ==========================================
# RENDERIZAÇÃO DA PÁGINA
# ==========================================
def render():
    st.title("📈 Evolução Real do Patrimônio")
    st.markdown("Compare o **Dinheiro Líquido do Bolso** (Aportes menos Saques) com o **Patrimônio Real** (Ativos + Aportes Pendentes).")

    sucesso_carregamento = False

    # ==========================================
    # 1. FASE DE EXTRAÇÃO E PROCESSAMENTO
    # ==========================================
    with st.status("Construindo linha do tempo da sua carteira...", expanded=True) as status:
        hoje = pd.Timestamp.today()
        
        st.write("Lendo movimentações de caixa...")
        df_dep = ler_planilha("Depositos")
        if not df_dep.empty and 'Email' in df_dep.columns:
            df_dep['Email'] = df_dep['Email'].astype(str).str.strip().str.lower()
            df_user_dep = df_dep[df_dep['Email'] == st.session_state.email].copy()
            
            if not df_user_dep.empty:
                df_user_dep['Data'] = pd.to_datetime(df_user_dep['Data'], dayfirst=True, errors='coerce')
                df_user_dep['Data'] = df_user_dep['Data'].fillna(hoje)
                df_user_dep.loc[df_user_dep['Data'] > hoje, 'Data'] = hoje
                df_user_dep['Valor'] = df_user_dep['Valor'].apply(extrair_numero_br)
                df_user_dep['MesAno'] = df_user_dep['Data'].dt.strftime('%Y-%m')
                df_dep_agrupado = df_user_dep.groupby('MesAno')['Valor'].sum().reset_index()
            else:
                df_dep_agrupado = pd.DataFrame(columns=['MesAno', 'Valor'])
        else:
            df_dep_agrupado = pd.DataFrame(columns=['MesAno', 'Valor'])

        st.write("Lendo histórico de compras e vendas...")
        df_invest = ler_planilha("Investimentos")
        if not df_invest.empty and 'Email' in df_invest.columns:
            df_invest['Email'] = df_invest['Email'].astype(str).str.strip().str.lower()
            df_user_inv = df_invest[df_invest['Email'] == st.session_state.email].copy()
            
            if not df_user_inv.empty:
                if 'DataCompra' in df_user_inv.columns:
                    df_user_inv['DataCompra'] = pd.to_datetime(df_user_inv['DataCompra'], dayfirst=True, errors='coerce')
                    df_user_inv['DataCompra'] = df_user_inv['DataCompra'].fillna(hoje)
                else:
                    df_user_inv['DataCompra'] = hoje
                
                df_user_inv.loc[df_user_inv['DataCompra'] > hoje, 'DataCompra'] = hoje
                df_user_inv['Ativo'] = df_user_inv['Ativo'].astype(str).str.strip().str.upper()
                df_user_inv['Quantidade'] = df_user_inv['Quantidade'].apply(extrair_numero_br)
                
                if 'PrecoMedio' in df_user_inv.columns:
                    df_user_inv['PrecoCusto'] = df_user_inv['PrecoMedio'].apply(extrair_numero_br)
                elif 'Preco' in df_user_inv.columns:
                    df_user_inv['PrecoCusto'] = df_user_inv['Preco'].apply(extrair_numero_br)
                else:
                    df_user_inv['PrecoCusto'] = 0.0
                
                st.write("Buscando cotações atualizadas...")
                cotacoes_dict = obter_cotacoes(st.session_state.email)
                df_user_inv['PrecoLive'] = df_user_inv['Ativo'].map(cotacoes_dict).fillna(0.0)
                
                df_user_inv['TemCotacao'] = df_user_inv['PrecoLive'] > 0
                df_user_inv['TotalCusto'] = df_user_inv['Quantidade'] * df_user_inv['PrecoCusto']
                
                df_user_inv['MesAno'] = df_user_inv['DataCompra'].dt.strftime('%Y-%m')
                df_inv_agrupado = df_user_inv.groupby(['MesAno', 'Ativo']).agg({
                    'Quantidade': 'sum',
                    'TotalCusto': 'sum',
                    'PrecoLive': 'first',
                    'TemCotacao': 'first'
                }).reset_index()
            else:
                df_inv_agrupado = pd.DataFrame(columns=['MesAno', 'Ativo', 'Quantidade', 'TotalCusto', 'PrecoLive', 'TemCotacao'])
        else:
            df_inv_agrupado = pd.DataFrame(columns=['MesAno', 'Ativo', 'Quantidade', 'TotalCusto', 'PrecoLive', 'TemCotacao'])

        if df_dep_agrupado.empty and df_inv_agrupado.empty:
            status.update(label="Nenhum dado encontrado.", state="complete", expanded=False)
            st.info("Registre aportes e movimentações na aba '📝 Lançamentos' para ver a evolução do seu patrimônio.")
            return

        st.write("Calculando histórico de Benchmarks (CDI, IBOV, etc.)...")
        meses_dep = df_dep_agrupado['MesAno'].unique().tolist() if not df_dep_agrupado.empty else []
        meses_inv = df_inv_agrupado['MesAno'].unique().tolist() if not df_inv_agrupado.empty else []
        
        todos_meses = sorted(list(set(meses_dep + meses_inv)))
        mes_atual = hoje.strftime('%Y-%m')
        
        if todos_meses:
            mes_inicial = min(todos_meses[0], mes_atual)
        else:
            mes_inicial = mes_atual
            
        mes_final = mes_atual
            
        range_meses = pd.date_range(start=f"{mes_inicial}-01", end=f"{mes_final}-01", freq='MS').strftime('%Y-%m').tolist()
        df_timeline = pd.DataFrame({'MesAno': range_meses})
        
        dict_benchmarks = obter_historico_benchmarks(mes_inicial, mes_final)
        
        saldo_cdi = 0.0
        saldo_ibov = 0.0
        saldo_sp500 = 0.0
        saldo_ipca = 0.0
        
        linha_aportes = []
        linha_cdi = []
        linha_ibov = []
        linha_sp500 = []
        linha_ipca = []
        
        total_aportado = 0.0
        
        for mes in range_meses:
            aporte_mes = df_dep_agrupado.loc[df_dep_agrupado['MesAno'] == mes, 'Valor'].sum() if not df_dep_agrupado.empty else 0.0
            
            total_aportado += aporte_mes
            saldo_cdi += aporte_mes
            saldo_ibov += aporte_mes
            saldo_sp500 += aporte_mes
            saldo_ipca += aporte_mes
            
            # Aplica a rentabilidade do mês atual
            b_data = dict_benchmarks.get(mes, {})
            saldo_cdi *= (1 + float(b_data.get('CDI', 0.0)))
            saldo_ibov *= (1 + float(b_data.get('IBOV', 0.0)))
            saldo_sp500 *= (1 + float(b_data.get('SP500_BRL', 0.0)))
            saldo_ipca *= (1 + float(b_data.get('IPCA', 0.0)))
            
            linha_aportes.append(total_aportado)
            linha_cdi.append(saldo_cdi)
            linha_ibov.append(saldo_ibov)
            linha_sp500.append(saldo_sp500)
            linha_ipca.append(saldo_ipca)
            
        df_timeline['TotalAportado'] = linha_aportes
        df_timeline['Valor_CDI'] = linha_cdi
        df_timeline['Valor_IBOV'] = linha_ibov
        df_timeline['Valor_SP500'] = linha_sp500
        df_timeline['Valor_IPCA'] = linha_ipca

        linha_patrimonio = []
        estoque_ativos = {} 
        
        for i, mes in enumerate(range_meses):
            compras_mes = df_inv_agrupado[df_inv_agrupado['MesAno'] == mes]
            for _, row in compras_mes.iterrows():
                ativo = row['Ativo']
                if ativo not in estoque_ativos:
                    estoque_ativos[ativo] = {
                        'qtd': 0.0, 'custo_acumulado': 0.0, 
                        'preco_live': row['PrecoLive'], 'tem_cotacao': row['TemCotacao']
                    }
                
                estoque_ativos[ativo]['qtd'] += row['Quantidade']
                estoque_ativos[ativo]['custo_acumulado'] += row['TotalCusto']
                estoque_ativos[ativo]['preco_live'] = row['PrecoLive']
                estoque_ativos[ativo]['tem_cotacao'] = row['TemCotacao']
            
            valor_mercado_mes = 0.0
            custo_total_mes = 0.0
            for d in estoque_ativos.values():
                custo_total_mes += d['custo_acumulado']
                if d['tem_cotacao']:
                    valor_mercado_mes += d['qtd'] * d['preco_live']
                else:
                    valor_mercado_mes += d['custo_acumulado']
                    
            # A mágica do Caixa Pendente na linha do tempo
            aportado_ate_mes = linha_aportes[i]
            caixa_livre_mes = max(0, aportado_ate_mes - custo_total_mes)
            
            patrimonio_real_mes = valor_mercado_mes + caixa_livre_mes
            linha_patrimonio.append(patrimonio_real_mes)
            
        df_timeline['PatrimonioReal'] = linha_patrimonio
        
        df_timeline['MesExibicao'] = pd.to_datetime(df_timeline['MesAno'], format='%Y-%m').dt.strftime('%m/%Y')
        df_timeline.loc[df_timeline.index[-1], 'MesExibicao'] = "Hoje"

        sucesso_carregamento = True
        status.update(label="Linha do tempo processada com sucesso!", state="complete", expanded=False)


    # ==========================================
    # 2. RENDERIZAÇÃO DA INTERFACE (MÉTRICAS E GRÁFICOS)
    # ==========================================
    if sucesso_carregamento:
        live_aportado = df_timeline.iloc[-1]['TotalAportado']
        live_atual = df_timeline.iloc[-1]['PatrimonioReal']
        
        live_cdi = df_timeline.iloc[-1]['Valor_CDI']
        live_ibov = df_timeline.iloc[-1]['Valor_IBOV']
        live_sp500 = df_timeline.iloc[-1]['Valor_SP500']
        live_ipca = df_timeline.iloc[-1]['Valor_IPCA']
        
        lucro_rs = live_atual - live_aportado
        lucro_pct = (lucro_rs / live_aportado * 100) if live_aportado > 0 else 0

        # Linha 1: Os Dados da Sua Carteira
        st.markdown("### 💼 Resumo da Carteira")
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Depositado", formata_br(live_aportado), delta=".", delta_color="off")
        col2.metric("Patrimônio Real", formata_br(live_atual), delta=".", delta_color="off")
        col3.metric("Rentabilidade Real", formata_br(lucro_rs), f"{lucro_pct:+.2f}%".replace('.', ','))
        
        # Linha 2: Os Dados Teóricos (Benchmarks interativos)
        st.markdown("---")
        st.markdown("### 🔎 Simulador de Benchmarks (Saldo Teórico)")
        st.caption("E se todo o seu dinheiro tivesse sido investido nesses indicadores? Marque as opções para comparar:")
        
        c_b1, c_b2, c_b3, c_b4 = st.columns(4)
        
        show_cdi = c_b1.checkbox("📈 100% CDI", value=False)
        if show_cdi:
            lucro_cdi = live_cdi - live_aportado
            pct_cdi = (lucro_cdi / live_aportado * 100) if live_aportado > 0 else 0
            c_b1.metric("Teórico CDI", formata_br(live_cdi), f"{pct_cdi:+.2f}%".replace('.', ','), delta_color="normal")
            
        show_ibov = c_b2.checkbox("📊 IBOVESPA", value=False)
        if show_ibov:
            lucro_ibov = live_ibov - live_aportado
            pct_ibov = (lucro_ibov / live_aportado * 100) if live_aportado > 0 else 0
            c_b2.metric("Teórico IBOV", formata_br(live_ibov), f"{pct_ibov:+.2f}%".replace('.', ','), delta_color="normal")
            
        show_sp500 = c_b3.checkbox("🌎 S&P 500 (BRL)", value=False)
        if show_sp500:
            lucro_sp500 = live_sp500 - live_aportado
            pct_sp500 = (lucro_sp500 / live_aportado * 100) if live_aportado > 0 else 0
            c_b3.metric("Teórico S&P 500", formata_br(live_sp500), f"{pct_sp500:+.2f}%".replace('.', ','), delta_color="normal")
            
        show_ipca = c_b4.checkbox("🛒 IPCA (Inflação)", value=False)
        if show_ipca:
            lucro_ipca = live_ipca - live_aportado
            pct_ipca = (lucro_ipca / live_aportado * 100) if live_aportado > 0 else 0
            c_b4.metric("Correção IPCA", formata_br(live_ipca), f"{pct_ipca:+.2f}%".replace('.', ','), delta_color="off")
            
        st.markdown("---")

        # --- GRÁFICO PLOTLY SUPER CARREGADO ---
        fig = go.Figure()

        # Linha Base: Dinheiro que saiu do bolso
        fig.add_trace(go.Scatter(
            x=df_timeline['MesExibicao'], y=df_timeline['TotalAportado'],
            mode='lines+markers', name='Total Depositado',
            line=dict(color='#8c92ac', width=3, dash='dot'),
            fill='tozeroy', fillcolor='rgba(140, 146, 172, 0.1)',
            hovertemplate="Depositado Acumulado: R$ %{y:,.2f}<extra></extra>"
        ))

        cor_saldo = '#00cc96' if live_atual >= live_aportado else '#ef553b'
        cor_area = 'rgba(0, 204, 150, 0.25)' if live_atual >= live_aportado else 'rgba(239, 85, 59, 0.25)'
        
        # Linha Principal: A Carteira do Usuário (Agora Patrimônio Real)
        fig.add_trace(go.Scatter(
            x=df_timeline['MesExibicao'], y=df_timeline['PatrimonioReal'],
            mode='lines+markers', name='Patrimônio Real',
            line=dict(color=cor_saldo, width=3),
            fill='tonexty', fillcolor=cor_area,
            hovertemplate="Patrimônio Real: R$ %{y:,.2f}<extra></extra>"
        ))

        # --- INJEÇÃO DOS BENCHMARKS ATIVADOS NO CHECKBOX ---
        if show_cdi:
            fig.add_trace(go.Scatter(
                x=df_timeline['MesExibicao'], y=df_timeline['Valor_CDI'],
                mode='lines+markers', name='Teórico 100% CDI',
                line=dict(color='#ffbf00', width=2, dash='dash'),
                hovertemplate="Teórico CDI: R$ %{y:,.2f}<extra></extra>"
            ))
            
        if show_ibov:
            fig.add_trace(go.Scatter(
                x=df_timeline['MesExibicao'], y=df_timeline['Valor_IBOV'],
                mode='lines+markers', name='Teórico IBOVESPA',
                line=dict(color='#33b5e5', width=2, dash='dash'),
                hovertemplate="Teórico IBOV: R$ %{y:,.2f}<extra></extra>"
            ))
            
        if show_sp500:
            fig.add_trace(go.Scatter(
                x=df_timeline['MesExibicao'], y=df_timeline['Valor_SP500'],
                mode='lines+markers', name='Teórico S&P 500 (BRL)',
                line=dict(color='#ff4444', width=2, dash='dash'),
                hovertemplate="Teórico S&P 500: R$ %{y:,.2f}<extra></extra>"
            ))
            
        if show_ipca:
            fig.add_trace(go.Scatter(
                x=df_timeline['MesExibicao'], y=df_timeline['Valor_IPCA'],
                mode='lines+markers', name='Correção IPCA',
                line=dict(color='#9933cc', width=2, dash='dash'),
                hovertemplate="Correção IPCA: R$ %{y:,.2f}<extra></extra>"
            ))

        fig.update_layout(
            height=480, 
            margin=dict(l=0, r=0, t=30, b=0),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            hovermode="x unified", 
            xaxis=dict(showgrid=False), 
            yaxis=dict(tickformat=",.2f")
        )
        
        st.plotly_chart(fig, width='stretch')

        # --- AUDITORIA VISUAL ---
        st.markdown("<br>", unsafe_allow_html=True)
        with st.expander("🔍 Inspecionar Dados Lidos (Auditoria)"):
            st.markdown("Confira nas tabelas abaixo em quais meses o sistema agrupou os seus lançamentos de caixa:")
            c_dbg1, c_dbg2 = st.columns(2)
            with c_dbg1:
                st.markdown("**1. Movimentação de Caixa por Mês**")
                if not df_dep_agrupado.empty:
                    df_dep_exibicao = df_dep_agrupado.copy()
                    df_dep_exibicao['Valor'] = df_dep_exibicao['Valor'].apply(formata_br)
                    st.dataframe(df_dep_exibicao, hide_index=True, width='stretch')
                else:
                    st.info("Nenhuma movimentação agrupada.")
            with c_dbg2:
                st.markdown("**2. Acúmulo no Gráfico**")
                df_dbg = df_timeline[['MesExibicao', 'TotalAportado', 'PatrimonioReal']].copy()
                df_dbg.rename(columns={'TotalAportado': 'Linha Cinza', 'PatrimonioReal': 'Linha Colorida'}, inplace=True)
                st.dataframe(df_dbg, hide_index=True, width='stretch')
