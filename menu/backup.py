import streamlit as st
import pandas as pd
import tempfile
import os
from utils import ler_planilha, deletar_registros_usuario, inserir_lote_registros

def render():
    st.title("📊 Importar e Exportar Dados (Excel)")
    st.markdown("Faça o backup completo ou a restauração dos seus dados utilizando planilhas do Excel (.xlsx).")
    
    email_logado = st.session_state.email.strip().lower()
    
    # ==========================================
    # MÁGICA VISUAL: NAVEGAÇÃO COM BOTÕES NATIVOS
    # ==========================================
    if "tela_backup" not in st.session_state:
        st.session_state.tela_backup = "exportar"
        
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("📤 Exportar para Excel", use_container_width=True, type="primary" if st.session_state.tela_backup == "exportar" else "secondary"):
            st.session_state.tela_backup = "exportar"
            st.rerun()
            
    with col2:
        if st.button("📥 Importar do Excel", use_container_width=True, type="primary" if st.session_state.tela_backup == "importar" else "secondary"):
            st.session_state.tela_backup = "importar"
            st.rerun()

    st.divider()
    
    # ==========================================
    # LÓGICA DE EXPORTAÇÃO (EXCEL FÍSICO)
    # ==========================================
    if st.session_state.tela_backup == "exportar":
        st.subheader("Gerar Planilha de Backup")
        st.write("Baixe todas as suas informações em um arquivo Excel consolidado. O arquivo conterá abas separadas para cada seção, preservando sua privacidade (sem a coluna de e-mail).")
        
        if st.button("Gerar Arquivo Excel", type="primary", use_container_width=True):
            with st.spinner("Compilando seus dados em Excel..."):
                abas_alvo = ["Configuracao", "Ativos_Config", "Depositos", "Investimentos"]
                
                with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
                    caminho_temp = tmp.name
                    
                try:
                    with pd.ExcelWriter(caminho_temp, engine='xlsxwriter') as writer:
                        for aba in abas_alvo:
                            df = ler_planilha(aba)
                            if not df.empty and 'Email' in df.columns:
                                df['Email'] = df['Email'].astype(str).str.strip().str.lower()
                                meus_dados = df[df['Email'] == email_logado].copy()
                                
                                if not meus_dados.empty:
                                    meus_dados = meus_dados.drop(columns=['Email'])
                                    meus_dados.to_excel(writer, sheet_name=aba, index=False)
                                else:
                                    pd.DataFrame({"Aviso": ["Aba sem dados"]}).to_excel(writer, sheet_name=aba, index=False)
                            else:
                                pd.DataFrame({"Aviso": ["Aba sem dados"]}).to_excel(writer, sheet_name=aba, index=False)
                                
                    with open(caminho_temp, "rb") as f:
                        processed_data = f.read()
                        
                finally:
                    if os.path.exists(caminho_temp):
                        os.remove(caminho_temp)
                
                st.success("Planilha de backup gerada com sucesso!")
                st.download_button(
                    label="⬇️ Baixar Planilha de Backup (.xlsx)",
                    data=processed_data,
                    file_name="meu_backup_investimentos.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    type="primary"
                )

    # ==========================================
    # LÓGICA DE IMPORTAÇÃO (EXCEL)
    # ==========================================
    elif st.session_state.tela_backup == "importar":
        st.subheader("Restaurar a partir de Planilha Excel")
        st.write("Suba o arquivo `.xlsx` de backup gerado anteriormente pelo sistema.")
        
        arquivo_upload = st.file_uploader("Selecione o arquivo Excel de backup", type=["xlsx"])
        
        if arquivo_upload is not None:
            try:
                xls = pd.ExcelFile(arquivo_upload)
                st.info(f"Arquivo lido com sucesso! Abas encontradas: {', '.join(xls.sheet_names)}")
                
                modo_importacao = st.radio(
                    "Modo de Restauração:",
                    options=[
                        "Substituir Tudo (Apaga os dados atuais e carrega apenas o arquivo)",
                        "Mesclar (Sobrepõe as configurações, mas apenas acrescenta os depósitos e investimentos)"
                    ],
                    index=0
                )
                
                st.warning("⚠️ Atenção: Esta ação irá modificar seu banco de dados na nuvem e não poderá ser desfeita.")
                
                if st.button("🚀 Iniciar Restauração via Excel", type="primary", use_container_width=True):
                    with st.spinner("Processando restauração dos dados... Isso pode demorar um pouco."):
                        
                        abas_alvo = ["Configuracao", "Ativos_Config", "Depositos", "Investimentos"]
                        teve_erro = False
                        
                        # Função de blindagem (Converte tudo para padrão pt-BR de forma segura)
                        def trata_numero(val, casas=4):
                            if pd.isna(val) or str(val).strip() == '': return ""
                            try:
                                f_val = float(str(val).replace(',', '.'))
                                if casas == 8:
                                    return f"{f_val:.8f}".replace('.', ',').rstrip('0').rstrip(',')
                                elif casas == 4:
                                    return f"{f_val:.4f}".replace('.', ',').rstrip('0').rstrip(',')
                                else:
                                    return f"{f_val:.2f}".replace('.', ',')
                            except:
                                return str(val)
                        
                        for aba in abas_alvo:
                            if aba in xls.sheet_names:
                                df_novo = pd.read_excel(xls, sheet_name=aba)
                                df_novo = df_novo.dropna(how='all')
                                
                                if not df_novo.empty and "Aviso" not in df_novo.columns:
                                    df_novo['Email'] = email_logado
                                    
                                    # 1º PASSO: Sincroniza as colunas exatas com a nuvem ANTES de processar
                                    df_molde = ler_planilha(aba)
                                    if not df_molde.empty:
                                        df_novo = df_novo.reindex(columns=df_molde.columns)
                                    
                                    # Substitui os NaNs por vazios para não quebrar a formatação
                                    df_novo = df_novo.fillna('')
                                    
                                    # 2º PASSO: Blindagem dinâmica de Dados (Não depende do nome exato)
                                    if 'Data' in df_novo.columns:
                                        df_novo['Data'] = pd.to_datetime(df_novo['Data'], errors='coerce').dt.strftime('%d/%m/%Y').fillna('')
                                        
                                    for col in df_novo.columns:
                                        col_l = col.lower()
                                        
                                        if aba == "Investimentos":
                                            if 'quant' in col_l or 'qtd' in col_l:
                                                df_novo[col] = df_novo[col].apply(lambda x: trata_numero(x, 8))
                                            elif 'prec' in col_l or 'preç' in col_l or 'custo' in col_l:
                                                df_novo[col] = df_novo[col].apply(lambda x: trata_numero(x, 4))
                                                
                                        elif aba == "Depositos":
                                            if 'valor' in col_l:
                                                df_novo[col] = df_novo[col].apply(lambda x: trata_numero(x, 2))
                                                
                                        elif aba == "Ativos_Config":
                                            if 'peso' in col_l:
                                                df_novo[col] = df_novo[col].apply(lambda x: trata_numero(x, 2))
                                                
                                        elif aba == "Configuracao":
                                            if col not in ['Email', 'Data', 'Aviso', 'Setor', 'Observacao']:
                                                df_novo[col] = df_novo[col].apply(lambda x: trata_numero(x, 2))

                                    # 3º PASSO: Salva no Google Sheets
                                    if aba in ["Configuracao", "Ativos_Config"] or modo_importacao.startswith("Substituir Tudo"):
                                        sucesso_del, msg_del = deletar_registros_usuario(aba, email_logado)
                                        if not sucesso_del:
                                            st.error(f"Erro ao limpar aba {aba}: {msg_del}")
                                            teve_erro = True
                                    
                                    sucesso_ins, msg_ins = inserir_lote_registros(aba, df_novo)
                                    if not sucesso_ins:
                                        st.error(f"Erro ao gravar aba {aba}: {msg_ins}")
                                        teve_erro = True
                                        
                                elif modo_importacao.startswith("Substituir Tudo"):
                                    sucesso_del, msg_del = deletar_registros_usuario(aba, email_logado)
                                    if not sucesso_del:
                                        st.error(f"Erro ao limpar aba {aba}: {msg_del}")
                                        teve_erro = True
                                        
                        if not teve_erro:
                            st.success("✅ Restauração via Excel concluída com sucesso! Atualize a página ou navegue pelo menu para visualizar suas informações.")
                            st.cache_data.clear()
                        else:
                            st.warning("⚠️ A restauração terminou, mas ocorreram alguns erros listados acima.")
                            
            except Exception as e:
                st.error(f"Erro ao ler ou processar a planilha. Verifique se o arquivo segue o formato correto. Detalhes: {e}")
