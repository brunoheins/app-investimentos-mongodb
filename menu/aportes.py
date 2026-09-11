import streamlit as st
import pandas as pd
import yfinance as yf
from utils import ler_planilha, formata_br, obter_cotacoes, extrair_numero_br, calcular_termometro_macro_usuario

# ==========================================
# ARMADURA NUMÉRICA UNIVERSAL
# ==========================================
def limpa_numero_seguro(val):
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
    email_lower = str(email).strip().lower()
    df_conf = ler_planilha("Configuracao")
    df_ativos_conf = ler_planilha("Ativos_Config")
    df_invest = ler_planilha("Investimentos")

    if not df_conf.empty: df_conf.columns = [str(c).strip() for c in df_conf.columns]

    if df_conf.empty or email_lower not in df_conf['Email'].astype(str).str.strip().str.lower().values:
        return [], valor_aporte, None, "Metas de Alocação Macro não definidas na Configuração."
    
    if df_ativos_conf.empty:
        df_ativos_conf = pd.DataFrame(columns=['Email', 'Categoria', 'Ativo', 'Peso'])

    df_conf['Email'] = df_conf['Email'].astype(str).str.strip().str.lower()
    user_conf = df_conf[df_conf['Email'] == email_lower].iloc[0].to_dict()

    peso_rv = extrair_numero_br(user_conf.get('RV', 50)) / 100.0
    peso_br = extrair_numero_br(user_conf.get('RV_Brasil', 50)) / 100.0
    peso_ex = extrair_numero_br(user_conf.get('RV_Exterior', 50)) / 100.0

    cat_targets = {
        "Renda Fixa": extrair_numero_br(user_conf.get('RF', 50)) / 100.0,
        "Ações": peso_rv * peso_br * (extrair_numero_br(user_conf.get('BR_Acoes', 50)) / 100.0),
        "FIIs": peso_rv * peso_br * (extrair_numero_br(user_conf.get('BR_FIIs', 50)) / 100.0),
        "Stocks": peso_rv * peso_ex * (extrair_numero_br(user_conf.get('EX_Stocks', 40)) / 100.0),
        "REITs": peso_rv * peso_ex * (extrair_numero_br(user_conf.get('EX_REITs', 30)) / 100.0),
        "ETFs": peso_rv * peso_ex * (extrair_numero_br(user_conf.get('EX_ETFs', 30)) / 100.0),
    }

    df_ativos_conf['Email'] = df_ativos_conf['Email'].astype(str).str.strip().str.lower()
    df_user_ativos = df_ativos_conf[df_ativos_conf['Email'] == email_lower].copy()
    
    cotacoes_dict = obter_cotacoes(email_lower)

    # --- 1. LER ATIVOS ALVOS OFICIAIS ---
    ativos_alvos = []
    for _, row in df_user_ativos.iterrows():
        cat = normalizar_categoria(row['Categoria'])
        if cat == "Renda Fixa": continue 
        ativo = str(row['Ativo']).strip().upper()
        val_peso = row.get('Peso') if pd.notna(row.get('Peso')) else row.get('Peso (%)', 0)
        peso_global = cat_targets.get(cat, 0) * (extrair_numero_br(val_peso) / 100.0)
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
        df_user_invest = df_invest[df_invest['Email'] == email_lower].copy()
        
        if not df_user_invest.empty:
            df_user_invest['Ativo'] = df_user_invest['Ativo'].astype(str).str.strip().str.upper()
            df_user_invest['Categoria'] = df_user_invest['Categoria'].apply(normalizar_categoria)
            df_user_invest['Quantidade'] = df_user_invest['Quantidade'].apply(extrair_numero_br)
            df_user_invest['PrecoLive'] = df_user_invest['Ativo'].map(cotacoes_dict).fillna(0.0)
            df_user_invest['TotalAtual'] = df_user_invest['Quantidade'] * df_user_invest['PrecoLive']
            
            col_preco = next((c for c in df_user_invest.columns if 'prec' in str(c).lower() or 'custo' in str(c).lower()), 'Preco')

            for idx_inv, row_inv in df_user_invest.iterrows():
                if row_inv['Categoria'] == "Renda Fixa" and row_inv['TotalAtual'] == 0:
                    preco_digitado = extrair_numero_br(row_inv.get(col_preco, 0))
                    df_user_invest.at[idx_inv, 'TotalAtual'] = row_inv['Quantidade'] * preco_digitado

            df_user_invest.loc[df_user_invest['Categoria'] == 'Renda Fixa', 'Ativo'] = 'OPORTUNIDADE DE RENDA FIXA'

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

    # --- UTILIZA O TERMÔMETRO CENTRALIZADO DO UTILS ---
    df_resumo_macro, _, erro_macro = calcular_termometro_macro_usuario(email_lower)
    if erro_macro:
        return [], valor_aporte, None, erro_macro

    # Recalcula o Alvo(%) com base no total_futuro para o motor de aportes funcionar perfeitamente
    df_calc_macro = df_calc.groupby('Categoria')['ValorAlvo'].sum().reset_index()
    df_resumo_macro = pd.merge(df_resumo_macro[['Categoria', 'Atual (%)', 'Status']], df_calc_macro, on='Categoria')
    df_resumo_macro['Alvo (%)'] = (df_resumo_macro['ValorAlvo'] / total_futuro * 100).round(1) if total_futuro > 0 else 0
    df_resumo_macro['Alvo'] = df_resumo_macro['ValorAlvo']
    df_resumo_macro['Atual'] = df_resumo_macro['Alvo'] - df_resumo_macro['ValorAlvo'] # Ajuste para compatibilidade

    # ==========================================
    # CASCATA HIERÁRQUICA ESTRITA
    # ==========================================
    df_resumo_macro['Deficit_Perc'] = df_resumo_macro['Alvo (%)'] - df_resumo_macro['Atual (%)']
    df_macro_ordem = df_resumo_macro[df_resumo_macro['Deficit_Perc'] > 0].sort_values(by=['Deficit_Perc', 'Alvo'], ascending=[False, False])
    
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
            'Falta_Comprar': row['Falta_Comprar'],
            'ValorAlvo': row['ValorAlvo']
        }

    # ==========================================
    # LÓGICA DIFERENCIADA: DIVIDIR vs INTEGRAL
    # ==========================================
    if not dividir:
        # ----------------------------------------------------
        # APORTE INTEGRAL: Joga todo o dinheiro em UM ÚNICO ATIVO
        # ----------------------------------------------------
        if not df_macro_ordem.empty:
            melhor_cat = df_macro_ordem.iloc[0]['Categoria']
            df_ativos_cat = df_disp[(df_disp['Categoria'] == melhor_cat) & (df_disp['Falta_Comprar'] > 0)].copy()
            
            if df_ativos_cat.empty:
                df_ativos_cat = df_disp[df_disp['Falta_Comprar'] > 0].copy()
                
            if not df_ativos_cat.empty:
                df_ativos_cat['Dist_Relativa'] = df_ativos_cat['Falta_Comprar'] / df_ativos_cat['ValorAlvo']
                df_ativos_cat = df_ativos_cat.sort_values(by=['Dist_Relativa', 'Falta_Comprar'], ascending=[False, False])
                
                row_escolhida = df_ativos_cat.iloc[0]
                ativo = row_escolhida['Ativo']
                d = compras_dict[ativo]
                preco = d['PrecoRef']
                
                if d['Is_RV'] and d['Is_BR']:
                    if preco > 0 and aporte_restante >= preco:
                        qtd = int(aporte_restante / preco)
                        gasto = qtd * preco
                    else:
                        qtd, gasto = 0, 0
                elif d['Is_RV'] and not d['Is_BR']:
                    qtd = aporte_restante / preco if preco > 0 else 0
                    gasto = aporte_restante
                else:
                    qtd = 0
                    gasto = aporte_restante
                    
                d['Valor'] += gasto
                d['Qtd'] += qtd
                aporte_restante -= gasto
    else:
        # ----------------------------------------------------
        # DIVIDIR PELO OBJETIVO: Rateio em Cascata Macro ➔ Micro
        # ----------------------------------------------------
        for idx_cat, row_cat in df_macro_ordem.iterrows():
            categoria = row_cat['Categoria']
            falta_macro_rs = row_cat['Alvo'] - row_cat['Atual']
            
            if aporte_restante <= 0.01: break
            
            budget_cat = min(aporte_restante, falta_macro_rs)
            if budget_cat <= 0: continue

            df_ativos_cat = df_disp[(df_disp['Categoria'] == categoria) & (df_disp['Falta_Comprar'] > 0)].copy()
            if df_ativos_cat.empty: continue

            zerados = df_ativos_cat[df_ativos_cat['TotalAtual_Original'] == 0].sort_values(by='PesoGlobal', ascending=False)
            for _, row_atv in zerados.iterrows():
                if budget_cat <= 0: break
                ativo = row_atv['Ativo']
                d = compras_dict[ativo]
                preco = d['PrecoRef']
                
                if d['Is_RV'] and d['Is_BR']:
                    if preco > 0 and budget_cat >= preco:
                        d['Valor'] += preco
                        d['Qtd'] += 1
                        d['Falta_Comprar'] -= preco
                        budget_cat -= preco
                        aporte_restante -= preco
                else:
                    gasto = min(budget_cat, d['Falta_Comprar'])
                    if gasto > 0:
                        qtd = gasto / preco if (preco > 0 and d['Is_RV']) else 0
                        d['Valor'] += gasto
                        d['Qtd'] += qtd
                        d['Falta_Comprar'] -= gasto
                        budget_cat -= preco
                        aporte_restante -= preco
            
            df_ativos_cat['Falta_Comprar_Atual'] = df_ativos_cat['Ativo'].apply(lambda x: compras_dict[x]['Falta_Comprar'])
            df_ativos_cat = df_ativos_cat[df_ativos_cat['Falta_Comprar_Atual'] > 0]
            
            if not df_ativos_cat.empty and budget_cat > 0:
                total_gap_cat = df_ativos_cat['Falta_Comprar_Atual'].sum()
                budget_para_dividir = budget_cat
                
                for _, row_atv in df_ativos_cat.iterrows():
                    ativo = row_atv['Ativo']
                    d = compras_dict[ativo]
                    preco = d['PrecoRef']
                    
                    fator = d['Falta_Comprar'] / total_gap_cat if total_gap_cat > 0 else 1/len(df_ativos_cat)
                    aloc_asset = min(budget_para_dividir * fator, d['Falta_Comprar'])
                    
                    if d['Is_RV'] and d['Is_BR']:
                        if preco > 0 and aloc_asset >= preco:
                            qtd = int(aloc_asset / preco)
                            gasto = qtd * preco
                        else:
                            qtd, gasto = 0, 0
                    elif d['Is_RV'] and not d['Is_BR']:
                        qtd = aloc_asset / preco if preco > 0 else 0
                        gasto = aloc_asset
                    else:
                        qtd = 0
                        gasto = aloc_asset
                        
                    d['Valor'] += gasto
                    d['Qtd'] += qtd
                    d['Falta_Comprar'] -= gasto
                    budget_cat -= gasto
                    aporte_restante -= gasto

        # ==========================================
        # OTIMIZADOR DE TROCOS GLOBAIS (Apenas para modo Dividir)
        # ==========================================
        def get_cat_priority(cat):
            val = df_resumo_macro.loc[df_resumo_macro['Categoria'] == cat, 'Deficit_Perc'].values
            return val[0] if len(val) > 0 else -999

        comprou_no_loop = True
        while aporte_restante > 0.01 and comprou_no_loop:
            comprou_no_loop = False
            ativos_ordenados = sorted(
                compras_dict.values(), 
                key=lambda x: (
                    get_cat_priority(x['Categoria']), 
                    x['Falta_Comprar'] / x['ValorAlvo'] if x['ValorAlvo'] > 0 else 0
                ), 
                reverse=True
            )
            
            for d in ativos_ordenados:
                if d['Falta_Comprar'] <= 0: continue
                preco = d['PrecoRef']
                if d['Is_RV'] and d['Is_BR'] and preco > 0 and aporte_restante >= preco:
                    d['Valor'] += preco
                    d['Qtd'] += 1
                    d['Falta_Comprar'] -= preco
                    aporte_restante -= preco
                    comprou_no_loop = True
                    break 

    # --- 5. MONTAGEM FINAL DO EXTRATO DE COMPRAS ---
    ativos_comprados = [d for d in compras_dict.values() if d['Valor'] > 0]
    
    def get_cat_priority(cat):
        val = df_resumo_macro.loc[df_resumo_macro['Categoria'] == cat, 'Deficit_Perc'].values
        return val[0] if len(val) > 0 else -999

    ativos_comprados.sort(
        key=lambda x: (
            get_cat_priority(x['Categoria']), 
            x['Falta_Comprar'] / x['ValorAlvo'] if x['ValorAlvo'] > 0 else 0
        ), 
        reverse=True
    )

    compras = []
    ordem = 1
    for d in ativos_comprados:
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
    
    if st.button("🚀 Calcular Onde Aportar", width='stretch', type="primary"):
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
