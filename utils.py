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
from datetime import datetime, timedelta # Importação ajustada para o limite de tempo

# ==========================================
# 1. CONEXÃO COM O MONGODB ATLAS (V2)
# ==========================================
@st.cache_resource
def init_connection():
    try:
        uri = st.secrets["MONGO_URI"]
        client = MongoClient(uri, server_api=ServerApi('1'), tlsCAFile=certifi.where())
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
    try:
        if aba_nome == "Usuarios":
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
        return False

def registrar_deposito(email, data, valor):
    try:
        data_val = datetime.strptime(str(data), "%d/%m/%Y")
        db.transacoes.insert_one({"email": str(email).strip().lower(), "tipo": "D", "dt": data_val, "val": float(valor)})
        st.cache_data.clear() 
        return True
    except Exception as e:
        return False

def registrar_compra(email, data, categoria, ativo, quantidade, preco_medio, observacao=""):
    try:
        data_val = datetime.strptime(str(data), "%d/%m/%Y")
        doc = {
            "email": str(email).strip().lower(), "tipo": "I", "dt": data_val,
            "cat": str(categoria).strip(), "atv": str(ativo).strip().upper(),
            "qtd": float(quantidade), "pm": float(preco_medio)
        }
        if observacao is not None:
            obs_str = str(observacao).strip()
            if obs_str and obs_str.lower() not in ["nan", "none"]: doc["obs"] = obs_str

        db.transacoes.insert_one(doc)
        st.cache_data.clear()
        return True
    except Exception as e:
        return False

# ==========================================
# 5. GERENCIADOR DE EDIÇÃO E BACKUP (AUDITORIA)
# ==========================================
def atualizar_historico_usuario(email, nome_aba, df_editado):
    try:
        e_lower = email.strip().lower()
        if nome_aba == "Depositos":
            db.transacoes.delete_many({"email": e_lower, "tipo": "D"})
            if not df_editado.empty:
                novos = []
                for _, row in df_editado.iterrows():
                    d = pd.to_datetime(row.get("Data"), errors='coerce', dayfirst=True)
                    if pd.notna(d): novos.append({"email": e_lower, "tipo": "D", "dt": d, "val": extrair_numero_br(row.get("Valor"))})
                if novos: db.transacoes.insert_many(novos)

        elif nome_aba == "Investimentos":
            db.transacoes.delete_many({"email": e_lower, "tipo": "I"})
            if not df_editado.empty:
                novos = []
                for _, row in df_editado.iterrows():
                    d = pd.to_datetime(row.get("DataCompra"), errors='coerce', dayfirst=True)
                    if pd.notna(d):
                        doc = {"email": e_lower, "tipo": "I", "dt": d, "cat": str(row.get("Categoria")), "atv": str(row.get("Ativo")).upper(), "qtd": extrair_numero_br(row.get("Quantidade")), "pm": extrair_numero_br(row.get("PrecoMedio"))}
                        obs = str(row.get("Observacao", "")).strip()
                        if obs and obs.lower() not in ["nan", "none"]: doc["obs"] = obs
                        novos.append(doc)
                if novos: db.transacoes.insert_many(novos)

        st.cache_data.clear()
        return True
    except Exception as e:
        return False

def deletar_registros_usuario(nome_aba, email):
    try:
        e_lower = email.strip().lower()
        if nome_aba == "Depositos": db.transacoes.delete_many({"email": e_lower, "tipo": "D"})
        elif nome_aba == "Investimentos": db.transacoes.delete_many({"email": e_lower, "tipo": "I"})
        elif nome_aba == "Configuracao": db.usuarios.update_one({"_id": e_lower}, {"$unset": {"metas": ""}})
        elif nome_aba == "Ativos_Config": db.usuarios.update_one({"_id": e_lower}, {"$set": {"ativos": []}})
        st.cache_data.clear()
        return True, "Sucesso"
    except Exception as e:
        return False, f"Erro: {e}"

def inserir_lote_registros(nome_aba, df):
    if df.empty: return True, "Vazio."
    try:
        email = df['Email'].iloc[0].strip().lower() if 'Email' in df.columns else ""
        if not email: return False, "E-mail não encontrado no lote."

        if nome_aba in ["Depositos", "Investimentos"]: atualizar_historico_usuario(email, nome_aba, df)
        elif nome_aba == "Configuracao": salvar_configuracao(email, df.iloc[0].to_dict())
        elif nome_aba == "Ativos_Config":
            for cat in df['Categoria'].unique(): salvar_ativos_categoria(email, cat, df[df['Categoria'] == cat])

        st.cache_data.clear()
        return True, "Sucesso"
    except Exception as e:
        return False, f"Erro: {e}"

# ==========================================
# 6. AUTENTICAÇÃO
# ==========================================
def registrar_novo_usuario(nome, email, senha):
    try:
        email_lower = email.strip().lower()
        if db.usuarios.count_documents({"_id": email_lower}) > 0: return False, "⚠️ Este e-mail já está cadastrado."
        db.usuarios.insert_one({"_id": email_lower, "senha": senha, "nome": nome.strip(), "status": "Pendente", "metas": {}, "ativos": []})
        st.cache_data.clear()
        return True, "✅ Cadastro enviado com sucesso!"
    except Exception as e: return False, f"Erro: {e}"

def verificar_email_cadastrado(email):
    try: return db.usuarios.count_documents({"_id": email.strip().lower()}) > 0
    except: return False

def redefinir_senha_aprovada(email, nova_senha):
    try:
        res = db.usuarios.update_one({"_id": email.strip().lower()}, {"$set": {"senha": nova_senha}})
        if res.matched_count > 0:
            st.cache_data.clear()
            return True, "✅ Senha alterada!"
        return False, "Usuário não encontrado."
    except Exception as e: return False, f"Erro: {e}"

def atualizar_dados_perfil(email, novo_nome, nova_senha):
    try:
        atualizacoes = {}
        if novo_nome: atualizacoes["nome"] = novo_nome.strip()
        if nova_senha: atualizacoes["senha"] = nova_senha
        if not atualizacoes: return True, "Nada a atualizar."

        res = db.usuarios.update_one({"_id": email.strip().lower()}, {"$set": atualizacoes})
        if res.matched_count > 0:
            st.cache_data.clear()
            return True, "✅ Perfil atualizado!"
        return False, "Usuário não encontrado."
    except Exception as e: return False, f"Erro: {e}"

def enviar_codigo_email(email_destino, codigo):
    try:
        remetente = st.secrets["email"]["endereco"]
        senha_app = st.secrets["email"]["senha_app"]
        msg = MIMEMultipart()
        msg['From'], msg['To'], msg['Subject'] = remetente, email_destino, "🔒 Código de Recuperação de Senha"
        msg.attach(MIMEText(f"Seu código: {codigo}", 'plain'))
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(remetente, senha_app)
        server.send_message(msg)
        server.quit()
        return True, "Enviado!"
    except Exception as e: return False, f"Erro: {e}"

# ==========================================
# 7. COTAÇÕES E INTELIGÊNCIA FINANCEIRA
# ==========================================
@st.cache_data(ttl=86400, show_spinner=False)
def buscar_setor_yahoo(ativo, categoria):
    if categoria == "Renda Fixa": return "Renda Fixa"
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
    if categoria in ["Ações", "FIIs"] and "." not in ticker and re.search(r'\d+$', ticker): ticker = f"{ticker}.SA"
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


# ==============================================================
# MOTOR DE COTAÇÕES 100% SOB DEMANDA COM CACHE DE RAM ISOLADO (Otimizado)
# ==============================================================
@st.cache_data(ttl=3600, show_spinner=False)
def obter_cotacoes(email_usuario):
    cotacoes = {}
    ativos_buscados = set()
    
    # 1. VARREDURA LOCAL: Puxa APENAS os ativos do usuário solicitado
    try:
        e_lower = email_usuario.strip().lower()
        df_invest = ler_planilha("Investimentos")
        df_config = ler_planilha("Ativos_Config")
        
        if not df_invest.empty:
            df_user = df_invest[df_invest['Email'].astype(str).str.lower() == e_lower]
            for _, row in df_user.iterrows():
                ativo = str(row.get('Ativo', '')).strip().upper()
                if ativo and ativo not in ["NAN", "NONE", ""]:
                    ativos_buscados.add(ativo)
                    pm = extrair_numero_br(row.get('PrecoMedio', row.get('Preco', 0)))
                    if pm > 0 and ativo not in cotacoes: 
                        cotacoes[ativo] = pm

        if not df_config.empty:
            df_user_conf = df_config[df_config['Email'].astype(str).str.lower() == e_lower]
            for _, row in df_user_conf.iterrows():
                ativo = str(row.get('Ativo', '')).strip().upper()
                if ativo and ativo not in ["NAN", "NONE", ""]: 
                    ativos_buscados.add(ativo)
                    
    except Exception as e:
        print(f"Erro ao buscar lista de ativos do usuário: {e}")
        
    if not ativos_buscados: 
        return cotacoes

    agora = datetime.now()
    limite_tempo = agora - timedelta(hours=1)
    
    ativos_para_atualizar = []
    
    # 2. CONSULTA CIRÚRGICA EM LOTE NO MONGO (Substitui o loop de find_one)
    try:
        docs_cache = list(db.cotacoes_cache.find({"_id": {"$in": list(ativos_buscados)}}))
        mapa_cache = {doc["_id"]: doc for doc in docs_cache}
    except Exception as e:
        print(f"Erro ao consultar cache em lote: {e}")
        mapa_cache = {}

    for ativo in ativos_buscados:
        doc = mapa_cache.get(ativo)
        if doc and doc.get("ultima_atualizacao", datetime.min) > limite_tempo:
            cotacoes[ativo] = doc.get("preco", 0.0)
        else:
            ativos_para_atualizar.append(ativo)
            
    if not ativos_para_atualizar:
        return cotacoes
        
    # 3. Separar Tesouro Direto de Ativos de Bolsa
    titulos_td_pedidos = [a for a in ativos_para_atualizar if " " in a or "TESOURO" in a]
    ativos_bolsa_pedidos = [a for a in ativos_para_atualizar if a not in titulos_td_pedidos]
    
    # --- 3A. ATUALIZAR TESOURO DIRETO ---
    if titulos_td_pedidos:
        mapa_td_limpo = {}
        
        def normalizar_nome_td(nome):
            return re.sub(r'[^A-Z0-9]', '', str(nome).upper())

        headers_td = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest"
        }
        
        urls_para_tentar = [
            "https://tesouro.gabriso.com/bonds"
        ]
        
        sucesso_api = False
        for url in urls_para_tentar:
            if sucesso_api: 
                break
            try:
                res_alt = requests.get(url, headers=headers_td, timeout=10)
                if res_alt.status_code == 200:
                    dados_json = res_alt.json()
                    lista_bonds = dados_json.get("bonds", [])
                    
                    if lista_bonds:
                        for bond in lista_bonds:
                            nome_original = str(bond.get("name", ""))
                            chave_limpa = normalizar_nome_td(nome_original)
                            preco_resgate = bond.get("unitary_redemption_value", 0.0)
                            preco = extrair_numero_br(preco_resgate)
                            
                            if chave_limpa and preco > 0:
                                mapa_td_limpo[chave_limpa] = preco
                        sucesso_api = True
            except:
                pass 

        for titulo in titulos_td_pedidos:
            chave_busca = normalizar_nome_td(titulo)
            
            if chave_busca in mapa_td_limpo:
                preco_td = mapa_td_limpo[chave_busca]
                cotacoes[titulo] = preco_td
                
                try:
                    db.cotacoes_cache.update_one(
                        {"_id": titulo},
                        {"$set": {"preco": preco_td, "ultima_atualizacao": agora}},
                        upsert=True
                    )
                except:
                    pass
            else:
                doc_velho = mapa_cache.get(titulo)
                if doc_velho: 
                    cotacoes[titulo] = doc_velho.get("preco", cotacoes.get(titulo, 0.0))
    
    # --- 3B. ATUALIZAR BOLSA YAHOO FINANCE ---
    if ativos_bolsa_pedidos:
        tickers_yf = []
        mapa_tickers = {}
        tem_exterior = False
        
        for ativo in ativos_bolsa_pedidos:
            ticker = ativo
            if "." not in ticker and re.search(r'\d+$', ticker):
                ticker = f"{ticker}.SA"
            
            if not ticker.endswith(".SA"): 
                tem_exterior = True
                
            tickers_yf.append(ticker)
            mapa_tickers[ticker] = ativo
            
        if tem_exterior:
            tickers_yf.append("BRL=X")
            
        try:
            df_raw = yf.download(list(set(tickers_yf)), period="1d", progress=False, threads=True)
            
            if df_raw.empty:
                st.toast("⚠️ Yahoo Finance não retornou dados. Usando backup.", icon="🚨")
                raise Exception("YF vazio.")
                
            s_last = df_raw.ffill().iloc[-1]
            
            cotacao_dolar = 1.0
            if tem_exterior:
                for p_col in ['Close', 'Adj Close']:
                    if isinstance(s_last.index, pd.MultiIndex):
                        if (p_col, "BRL=X") in s_last.index:
                            cotacao_dolar = float(s_last[(p_col, "BRL=X")])
                            break
                        elif ("BRL=X", p_col) in s_last.index:
                            cotacao_dolar = float(s_last[("BRL=X", p_col)])
                            break
                    else:
                        if "BRL=X" in tickers_yf and len(set(tickers_yf)) == 1:
                            cotacao_dolar = float(s_last.get(p_col, 1.0))
                            break
                            
            for ticker in tickers_yf:
                if ticker == "BRL=X": 
                    continue
                
                preco = None
                for p_col in ['Close', 'Adj Close']:
                    if isinstance(s_last.index, pd.MultiIndex):
                        if (p_col, ticker) in s_last.index:
                            preco = s_last[(p_col, ticker)]
                            break
                        elif (ticker, p_col) in s_last.index:
                            preco = s_last[(ticker, p_col)]
                            break
                    else:
                        ativos_pedidos = set([t for t in tickers_yf if t != "BRL=X"])
                        if len(ativos_pedidos) == 1:
                            preco = s_last.get(p_col)
                            break
                            
                if preco is not None and not pd.isna(preco):
                    preco_float = float(preco)
                    
                    if not ticker.endswith(".SA"):
                        preco_float *= cotacao_dolar
                        
                    ativo_original = mapa_tickers[ticker]
                    cotacoes[ativo_original] = preco_float
                    
                    db.cotacoes_cache.update_one(
                        {"_id": ativo_original},
                        {"$set": {"preco": preco_float, "ultima_atualizacao": agora}},
                        upsert=True
                    )
        except Exception as e:
            for ativo in ativos_bolsa_pedidos:
                doc_velho = mapa_cache.get(ativo)
                if doc_velho: 
                    cotacoes[ativo] = doc_velho.get("preco", cotacoes.get(ativo, 0.0))

    return cotacoes
    

@st.cache_data(ttl=300, show_spinner=False)
def obter_ativos_por_categoria(email_usuario):
    cat_dict = {"Renda Fixa": [], "Ações": [], "FIIs": [], "Stocks": [], "REITs": [], "ETFs": []}
    try:
        df_config = ler_planilha("Ativos_Config")
        if not df_config.empty:
            for _, row in df_config[df_config['Email'].astype(str).str.lower() == email_usuario.strip().lower()].iterrows():
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

# ==========================================
# CÉREBRO DE BENCHMARKS (API BCB + YFINANCE + MONGODB)
# ==========================================
@st.cache_data(ttl=86400, show_spinner=False)
def obter_historico_benchmarks(mes_inicial, mes_final):
    """Busca o histórico e usa o MongoDB como Cache Diário (D-0) para evitar Rate Limit"""
    
    doc_id = f"benchmarks_{mes_inicial}_{mes_final}"
    agora = datetime.now()
    hoje_zero_hora = agora.replace(hour=0, minute=0, second=0, microsecond=0)
    
    doc_banco = None
    try:
        doc_banco = db.benchmarks_cache.find_one({"_id": doc_id})
        if doc_banco and doc_banco.get("ultima_atualizacao", datetime.min) >= hoje_zero_hora:
            return doc_banco.get("dados", {})
    except Exception as e:
        print(f"Erro ao ler cache de benchmarks no Mongo: {e}")

    dados_velhos = doc_banco.get("dados", {}) if doc_banco else {}
    
    dt_ini_bcb = f"01/{mes_inicial[-2:]}/{mes_inicial[:4]}"
    periodo_fim = pd.to_datetime(mes_final + '-01') + pd.offsets.MonthEnd(1)
    dt_fim_bcb = periodo_fim.strftime('%d/%m/%Y')
    
    df_bench = pd.DataFrame({'MesAno': pd.date_range(start=f"{mes_inicial}-01", end=periodo_fim, freq='MS').strftime('%Y-%m')})
    df_bench['CDI'] = 0.0
    df_bench['IPCA'] = 0.0
    df_bench['IBOV'] = 0.0
    df_bench['SP500_BRL'] = 0.0
    
    headers = {"User-Agent": "Mozilla/5.0"}
    
    try:
        url_cdi = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.4391/dados?formato=json&dataInicial={dt_ini_bcb}&dataFinal={dt_fim_bcb}"
        res_cdi = requests.get(url_cdi, headers=headers, timeout=5)
        if res_cdi.status_code == 200:
            df_cdi_raw = pd.DataFrame(res_cdi.json())
            df_cdi_raw['MesAno'] = pd.to_datetime(df_cdi_raw['data'], format='%d/%m/%Y').dt.strftime('%Y-%m')
            df_cdi_raw['valor'] = df_cdi_raw['valor'].astype(float) / 100.0
            for _, row in df_cdi_raw.iterrows():
                df_bench.loc[df_bench['MesAno'] == row['MesAno'], 'CDI'] = row['valor']
    except Exception:
        for mes_str, valores in dados_velhos.items():
            df_bench.loc[df_bench['MesAno'] == mes_str, 'CDI'] = valores.get('CDI', 0.0)

    try:
        url_ipca = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados?formato=json&dataInicial={dt_ini_bcb}&dataFinal={dt_fim_bcb}"
        res_ipca = requests.get(url_ipca, headers=headers, timeout=5)
        if res_ipca.status_code == 200:
            df_ipca_raw = pd.DataFrame(res_ipca.json())
            df_ipca_raw['MesAno'] = pd.to_datetime(df_ipca_raw['data'], format='%d/%m/%Y').dt.strftime('%Y-%m')
            df_ipca_raw['valor'] = df_ipca_raw['valor'].astype(float) / 100.0
            for _, row in df_ipca_raw.iterrows():
                df_bench.loc[df_bench['MesAno'] == row['MesAno'], 'IPCA'] = row['valor']
    except Exception:
        for mes_str, valores in dados_velhos.items():
            df_bench.loc[df_bench['MesAno'] == mes_str, 'IPCA'] = valores.get('IPCA', 0.0)

    try:
        dt_ini_yf = (pd.to_datetime(f"{mes_inicial}-01") - pd.DateOffset(months=1)).strftime('%Y-%m-%d')
        dt_fim_yf = (periodo_fim + pd.DateOffset(days=5)).strftime('%Y-%m-%d')
        
        tickers = ['^BVSP', '^GSPC', 'BRL=X']
        df_yf = yf.download(tickers, start=dt_ini_yf, end=dt_fim_yf, interval='1mo', progress=False)
        
        if df_yf.empty or 'Close' not in df_yf.columns:
            raise Exception("YF bloqueou.")
            
        df_close = df_yf['Close']
        if df_close.index.tz is not None:
            df_close.index = df_close.index.tz_localize(None)
            
        if '^BVSP' in df_close.columns:
            ret_ibov = df_close['^BVSP'].pct_change()
            for idx_date, val in ret_ibov.items():
                if pd.notna(val):
                    df_bench.loc[df_bench['MesAno'] == str(idx_date)[:7], 'IBOV'] = float(val)

        if '^GSPC' in df_close.columns and 'BRL=X' in df_close.columns:
            preco_sp500_brl = df_close['^GSPC'] * df_close['BRL=X']
            ret_sp500_brl = preco_sp500_brl.pct_change()
            for idx_date, val in ret_sp500_brl.items():
                if pd.notna(val):
                    df_bench.loc[df_bench['MesAno'] == str(idx_date)[:7], 'SP500_BRL'] = float(val)

    except Exception:
        for mes_str, valores in dados_velhos.items():
            df_bench.loc[df_bench['MesAno'] == mes_str, 'IBOV'] = valores.get('IBOV', 0.0)
            df_bench.loc[df_bench['MesAno'] == mes_str, 'SP500_BRL'] = valores.get('SP500_BRL', 0.0)

    resultado_dict = df_bench.set_index('MesAno').to_dict(orient='index')
    
    try:
        db.benchmarks_cache.update_one(
            {"_id": doc_id},
            {"$set": {"dados": resultado_dict, "ultima_atualizacao": agora}},
            upsert=True
        )
    except Exception as e:
        print(f"Erro ao salvar benchmarks no Mongo: {e}")

    return resultado_dict

# ==============================================================
# MOTOR DE DIVIDENDOS COM CACHE GLOBAL NO MONGODB (D-0)
# ==============================================================
@st.cache_data(ttl=3600, show_spinner=False)
def buscar_historico_dividendos(df_transacoes):
    hoje = pd.Timestamp.today().tz_localize(None)
    um_ano_atras = hoje - pd.DateOffset(months=12)
    dois_anos_atras = hoje - pd.DateOffset(months=24) # Margem de segurança para o banco
    
    dados_dividendos = []
    ativos_com_erro = []

    # Localiza a coluna de Data dinamicamente
    col_data = next((c for c in df_transacoes.columns if 'dat' in str(c).lower()), None)
    
    if col_data:
        df_transacoes['Data_Calc'] = pd.to_datetime(df_transacoes[col_data], format='%d/%m/%Y', errors='coerce')
    else:
        df_transacoes['Data_Calc'] = pd.to_datetime('2000-01-01')

    # Remove linhas onde a data não pôde ser lida
    df_transacoes = df_transacoes.dropna(subset=['Data_Calc'])
    ativos = df_transacoes['Ativo'].unique()

    agora = datetime.now()
    hoje_zero_hora = agora.replace(hour=0, minute=0, second=0, microsecond=0)

    for ativo in ativos:
        df_ativo_tx = df_transacoes[df_transacoes['Ativo'] == ativo]

        # Normaliza o ticker para a B3
        ticker_yf = ativo
        if "." not in ticker_yf and re.search(r'\d+$', ticker_yf):
            ticker_yf = f"{ticker_yf}.SA"

        divs = pd.Series(dtype=float)

        try:
            # 1. VERIFICA O MONGODB PRIMEIRO (Cache D-0)
            doc_cache = db.dividendos_cache.find_one({"_id": ticker_yf})
            
            # Se já foi atualizado hoje, puxa do banco instantaneamente
            if doc_cache and doc_cache.get("ultima_atualizacao", datetime.min) >= hoje_zero_hora:
                divs_dict = doc_cache.get("dividendos", {})
                if divs_dict:
                    # Reconstrói a série temporal do Pandas
                    divs = pd.Series({pd.to_datetime(k): float(v) for k, v in divs_dict.items()})
            else:
                # 2. SE NÃO TEM OU ESTÁ VELHO, BATE NO YAHOO FINANCE
                ticker = yf.Ticker(ticker_yf)
                divs_raw = ticker.dividends 
                
                if not divs_raw.empty:
                    divs_raw.index = divs_raw.index.tz_localize(None)
                    
                    # Salva os últimos 2 anos no banco para não pesar, mas garantir histórico
                    divs_salvar = divs_raw[divs_raw.index >= dois_anos_atras]
                    
                    # Converte para dicionário amigável para o MongoDB (Data em string)
                    divs_dict = {d.strftime('%Y-%m-%d'): float(v) for d, v in divs_salvar.items()}
                    
                    # Atualiza o banco (ou cria se não existir)
                    db.dividendos_cache.update_one(
                        {"_id": ticker_yf},
                        {"$set": {"dividendos": divs_dict, "ultima_atualizacao": agora}},
                        upsert=True
                    )
                    divs = divs_salvar
                else:
                    # Se não distribui dividendos, salva vazio para não tentar de novo hoje
                    db.dividendos_cache.update_one(
                        {"_id": ticker_yf},
                        {"$set": {"dividendos": {}, "ultima_atualizacao": agora}},
                        upsert=True
                    )

            # 3. CRUZA O HISTÓRICO GLOBAL COM A CARTEIRA DO USUÁRIO
            if not divs.empty:
                # Filtra apenas os últimos 12 meses para exibir
                divs = divs[divs.index >= um_ano_atras]
                
                for data_div, valor_por_cota in divs.items():
                    # MÁGICA HISTÓRICA: Soma as cotas compradas ANTES ou NO DIA da Data Com
                    qtd_na_data = df_ativo_tx[df_ativo_tx['Data_Calc'] <= data_div]['Quantidade'].sum()
                    
                    if qtd_na_data > 0:
                        dados_dividendos.append({
                            'Data': data_div,
                            'Mês_Sort': data_div.strftime('%Y-%m'),
                            'Ativo': ativo,
                            'Valor por Cota': valor_por_cota,
                            'Total Recebido': valor_por_cota * qtd_na_data
                        })
                        
        except Exception as e:
            # 4. FALLBACK BLINDADO: Se o Yahoo Finance bloquear o IP (Rate Limit) ou cair a internet,
            # nós resgatamos o histórico do MongoDB ignorando a data de atualização.
            print(f"Falha na API para {ativo}, tentando usar cache velho: {e}")
            try:
                doc_velho = db.dividendos_cache.find_one({"_id": ticker_yf})
                if doc_velho and doc_velho.get("dividendos"):
                    divs_dict = doc_velho.get("dividendos", {})
                    divs = pd.Series({pd.to_datetime(k): float(v) for k, v in divs_dict.items()})
                    divs = divs[divs.index >= um_ano_atras]
                    
                    for data_div, valor_por_cota in divs.items():
                        qtd_na_data = df_ativo_tx[df_ativo_tx['Data_Calc'] <= data_div]['Quantidade'].sum()
                        if qtd_na_data > 0:
                            dados_dividendos.append({
                                'Data': data_div,
                                'Mês_Sort': data_div.strftime('%Y-%m'),
                                'Ativo': ativo,
                                'Valor por Cota': valor_por_cota,
                                'Total Recebido': valor_por_cota * qtd_na_data
                            })
                else:
                    ativos_com_erro.append(ativo)
            except:
                ativos_com_erro.append(ativo)
                
    return pd.DataFrame(dados_dividendos), ativos_com_erro
    
# ==========================================
# 8. ADMIN / IMPERSONAÇÃO
# ==========================================
def listar_todos_usuarios():
    try:
        usuarios = list(db.usuarios.find({}, {"_id": 1, "nome": 1}))
        return [{"email": u["_id"], "nome": u.get("nome", "Sem Nome")} for u in usuarios]
    except Exception as e:
        return []
