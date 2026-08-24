import streamlit as st
import pandas as pd
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
import certifi
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
import yfinance as yf
import re
from datetime import datetime

# ==========================================
# 1. CONEXÃO COM O MONGODB ATLAS (V2)
# ==========================================
@st.cache_resource
def init_connection():
    try:
        uri = st.secrets["MONGO_URI"]
        # Usamos certifi para blindar contra bloqueios de rede/firewalls (ex: Zscaler)
        client = MongoClient(uri, server_api=ServerApi('1'), tlsCAFile=certifi.where())
        # CONECTANDO AO BANCO OTIMIZADO V2
        return client['app_v2']
    except Exception as e:
        st.error(f"Erro ao conectar com o MongoDB: {e}")
        st.stop()

db = init_connection()

# ==========================================
# 2. FUNÇÕES DE FORMATAÇÃO E LIMPEZA
# ==========================================
def extrair_numero_br(valor):
    if pd.isna(valor) or valor == '' or valor is None: return 0.0
    if isinstance(valor, (int, float)): return float(valor)
    v = str(valor).upper().replace('R$', '').replace('%', '').strip()
    if not v: return 0.0
    if '.' in v and ',' in v:
        if v.rfind(',') > v.rfind('.'): v = v.replace('.', '').replace(',', '.')
        else: v = v.replace(',', '')
    elif ',' in v: v = v.replace(',', '.')
    try: return float(v)
    except ValueError: return 0.0

def formata_br(valor):
    try: return f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except: return "R$ 0,00"

# ==========================================
# 3. O "TRADUTOR" MAGNÍFICO (ADAPTER PATTERN)
# ==========================================
@st.cache_data(ttl=300, show_spinner=False)
def ler_planilha(aba_nome):
    """
    Traduz os dados compactados da V2 de volta para o formato de planilhas 
    que o resto do aplicativo (gráficos, menus) já está acostumado a ler.
    """
    try:
        if aba_nome == "Usuarios":
            # Busca pelo _id ao invés de email
            usuarios = list(db.usuarios.find({}, {"_id": 1, "senha": 1, "nome": 1, "status": 1}))
            if not usuarios: return pd.DataFrame(columns=['Email', 'Senha', 'Nome', 'Status'])
            df = pd.DataFrame(usuarios)
            df.rename(columns={"_id": "Email", "senha": "Senha", "nome": "Nome", "status": "Status"}, inplace=True)
            return df
            
        elif aba_nome == "Configuracao":
            usuarios = list(db.usuarios.find({}, {"_id": 1, "metas": 1}))
            linhas = []
            for u in usuarios:
                m = u.get("metas", {})
                if m:
                    linhas.append({
                        "Email": u.get("_id"), "RF": m.get("rf",0), "RV": m.get("rv",0),
                        "RV_Brasil": m.get("br",0), "RV_Exterior": m.get("ex",0),
                        "BR_Acoes": m.get("ac",0), "BR_FIIs": m.get("fii",0),
                        "EX_Stocks": m.get("st",0), "EX_REITs": m.get("re",0), "EX_ETFs": m.get("et",0)
                    })
            if not linhas: return pd.DataFrame(columns=['Email', 'RF', 'RV', 'RV_Brasil', 'RV_Exterior', 'BR_Acoes', 'BR_FIIs', 'EX_Stocks', 'EX_REITs', 'EX_ETFs'])
            return pd.DataFrame(linhas)
            
        elif aba_nome == "Ativos_Config":
            usuarios = list(db.usuarios.find({}, {"_id": 1, "ativos": 1}))
            linhas = []
            for u in usuarios:
                for a in u.get("ativos", []):
                    linhas.append({
                        "Email": u.get("_id"), "Categoria": a.get("cat"), "Ativo": a.get("atv"),
                        "Peso": a.get("p"), "Setor": a.get("set")
                    })
            if not linhas: return pd.DataFrame(columns=['Email', 'Categoria', 'Ativo', 'Peso', 'Setor'])
            return pd.DataFrame(linhas)
            
        elif aba_nome == "Depositos":
            txs = list(db.transacoes.find({"tipo": "D"}, {"_id": 0}))
            linhas = []
            for t in txs:
                linhas.append({
                    "Email": t.get("email"), 
                    "Data": t.get("dt").strftime('%d/%m/%Y') if pd.notnull(t.get("dt")) else "", 
                    "Valor": t.get("val")
                })
            if not linhas: return pd.DataFrame(columns=['Email', 'Data', 'Valor'])
            return pd.DataFrame(linhas)
            
        elif aba_nome == "Investimentos":
            txs = list(db.transacoes.find({"tipo": "I"}, {"_id": 0}))
            linhas = []
            for t in txs:
                linhas.append({
                    "Email": t.get("email"),
                    "DataCompra": t.get("dt").strftime('%d/%m/%Y') if pd.notnull(t.get("dt")) else "",
                    "Categoria": t.get("cat"),
                    "Ativo": t.get("atv"),
                    "Quantidade": t.get("qtd"),
                    "PrecoMedio": t.get("pm"),
                    "Observacao": t.get("obs", "")
                })
            if not linhas: return pd.DataFrame(columns=['Email', 'DataCompra', 'Categoria', 'Ativo', 'Quantidade', 'PrecoMedio', 'Observacao'])
            return pd.DataFrame(linhas)
            
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Erro ao ler a tabela '{aba_nome}': {e}")
        return pd.DataFrame()

# ==========================================
# 4. TRADUTORES DE GRAVAÇÃO (EMBEDDING E UNIFICAÇÃO)
# ==========================================
def salvar_configuracao(email, dados_dict):
    try:
        db.usuarios.update_one(
            {"_id": str(email).strip().lower()},
            {"$set": {
                "metas.rf": float(str(dados_dict['RF']).replace(',', '.')),
                "metas.rv": float(str(dados_dict['RV']).replace(',', '.')),
                "metas.br": float(str(dados_dict['RV_Brasil']).replace(',', '.')),
                "metas.ex": float(str(dados_dict['RV_Exterior']).replace(',', '.')),
                "metas.ac": float(str(dados_dict['BR_Acoes']).replace(',', '.')),
                "metas.fii": float(str(dados_dict['BR_FIIs']).replace(',', '.')),
                "metas.st": float(str(dados_dict['EX_Stocks']).replace(',', '.')),
                "metas.re": float(str(dados_dict['EX_REITs']).replace(',', '.')),
                "metas.et": float(str(dados_dict['EX_ETFs']).replace(',', '.'))
            }},
            upsert=True
        )
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erro ao salvar metas: {str(e)}")
        return False

def salvar_ativos_categoria(email, categoria, df_ativos):
    try:
        user = db.usuarios.find_one({"_id": str(email).strip().lower()})
        ativos_mantidos = []
        if user:
            ativos_mantidos = [a for a in user.get("ativos", []) if a.get("cat") != str(categoria).strip()]
            
        for _, row in df_ativos.iterrows():
            ativo = str(row.get('Ativo', '')).strip().upper()
            val_peso = row.get('Peso') if 'Peso' in df_ativos.columns else row.get('Peso (%)', 0)
            peso = extrair_numero_br(val_peso)
            setor = str(row.get('Setor', '')).strip()
            if not setor or setor.lower() in ['nan', 'none']: setor = buscar_setor_yahoo(ativo, str(categoria))
            
            if ativo and ativo != "NAN":
                ativos_mantidos.append({"cat": str(categoria).strip(), "atv": ativo, "p": float(peso), "set": setor})
                
        db.usuarios.update_one(
            {"_id": str(email).strip().lower()},
            {"$set": {"ativos": ativos_mantidos}},
            upsert=True
        )
        st.cache_data.clear() 
        return True
    except Exception as e:
        st.error(f"Erro ao salvar ativos: {str(e)}")
        return False

def registrar_deposito(email, data, valor):
    try:
        data_val = datetime.strptime(str(data), "%d/%m/%Y")
        db.transacoes.insert_one({
            "email": str(email).strip().lower(), 
            "tipo": "D", 
            "dt": data_val, 
            "val": float(valor)
        })
        st.cache_data.clear() 
        return True
    except Exception as e:
        st.error(f"Erro ao salvar depósito: {str(e)}")
        return False

def registrar_compra(email, data, categoria, ativo, quantidade, preco_medio, observacao=""):
    try:
        data_val = datetime.strptime(str(data), "%d/%m/%Y")
        doc = {
            "email": str(email).strip().lower(), 
            "tipo": "I", 
            "dt": data_val,
            "cat": str(categoria).strip(), 
            "atv": str(ativo).strip().upper(),
            "qtd": float(quantidade), 
            "pm": float(preco_medio)
        }
        # Blindagem extra na observação
        if observacao is not None:
            obs_str = str(observacao).strip()
            if obs_str and obs_str.lower() not in ["nan", "none"]: 
                doc["obs"] = obs_str
                
        db.transacoes.insert_one(doc)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Detalhe do erro ao salvar ordem: {str(e)}")
        return False

# ==========================================
# 5. GERENCIADOR DE EDIÇÃO E BACKUP (AUDITORIA)
# ==========================================
def atualizar_historico_usuario(email, nome_aba, df_editado):
    try:
        e_lower = str(email).strip().lower()
        if nome_aba == "Depositos":
            db.transacoes.delete_many({"email": e_lower, "tipo": "D"})
            if not df_editado.empty:
                novos = []
                for _, row in df_editado.iterrows():
                    d = pd.to_datetime(row.get("Data"), errors='coerce', dayfirst=True)
                    if pd.notna(d):
                        novos.append({
                            "email": e_lower, "tipo": "D", "dt": d, "val": extrair_numero_br(row.get("Valor"))
                        })
                if novos: db.transacoes.insert_many(novos)
                
        elif nome_aba == "Investimentos":
            db.transacoes.delete_many({"email": e_lower, "tipo": "I"})
            if not df_editado.empty:
                novos = []
                for _, row in df_editado.iterrows():
                    d = pd.to_datetime(row.get("DataCompra"), errors='coerce', dayfirst=True)
                    if pd.notna(d):
                        doc = {
                            "email": e_lower, "tipo": "I", "dt": d, 
                            "cat": str(row.get("Categoria")), "atv": str(row.get("Ativo")).upper(),
                            "qtd": extrair_numero_br(row.get("Quantidade")), "pm": extrair_numero_br(row.get("PrecoMedio"))
                        }
                        obs = str(row.get("Observacao", "")).strip()
                        if obs and obs.lower() not in ["nan", "none"]:
                            doc["obs"] = obs
                        novos.append(doc)
                if novos: db.transacoes.insert_many(novos)
        else:
            # BLINDAGEM: Se o nome estiver errado no lancamentos.py, o app vai te avisar na hora!
            st.error(f"❌ Erro interno: O nome da aba '{nome_aba}' não é reconhecido. O sistema espera 'Investimentos' ou 'Depositos'.")
            return False
            
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erro ao salvar edição: {str(e)}")
        return False

def deletar_registros_usuario(nome_aba, email):
    try:
        e_lower = str(email).strip().lower()
        if nome_aba == "Depositos": db.transacoes.delete_many({"email": e_lower, "tipo": "D"})
        elif nome_aba == "Investimentos": db.transacoes.delete_many({"email": e_lower, "tipo": "I"})
        elif nome_aba == "Configuracao": db.usuarios.update_one({"_id": e_lower}, {"$unset": {"metas": ""}})
        elif nome_aba == "Ativos_Config": db.usuarios.update_one({"_id": e_lower}, {"$set": {"ativos": []}})
        st.cache_data.clear()
        return True, "Sucesso"
    except Exception as e:
        return False, f"Erro: {str(e)}"

def inserir_lote_registros(nome_aba, df):
    if df.empty: return True, "Vazio."
    try:
        email = df['Email'].iloc[0].strip().lower() if 'Email' in df.columns else ""
        if not email: return False, "E-mail não encontrado no lote."
        
        if nome_aba in ["Depositos", "Investimentos"]:
            atualizar_historico_usuario(email, nome_aba, df)
            
        elif nome_aba == "Configuracao":
            dados = df.iloc[0].to_dict()
            salvar_configuracao(email, dados)
            
        elif nome_aba == "Ativos_Config":
            for cat in df['Categoria'].unique():
                df_cat = df[df['Categoria'] == cat]
                salvar_ativos_categoria(email, cat, df_cat)
                
        st.cache_data.clear()
        return True, "Sucesso"
    except Exception as e:
        return False, f"Erro: {str(e)}"

# ==========================================
# 6. AUTENTICAÇÃO
# ==========================================
def registrar_novo_usuario(nome, email, senha):
    try:
        email_lower = str(email).strip().lower()
        if db.usuarios.count_documents({"_id": email_lower}) > 0:
            return False, "⚠️ Este e-mail já está cadastrado. Caso não se recorde da senha, vá em 'Esqueci a Senha'."
            
        novo_usuario = {"_id": email_lower, "senha": str(senha), "nome": str(nome).strip(), "status": "Pendente", "metas": {}, "ativos": []}
        db.usuarios.insert_one(novo_usuario)
        st.cache_data.clear()
        return True, "✅ Cadastro enviado com sucesso! Aguarde a liberação."
    except Exception as e: return False, f"Erro ao cadastrar: {str(e)}"
        
def verificar_email_cadastrado(email):
    try: return db.usuarios.count_documents({"_id": str(email).strip().lower()}) > 0
    except: return False

def redefinir_senha_aprovada(email, nova_senha):
    try:
        res = db.usuarios.update_one({"_id": str(email).strip().lower()}, {"$set": {"senha": str(nova_senha)}})
        if res.matched_count > 0:
            st.cache_data.clear()
            return True, "✅ Senha alterada com sucesso! Você já pode fazer login."
        return False, "Usuário não encontrado."
    except Exception as e: return False, f"Erro: {str(e)}"

def atualizar_dados_perfil(email, novo_nome, nova_senha):
    try:
        atualizacoes = {}
        if novo_nome: atualizacoes["nome"] = str(novo_nome).strip()
        if nova_senha: atualizacoes["senha"] = str(nova_senha)
        if not atualizacoes: return True, "Nada a atualizar."
        
        res = db.usuarios.update_one({"_id": str(email).strip().lower()}, {"$set": atualizacoes})
        if res.matched_count > 0:
            st.cache_data.clear()
            return True, "✅ Perfil atualizado com sucesso!"
        return False, "Usuário não encontrado."
    except Exception as e: return False, f"Erro: {str(e)}"

def enviar_codigo_email(email_destino, codigo):
    try:
        remetente = st.secrets["email"]["endereco"]
        senha_app = st.secrets["email"]["senha_app"]
        msg = MIMEMultipart()
        msg['From'], msg['To'], msg['Subject'] = remetente, str(email_destino), "🔒 Código de Recuperação de Senha - App Investimentos"
        corpo = f"Olá!\n\nVocê solicitou a recuperação de senha no seu App de Investimentos.\n\nSeu código de segurança é: {codigo}\n\nSe você não solicitou esta alteração, apenas ignore este e-mail."
        msg.attach(MIMEText(corpo, 'plain'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(remetente, senha_app)
        server.send_message(msg)
        server.quit()
        return True, "E-mail enviado com sucesso!"
    except Exception as e: return False, f"Erro: {str(e)}"

# ==========================================
# 7. COTAÇÕES E INTELIGÊNCIA FINANCEIRA
# ==========================================
@st.cache_data(ttl=86400, show_spinner=False)
def buscar_setor_yahoo(ativo, categoria):
    if str(categoria) == "Renda Fixa": return "Renda Fixa"
    t_clean = str(ativo).upper().replace(".SA", "").strip()
    if str(categoria) == "FIIs":
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

    ticker = t_clean
    if str(categoria) in ["Ações", "FIIs"] and "." not in ticker and re.search(r'\d+$', ticker): ticker = f"{ticker}.SA"
    try:
        info = yf.Ticker(ticker).info
        setor = info.get('sector', '')
        if not setor or str(setor).lower() in ['none', 'nan', '']: setor = info.get('industry', 'Não Classificado')
        traducao = {
            "Financial Services": "Financeiro", "Utilities": "Utilidade Pública",
            "Basic Materials": "Materiais Básicos", "Industrials": "Industrial",
            "Consumer Defensive": "Consumo Não-Cíclico", "Consumer Cyclical": "Consumo Cíclico",
            "Healthcare": "Saúde", "Technology": "Tecnologia", "Communication Services": "Comunicações",
            "Energy": "Energia", "Real Estate": "Imobiliário"
        }
        return traducao.get(setor, setor if setor else "Não Classificado")
    except: return "Não Classificado"

@st.cache_data(ttl=300, show_spinner=False)
def obter_cotacoes():
    cotacoes, ativos_buscados = {}, set()
    try:
        if 'email' in st.session_state:
            email_usuario = str(st.session_state.email).strip().lower()
            df_invest = ler_planilha("Investimentos")
            if not df_invest.empty:
                for _, row in df_invest[df_invest['Email'].astype(str).str.lower() == email_usuario].iterrows():
                    ativo = str(row.get('Ativo', '')).strip().upper()
                    if ativo and ativo not in ["NAN", "NONE", ""]:
                        ativos_buscados.add(ativo)
                        pm = extrair_numero_br(row.get('PrecoMedio', row.get('Preco', 0)))
                        if pm > 0 and ativo not in cotacoes: cotacoes[ativo] = pm

            df_config = ler_planilha("Ativos_Config")
            if not df_config.empty:
                for _, row in df_config[df_config['Email'].astype(str).str.lower() == email_usuario].iterrows():
                    ativo = str(row.get('Ativo', '')).strip().upper()
                    if ativo and ativo not in ["NAN", "NONE", ""]: ativos_buscados.add(ativo)

        if not ativos_buscados: return cotacoes
        titulos_tesouro = []
        try:
            df_td = pd.read_csv("https://www.tesourodireto.com.br/documents/d/guest/rendimento-resgatar-csv?download=true", sep=';', encoding='utf-8-sig', storage_options={'User-Agent': 'Mozilla/5.0'})
            df_td.columns = [str(c).strip().upper() for c in df_td.columns]
            col_titulo = next((col for col in df_td.columns if 'TÍTULO' in col), df_td.columns[0])
            col_preco = next((col for col in df_td.columns if 'RESGATE' in col or 'PREÇO' in col), df_td.columns[2])
            for _, row in df_td.iterrows():
                nome_limpo = " ".join(str(row[col_titulo]).upper().split())
                if nome_limpo and nome_limpo != "NAN": titulos_tesouro.append({"nome": nome_limpo, "valor": extrair_numero_br(row[col_preco])})
        except:
            try:
                res_td2 = requests.get("https://tesouro.gabriso.com/bonds", headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
                if res_td2.status_code == 200:
                    for bond in res_td2.json().get("bonds", []):
                        nome_limpo = " ".join(str(bond.get("name", "")).upper().split())
                        titulos_tesouro.append({"nome": nome_limpo, "valor": float(bond.get("unitary_redemption_value", 0.0))})
            except: pass

        mapa_ativos = {" ".join(a.upper().split()): a for a in ativos_buscados}
        ativos_ja_encontrados = set()
        for titulo in titulos_tesouro:
            if titulo["nome"] in mapa_ativos:
                nome_original = mapa_ativos[titulo["nome"]]
                cotacoes[nome_original] = titulo["valor"]
                ativos_ja_encontrados.add(nome_original)
                
        ativos_buscados = ativos_buscados - ativos_ja_encontrados
        if ativos_buscados:
            tickers_yf, mapa_tickers, tem_exterior = [], {}, False
            for ativo in ativos_buscados:
                ticker = ativo
                if "." not in ticker and re.search(r'\d+$', ticker): ticker = f"{ticker}.SA"
                if not ticker.endswith(".SA"): tem_exterior = True
                tickers_yf.append(ticker)
                mapa_tickers[ticker] = ativo 

            if tem_exterior: tickers_yf.append("BRL=X")
            try:
                df_raw = yf.download(list(set(tickers_yf)), period="1d", progress=False, ignore_tz=True)
                if not df_raw.empty:
                    df_prices = pd.DataFrame()
                    if isinstance(df_raw.columns, pd.MultiIndex):
                        for col_type in ['Close', 'Adj Close']:
                            if col_type in df_raw.columns.get_level_values(0): df_prices = df_raw[col_type]; break
                            elif col_type in df_raw.columns.get_level_values(1): df_prices = df_raw.xs(col_type, axis=1, level=1); break
                    else:
                        col = 'Close' if 'Close' in df_raw.columns else 'Adj Close'
                        if col in df_raw.columns: df_prices = df_raw[[col]].copy(); df_prices.columns = [tickers_yf[0]]
                    
                    if isinstance(df_prices, pd.Series): df_prices = df_prices.to_frame(name=tickers_yf[0])
                    if not df_prices.empty:
                        cotacao_dolar = float(df_prices["BRL=X"].iloc[-1]) if tem_exterior and "BRL=X" in df_prices.columns else 1.0
                        for ticker in tickers_yf:
                            if ticker == "BRL=X": continue
                            if ticker in df_prices.columns and pd.notna(float(df_prices[ticker].iloc[-1])):
                                preco = float(df_prices[ticker].iloc[-1])
                                cotacoes[mapa_tickers[ticker]] = preco * cotacao_dolar if not ticker.endswith(".SA") else preco
            except: pass
        return cotacoes
    except: return cotacoes

@st.cache_data(ttl=300, show_spinner=False)
def obter_ativos_por_categoria(email_usuario):
    cat_dict = {"Renda Fixa": [], "Ações": [], "FIIs": [], "Stocks": [], "REITs": [], "ETFs": []}
    try:
        df_config = ler_planilha("Ativos_Config")
        if not df_config.empty:
            for _, row in df_config[df_config['Email'].astype(str).str.lower() == str(email_usuario).strip().lower()].iterrows():
                categoria_bruta, ativo = str(row.get('Categoria', '')).strip().upper(), str(row.get('Ativo', '')).strip().upper()
                categoria = ""
                if categoria_bruta in ["AÇÕES", "ACOES", "AÇÃO", "ACAO"]: categoria = "Ações"
                elif categoria_bruta in ["FIIS", "FII"]: categoria = "FIIs"
                elif categoria_bruta in ["IPCA", "RENDA FIXA", "RF"]: categoria = "Renda Fixa"
                elif categoria_bruta in ["STOCKS", "STOCK"]: categoria = "Stocks"
                elif categoria_bruta in ["REITS", "REIT"]: categoria = "REITs"
                elif categoria_bruta in ["ETFS", "ETF"]: categoria = "ETFs"
                if ativo and ativo != "NAN" and categoria and ativo not in cat_dict[categoria]: cat_dict[categoria].append(ativo)
        try:
            res_td = requests.get("https://tesouro.gabriso.com/bonds", headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            if res_td.status_code == 200:
                for bond in res_td.json().get("bonds", []):
                    nome = str(bond.get("name", "")).strip().upper()
                    if any(p in nome for p in ["IPCA+", "SELIC", "PREFIXADO"]) and not any(p in nome for p in ["EDUCA", "APOSENTADORIA"]):
                        if nome not in cat_dict["Renda Fixa"]: cat_dict["Renda Fixa"].append(nome)
        except: pass
        for cat in cat_dict: cat_dict[cat].sort()
        return {categoria: ativos for categoria, ativos in cat_dict.items() if len(ativos) > 0}
    except: return {categoria: ativos for categoria, ativos in cat_dict.items() if len(ativos) > 0}
