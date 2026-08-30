import streamlit as st
import pandas as pd
import yfinance as yf
from utils import ler_planilha, formata_br

# ==========================================
# ARMADURA NUMÉRICA UNIVERSAL
# ==========================================
def limpa_numero_seguro(val):
    """Garante que a planilha seja lida sem zerar, independente de ser pt-BR ou US"""
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

# ==========================================
# MÁGICA ANTI-QUEBRA DO YAHOO FINANCE
# ==========================================
@st.cache_data(ttl=900, show_spinner=False)
def obter_cotacoes(email_usuario):
    """Busca cotações APENAS para os ativos do usuário logado"""
    df_invest = ler_planilha("Investimentos")
    if df_invest.empty: return {}
    
    df_invest.columns = [str(c).strip() for c in df_invest.columns]
    if 'Ativo' not in df_invest.columns or 'Email' not in df_invest.columns: return {}
    
    df_user = df_invest[df_invest['Email'].astype(str).str.strip().str.lower() == email_usuario]
    ativos = df_user['Ativo'].dropna().unique()
    
    tickers_yf = []
    
    for a in ativos:
        a_str = str(a).strip().upper()
        if not a_str or "TESOURO" in a_str or "CDB" in a_str or "LCI" in a_str or "LCA" in a_str:
            continue
            
        import re
        if "." not in a_str and re.search(r'\d+$', a_str):
            tickers_yf.append(f"{a_str}.SA")
        else:
            tickers_yf.append(a_str)
            
    if not tickers_yf: return {}
    if 'BRL=X' not in tickers_yf: tickers_yf.append('BRL=X')

    try:
        df_raw = yf.download(list(set(tickers_yf)), period="5d", progress=False, ignore_tz=True)
        if df_raw.empty: return {}

        if isinstance(df_raw.columns, pd.MultiIndex):
            lvl_0 = df_raw.columns.get_level_values(0)
            lvl_1 = df_raw.columns.get_level_values(1)
            
            if 'Adj Close' in lvl_0: df_prices = df_raw['Adj Close']
            elif 'Close' in lvl_0: df_prices = df_raw['Close']
            elif 'Adj Close' in lvl_1: df_prices = df_raw.xs('Adj Close', axis=1, level=1)
            elif 'Close' in lvl_1: df_prices = df_raw.xs('Close', axis=1, level=1)
            else: return {} 
        else:
            col_target = 'Adj Close' if 'Adj Close' in df_raw.columns else 'Close'
            if col_target in df_raw.columns:
                df_prices = df_raw[[col_target]].copy()
                df_prices.columns = [tickers_yf[0]]
            else:
                df_prices = df_raw.iloc[:, [0]].copy()
                df_prices.columns = [tickers_yf[0]]

        if isinstance(df_prices, pd.Series):
            df_prices = df_prices.to_frame(name=tickers_yf[0])

        cotacoes = {}
        dolar_atual = df_prices['BRL=X'].iloc[-1] if 'BRL=X' in df_prices.columns else 5.50
        
        for col in df_prices.columns:
            if col == 'BRL=X': continue
            s_valid = df_prices[col].dropna()
            if s_valid.empty: continue
            
            preco = s_valid.iloc[-1]
                
            if not col.endswith('.SA'):
                preco = preco * dolar_atual
                
            chave = col.replace('.SA', '')
            cotacoes[chave] = preco
            
        return cotacoes
    except Exception as e:
        print(f"Erro na API de cotações: {e}")
        return {}


def normalizar_categoria(cat_str):
    c = str(cat_str).strip().upper()
    if c in ["IPCA", "RF", "RENDA FIXA", "TESOURO", "PREFIXADO", "CDI", "SELIC"]: return "Renda Fixa"
    if c in ["AÇÕES", "ACOES", "AÇÃO", "ACAO", "BRASIL"]: return "Ações"
    if c in ["FIIS", "FII", "FUNDO IMOBILIARIO", "FUNDOS IMOBILIÁRIOS"]: return "FIIs"
    if c in ["STOCKS", "STOCK", "EXTERIOR"]: return "Stocks"
    if c in ["REITS", "REIT"]: return "REITs"
    if c in ["ETFS", "ETF"]: return "ETFs"
    return str(cat_str).strip()


def motor_de_aportes(email, valor_aporte, dividir=True):
    df_conf = ler_planilha("Configuracao")
    df_ativos_conf = ler_planilha("Ativos_Config")
    df_invest = ler_planilha("Investimentos")

    if not df_conf.empty: df_conf.columns = [str(c).strip() for c in df_conf.columns]

    if df_conf.empty or email not in df_conf['Email'].astype(str).str.strip().str.lower().values:
        return [], valor_aporte, None, "Metas de Alocação Macro não definidas na Configuração."
    
    if df_ativos_conf.empty:
        df_ativos_conf = pd.DataFrame(columns=['Email', 'Categoria', 'Ativo', 'Peso'])

    df_conf['Email'] = df_conf['Email'].astype(str).str.strip().str.lower()
    user_conf = df_conf[df_conf['Email'] == email].iloc[0].to_dict()

    peso_rv = limpa_numero_seguro(user_conf.get('RV', 50)) / 100.0
    peso_br = limpa_numero_seguro(user_conf.get('RV_Brasil', 50)) / 100.0
    peso_ex = limpa_numero_seguro(user_conf.get('RV_Exterior', 50)) / 100.0

    cat_targets = {
        "Renda Fixa": limpa_numero_seguro(user_conf.get('RF', 50)) / 100.0,
        "Ações": peso_rv * peso_br * (limpa_numero_seguro(user_conf.get('BR_Acoes', 50)) / 100.0),
        "FIIs": peso_rv * peso_br * (limpa_numero_seguro(user_conf.get('BR_FIIs', 50)) / 100.0),
        "Stocks": peso_rv * peso_ex * (limpa_numero_seguro(user_conf.get('EX_Stocks', 40)) / 100.0),
        "REITs": peso_rv * peso_ex * (limpa_numero_seguro(user_conf.get('EX_REITs', 30)) / 100.0),
        "ETFs": peso_rv * peso_ex * (limpa_numero_seguro(user_conf.get('EX_ETFs', 30)) / 100.0),
    }

    df_ativos_conf['Email'] = df_ativos_conf['Email'].astype(str).str.strip().str.lower()
    df_user_ativos = df_ativos_conf[df_ativos_conf['Email'] == email].copy()
    
    cotacoes_dict = obter_cotacoes(email)

    # --- 1. LER ATIVOS ALVOS OFICIAIS ---
    ativos_alvos = []
    for _, row in df_user_ativos.iterrows():
        cat = normalizar_categoria(row['Categoria'])
        if cat == "Renda Fixa": continue 
        ativo = str(row['Ativo']).strip().upper()
        val_peso = row.get('Peso') if pd.notna(row.get('Peso')) else row.get('Peso (%)', 0)
        peso_global = cat_targets.get(cat, 0) * (limpa_numero_seguro(val_peso) / 100.0)
        if ativo and ativo != "NAN":
            ativos_alvos.append({'Categoria': cat, 'Ativo': ativo, 'PesoGlobal': peso_global})

    peso_rf = cat_targets.get("Renda Fixa", 0)
    if peso_rf > 0:
        ativos_alvos.append({'Categoria': 'Renda Fixa', 'Ativo': 'OPORTUNIDADE DE RENDA FIXA', 'PesoGlobal': peso_rf})

    df_alvos = pd.DataFrame(ativos_alvos)
    if not df_alvos.empty:
        df_alvos['Is_Target'] = True
    else:
        df_alvos = pd.DataFrame(columns=['Categoria', 'Ativo', 'PesoGlobal', 'Is_Target'])

    # --- 2. LER ESTOQUE DA CARTEIRA REAL ---
    df_carteira = pd.DataFrame(columns=['Categoria', 'Ativo', 'TotalAtual'])
    
    if not df_invest.empty: df_invest.columns = [str(c).strip() for c in df_invest.columns]
    
    if not df_invest.empty and 'Email' in df_invest.columns:
        df_invest['Email'] = df_invest['Email'].astype(str).str.strip().str.lower()
        df_user_invest = df_invest[df_invest['Email'] == email].copy()
        
        if not df_user_invest.empty:
            df_user_invest['Ativo'] = df_user_invest['Ativo'].astype(str).str.strip().str.upper()
            df_user_invest['Categoria'] = df_user_invest['Categoria'].apply(normalizar_categoria)
            df_user_invest['Quantidade'] = df_user_invest['Quantidade'].apply(limpa_numero_seguro)
            df_user_invest['PrecoLive'] = df_user_invest['Ativo'].map(cotacoes_dict).fillna(0.0)
            df_user_invest['TotalAtual'] = df_user_invest['Quantidade'] * df_user_invest['PrecoLive']
            
            col_preco = next((c for c in df_user_invest.columns if 'prec' in str(c).lower() or 'custo' in str(c).lower()), 'Preco')

            for idx_inv, row_inv in df_user_invest.iterrows():
                if row_inv['Categoria'] == "Renda Fixa" and row_inv['TotalAtual'] == 0:
                    preco_digitado = limpa_numero_seguro(row_inv.get(col_preco, 0))
                    df_user_invest.at[idx_inv, 'TotalAtual'] = row_inv['Quantidade'] * preco_digitado

            df_carteira = df_user_invest.groupby(['Categoria', 'Ativo']).agg({
                'TotalAtual': 'sum'
            }).reset_index()

    # --- 3. MATEMÁTICA E CÁLCULO DE GAPS ---
    total_atual = df_carteira['TotalAtual'].sum() if not df_carteira.empty else 0
    total_futuro = total_atual + valor_aporte 
    
    df_calc = pd.merge(df_alvos, df_carteira, on=['Categoria', 'Ativo'], how='outer')
    df_calc['Is_Target'] = df_calc['Is_Target'].fillna(False)
    df_calc['PesoGlobal'] = df_calc['PesoGlobal'].fillna(0)
    df_calc['TotalAtual'] = df_calc['TotalAtual'].fillna(0)
    df_calc['PrecoAtual'] = df_calc['Ativo'].map(cotacoes_dict).fillna(0.0)
    
    df_calc['ValorAlvo'] = df_calc['PesoGlobal'] * total_futuro
    df_calc['Falta_Comprar'] = df_calc['ValorAlvo'] - df_calc['TotalAtual']
    df_calc['TotalAtual_Original'] = df_calc['TotalAtual'].copy()

    # --- PREPARAÇÃO DO TERMÔMETRO VISUAL ---
    df_resumo_macro = df_calc.groupby('Categoria').agg(
        Alvo=('ValorAlvo', 'sum'),
        Atual=('TotalAtual', 'sum')
    ).reset_index()
    
    df_resumo_macro['Alvo (%)'] = (df_resumo_macro['Alvo'] / total_futuro * 100).round(1) if total_futuro > 0 else 0
    df_resumo_macro['Atual (%)'] = (df_resumo_macro['Atual'] / total_atual * 100).round(1) if total_atual > 0 else 0
    df_resumo_macro['Status'] = df_resumo_macro.apply(
        lambda x: "🟢 Na Meta" if abs(x['Alvo (%)'] - x['Atual (%)']) <= 2 
        else ("🔴 Abaixo da Meta" if x['Atual (%)'] < x['Alvo (%)'] else "🟡 Acima da Meta"), 
        axis=1
    )
    df_resumo_macro = df_resumo_macro.sort_values(by='Alvo (%)', ascending=False).reset_index(drop=True)

    # --- 4. ALOCAÇÃO INTELIGENTE BLINDADA ---
    compras_dict = {}
    aporte_restante = valor_aporte
    df_disp = df_calc[df_calc['Is_Target'] == True].copy()
    
    for idx, row in df_disp.iterrows():
        ativo = row['Ativo']
        compras_dict[ativo] = {
            'Categoria': row['Categoria'],
            'Ativo': ativo,
            'Valor': 0.0,
            'PrecoRef': row['PrecoAtual'],
            'Qtd': 0.0,
            'Is_RV': row['Categoria'] in ["Ações", "FIIs", "Stocks", "REITs", "ETFs"],
            'Is_BR': row['Categoria'] in ["Ações", "FIIs"],
            'Qtd_Alvo': row['ValorAlvo'] / row['PrecoAtual'] if row['PrecoAtual'] > 0 else 9999,
            'Qtd_Atual': row['TotalAtual_Original'] / row['PrecoAtual'] if row['PrecoAtual'] > 0 else 0,
            'Falta_Comprar': row['Falta_Comprar']
        }

    if not dividir:
        # Aporte Integral: Aloca 100% no ativo mais defasado da carteira
        df_disp = df_disp.sort_values(by='Falta_Comprar', ascending=False)
        if not df_disp.empty:
            ativo = df_disp.iloc[0]['Ativo']
            d = compras_dict[ativo]
            preco = d['PrecoRef']
            alocacao_teorica = aporte_restante
            
            if d['Is_RV'] and d['Is_BR']:
                if preco > 0 and alocacao_teorica >= preco:
                    qtd = int(alocacao_teorica / preco)
                    gasto = qtd * preco
                else:
                    qtd, gasto = 0, 0
            elif d['Is_RV'] and not d['Is_BR']:
                if preco > 0:
                    qtd = alocacao_teorica / preco
                    gasto = alocacao_teorica
                else:
                    qtd, gasto = 0, 0
            else:
                qtd = 0
                gasto = alocacao_teorica
                
            d['Valor'] += gasto
            d['Qtd'] += qtd
            d['Falta_Comprar'] -= gasto
            aporte_restante -= gasto

    else:
        # Aporte Dividido: Distribuição Otimizada
        df_gap = df_disp[df_disp['Falta_Comprar'] > 0].copy()
        
        # Filtra os ativos que realmente têm gap e força a alocação matemática
        if not df_gap.empty:
            total_gap = df_gap['Falta_Comprar'].sum()
            for idx, row in df_gap.iterrows():
                ativo = row['Ativo']
                d = compras_dict[ativo]
                preco = d['PrecoRef']
                fator = d['Falta_Comprar'] / total_gap
                alocacao_teorica = valor_aporte * fator
                
                if d['Is_RV'] and d['Is_BR']:
                    if preco > 0 and alocacao_teorica >= preco:
                        qtd = int(alocacao_teorica / preco) 
                        gasto = qtd * preco
                    else:
                        qtd, gasto = 0, 0
                elif d['Is_RV'] and not d['Is_BR']:
                    qtd = alocacao_teorica / preco if preco > 0 else 0
                    gasto = alocacao_teorica
                else:
                    qtd = 0
                    gasto = alocacao_teorica
                    
                d['Valor'] += gasto
                d['Qtd'] += qtd
                d['Falta_Comprar'] -= gasto
                aporte_restante -= gasto
        
        # Se todos estiverem na meta, distribui o aporte conforme os pesos globais
        else:
            total_peso = df_disp['PesoGlobal'].sum()
            for idx, row in df_disp.iterrows():
                ativo = row['Ativo']
                d = compras_dict[ativo]
                preco = d['PrecoRef']
                fator = row['PesoGlobal'] / total_peso if total_peso > 0 else 1/len(df_disp)
                alocacao_teorica = valor_aporte * fator
                
                if d['Is_RV'] and d['Is_BR']:
                    if preco > 0 and alocacao_teorica >= preco:
                        qtd = int(alocacao_teorica / preco)
                        gasto = qtd * preco
                    else:
                        qtd, gasto = 0, 0
                elif d['Is_RV'] and not d['Is_BR']:
                    qtd = alocacao_teorica / preco if preco > 0 else 0
                    gasto = alocacao_teorica
                else:
                    qtd = 0
                    gasto = alocacao_teorica
                    
                d['Valor'] += gasto
                d['Qtd'] += qtd
                d['Falta_Comprar'] -= gasto
                aporte_restante -= gasto

        # Aporte Dividido: Passo 2 - Otimizador de Trocos (Focado 100% em Ativos do Brasil)
        comprou_no_loop = True
        while aporte_restante > 0.01 and comprou_no_loop:
            comprou_no_loop = False
            ativos_ordenados = sorted(compras_dict.values(), key=lambda x: x['Falta_Comprar'], reverse=True)
            
            for d in ativos_ordenados:
                preco = d['PrecoRef']
                # Tenta comprar mais cotas inteiras de ativos Brasileiros (Ações/FIIs) para reaproveitar as "sobras"
                if d['Is_RV'] and d['Is_BR'] and preco > 0 and aporte_restante >= preco:
                    d['Valor'] += preco
                    d['Qtd'] += 1
                    d['Falta_Comprar'] -= preco
                    aporte_restante -= preco
                    comprou_no_loop = True
                    break 

    # --- 5. MONTAGEM FINAL DO EXTRATO DE COMPRAS ---
    compras = []
    ordem = 1
    for d in sorted(compras_dict.values(), key=lambda x: x['Valor'], reverse=True):
        if d['Valor'] > 0:
            qtd_sugerida_str = "-"
            qtd_faltante_str = "-"
            if d['Is_RV']:
                qtd_faltante = max(0, d['Qtd_Alvo'] - d['Qtd_Atual']) if d['Qtd_Alvo'] != 9999 else 0
                if d['Is_BR']:
                    qtd_sugerida_str = f"{int(d['Qtd'])} un"
                    qtd_faltante_str = f"{int(qtd_faltante)} un" if qtd_faltante > 0 else "-"
                else:
                    qtd_sugerida_str = f"{d['Qtd']:.4f} un".replace('.', ',')
                    qtd_faltante_str = f"{qtd_faltante:.4f} un".replace('.', ',') if qtd_faltante > 0 else "-"
                    
            compras.append({
                'Ordem': ordem,
                'Categoria': d['Categoria'],
                'Ativo': d['Ativo'],
                'Valor': d['Valor'],
                'PrecoRef': d['PrecoRef'],
                'Qtd_Sugerida': qtd_sugerida_str,
                'Qtd_Faltante': qtd_faltante_str,
                'Is_RV': d['Is_RV']
            })
            ordem += 1

    return compras, aporte_restante, df_resumo_macro, None


def render():
    st.title("🎯 Guia de Aportes Inteligente")
    st.markdown("Descubra exatamente onde alocar seu dinheiro para manter a carteira alinhada aos seus objetivos.")

    st.markdown("### 1. Dados do Aporte")
    col1, col2 = st.columns([1, 1], gap="large")
    with col1:
        valor_aporte = st.number_input("💸 Valor do Aporte (R$)", min_value=0.0, value=1000.0, step=100.0)
    with col2:
        opcao_est = st.radio("Estratégia do Aporte:", ["Dividir pelo Objetivo", "Aporte Integral"], horizontal=True)
        dividir = "Dividir" in opcao_est

    st.markdown("<br>", unsafe_allow_html=True)
    
    if st.button("🚀 Calcular Onde Aportar", use_container_width=True, type="primary"):
        if valor_aporte <= 0:
            st.warning("Insira um valor maior que zero para o aporte.")
            return

        with st.spinner("Analisando o balanço real da sua carteira..."):
            compras, aporte_restante, df_macro, erro = motor_de_aportes(st.session_state.email, valor_aporte, dividir)

            if erro:
                st.error(f"⚠️ {erro}")
                return
                
        st.markdown("---")
        st.subheader("📊 Termômetro da Carteira (Antes do Aporte)")
        
        st.dataframe(
            df_macro[['Categoria', 'Alvo (%)', 'Atual (%)', 'Status']].style.format({
                'Alvo (%)': "{:.2f}%",
                'Atual (%)': "{:.2f}%"
            }).map(
                lambda x: 'color: #00C851' if '🟢' in str(x) else ('color: #ff4444' if '🔴' in str(x) else 'color: #ffbb33'), 
                subset=['Status']
            ),
            width='stretch', 
            hide_index=True
        )

        st.markdown("---")
        st.subheader("🛒 Suas Ordens de Compra Sugeridas")

        if compras:
            for c in compras:
                with st.container():
                    st.markdown(f"#### {c['Ordem']}º Compra: `{c['Ativo']}` <span style='font-size:0.8em; color:gray;'>({c['Categoria']})</span>", unsafe_allow_html=True)
                    if c['Is_RV']:
                        c_r1, c_r2, c_r3, c_r4 = st.columns(4)
                        c_r1.metric("Alocar", formata_br(c['Valor']))
                        c_r2.metric("Cotação", formata_br(c['PrecoRef']) if c['PrecoRef'] > 0 else "N/A")
                        c_r3.metric("Comprar", c['Qtd_Sugerida'])
                        c_r4.metric("Falta p/ Meta", c['Qtd_Faltante'])
                    else:
                        c_r1, c_r2, c_r3 = st.columns(3)
                        c_r1.metric("Alocar", formata_br(c['Valor']))
                        c_r2.metric("Estratégia", "Escolha Livre")
                        c_r3.metric("Sugestão", "Melhor Taxa IPCA+")
                    st.markdown("<hr style='margin: 0.5em 0; border: 0; border-top: 1px dashed #ddd;'>", unsafe_allow_html=True)

            if aporte_restante > 0.05:
                st.info(f"💰 **Sobrou {formata_br(aporte_restante)}**. Esse valor representa o 'troco' que não foi suficiente para comprar uma cota inteira adicional dos ativos selecionados.")
            else:
                st.success("✅ Todo o valor foi distribuído com precisão cirúrgica para rebalancear a sua carteira!")
        else:
            st.info("Nenhuma sugestão gerada. Verifique se o valor do aporte é suficiente para comprar os ativos que estão para trás na sua meta.")
