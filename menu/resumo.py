import streamlit as st
import pandas as pd
import plotly.express as px
from utils import ler_planilha, obter_cotacoes, extrair_numero_br, formata_br

def render():
    st.title("📊 Resumo Geral da Carteira")
    
    df_invest = ler_planilha("Investimentos")
    if not df_invest.empty:
        df_invest['Email'] = df_invest['Email'].astype(str).str.strip().str.lower()
        dados_usuario = df_invest[df_invest['Email'] == st.session_state.email].copy()
        
        if not dados_usuario.empty:
            dados_usuario['Ativo'] = dados_usuario['Ativo'].astype(str).str.strip().str.upper()
            dados_usuario['Categoria'] = dados_usuario['Categoria'].astype(str).str.strip()
            
            dados_usuario['Quantidade'] = dados_usuario['Quantidade'].apply(extrair_numero_br)
            dados_usuario['PrecoMedio'] = dados_usuario['PrecoMedio'].apply(extrair_numero_br)
            
            cotacoes_dict = obter_cotacoes()
            dados_usuario['PrecoLive'] = dados_usuario['Ativo'].map(cotacoes_dict).fillna(0.0)
            
            dados_usuario['PrecoAtual'] = dados_usuario.apply(
                lambda row: row['PrecoLive'] if row['PrecoLive'] > 0 else row['PrecoMedio'], axis=1
            )
            
            dados_usuario['TotalInvestido'] = dados_usuario['Quantidade'] * dados_usuario['PrecoMedio']
            dados_usuario['TotalAtual'] = dados_usuario['Quantidade'] * dados_usuario['PrecoAtual']
            
            # --- NOVO: CRUZAMENTO PARA BUSCAR SETORES ---
            df_config = ler_planilha("Ativos_Config")
            dict_setores = {}
            if not df_config.empty and 'Email' in df_config.columns:
                df_config['Email'] = df_config['Email'].astype(str).str.strip().str.lower()
                meus_configs = df_config[df_config['Email'] == st.session_state.email].copy()
                if 'Setor' not in meus_configs.columns:
                    meus_configs['Setor'] = 'Não Classificado'
                dict_setores = dict(zip(meus_configs['Ativo'].str.upper().str.strip(), meus_configs['Setor']))
                
            dados_usuario['Setor'] = dados_usuario['Ativo'].map(dict_setores).fillna('Não Classificado')
            
            carteira_agrupada = dados_usuario.groupby(['Ativo', 'Categoria', 'Setor']).agg({
                'Quantidade': 'sum',
                'TotalInvestido': 'sum',
                'TotalAtual': 'sum',
                'PrecoAtual': 'first'
            }).reset_index()
            
            carteira_agrupada['PrecoMedio'] = carteira_agrupada['TotalInvestido'] / carteira_agrupada['Quantidade'].replace(0, 1)
            carteira_agrupada.loc[carteira_agrupada['Quantidade'] == 0, 'PrecoMedio'] = 0
            
            carteira_agrupada['EvolucaoPct'] = ((carteira_agrupada['PrecoAtual'] - carteira_agrupada['PrecoMedio']) / carteira_agrupada['PrecoMedio'].replace(0, 1)) * 100
            carteira_agrupada.loc[carteira_agrupada['PrecoMedio'] == 0, 'EvolucaoPct'] = 0
            
            df_depositos = ler_planilha("Depositos")
            total_carteira_investido = 0.0
            
            if not df_depositos.empty and 'Email' in df_depositos.columns:
                df_depositos['Email'] = df_depositos['Email'].astype(str).str.strip().str.lower()
                meus_depositos = df_depositos[df_depositos['Email'] == st.session_state.email].copy()
                
                if not meus_depositos.empty:
                    meus_depositos['Valor'] = meus_depositos['Valor'].apply(extrair_numero_br)
                    total_carteira_investido = meus_depositos['Valor'].sum()
            
            total_carteira_atual = carteira_agrupada['TotalAtual'].sum()
            evolucao_total_carteira = ((total_carteira_atual - total_carteira_investido) / total_carteira_investido if total_carteira_investido > 0 else 0) * 100
            
            col_c1, col_c2, col_c3 = st.columns(3)
            col_c1.metric("Total Investido", formata_br(total_carteira_investido))
            col_c2.metric("Valor Atual", formata_br(total_carteira_atual))
            col_c3.metric("Evolução", f"{evolucao_total_carteira:+.2f}%".replace('.', ','))
            
            st.markdown("---")
            
            col_grafico, col_tabelas = st.columns([1, 1.5], gap="large")
            
            with col_grafico:
                st.subheader("Distribuição")
                df_categoria = carteira_agrupada.groupby('Categoria')['TotalAtual'].sum().reset_index()
                fig = px.pie(df_categoria, values='TotalAtual', names='Categoria', hole=0.4)
                fig.update_traces(textinfo='label+percent')
                fig.update_layout(height=350, margin=dict(t=20, b=20, l=0, r=0), showlegend=False)
                st.plotly_chart(fig, width='stretch')
            
            with col_tabelas:
                st.subheader("Detalhamento por Ativos")
                for cat in carteira_agrupada['Categoria'].unique():
                    with st.expander(f"📁 {cat}", expanded=False): 
                        df_exibicao = carteira_agrupada[carteira_agrupada['Categoria'] == cat][['Ativo', 'Setor', 'Quantidade', 'PrecoMedio', 'PrecoAtual', 'TotalAtual', 'EvolucaoPct']].copy()
                        
                        df_exibicao['Quantidade'] = df_exibicao['Quantidade'].map('{:,.4f}'.format).str.replace(',', 'X').str.replace('.', ',').str.replace('X', '.').str.rstrip('0').str.rstrip(',')
                        df_exibicao['PrecoMedio'] = df_exibicao['PrecoMedio'].apply(formata_br)
                        df_exibicao['PrecoAtual'] = df_exibicao['PrecoAtual'].apply(formata_br)
                        df_exibicao['TotalAtual'] = df_exibicao['TotalAtual'].apply(formata_br)
                        df_exibicao['EvolucaoPct'] = df_exibicao['EvolucaoPct'].map('{:+.2f}%'.format).str.replace('.', ',')
                        
                        st.dataframe(df_exibicao, width='stretch', hide_index=True)

            # ==========================================
            # NOVO: RAIO-X DE EXPOSIÇÃO SETORIAL GLOBAL
            # ==========================================
            st.markdown("---")
            st.subheader("🍕 Raio-X de Exposição Setorial")
            st.markdown("Acompanhe como o seu **Patrimônio de Renda Variável** está espalhado pela economia real para evitar a concentração de risco. Para alterar os nomes dos setores, vá na aba Configuração da Carteira.")
            
            df_rv = carteira_agrupada[carteira_agrupada['Categoria'] != 'Renda Fixa']
            
            if not df_rv.empty and df_rv['TotalAtual'].sum() > 0:
                df_rv_setor = df_rv.groupby('Setor')['TotalAtual'].sum().reset_index()
                
                c_grafico_setor, c_tabela_setor = st.columns([1, 1.5], gap="large")
                
                with c_grafico_setor:
                    fig_setor = px.pie(df_rv_setor, values='TotalAtual', names='Setor', hole=0.4)
                    fig_setor.update_traces(textinfo='percent')
                    fig_setor.update_layout(height=350, margin=dict(t=20, b=20, l=0, r=0), legend=dict(orientation="h", y=-0.2))
                    st.plotly_chart(fig_setor, width='stretch')
                
                with c_tabela_setor:
                    df_rv_setor_exibicao = df_rv_setor.sort_values(by='TotalAtual', ascending=False)
                    df_rv_setor_exibicao['Total (R$)'] = df_rv_setor_exibicao['TotalAtual'].apply(formata_br)
                    df_rv_setor_exibicao['Peso (%)'] = (df_rv_setor_exibicao['TotalAtual'] / df_rv_setor_exibicao['TotalAtual'].sum() * 100).map('{:.2f}%'.format).str.replace('.', ',')
                    
                    st.dataframe(
                        df_rv_setor_exibicao[['Setor', 'Total (R$)', 'Peso (%)']],
                        width='stretch', 
                        hide_index=True
                    )
            else:
                st.info("Você ainda não tem ativos de Renda Variável com saldo para exibir o Raio-X.")

        else:
            st.info("Nenhum investimento encontrado.")
    else:
        st.error("Erro ao ler aba 'Investimentos'.")
