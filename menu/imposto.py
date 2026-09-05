import streamlit as st
import pandas as pd
import datetime
from utils import ler_planilha, formata_br, extrair_numero_br

# ==========================================
# FUNÇÕES DE APOIO E CÁLCULO MENSAL
# ==========================================
def limpa_numero_seguro(val):
    if pd.isna(val) or str(val).strip() == '': return 0.0
    if isinstance(val, (int, float)): return float(val)
    v = str(val).strip().replace('R$', '').replace(' ', '')
    if '.' in v and ',' in v:
        v = v.replace('.', '').replace(',', '.')
    elif ',' in v:
        v = v.replace(',', '.')
    try: return float(v)
    except: return 0.0

def normalizar_categoria(cat_str):
    c = str(cat_str).strip().upper()
    if c in ["IPCA", "RF", "RENDA FIXA", "TESOURO", "PREFIXADO", "CDI", "SELIC"]: return "Renda Fixa"
    if c in ["AÇÕES", "ACOES", "AÇÃO", "ACAO", "BRASIL"]: return "Ações"
    if c in ["FIIS", "FII", "FUNDO IMOBILIARIO", "FUNDOS IMOBILIÁRIOS"]: return "FIIs"
    if c in ["STOCKS", "STOCK", "EXTERIOR"]: return "Stocks"
    if c in ["REITS", "REIT"]: return "REITs"
    if c in ["ETFS", "ETF"]: return "ETFs"
    return str(cat_str).strip()

def calcular_impostos(email):
    cols_vendas = ['Data', 'Mes_Ano', 'Ano', 'Ativo', 'Categoria', 'Valor_Venda', 'Lucro']
    
    df_invest = ler_planilha("Investimentos")
    if df_invest.empty: return pd.DataFrame(columns=cols_vendas)
    
    df_invest.columns = [str(c).strip() for c in df_invest.columns]
    if 'Email' not in df_invest.columns or 'Ativo' not in df_invest.columns: 
        return pd.DataFrame(columns=cols_vendas)

    df_user = df_invest[df_invest['Email'].astype(str).str.strip().str.lower() == email].copy()
    if df_user.empty: return pd.DataFrame(columns=cols_vendas)

    col_data = next((c for c in df_user.columns if 'data' in str(c).lower()), None)
    col_preco = next((c for c in df_user.columns if 'prec' in str(c).lower() or 'custo' in str(c).lower()), None)
    
    if not col_data or not col_preco: 
        return pd.DataFrame(columns=cols_vendas)

    df_user['Data'] = pd.to_datetime(df_user[col_data], errors='coerce', dayfirst=True)
    df_user = df_user.dropna(subset=['Data']).sort_values(by='Data')
    df_user['Quantidade'] = df_user['Quantidade'].apply(limpa_numero_seguro)
    df_user[col_preco] = df_user[col_preco].apply(limpa_numero_seguro)
    df_user['Categoria'] = df_user['Categoria'].apply(normalizar_categoria)

    pm_dict = {}
    historico_vendas = []

    for _, row in df_user.iterrows():
        ativo = str(row['Ativo']).strip().upper()
        qtd = row['Quantidade']
        preco = row[col_preco]
        cat = row['Categoria']
        data = row['Data']
        
        if ativo not in pm_dict:
            pm_dict[ativo] = {'qtd': 0.0, 'custo_total': 0.0, 'pm': 0.0}
            
        if qtd > 0: 
            pm_dict[ativo]['qtd'] += qtd
            pm_dict[ativo]['custo_total'] += (qtd * preco)
            if pm_dict[ativo]['qtd'] > 0:
                pm_dict[ativo]['pm'] = pm_dict[ativo]['custo_total'] / pm_dict[ativo]['qtd']
                
        elif qtd < 0: 
            qtd_vendida = abs(qtd)
            valor_venda = qtd_vendida * preco
            pm_atual = pm_dict[ativo]['pm']
            custo_venda = qtd_vendida * pm_atual
            lucro = valor_venda - custo_venda
            
            pm_dict[ativo]['qtd'] -= qtd_vendida
            pm_dict[ativo]['custo_total'] -= custo_venda
            if pm_dict[ativo]['qtd'] <= 0.0001: 
                pm_dict[ativo]['qtd'] = 0.0
                pm_dict[ativo]['custo_total'] = 0.0
                
            historico_vendas.append({
                'Data': data,
                'Mes_Ano': data.strftime('%Y-%m'),
                'Ano': data.strftime('%Y'),
                'Ativo': ativo,
                'Categoria': cat,
                'Valor_Venda': valor_venda,
                'Lucro': lucro
            })
            
    if not historico_vendas:
        return pd.DataFrame(columns=cols_vendas)
        
    return pd.DataFrame(historico_vendas)

# ==========================================
# RENDERIZAÇÃO DA PÁGINA
# ==========================================
def render():
    st.title("🦁 Radar de Imposto de Renda")
    st.markdown("Acompanhe sua margem de isenção mensal, estime DARFs e automatize sua declaração anual.")
    
    # ==========================================
    # NAVEGAÇÃO POR BOTÕES DE ESTADO (TIPO CONFIGURAÇÃO)
    # ==========================================
    if 'aba_imposto' not in st.session_state:
        st.session_state.aba_imposto = "Mensal"

    def mudar_aba_imposto(nova_aba):
        st.session_state.aba_imposto = nova_aba

    st.markdown("<br>", unsafe_allow_html=True)
    c_aba1, c_aba2 = st.columns(2)
    
    c_aba1.button(
        "🚨 1. Apuração Mensal (Vendas e DARF)", 
        width='stretch', 
        on_click=mudar_aba_imposto, args=("Mensal",),
        type="primary" if st.session_state.aba_imposto == "Mensal" else "secondary"
    )

    c_aba2.button(
        "🧾 2. Declaração Anual (Bens e Direitos)", 
        width='stretch', 
        on_click=mudar_aba_imposto, args=("Anual",),
        type="primary" if st.session_state.aba_imposto == "Anual" else "secondary"
    )
    
    st.markdown("---")

    # =========================================================
    # CONTEÚDO 1: APURAÇÃO MENSAL E DARF
    # =========================================================
    if st.session_state.aba_imposto == "Mensal":
        df_vendas = calcular_impostos(st.session_state.email)
        
        if df_vendas.empty:
            st.info("Nenhuma venda (quantidade negativa) foi localizada no seu histórico de investimentos. Seu Leão está dormindo tranquilo! 💤")

        hoje = datetime.datetime.today()
        mes_atual = hoje.strftime('%Y-%m')
        ano_atual = hoje.strftime('%Y')
        
        # --- LÓGICA DO MÊS ANTERIOR PARA O ALERTA DE DARF ---
        primeiro_dia_atual = hoje.replace(day=1)
        ultimo_dia_anterior = primeiro_dia_atual - datetime.timedelta(days=1)
        mes_anterior_str = ultimo_dia_anterior.strftime('%Y-%m')
        nome_mes_anterior = ultimo_dia_anterior.strftime('%m/%Y')
        
        st.header("🇧🇷 Radar Brasil (Mês Atual)")
        
        # 🚨 ALERTA DE DARF DO MÊS PASSADO 🚨
        if not df_vendas.empty:
            df_mes_anterior = df_vendas[df_vendas['Mes_Ano'] == mes_anterior_str]
            
            darf_total_ant = 0
            mensagens_darf_ant = []
            
            if not df_mes_anterior.empty:
                # Verifica Ações Mês Passado
                df_ac_ant = df_mes_anterior[df_mes_anterior['Categoria'] == 'Ações']
                vendas_ac_ant = df_ac_ant['Valor_Venda'].sum() if not df_ac_ant.empty else 0
                lucro_ac_ant = df_ac_ant['Lucro'].sum() if not df_ac_ant.empty else 0
                if vendas_ac_ant > 20000 and lucro_ac_ant > 0:
                    darf_ac = lucro_ac_ant * 0.15
                    darf_total_ant += darf_ac
                    mensagens_darf_ant.append(f"Ações: {formata_br(darf_ac)}")
                    
                # Verifica FIIs Mês Passado
                df_fii_ant = df_mes_anterior[df_mes_anterior['Categoria'] == 'FIIs']
                lucro_fii_ant = df_fii_ant['Lucro'].sum() if not df_fii_ant.empty else 0
                if lucro_fii_ant > 0:
                    darf_fii = lucro_fii_ant * 0.20
                    darf_total_ant += darf_fii
                    mensagens_darf_ant.append(f"FIIs: {formata_br(darf_fii)}")
                    
            if darf_total_ant > 0:
                st.error(f"🚨 **ALERTA DE VENCIMENTO:** Você teve lucros tributáveis em **{nome_mes_anterior}**. Há uma **DARF estimada de {formata_br(darf_total_ant)}** que vence no último dia útil deste mês! ({' + '.join(mensagens_darf_ant)})")

        df_mes = df_vendas[df_vendas['Mes_Ano'] == mes_atual] if not df_vendas.empty else pd.DataFrame(columns=df_vendas.columns)
        
        c_br1, c_br2 = st.columns(2, gap="large")
        
        with c_br1:
            st.subheader("Ações")
            st.caption("**Regra:** Vendas de até R$ 20.000,00 no mês são isentas. Acima disso, incide IR de 15% sobre o lucro (em swing trade). Prejuízos anteriores podem ser compensados.")
            
            df_acoes_mes = df_mes[df_mes['Categoria'] == 'Ações']
            total_vendas_acoes = df_acoes_mes['Valor_Venda'].sum() if not df_acoes_mes.empty else 0
            lucro_acoes = df_acoes_mes['Lucro'].sum() if not df_acoes_mes.empty else 0
            
            progresso = min(total_vendas_acoes / 20000.0, 1.0)
            
            st.markdown(f"**Total Vendido no Mês:** {formata_br(total_vendas_acoes)} / R$ 20.000,00")
            
            if total_vendas_acoes <= 20000:
                st.progress(progresso)
                st.success(f"✅ Dentro do limite de isenção! (Faltam {formata_br(20000 - total_vendas_acoes)} para estourar)")
                if lucro_acoes > 0:
                    st.caption(f"Seu lucro de {formata_br(lucro_acoes)} este mês está **ISENTO** de IR.")
            else:
                st.progress(1.0)
                st.error(f"❌ Limite estourado! Vendas superaram 20k.")
                if lucro_acoes > 0:
                    darf_acoes = lucro_acoes * 0.15
                    st.warning(f"**Lucro Tributável:** {formata_br(lucro_acoes)} | **DARF Estimada (15%):** {formata_br(darf_acoes)}")
                else:
                    st.info(f"Você estourou o limite de vendas, mas teve Prejuízo de {formata_br(lucro_acoes)}. Nenhuma DARF devida.")
                    
        with c_br2:
            st.subheader("FIIs")
            st.caption("**Regra:** Não existe faixa de isenção. O IR é de 20% sobre qualquer lucro obtido na venda de cotas. Prejuízos de meses anteriores podem ser compensados.")
            
            df_fiis_mes = df_mes[df_mes['Categoria'] == 'FIIs']
            lucro_fiis = df_fiis_mes['Lucro'].sum() if not df_fiis_mes.empty else 0
            
            if df_fiis_mes.empty:
                st.info("Nenhuma venda de FIIs realizada neste mês.")
            else:
                st.markdown(f"**Resultado das Vendas (Mês):** {formata_br(lucro_fiis)}")
                if lucro_fiis > 0:
                    darf_fiis = lucro_fiis * 0.20
                    st.warning(f"**DARF Estimada (20%):** {formata_br(darf_fiis)}")
                    st.caption("Lembre-se de descontar prejuízos de meses anteriores antes de pagar a DARF.")
                else:
                    st.success("Você operou com prejuízo este mês. Guarde este valor para abater de lucros futuros!")

        st.markdown("---")
        
        st.header("🌎 Dossiê Exterior (Ano Vigente)")
        st.markdown("Pela Lei 14.754/2023, o imposto sobre investimentos internacionais (Stocks, REITs, ETFs) é apurado anualmente. Os lucros são tributados em **15%**, permitindo a compensação de prejuízos dentro do mesmo ano.")
        
        cats_exterior = ['Stocks', 'REITs', 'ETFs']
        df_ano_ext = df_vendas[(df_vendas['Ano'] == ano_atual) & (df_vendas['Categoria'].isin(cats_exterior))] if not df_vendas.empty else pd.DataFrame(columns=df_vendas.columns)
        
        if df_ano_ext.empty:
            st.info("Nenhuma venda de ativos no exterior registrada no ano de " + ano_atual + ".")
        else:
            lucro_ext_ano = df_ano_ext['Lucro'].sum()
            
            c_ext1, c_ext2, c_ext3 = st.columns(3)
            c_ext1.metric("Total Vendido no Ano", formata_br(df_ano_ext['Valor_Venda'].sum()))
            c_ext2.metric("Lucro Líquido YTD", formata_br(lucro_ext_ano))
            
            if lucro_ext_ano > 0:
                ir_ext = lucro_ext_ano * 0.15
                c_ext3.metric("Imposto Acumulado (15%)", formata_br(ir_ext), delta="A pagar no Ajuste Anual", delta_color="inverse")
            else:
                c_ext3.metric("Imposto Acumulado", "R$ 0,00")
                st.success(f"Seu saldo anual no exterior é de prejuízo ({formata_br(lucro_ext_ano)}). Esse valor abaterá futuros lucros neste mesmo ano calendário.")

        if not df_vendas.empty:
            with st.expander("Ver histórico de Vendas (Auditoria)"):
                df_exibicao = df_vendas.sort_values(by='Data', ascending=False).head(15).copy()
                df_exibicao['Data'] = df_exibicao['Data'].dt.strftime('%d/%m/%Y')
                df_exibicao['Valor_Venda'] = df_exibicao['Valor_Venda'].apply(lambda x: f"R$ {x:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'))
                df_exibicao['Lucro'] = df_exibicao['Lucro'].apply(lambda x: f"R$ {x:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'))
                
                st.dataframe(
                    df_exibicao[['Data', 'Ativo', 'Categoria', 'Valor_Venda', 'Lucro']],
                    width='stretch',
                    hide_index=True
                )

    # =========================================================
    # CONTEÚDO 2: DECLARAÇÃO ANUAL (BENS E DIREITOS)
    # =========================================================
    elif st.session_state.aba_imposto == "Anual":
        st.markdown("Automatize a sua declaração de **Bens e Direitos**. Os valores aqui refletem o **Custo de Aquisição** histórico das posições fechadas em 31/12 de cada ano-calendário.")

        ano_atual_bens = datetime.datetime.now().year
        # Normalmente a declaração feita no ano atual refere-se ao ano calendário anterior
        anos_disponiveis = [ano_atual_bens - 1, ano_atual_bens - 2, ano_atual_bens - 3]
        
        col_ano, _ = st.columns([1, 3])
        ano_base = col_ano.selectbox("📅 Selecione o Ano-Calendário da Declaração:", anos_disponiveis)
        ano_anterior = ano_base - 1

        with st.spinner("Processando histórico de aquisições..."):
            df_invest_bens = ler_planilha("Investimentos")
            
            if df_invest_bens.empty or 'Email' not in df_invest_bens.columns:
                st.warning("Nenhum dado de investimento encontrado para processar a declaração.")
            else:
                df_user_inv = df_invest_bens[df_invest_bens['Email'].astype(str).str.strip().str.lower() == st.session_state.email].copy()
                
                if df_user_inv.empty:
                    st.info("Sua carteira está vazia ou sem lançamentos.")
                else:
                    col_data = next((c for c in df_user_inv.columns if 'data' in str(c).lower()), None)
                    col_preco = next((c for c in df_user_inv.columns if 'prec' in str(c).lower() or 'custo' in str(c).lower()), None)

                    if not col_data or not col_preco:
                        st.error("Não foram encontradas colunas de Data ou Preço na planilha para calcular o histórico.")
                    else:
                        df_user_inv['DataCompra'] = pd.to_datetime(df_user_inv[col_data], dayfirst=True, errors='coerce')
                        df_user_inv['Ativo'] = df_user_inv['Ativo'].astype(str).str.strip().str.upper()
                        df_user_inv['Quantidade'] = df_user_inv['Quantidade'].apply(extrair_numero_br)
                        df_user_inv['PrecoCusto'] = df_user_inv[col_preco].apply(extrair_numero_br)
                        df_user_inv['CustoTotal'] = df_user_inv['Quantidade'] * df_user_inv['PrecoCusto']

                        data_limite_base = pd.to_datetime(f"{ano_base}-12-31")
                        data_limite_anterior = pd.to_datetime(f"{ano_anterior}-12-31")

                        # Posição Ano Base
                        df_base = df_user_inv[df_user_inv['DataCompra'] <= data_limite_base]
                        posicao_base = df_base.groupby('Ativo').agg({'Quantidade': 'sum', 'CustoTotal': 'sum'}).reset_index()
                        posicao_base = posicao_base[posicao_base['Quantidade'] > 0.0001]
                        posicao_base['PrecoMedio'] = posicao_base['CustoTotal'] / posicao_base['Quantidade']

                        # Posição Ano Anterior
                        df_anterior = df_user_inv[df_user_inv['DataCompra'] <= data_limite_anterior]
                        posicao_anterior = df_anterior.groupby('Ativo').agg({'Quantidade': 'sum', 'CustoTotal': 'sum'}).reset_index()
                        posicao_anterior = posicao_anterior[posicao_anterior['Quantidade'] > 0.0001]

                        total_declarar_base = posicao_base['CustoTotal'].sum()
                        total_declarar_anterior = posicao_anterior['CustoTotal'].sum()

                        st.markdown("---")
                        st.markdown("### 📊 Visão Geral - Bens e Direitos")
                        
                        col1, col2 = st.columns(2)
                        
                        col1.markdown(f"""
                            <div style="background-color: rgba(128, 128, 128, 0.05); border: 1px solid rgba(128, 128, 128, 0.2); padding: 0.8rem 1rem; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); min-height: 100px;">
                                <div style="font-weight: 600; color: gray; font-size: 0.95rem; padding-bottom: 0.25rem;">Situação em 31/12/{ano_anterior}</div>
                                <div style="font-size: 1.8rem; color: #8c92ac;">{formata_br(total_declarar_anterior)}</div>
                            </div>
                        """, unsafe_allow_html=True)
                        
                        col2.markdown(f"""
                            <div style="background-color: rgba(128, 128, 128, 0.05); border: 1px solid rgba(128, 128, 128, 0.2); padding: 0.8rem 1rem; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); min-height: 100px;">
                                <div style="font-weight: 600; color: gray; font-size: 0.95rem; padding-bottom: 0.25rem;">Situação em 31/12/{ano_base}</div>
                                <div style="font-size: 1.8rem; color: #33b5e5;">{formata_br(total_declarar_base)}</div>
                            </div>
                        """, unsafe_allow_html=True)
                        
                        st.markdown("<br>", unsafe_allow_html=True)

                        if posicao_base.empty:
                            st.success(f"Nenhum ativo sob custódia na virada de {ano_base}.")
                        else:
                            st.markdown("### 📝 Dados para Copiar e Colar")
                            st.caption("Expanda cada ativo para ver a sugestão de texto formatada para o programa da Receita Federal.")
                            
                            for _, row in posicao_base.iterrows():
                                ativo = row['Ativo']
                                qtd = row['Quantidade']
                                pm = row['PrecoMedio']
                                total_base = row['CustoTotal']
                                
                                linha_anterior = posicao_anterior[posicao_anterior['Ativo'] == ativo]
                                total_ant = linha_anterior['CustoTotal'].iloc[0] if not linha_anterior.empty else 0.0
                                
                                texto_receita = f"{int(qtd)} unidades do ativo {ativo}, adquiridas ao preço médio de {formata_br(pm)}. Custódia na corretora [INSERIR NOME/CNPJ]."
                                
                                with st.expander(f"📌 {ativo} | Valor em 31/12/{ano_base}: {formata_br(total_base)}"):
                                    c_desc, c_vals = st.columns([3, 1])
                                    
                                    with c_desc:
                                        st.markdown("**Texto Sugerido (Discriminação):**")
                                        st.code(texto_receita, language="text")
                                        
                                    with c_vals:
                                        st.markdown(f"**Situação 31/12/{ano_anterior}:**<br>{formata_br(total_ant)}", unsafe_allow_html=True)
                                        st.markdown(f"**Situação 31/12/{ano_base}:**<br>{formata_br(total_base)}", unsafe_allow_html=True)
