import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import yfinance as yf
import requests
from dateutil.relativedelta import relativedelta
import re
import datetime
from utils import ler_planilha, salvar_configuracao, salvar_ativos_categoria, formata_br

# ==========================================
# CÉREBRO DE DADOS DO BACKTEST (BCB)
# ==========================================
@st.cache_data(ttl=86400, show_spinner=False)
def fetch_bcb_history(codigo, dt_ini, dt_fim):
    url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json&dataInicial={dt_ini.strftime('%d/%m/%Y')}&dataFinal={dt_fim.strftime('%d/%m/%Y')}"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            df = pd.DataFrame(res.json())
            df['Date'] = pd.to_datetime(df['data'], format='%d/%m/%Y')
            df.set_index('Date', inplace=True)
            df['valor'] = df['valor'].astype(float) / 100.0
            return df[['valor']]
    except:
        pass
    return pd.DataFrame()


def render():
    st.title("⚙️ Central de Configuração da Carteira")
    
    if 'backup_macro' not in st.session_state:
        df_conf = ler_planilha("Configuracao")
        user_conf = {}
        if not df_conf.empty:
            df_conf['Email'] = df_conf['Email'].astype(str).str.strip().str.lower()
            row = df_conf[df_conf['Email'] == st.session_state.email]
            if not row.empty:
                user_conf = row.iloc[0].to_dict()
        
        st.session_state.backup_macro = {
            'rf': float(str(user_conf.get('RF', 50.0)).replace(',', '.')),
            'rv': float(str(user_conf.get('RV', 50.0)).replace(',', '.')),
            'rv_br': float(str(user_conf.get('RV_Brasil', 50.0)).replace(',', '.')),
            'rv_ex': float(str(user_conf.get('RV_Exterior', 50.0)).replace(',', '.')),
            'br_ac': float(str(user_conf.get('BR_Acoes', 50.0)).replace(',', '.')),
            'br_fii': float(str(user_conf.get('BR_FIIs', 50.0)).replace(',', '.')),
            'ex_st': float(str(user_conf.get('EX_Stocks', 40.0)).replace(',', '.')),
            'ex_re': float(str(user_conf.get('EX_REITs', 30.0)).replace(',', '.')),
            'ex_et': float(str(user_conf.get('EX_ETFs', 30.0)).replace(',', '.'))
        }

    if 'aba_config' not in st.session_state:
        st.session_state.aba_config = "Metas"

    def mudar_aba_config(nova_aba):
        st.session_state.aba_config = nova_aba

    st.markdown("<br>", unsafe_allow_html=True)
    c_aba1, c_aba2, c_aba3 = st.columns(3)
    
    # ATUALIZADO: width='stretch'
    c_aba1.button(
        "🎯 1. Metas de Alocação", 
        width='stretch', 
        on_click=mudar_aba_config, args=("Metas",),
        type="primary" if st.session_state.aba_config == "Metas" else "secondary"
    )

    c_aba2.button(
        "📋 2. Ativos e Setores", 
        width='stretch', 
        on_click=mudar_aba_config, args=("Ativos",),
        type="primary" if st.session_state.aba_config == "Ativos" else "secondary"
    )
    
    c_aba3.button(
        "⏪ 3. Backtesting", 
        width='stretch', 
        on_click=mudar_aba_config, args=("Backtest",),
        type="primary" if st.session_state.aba_config == "Backtest" else "secondary"
    )
    
    st.markdown("---")

    # ==========================================
    # ABA 1: METAS DE ALOCAÇÃO
    # ==========================================
    if st.session_state.aba_config == "Metas":
        st.markdown("Ajuste seus percentuais macro. O sistema compensa automaticamente para a soma sempre cravar **100%**.")

        if 'rf_val' not in st.session_state:
            st.session_state.rf_val = st.session_state.backup_macro['rf']
            st.session_state.rv_val = st.session_state.backup_macro['rv']
            st.session_state.rv_br_val = st.session_state.backup_macro['rv_br']
            st.session_state.rv_ex_val = st.session_state.backup_macro['rv_ex']
            st.session_state.br_ac_val = st.session_state.backup_macro['br_ac']
            st.session_state.br_fii_val = st.session_state.backup_macro['br_fii']
            st.session_state.ex_st_val = st.session_state.backup_macro['ex_st']
            st.session_state.ex_re_val = st.session_state.backup_macro['ex_re']
            st.session_state.ex_et_val = st.session_state.backup_macro['ex_et']

        def ajusta_macro(modificado):
            if modificado == 'rf': st.session_state.rv_val = round(100.0 - st.session_state.rf_val, 2)
            else: st.session_state.rf_val = round(100.0 - st.session_state.rv_val, 2)
        def ajusta_rv(modificado):
            if modificado == 'br': st.session_state.rv_ex_val = round(100.0 - st.session_state.rv_br_val, 2)
            else: st.session_state.rv_br_val = round(100.0 - st.session_state.rv_ex_val, 2)
        def ajusta_br(modificado):
            if modificado == 'ac': st.session_state.br_fii_val = round(100.0 - st.session_state.br_ac_val, 2)
            else: st.session_state.br_ac_val = round(100.0 - st.session_state.br_fii_val, 2)
        def ajusta_ex(modificado):
            if modificado == 'st':
                novo_et = round(100.0 - st.session_state.ex_st_val - st.session_state.ex_re_val, 2)
                if novo_et < 0:
                    st.session_state.ex_et_val = 0.0
                    st.session_state.ex_re_val = round(100.0 - st.session_state.ex_st_val, 2)
                else: st.session_state.ex_et_val = novo_et
            elif modificado == 're':
                novo_et = round(100.0 - st.session_state.ex_st_val - st.session_state.ex_re_val, 2)
                if novo_et < 0:
                    st.session_state.ex_et_val = 0.0
                    st.session_state.ex_st_val = round(100.0 - st.session_state.ex_re_val, 2)
                else: st.session_state.ex_et_val = novo_et
            elif modificado == 'et':
                novo_st = round(100.0 - st.session_state.ex_et_val - st.session_state.ex_re_val, 2)
                if novo_st < 0:
                    st.session_state.ex_st_val = 0.0
                    st.session_state.ex_re_val = round(100.0 - st.session_state.ex_et_val, 2)
                else: st.session_state.ex_st_val = novo_st

        col_esquerda, col_direita = st.columns([1.4, 1], gap="medium")

        with col_esquerda:
            st.subheader("Nível 1: Macro Alocação")
            c1, c2 = st.columns(2)
            c1.number_input("Renda Fixa (RF) %", min_value=0.0, max_value=100.0, step=1.0, key="rf_val", on_change=ajusta_macro, args=('rf',))
            c2.number_input("Renda Variável (RV) %", min_value=0.0, max_value=100.0, step=1.0, key="rv_val", on_change=ajusta_macro, args=('rv',))

            st.caption("""
            **Ponto de partida:** 50% em cada | **Critério:** quanto consegue ter de volatilidade sem se incomodar  
            **Orientação:** mínimo 20% em renda fixa | **Usufruto:** 50% RF e 50% RV
            """)
            
            st.markdown("---")
            
            st.subheader("Nível 2: Renda Variável")
            c3, c4 = st.columns(2)
            c3.number_input("Brasil %", min_value=0.0, max_value=100.0, step=1.0, key="rv_br_val", on_change=ajusta_rv, args=('br',))
            c4.number_input("Exterior %", min_value=0.0, max_value=100.0, step=1.0, key="rv_ex_val", on_change=ajusta_rv, args=('ex',))

            st.caption("""
            **Ponto de partida:** 70% Brasil e 30% EUA | **Critério:** distância da etapa de usufruto  
            **Orientação:** mínimo 20% e máximo 50% nos EUA (Preferência ETF domiciliado na Irlanda de Acumulação)  
            **Usufruto:** 80% Brasil e 20% Global
            """)
            
            st.markdown("---")
            
            c_b1, c_b2 = st.columns(2)
            with c_b1:
                st.subheader("Nível 3A: Brasil")
                st.number_input("Ações %", min_value=0.0, max_value=100.0, step=1.0, key="br_ac_val", on_change=ajusta_br, args=('ac',))
                st.number_input("FIIs %", min_value=0.0, max_value=100.0, step=1.0, key="br_fii_val", on_change=ajusta_br, args=('fii',))
                    
            with c_b2:
                st.subheader("Nível 3B: Exterior")
                st.number_input("Stocks %", min_value=0.0, max_value=100.0, step=1.0, key="ex_st_val", on_change=ajusta_ex, args=('st',))
                st.number_input("REITs %", min_value=0.0, max_value=100.0, step=1.0, key="ex_re_val", on_change=ajusta_ex, args=('re',))
                st.number_input("ETFs %", min_value=0.0, max_value=100.0, step=1.0, key="ex_et_val", on_change=ajusta_ex, args=('et',))
         
            st.caption("""
            **Ponto de partida:** 50% em cada | **Critério:** distância da etapa de usufruto  
            **Orientação:** no mínimo 30% e máximo 70% tanto em ações/stocks quanto FIIs/REITs. Pelo menos 50% em ETFs Irlandês.  
            **Usufruto:** 30% Ações, 70% FIIs | **Exterior:** 70% REITs, 20% Stocks, 10% ETFs (Migrar para ativos pagadores)
            **Sucessão:** Preferir ETFs Irlandeses e saques mensais, para Stocks/REITs EUA há limite de isenção de US$ 60 mil.
            """)
            
            st.markdown("<br>", unsafe_allow_html=True)
            # ATUALIZADO: width='stretch'
            if st.button("💾 Salvar Configuração Macro", width='stretch', type="primary"):
                dados_para_salvar = {
                    'RF': f"{st.session_state.rf_val:.2f}".replace('.', ','), 
                    'RV': f"{st.session_state.rv_val:.2f}".replace('.', ','), 
                    'RV_Brasil': f"{st.session_state.rv_br_val:.2f}".replace('.', ','), 
                    'RV_Exterior': f"{st.session_state.rv_ex_val:.2f}".replace('.', ','),
                    'BR_Acoes': f"{st.session_state.br_ac_val:.2f}".replace('.', ','), 
                    'BR_FIIs': f"{st.session_state.br_fii_val:.2f}".replace('.', ','), 
                    'EX_Stocks': f"{st.session_state.ex_st_val:.2f}".replace('.', ','), 
                    'EX_REITs': f"{st.session_state.ex_re_val:.2f}".replace('.', ','), 
                    'EX_ETFs': f"{st.session_state.ex_et_val:.2f}".replace('.', ',')
                }
                if salvar_configuracao(st.session_state.email, dados_para_salvar):
                    st.success("✅ Metas atualizadas e persistidas com sucesso! (Precisão travada em 2 casas decimais)")

        with col_direita:
            st.subheader("🎯 Resumo do Objetivo")
            st.markdown("Distribuição real sobre o **patrimônio total**:")
            
            peso_rv = st.session_state.rv_val / 100.0
            peso_br = st.session_state.rv_br_val / 100.0
            peso_ex = st.session_state.rv_ex_val / 100.0
            
            df_resumo = pd.DataFrame({
                "Categoria": ["Renda Fixa", "Ações", "FIIs", "Stocks", "REITs", "ETFs"],
                "% Alvo Final": [
                    st.session_state.rf_val, 
                    peso_rv * peso_br * st.session_state.br_ac_val,
                    peso_rv * peso_br * st.session_state.br_fii_val,
                    peso_rv * peso_ex * st.session_state.ex_st_val,
                    peso_rv * peso_ex * st.session_state.ex_re_val,
                    peso_rv * peso_ex * st.session_state.ex_et_val
                ]
            })
            
            df_resumo_grafico = df_resumo[df_resumo["% Alvo Final"] > 0]
            
            df_resumo['% Alvo Final'] = df_resumo['% Alvo Final'].apply(lambda x: f"{x:.2f}%".replace('.', ','))
            
            df_resumo = df_resumo.reset_index(drop=True)
            st.dataframe(df_resumo, width='stretch', hide_index=True)
            
            fig_resumo = px.pie(df_resumo_grafico, values='% Alvo Final', names="Categoria", hole=0.5)
            fig_resumo.update_traces(textinfo='label+percent')
            fig_resumo.update_layout(height=300, margin=dict(t=10, b=10, l=10, r=10), showlegend=False)
            st.plotly_chart(fig_resumo, width='stretch')

        st.session_state.backup_macro.update({
            'rf': st.session_state.rf_val, 'rv': st.session_state.rv_val,
            'rv_br': st.session_state.rv_br_val, 'rv_ex': st.session_state.rv_ex_val,
            'br_ac': st.session_state.br_ac_val, 'br_fii': st.session_state.br_fii_val,
            'ex_st': st.session_state.ex_st_val, 'ex_re': st.session_state.ex_re_val,
            'ex_et': st.session_state.ex_et_val
        })

    # ==========================================
    # ABA 2: ATIVOS E SETORES
    # ==========================================
    elif st.session_state.aba_config == "Ativos":
        st.subheader("📋 Composição de Ativos por Categoria")
        st.markdown("Adicione os ativos (tickers) e defina a porcentagem interna de cada um. A soma de cada categoria deve fechar exatamente 100%.")

        if 'cat_config' not in st.session_state:
            st.session_state.cat_config = "Ações"

        def mudar_cat_config(nova_cat):
            st.session_state.cat_config = nova_cat

        st.markdown("<br>", unsafe_allow_html=True)
        categorias = ["Ações", "FIIs", "Stocks", "REITs", "ETFs"]
        cols_cat = st.columns(len(categorias))
        
        for i, cat in enumerate(categorias):
            # ATUALIZADO: width='stretch'
            cols_cat[i].button(
                cat, width='stretch', on_click=mudar_cat_config, args=(cat,),
                type="primary" if st.session_state.cat_config == cat else "secondary",
                key=f"btn_nav_{cat}"
            )
        
        cat_selecionada = st.session_state.cat_config
        st.markdown("---")
        st.markdown(f"### ⚙️ Editando: **{cat_selecionada}**")

        df_ativos_existentes = ler_planilha("Ativos_Config")
        if not df_ativos_existentes.empty and 'Email' in df_ativos_existentes.columns:
            df_ativos_existentes['Email'] = df_ativos_existentes['Email'].astype(str).str.strip().str.lower()
            df_ativos_existentes['Categoria'] = df_ativos_existentes['Categoria'].astype(str).str.strip()
            df_ativos_user = df_ativos_existentes[df_ativos_existentes['Email'] == st.session_state.email]
        else:
            df_ativos_user = pd.DataFrame(columns=['Email', 'Categoria', 'Ativo', 'Peso'])

        cols_disp = ['Ativo', 'Peso']
        if 'Setor' in df_ativos_user.columns:
            cols_disp.append('Setor')
            
        df_cat_salvo = df_ativos_user[df_ativos_user['Categoria'] == cat_selecionada][cols_disp].copy()
        
        if 'Setor' not in df_cat_salvo.columns:
            df_cat_salvo['Setor'] = ''
            
        if df_cat_salvo.empty:
            df_inicial = pd.DataFrame({"Ativo": [""], "Peso (%)": ["100,00"], "Setor": [""]})
        else:
            df_cat_salvo.rename(columns={'Peso': 'Peso (%)'}, inplace=True)
            df_cat_salvo['Peso (%)'] = pd.to_numeric(df_cat_salvo['Peso (%)'].astype(str).str.replace(',', '.'), errors='coerce').apply(lambda x: f"{x:.2f}".replace('.', ','))
            df_cat_salvo['Setor'] = df_cat_salvo['Setor'].replace(['Não Classificado', 'nan', 'None'], '')
            df_inicial = df_cat_salvo

        col_tabela, col_graf_setor = st.columns([1.5, 1], gap="medium")
        
        with col_tabela:
            df_inicial = df_inicial.reset_index(drop=True)
            
            df_editado = st.data_editor(
                df_inicial,
                num_rows="dynamic",
                width='stretch',
                hide_index=True, 
                key=f"editor_cat_v2_{cat_selecionada}",
                column_config={
                    "Ativo": st.column_config.TextColumn("Ativo (Ticker)", required=True),
                    "Peso (%)": st.column_config.TextColumn("Peso (%) (Ex: 10,50)"),
                    "Setor": st.column_config.TextColumn(
                        "Setor / Segmento", 
                        help="Deixe em branco e o sistema preencherá automaticamente ao salvar!", 
                        default=""
                    )
                }
            )

            soma_pesos = pd.to_numeric(df_editado['Peso (%)'].astype(str).str.replace(',', '.'), errors='coerce').sum()
            
            col_info, col_btn = st.columns([2, 1])
            with col_info:
                if abs(soma_pesos - 100.0) < 0.01:
                    st.success(f"✅ Soma: **{str(round(soma_pesos, 2)).replace('.', ',')}%**")
                else:
                    st.warning(f"⚠️ Soma: **{str(round(soma_pesos, 2)).replace('.', ',')}%** (O ideal é 100%)")
            
            with col_btn:
                # ATUALIZADO: width='stretch'
                if st.button(f"💾 Salvar {cat_selecionada}", key=f"btn_save_{cat_selecionada}", width='stretch'):
                    df_para_salvar = df_editado.copy()
                    df_para_salvar.rename(columns={'Peso (%)': 'Peso'}, inplace=True)
                    
                    df_para_salvar['Peso'] = pd.to_numeric(df_para_salvar['Peso'].astype(str).str.replace(',', '.'), errors='coerce').apply(lambda x: f"{x:.2f}".replace('.', ','))
                    
                    with st.spinner("Validando ativos na Bolsa..."):
                        ativos_invalidos = []
                        if cat_selecionada != "Renda Fixa":
                            for ativo in df_para_salvar['Ativo']:
                                ativo_str = str(ativo).strip().upper()
                                if not ativo_str or ativo_str == 'NAN':
                                    continue
                                    
                                ticker = ativo_str
                                if cat_selecionada in ["Ações", "FIIs"]:
                                    if "." not in ticker and re.search(r'\d+$', ticker):
                                        ticker = f"{ticker}.SA"
                                
                                try:
                                    if yf.Ticker(ticker).history(period="1d").empty:
                                        ativos_invalidos.append(ativo_str)
                                except:
                                    ativos_invalidos.append(ativo_str)
                                    
                        if ativos_invalidos:
                            st.error(f"❌ **Ativo(s) Inválido(s):** Não encontramos `{', '.join(ativos_invalidos)}` no Yahoo Finance. Verifique se o código está correto antes de salvar.")
                        else:
                            if salvar_ativos_categoria(st.session_state.email, cat_selecionada, df_para_salvar):
                                st.success("Todos os ativos validados e salvos com formatação correta!")
                                st.rerun()

        with col_graf_setor:
            st.markdown(f"**Exposição Setorial Alvo ({cat_selecionada})**")
            df_setores = df_editado.copy()
            df_setores['Peso (%)'] = pd.to_numeric(df_setores['Peso (%)'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
            df_setores['Setor'] = df_setores['Setor'].fillna('Pendente').apply(lambda x: 'Pendente (Auto)' if str(x).strip() == '' else x)
            
            df_group_setor = df_setores.groupby('Setor')['Peso (%)'].sum().reset_index()
            df_group_setor = df_group_setor[df_group_setor['Peso (%)'] > 0]
            
            if not df_group_setor.empty:
                fig_setores = px.pie(df_group_setor, values='Peso (%)', names='Setor', hole=0.4)
                fig_setores.update_traces(textinfo='percent', textposition='inside')
                fig_setores.update_layout(height=280, margin=dict(t=10, b=10, l=10, r=10), showlegend=True, legend=dict(orientation="h", y=-0.2))
                st.plotly_chart(fig_setores, width='stretch')
            else:
                st.info("Preencha a tabela para ver a distribuição.")


    # ==========================================
    # ABA 3: BACKTESTING DE ESTRATÉGIA COM APORTES MENSAIS
    # ==========================================
    elif st.session_state.aba_config == "Backtest":
        st.subheader("⏪ Máquina do Tempo (Backtesting DCA)")
        st.markdown("Descubra como a sua **configuração de pesos atual** teria performado no passado com **aportes regulares**.")

        user_conf = st.session_state.backup_macro
        peso_rv = user_conf['rv'] / 100.0
        peso_br = user_conf['rv_br'] / 100.0
        peso_ex = user_conf['rv_ex'] / 100.0

        cat_targets = {
            "Ações": peso_rv * peso_br * (user_conf['br_ac'] / 100.0),
            "FIIs": peso_rv * peso_br * (user_conf['br_fii'] / 100.0),
            "Stocks": peso_rv * peso_ex * (user_conf['ex_st'] / 100.0),
            "REITs": peso_rv * peso_ex * (user_conf['ex_re'] / 100.0),
            "ETFs": peso_rv * peso_ex * (user_conf['ex_et'] / 100.0),
        }
        
        peso_rf_global = user_conf['rf'] / 100.0

        df_ativos_existentes = ler_planilha("Ativos_Config")
        ativos_alvo = {}
        
        if not df_ativos_existentes.empty and 'Email' in df_ativos_existentes.columns:
            df_ativos_existentes['Email'] = df_ativos_existentes['Email'].astype(str).str.strip().str.lower()
            df_ativos_user = df_ativos_existentes[df_ativos_existentes['Email'] == st.session_state.email]
            
            for _, row in df_ativos_user.iterrows():
                cat = str(row.get('Categoria', '')).strip()
                ativo = str(row.get('Ativo', '')).strip().upper()
                peso_interno = float(str(row.get('Peso', 0)).replace(',', '.')) / 100.0
                
                peso_global = cat_targets.get(cat, 0) * peso_interno
                if peso_global > 0 and ativo and ativo != "NAN":
                    ticker = ativo
                    if cat in ["Ações", "FIIs"]:
                        if "." not in ticker and re.search(r'\d+$', ticker):
                            ticker = f"{ticker}.SA"
                    ativos_alvo[ticker] = peso_global
                    
        total_w = sum(ativos_alvo.values()) + peso_rf_global
        if total_w > 0:
            ativos_alvo = {k: v / total_w for k, v in ativos_alvo.items()}
            peso_rf_global = peso_rf_global / total_w

        if len(ativos_alvo) == 0 and peso_rf_global == 0:
            st.warning("⚠️ Você precisa preencher as abas 'Metas' e 'Ativos' antes de rodar o Backtest.")
            return

        st.markdown("---")
        c_opts1, c_opts2, c_opts3, c_opts4 = st.columns([1, 1, 1, 1.2]) 
        
        opcoes_tempo = {"1 Ano": 1, "3 Anos": 3, "5 Anos": 5, "10 Anos": 10, "20 Anos": 20, "Máximo Possível": 30}
        anos_str = c_opts1.selectbox("⏳ Período:", list(opcoes_tempo.keys()), index=2)
        anos_int = opcoes_tempo[anos_str]
        
        aporte_inicial = c_opts2.number_input("💵 Aporte Inicial (R$):", min_value=0.0, value=5000.0, step=1000.0)
        aporte_mensal = c_opts3.number_input("🔁 Aporte Mensal (R$):", min_value=0.0, value=1000.0, step=100.0)
        
        with c_opts4:
            st.markdown("<div style='margin-bottom: 0.3rem;'><b>📊 Comparativos:</b></div>", unsafe_allow_html=True)
            c_sub1, c_sub2 = st.columns(2)
            chk_cdi = c_sub1.checkbox("CDI", value=True)
            chk_sp500 = c_sub1.checkbox("S&P 500", value=False)
            chk_ibov = c_sub2.checkbox("IBOVESPA", value=True)
            chk_ipca = c_sub2.checkbox("IPCA", value=False)
            
        benchmarks = []
        if chk_cdi: benchmarks.append("CDI")
        if chk_ibov: benchmarks.append("IBOVESPA")
        if chk_sp500: benchmarks.append("S&P 500 (BRL)")
        if chk_ipca: benchmarks.append("IPCA")

        if aporte_inicial == 0 and aporte_mensal == 0:
            st.warning("Insira um Aporte Inicial ou Aporte Mensal para realizar a simulação.")
            return

        # ATUALIZADO: width='stretch'
        if st.button("🚀 Rodar Backtest da Carteira", width='stretch', type="primary"):
            with st.spinner(f"Viajando no tempo e investindo todos os meses por {anos_str}..."):
                
                hoje = datetime.datetime.today()
                dt_ini = hoje - relativedelta(years=anos_int)
                dt_fim = hoje
                
                dt_ini_str = dt_ini.strftime('%Y-%m-%d')
                dt_fim_str = dt_fim.strftime('%Y-%m-%d')
                
                tickers_download = list(ativos_alvo.keys())
                
                tem_exterior = any(not t.endswith('.SA') for t in ativos_alvo.keys())
                if tem_exterior and 'BRL=X' not in tickers_download:
                    tickers_download.append('BRL=X')
                    
                if "IBOVESPA" in benchmarks: tickers_download.append('^BVSP')
                if "S&P 500 (BRL)" in benchmarks: 
                    tickers_download.extend(['^GSPC', 'BRL=X'])
                
                tickers_list = list(set(tickers_download))
                df_raw = yf.download(tickers_list, start=dt_ini_str, end=dt_fim_str, progress=False, ignore_tz=True)
                
                if df_raw.empty:
                    st.error("Não foi possível buscar o histórico de preços. O servidor do Yahoo Finance pode estar instável.")
                    return
                
                if isinstance(df_raw.columns, pd.MultiIndex):
                    lvl_0 = df_raw.columns.get_level_values(0)
                    lvl_1 = df_raw.columns.get_level_values(1)
                    
                    if 'Adj Close' in lvl_0:
                        df_prices = df_raw['Adj Close']
                    elif 'Close' in lvl_0:
                        df_prices = df_raw['Close']
                    elif 'Adj Close' in lvl_1:
                        df_prices = df_raw.xs('Adj Close', axis=1, level=1)
                    elif 'Close' in lvl_1:
                        df_prices = df_raw.xs('Close', axis=1, level=1)
                    else:
                        st.error("Não encontramos a coluna de Fechamento nos dados do Yahoo Finance.")
                        return
                else:
                    col_target = 'Adj Close' if 'Adj Close' in df_raw.columns else 'Close'
                    if col_target in df_raw.columns:
                        df_prices = df_raw[[col_target]].copy()
                        df_prices.columns = [tickers_list[0]]
                    else:
                        df_prices = df_raw.iloc[:, [0]].copy()
                        df_prices.columns = [tickers_list[0]]
                        
                if isinstance(df_prices, pd.Series):
                    df_prices = df_prices.to_frame(name=tickers_list[0])
                
                port_tickers = [t for t in ativos_alvo.keys() if t in df_prices.columns]
                
                if len(port_tickers) == 0 and peso_rf_global == 0:
                    st.error("Não foi possível localizar o histórico de nenhum ativo da sua carteira.")
                    return
                
                if port_tickers:
                    df_port_prices = df_prices[port_tickers].copy()
                    if tem_exterior and 'BRL=X' in df_prices.columns:
                        for t in port_tickers:
                            if not t.endswith('.SA'):
                                df_port_prices[t] = df_port_prices[t] * df_prices['BRL=X']
                else:
                    df_port_prices = pd.DataFrame(index=[dt_ini])
                
                ativos_novatos = []
                data_limite = pd.to_datetime(dt_ini_str) + pd.DateOffset(days=30)
                
                if port_tickers:
                    for t in port_tickers:
                        primeiro_dado = df_port_prices[t].first_valid_index()
                        if pd.notna(primeiro_dado) and primeiro_dado > data_limite:
                            ativos_novatos.append(f"`{t}` ({primeiro_dado.strftime('%m/%Y')})")
                
                if ativos_novatos:
                    st.info(f"💡 **Caixa Inteligente:** A simulação de **{anos_str}** foi mantida intacta! Como os ativos a seguir não existiam no início, o sistema simulou o peso deles rendendo 100% do CDI até o dia do lançamento: {', '.join(ativos_novatos)}.")

                actual_start_date = dt_ini 
                
                if port_tickers:
                    df_port_ret = df_port_prices.resample('ME').last().pct_change()
                    df_port_ret.index = df_port_ret.index.strftime('%Y-%m')
                else:
                    df_port_ret = pd.DataFrame()
                
                df_cdi = fetch_bcb_history(4391, actual_start_date - pd.DateOffset(months=1), dt_fim)
                if not df_cdi.empty:
                    df_cdi.index = df_cdi.index.strftime('%Y-%m')
                    df_cdi.rename(columns={'valor': 'CDI'}, inplace=True)
                
                df_ipca = pd.DataFrame()
                if "IPCA" in benchmarks:
                    df_ipca = fetch_bcb_history(433, actual_start_date - pd.DateOffset(months=1), dt_fim)
                    if not df_ipca.empty:
                        df_ipca.index = df_ipca.index.strftime('%Y-%m')
                        df_ipca.rename(columns={'valor': 'IPCA'}, inplace=True)
                
                df_merged = df_port_ret.join(df_cdi, how='outer')
                if not df_ipca.empty:
                    df_merged = df_merged.join(df_ipca, how='outer')
                    
                if 'CDI' in df_merged.columns:
                    for t in port_tickers:
                        df_merged[t] = df_merged[t].fillna(df_merged['CDI'])
                
                df_merged = df_merged.fillna(0)
                
                port_returns = pd.Series(0.0, index=df_merged.index)
                for t in port_tickers:
                    port_returns += df_merged[t] * ativos_alvo[t]
                if peso_rf_global > 0 and 'CDI' in df_merged.columns:
                    port_returns += df_merged['CDI'] * peso_rf_global
                df_merged['Sua Carteira'] = port_returns
                
                colunas_acumular = ['Sua Carteira']
                
                if "CDI" in benchmarks and 'CDI' in df_merged.columns:
                    colunas_acumular.append('CDI')
                if "IPCA" in benchmarks and 'IPCA' in df_merged.columns:
                    colunas_acumular.append('IPCA')
                if "IBOVESPA" in benchmarks and '^BVSP' in df_prices.columns:
                    ibov_ret = df_prices['^BVSP'].resample('ME').last().pct_change().dropna()
                    ibov_ret.index = ibov_ret.index.strftime('%Y-%m')
                    df_merged = df_merged.join(ibov_ret.rename('IBOV'), how='left').fillna(0)
                    colunas_acumular.append('IBOV')
                if "S&P 500 (BRL)" in benchmarks and '^GSPC' in df_prices.columns and 'BRL=X' in df_prices.columns:
                    sp_brl = df_prices['^GSPC'] * df_prices['BRL=X']
                    sp_ret = sp_brl.resample('ME').last().pct_change().dropna()
                    sp_ret.index = sp_ret.index.strftime('%Y-%m')
                    df_merged = df_merged.join(sp_ret.rename('SP500_BRL'), how='left').fillna(0)
                    colunas_acumular.append('SP500_BRL')

                if df_merged.iloc[0].sum() == 0:
                    df_merged = df_merged.iloc[1:]

                df_cum = pd.DataFrame(index=df_merged.index, columns=colunas_acumular)
                linha_custo = []
                
                saldos = {c: aporte_inicial for c in colunas_acumular}
                total_bolso = aporte_inicial
                
                for idx, row in df_merged.iterrows():
                    for c in colunas_acumular:
                        saldos[c] = saldos[c] * (1 + row.get(c, 0.0))
                        saldos[c] += aporte_mensal
                        df_cum.loc[idx, c] = saldos[c]
                        
                    total_bolso += aporte_mensal
                    linha_custo.append(total_bolso)
                        
                df_cum['Total_Investido'] = linha_custo

                try:
                    mes_zero = (pd.to_datetime(df_cum.index[0] + '-01') - pd.DateOffset(months=1)).strftime('%Y-%m')
                    linha_zero = {c: aporte_inicial for c in colunas_acumular}
                    linha_zero['Total_Investido'] = aporte_inicial
                    df_cum.loc[mes_zero] = linha_zero
                    df_cum = df_cum.sort_index()
                except:
                    pass

                st.markdown("### 🏆 Resultado da Simulação")
                
                val_final_port = df_cum['Sua Carteira'].iloc[-1]
                custo_final = df_cum['Total_Investido'].iloc[-1]
                lucro_rs = val_final_port - custo_final
                lucro_pct = (lucro_rs / custo_final) * 100 if custo_final > 0 else 0
                
                kpi1, kpi2, kpi3, kpi4 = st.columns(4)
                kpi1.metric("Total Investido", formata_br(custo_final))
                kpi2.metric("Valor Final da Carteira", formata_br(val_final_port))
                kpi3.metric("Lucro Limpo (R$)", formata_br(lucro_rs))
                kpi4.metric("Rentabilidade da Carteira", f"+{lucro_pct:.2f}%".replace('.', ','), delta_color="normal")

                st.markdown("---")
                
                fig = go.Figure()

                fig.add_trace(go.Scatter(
                    x=df_cum.index, y=df_cum['Total_Investido'],
                    mode='lines', name='Seu Dinheiro Investido',
                    line=dict(color='#8c92ac', width=3, dash='dot'),
                    fill='tozeroy', fillcolor='rgba(140, 146, 172, 0.1)',
                    hovertemplate="Investido (Bolso): R$ %{y:,.2f}<extra></extra>"
                ))

                fig.add_trace(go.Scatter(
                    x=df_cum.index, y=df_cum['Sua Carteira'],
                    mode='lines', name='Sua Carteira',
                    line=dict(color='#00cc96', width=4),
                    hovertemplate="Sua Carteira: R$ %{y:,.2f}<extra></extra>"
                ))

                dic_cores = {'CDI': '#ffbf00', 'IBOV': '#33b5e5', 'SP500_BRL': '#ff4444', 'IPCA': '#9933cc'}
                dic_nomes = {'CDI': 'Teórico CDI', 'IBOV': 'Teórico IBOVESPA', 'SP500_BRL': 'Teórico S&P 500 (BRL)', 'IPCA': 'Correção IPCA'}
                
                for col in colunas_acumular:
                    if col != 'Sua Carteira':
                        fig.add_trace(go.Scatter(
                            x=df_cum.index, y=df_cum[col],
                            mode='lines', name=dic_nomes.get(col, col),
                            line=dict(color=dic_cores.get(col, '#ffffff'), width=2, dash='dash'),
                            hovertemplate=dic_nomes.get(col, col) + ": R$ %{y:,.2f}<extra></extra>"
                        ))

                fig.update_layout(
                    height=500, 
                    margin=dict(l=0, r=0, t=30, b=0),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                    hovermode="x unified", 
                    xaxis=dict(showgrid=False), 
                    yaxis=dict(tickformat=",.2f")
                )
                
                st.plotly_chart(fig, width='stretch')
                st.caption("Nota: Este backtest adota a premissa de que você comprou frações exatas e fez o rebalanceamento invisível perfeito todos os meses seguindo sua alocação macro e micro atual.")
