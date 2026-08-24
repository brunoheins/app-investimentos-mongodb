import streamlit as st
import pandas as pd
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
import yfinance as yf
import re

# ==========================================
# 1. CONEXÃO COM O MONGODB ATLAS
# ==========================================
@st.cache_resource
def init_connection():
    """Inicializa a conexão com o banco de dados usando a URL salva nos secrets."""
    try:
        uri = st.secrets["MONGO_URI"]
        client = MongoClient(uri, server_api=ServerApi('1'))
        client.admin.command('ping') # Testa a conexão
        return client['app_investimentos']
    except Exception as e:
        st.error(f"Erro ao conectar com o MongoDB: {e}")
        st.stop()

# Instância global do banco de dados para ser usada pelas funções
db = init_connection()

# ==========================================
# 2. FUNÇÕES DE FORMATAÇÃO E LIMPEZA
# ==========================================
def extrair_numero_br(valor):
    """Converte strings de planilhas para float lidando com formatos BR e US automaticamente"""
    if pd.isna(valor) or valor == '' or valor is None:
        return 0.0
    
    if isinstance(valor, (int, float)):
        return float(valor)
        
    v = str(valor).upper().replace('R$', '').replace('%', '').strip()
    if not v:
        return 0.0
        
    if '.' in v and ',' in v:
        if v.rfind(',') > v.rfind('.'):
            v = v.replace('.', '').replace(',', '.')
        else:
            v = v.replace(',', '')
    elif ',' in v:
        v = v.replace(',', '.')
        
    try:
        return float(v)
    except ValueError:
        return 0.0

def formata_br(valor):
    """Gera visualização de dinheiro no padrão BR"""
    try:
        return f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return "R$ 0,00"

# ==========================================
# 3. LEITURA E ESCRITA GERAL NO MONGODB
# ==========================================
@st.cache_data(ttl=300, show_spinner=False)
def ler_planilha(aba_nome):
    """Substitui a leitura do Google Sheets pela leitura das coleções do Mongo."""
    try:
        colecao = aba_nome.lower()
        valores = list(db[colecao].find({}, {"_id": 0}))
        
        if not valores:
            if aba_nome == "Ativos_Config":
                return pd.DataFrame(columns=['Email', 'Categoria', 'Ativo', 'Peso', 'Setor'])
            elif aba_nome == "Usuarios":
                return pd.DataFrame(columns=['Email', 'Senha', 'Nome', 'Status'])
            elif aba_nome == "Configuracao":
                return pd.DataFrame(columns=['Email', 'RF', 'RV', 'RV_Brasil', 'RV_Exterior', 'BR_Acoes', 'BR_FIIs', 'EX_Stocks', 'EX_REITs', 'EX_ETFs'])
            elif aba_nome == "Investimentos":
                return pd.DataFrame(columns=['Email', 'DataCompra', 'Categoria', 'Ativo', 'Quantidade', 'PrecoMedio', 'Observacao'])
            elif aba_nome == "Depositos":
                return pd.DataFrame(columns=['Email', 'Data', 'Valor'])
            return pd.DataFrame()
        
        df = pd.DataFrame(valores)
        
        # Garante a conversão caso venha texto do banco (compatibilidade com histórico legado)
        colunas_numericas = [
            'Quantidade', 'PrecoMedio', 'PrecoAtual', 'Valor', 'Peso', 'Peso (%)',
            'RF', 'RV', 'RV_Brasil', 'RV_Exterior', 
            'BR_Acoes', 'BR_FIIs', 'EX_Stocks', 'EX_REITs', 'EX_ETFs'
        ]
        
        for col in df.columns:
            if col in colunas_numericas:
                df[col] = df[col].apply(extrair_numero_br)
                
        return df
    except Exception as e:
        st.error(f"Erro de conexão ao ler a coleção '{aba_nome}': {e}")
        return pd.DataFrame()

def atualizar_historico_usuario(email, nome_aba, df_editado):
    """Substitui toda a coleção do usuário com os dados editados (Auditoria)."""
    try:
        colecao = nome_aba.lower()
        
        # Remove registros antigos do usuário
        db[colecao].delete_many({"Email": email.strip().lower()})
        
        # Insere os dados editados
        if not df_editado.empty:
            df_novo = df_editado.copy()
            df_novo['Email'] = email.strip().lower()
            
            # Converte valores numéricos formatados para float padrão antes de gravar
            for col in df_novo.columns:
                if 'Valor' in col or 'Preco' in col or 'Quantidade' in col:
                    df_novo[col] = df_novo[col].apply(extrair_numero_br)

            registros = df_novo.to_dict('records')
            if registros:
                db[colecao].insert_many(registros)
        
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erro ao salvar edição: {e}")
        return False

def deletar_registros_usuario(nome_aba, email):
    """Apaga todos os dados de um usuário em uma aba específica."""
    try:
        db[nome_aba.lower()].delete_many({"Email": email.strip().lower()})
        st.cache_data.clear()
        return True, "Sucesso"
    except Exception as e:
        return False, f"Erro ao apagar dados do MongoDB: {e}"

def inserir_lote_registros(nome_aba, df):
    """Insere registros em massa no MongoDB (usado pelo Importar/Backup)."""
    if df.empty:
        return True, "Planilha vazia, nada a inserir."
    try:
        df_limpo = df.astype(str).replace(["nan", "NaT", "None", "<NA>"], "")
        registros = df_limpo.to_dict('records')
        db[nome_aba.lower()].insert_many(registros)
        st.cache_data.clear()
        return True, "Sucesso"
    except Exception as e:
        return False, f"Erro ao salvar no MongoDB: {e}"

# ==========================================
# 4. CONFIGURAÇÕES E METAS DE ALOCAÇÃO
# ==========================================
def salvar_configuracao(email, dados_dict):
    """Salva a alocação Macro do usuário na coleção 'configuracao'."""
    try:
        documento = {
            "Email": email.strip().lower(),
            "RF": float(dados_dict['RF'].replace(',', '.')), 
            "RV": float(dados_dict['RV'].replace(',', '.')), 
            "RV_Brasil": float(dados_dict['RV_Brasil'].replace(',', '.')), 
            "RV_Exterior": float(dados_dict['RV_Exterior'].replace(',', '.')), 
            "BR_Acoes": float(dados_dict['BR_Acoes'].replace(',', '.')), 
            "BR_FIIs": float(dados_dict['BR_FIIs'].replace(',', '.')), 
            "EX_Stocks": float(dados_dict['EX_Stocks'].replace(',', '.')), 
            "EX_REITs": float(dados_dict['EX_REITs'].replace(',', '.')), 
            "EX_ETFs": float(dados_dict['EX_ETFs'].replace(',', '.'))
        }
        
        # O 'upsert=True' atualiza se existir, se não, cria.
        db.configuracao.update_one({"Email": email.strip().lower()}, {"$set": documento}, upsert=True)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erro ao salvar configuração: {e}")
        return False

def salvar_ativos_categoria(email, categoria, df_ativos):
    """Salva a alocação Micro (Ações, FIIs) na coleção 'ativos_config'."""
    try:
        # Apaga a configuração antiga dessa categoria para este usuário
        db.ativos_config.delete_many({"Email": email.strip().lower(), "Categoria": categoria.strip()})
        
        novos_registros = []
        for _, row in df_ativos.iterrows():
            ativo = str(row.get('Ativo', '')).strip().upper()
            
            col_peso = 'Peso' if 'Peso' in df_ativos.columns else 'Peso (%)'
            val_peso = row.get(col_peso, 0)
            peso = extrair_numero_br(val_peso)
            
            setor = str(row.get('Setor', '')).strip()
            if not setor or setor.lower() in ['nan', 'none', 'não classificado', 'nao classificado']:
                setor = buscar_setor_yahoo(ativo, categoria)
                
            if ativo and ativo != "NAN":
                novos_registros.append({
                    "Email": email.strip().lower(),
                    "Categoria": categoria.strip(),
                    "Ativo": ativo,
                    "Peso": float(peso),
                    "Setor": setor
                })
                
        if novos_registros:
            db.ativos_config.insert_many(novos_registros)
            
        st.cache_data.clear() 
        return True
    except Exception as e:
        st.error(f"Erro ao salvar ativos: {e}")
        return False

# ==========================================
# 5. LANÇAMENTOS (COMPRAS, VENDAS, DEPÓSITOS)
# ==========================================
def registrar_deposito(email, data, valor):
    """Grava aporte/saque na coleção 'depositos'."""
    try:
        novo_deposito = {
            "Email": email.strip().lower(),
            "Data": data,
            "Valor": float(valor)
        }
        db.depositos.insert_one(novo_deposito)
        st.cache_data.clear() 
        return True
    except Exception as e:
        st.error(f"Erro ao salvar depósito: {e}")
        return False

def registrar_compra(email, data, categoria, ativo, quantidade, preco_medio, observacao=""):
    """Grava ordem de ativo na coleção 'investimentos'."""
    try:
        nova_ordem = {
            "Email": email.strip().lower(),
            "DataCompra": data,
            "Categoria": categoria.strip(),
            "Ativo": ativo.strip().upper(),
            "Quantidade": float(quantidade),
            "PrecoMedio": float(preco_medio),
            "Observacao": observacao.strip()
        }
        db.investimentos.insert_one(nova_ordem)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erro ao salvar compra: {e}")
        return False

# ==========================================
# 6. AUTENTICAÇÃO E GERENCIAMENTO DE USUÁRIOS
# ==========================================
def registrar_novo_usuario(nome, email, senha):
    try:
        email_lower = email.strip().lower()
        if verificar_email_cadastrado(email_lower):
            return False, "⚠️ Este e-mail já está cadastrado. Caso não se recorde da senha, vá em 'Esqueci a Senha'."
            
        novo_usuario = {
            "Email": email_lower,
            "Senha": senha,
            "Nome": nome.strip(),
            "Status": "Pendente"
        }
        db.usuarios.insert_one(novo_usuario)
        st.cache_data.clear()
        return True, "✅ Cadastro enviado com sucesso! Aguarde a liberação do administrador."
    except Exception as e:
        return False, f"Erro ao cadastrar: {e}"

def verificar_email_cadastrado(email):
    try:
        count = db.usuarios.count_documents({"Email": email.strip().lower()})
        return count > 0
    except:
        return False

def redefinir_senha_aprovada(email, nova_senha):
    try:
        resultado = db.usuarios.update_one(
            {"Email": email.strip().lower()},
            {"$set": {"Senha": nova_senha}}
        )
        if resultado.matched_count > 0:
            st.cache_data.clear()
            return True, "✅ Senha alterada com sucesso! Você já pode fazer login."
        return False, "Usuário não encontrado."
    except Exception as e:
        return False, f"Erro ao gravar nova senha: {e}"

def atualizar_dados_perfil(email, novo_nome, nova_senha):
    try:
        atualizacoes = {}
        if novo_nome: atualizacoes["Nome"] = novo_nome.strip()
        if nova_senha: atualizacoes["Senha"] = nova_senha
        
        if not atualizacoes: return True, "Nada a atualizar."
        
        resultado = db.usuarios.update_one(
            {"Email": email.strip().lower()},
            {"$set": atualizacoes}
        )
        if resultado.matched_count > 0:
            st.cache_data.clear()
            return True, "✅ Perfil atualizado com sucesso!"
        return False, "Usuário não encontrado."
    except Exception as e:
        return False, f"Erro ao atualizar perfil: {e}"

def enviar_codigo_email(email_destino, codigo):
    """Envia E-mail de recuperação mantendo sua estrutura SMTP original."""
    try:
        remetente = st.secrets["email"]["endereco"]
        senha_app = st.secrets["email"]["senha_app"]
        
        msg = MIMEMultipart()
        msg['From'] = remetente
        msg['To'] = email_destino
        msg['Subject'] = "🔒 Código de Recuperação de Senha - App Investimentos"
        
        corpo = f"Olá!\n\nVocê solicitou a recuperação de senha no seu App de Investimentos.\n\nSeu código de segurança é: {codigo}\n\nSe você não solicitou esta alteração, apenas ignore este e-mail."
        msg.attach(MIMEText(corpo, 'plain'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(remetente, senha_app)
        server.send_message(msg)
        server.quit()
        
        return True, "E-mail enviado com sucesso!"
    except Exception as e:
        return False, f"Erro ao enviar o e-mail: {e}"

# ==========================================
# 7. COTAÇÕES E INTELIGÊNCIA FINANCEIRA (YAHOO / BCB)
# ==========================================
@st.cache_data(ttl=86400, show_spinner=False)
def buscar_setor_yahoo(ativo, categoria):
    if categoria == "Renda Fixa":
        return "Renda Fixa"
        
    t_clean = str(ativo).upper().replace(".SA", "").strip()

    if categoria == "FIIs":
        fiis_papel = ["MXRF11", "KNCR11", "KNIP11", "CPTS11", "IRDM11", "RECR11", "VGIR11", "VRTA11", "HCTR11", "DEVA11", "VGHF11", "MCCI11", "CVBI11", "HGCR11", "KNSC11", "RBRR11", "URPR11", "HABT11", "VCJR11", "ARRI11", "RBRY11", "OUJP11", "CACR11", "NCHB11", "KNHY11", "SNCI11", "RZAK11", "BARI11"]
        fiis_logistica = ["HGLG11", "BTLG11", "XPLG11", "VILG11", "BRCO11", "LVBI11", "GGRC11", "HSLG11", "RBRL11", "SDIL11", "TRXF11", "GALG11", "GARE11", "HLG11", "FIIB11", "VTLG11", "PATL11"]
        fiis_shoppings = ["XPML11", "VISC11", "HSML11", "MALL11", "HGBS11", "WPLZ11", "GSFI11", "CPSH11", "MALS11"]
        fiis_lajes = ["HGRE11", "BRCR11", "PVBI11", "JSRE11", "VINO11", "RECT11", "TEPP11", "RCRB11", "RBED11", "CBOP11", "HOFC11", "VLOL11"]
        fiis_hibridos = ["KNRI11", "ALZR11", "TGAR11", "HGRU11", "KFOF11", "MAXR11", "TRXF11", "RBVA11", "MCHY11"]
        fiis_fof = ["BCFF11", "HFOF11", "KISU11", "RBRF11", "MGFF11", "CPFF11", "XPFN11", "HGFF11", "KFOF11", "BLMG11", "RZFO11"]
        fiis_agro = ["VGIA11", "RZAG11", "SNAG11", "KNCA11", "RURA11", "EGAF11", "FGAA11", "GCRA11", "VCRA11", "XPCA11", "DCRA11", "AGRX11"]
        
        if t_clean in fiis_papel: return "Papel (TVM)"
        if t_clean in fiis_logistica: return "Logística"
        if t_clean in fiis_shoppings: return "Shoppings"
        if t_clean in fiis_lajes: return "Lajes Corporativas"
        if t_clean in fiis_hibridos: return "Híbrido"
        if t_clean in fiis_fof: return "Fundo de Fundos (FOF)"
        if t_clean in fiis_agro: return "Fiagro"

    ticker = ativo
    if categoria in ["Ações", "FIIs"]:
        if "." not in ticker and re.search(r'\d+$', ticker):
            ticker = f"{ticker}.SA"
            
    try:
        info = yf.Ticker(ticker).info
        setor = info.get('sector', '')
        if not setor or str(setor).lower() in ['none', 'nan', '']:
            setor = info.get('industry', 'Não Classificado')
            
        traducao = {
            "Financial Services": "Financeiro", "Utilities": "Utilidade Pública",
            "Basic Materials": "Materiais Básicos", "Industrials": "Industrial",
            "Consumer Defensive": "Consumo Não-Cíclico", "Consumer Cyclical": "Consumo Cíclico",
            "Healthcare": "Saúde", "Technology": "Tecnologia", "Communication Services": "Comunicações",
            "Energy": "Energia", "Real Estate": "Imobiliário"
        }
        return traducao.get(setor, setor if setor else "Não Classificado")
    except:
        return "Não Classificado"

@st.cache_data(ttl=300, show_spinner=False)
def obter_cotacoes():
    import yfinance as yf
    import requests
    import re
    import pandas as pd
    
    cotacoes = {}
    ativos_buscados = set()
    
    try:
        if 'email' in st.session_state:
            email_usuario = st.session_state.email.strip().lower()
            
            df_invest = ler_planilha("Investimentos")
            if not df_invest.empty and 'Email' in df_invest.columns:
                meus_invest = df_invest[df_invest['Email'].astype(str).str.strip().str.lower() == email_usuario]
                for _, row in meus_invest.iterrows():
                    ativo = str(row.get('Ativo', '')).strip().upper()
                    if ativo and ativo not in ["NAN", "NONE", ""]:
                        ativos_buscados.add(ativo)
                        preco_custo = 0.0
                        if 'PrecoMedio' in row and pd.notnull(row['PrecoMedio']):
                            preco_custo = extrair_numero_br(row['PrecoMedio'])
                        elif 'Preco' in row and pd.notnull(row['Preco']):
                            preco_custo = extrair_numero_br(row['Preco'])
                        if preco_custo > 0 and ativo not in cotacoes:
                            cotacoes[ativo] = preco_custo

            df_config = ler_planilha("Ativos_Config")
            if not df_config.empty and 'Email' in df_config.columns:
                meus_configs = df_config[df_config['Email'].astype(str).str.strip().str.lower() == email_usuario]
                for _, row in meus_configs.iterrows():
                    ativo = str(row.get('Ativo', '')).strip().upper()
                    if ativo and ativo not in ["NAN", "NONE", ""]:
                        ativos_buscados.add(ativo)

        if not ativos_buscados: return cotacoes

        titulos_tesouro = []
        try:
            url_csv = "https://www.tesourodireto.com.br/documents/d/guest/rendimento-resgatar-csv?download=true"
            df_td = pd.read_csv(url_csv, sep=';', encoding='utf-8-sig', storage_options={'User-Agent': 'Mozilla/5.0'})
            df_td.columns = [str(c).strip().upper() for c in df_td.columns]
            col_titulo = next((col for col in df_td.columns if 'TÍTULO' in col), df_td.columns[0])
            col_preco = next((col for col in df_td.columns if 'RESGATE' in col or 'PREÇO' in col), df_td.columns[2])
            for _, row in df_td.iterrows():
                nome_cru = str(row[col_titulo])
                valor_cru = str(row[col_preco])
                nome_titulo_limpo = " ".join(nome_cru.upper().split())
                if nome_titulo_limpo and nome_titulo_limpo != "NAN":
                    titulos_tesouro.append({"nome": nome_titulo_limpo, "valor": extrair_numero_br(valor_cru)})
        except Exception as e1:
            try:
                headers = {"User-Agent": "Mozilla/5.0"}
                url_td2 = "https://tesouro.gabriso.com/bonds"
                res_td2 = requests.get(url_td2, headers=headers, timeout=5)
                if res_td2.status_code == 200:
                    for bond in res_td2.json().get("bonds", []):
                        nome_titulo_limpo = " ".join(str(bond.get("name", "")).upper().split())
                        titulos_tesouro.append({"nome": nome_titulo_limpo, "valor": float(bond.get("unitary_redemption_value", 0.0))})
            except: pass

        mapa_ativos = {" ".join(a.upper().split()): a for a in ativos_buscados}
        ativos_ja_encontrados = set()
        for titulo in titulos_tesouro:
            nome = titulo["nome"]
            valor = titulo["valor"]
            if nome in mapa_ativos:
                nome_original = mapa_ativos[nome]
                cotacoes[nome_original] = valor
                ativos_ja_encontrados.add(nome_original)
                
        ativos_buscados = ativos_buscados - ativos_ja_encontrados

        if ativos_buscados:
            tickers_yf = []
            mapa_tickers = {}
            tem_exterior = False
            for ativo in ativos_buscados:
                ticker = ativo
                if "." not in ticker and re.search(r'\d+$', ticker):
                    ticker = f"{ticker}.SA"
                if not ticker.endswith(".SA"):
                    tem_exterior = True
                tickers_yf.append(ticker)
                mapa_tickers[ticker] = ativo 

            if tem_exterior: tickers_yf.append("BRL=X")

            try:
                df_raw = yf.download(list(set(tickers_yf)), period="1d", progress=False, ignore_tz=True)
                if not df_raw.empty:
                    if isinstance(df_raw.columns, pd.MultiIndex):
                        lvl_0 = df_raw.columns.get_level_values(0)
                        lvl_1 = df_raw.columns.get_level_values(1)
                        if 'Close' in lvl_0: df_prices = df_raw['Close']
                        elif 'Adj Close' in lvl_0: df_prices = df_raw['Adj Close']
                        elif 'Close' in lvl_1: df_prices = df_raw.xs('Close', axis=1, level=1)
                        elif 'Adj Close' in lvl_1: df_prices = df_raw.xs('Adj Close', axis=1, level=1)
                        else: df_prices = pd.DataFrame()
                    else:
                        col = 'Close' if 'Close' in df_raw.columns else 'Adj Close'
                        if col in df_raw.columns:
                            df_prices = df_raw[[col]].copy()
                            df_prices.columns = [tickers_yf[0]]
                        else:
                            df_prices = pd.DataFrame()
                            
                    if isinstance(df_prices, pd.Series): df_prices = df_prices.to_frame(name=tickers_yf[0])

                    if not df_prices.empty:
                        cotacao_dolar = float(df_prices["BRL=X"].iloc[-1]) if tem_exterior and "BRL=X" in df_prices.columns else 1.0
                        for ticker in tickers_yf:
                            if ticker == "BRL=X": continue
                            try:
                                if ticker in df_prices.columns:
                                    preco_original = float(df_prices[ticker].iloc[-1])
                                    if pd.notna(preco_original):
                                        preco_final = preco_original * cotacao_dolar if not ticker.endswith(".SA") else preco_original
                                        cotacoes[mapa_tickers[ticker]] = preco_final
                            except: pass
            except: pass
        return cotacoes
    except: return cotacoes

@st.cache_data(ttl=300, show_spinner=False)
def obter_ativos_por_categoria(email_usuario):
    cat_dict = {"Renda Fixa": [], "Ações": [], "FIIs": [], "Stocks": [], "REITs": [], "ETFs": []}
    try:
        df_config = ler_planilha("Ativos_Config")
        if not df_config.empty and 'Email' in df_config.columns:
            meus_ativos = df_config[df_config['Email'].astype(str).str.strip().str.lower() == email_usuario.strip().lower()]
            for _, row in meus_ativos.iterrows():
                categoria_bruta = str(row.get('Categoria', '')).strip().upper()
                ativo = str(row.get('Ativo', '')).strip().upper()
                
                categoria = ""
                if categoria_bruta in ["AÇÕES", "ACOES", "AÇÃO", "ACAO"]: categoria = "Ações"
                elif categoria_bruta in ["FIIS", "FII"]: categoria = "FIIs"
                elif categoria_bruta in ["IPCA", "RENDA FIXA", "RF"]: categoria = "Renda Fixa"
                elif categoria_bruta in ["STOCKS", "STOCK"]: categoria = "Stocks"
                elif categoria_bruta in ["REITS", "REIT"]: categoria = "REITs"
                elif categoria_bruta in ["ETFS", "ETF"]: categoria = "ETFs"
                
                if ativo and ativo != "NAN" and categoria:
                    if ativo not in cat_dict[categoria]:
                        cat_dict[categoria].append(ativo)
                        
        try:
            url_td = "https://tesouro.gabriso.com/bonds"
            headers = {"User-Agent": "Mozilla/5.0"}
            res_td = requests.get(url_td, headers=headers, timeout=10)
            if res_td.status_code == 200:
                palavras_permitidas = ["IPCA+", "SELIC", "PREFIXADO"]
                palavras_nao_permitidas = ["EDUCA", "APOSENTADORIA"]
                for bond in res_td.json().get("bonds", []):
                    nome = str(bond.get("name", "")).strip().upper()
                    if any(p in nome for p in palavras_permitidas) and not any(p in nome for p in palavras_nao_permitidas):
                        if nome not in cat_dict["Renda Fixa"]: cat_dict["Renda Fixa"].append(nome)
        except: pass
            
        for cat in cat_dict: cat_dict[cat].sort()
        return {categoria: ativos for categoria, ativos in cat_dict.items() if len(ativos) > 0}
    except:
        return {categoria: ativos for categoria, ativos in cat_dict.items() if len(ativos) > 0}
