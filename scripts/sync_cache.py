import os
import re
import io
import pandas as pd
import requests
import yfinance as yf
from pymongo import MongoClient
from datetime import datetime, timedelta

def get_db():
    MONGO_URI = os.getenv("MONGO_URI")
    if not MONGO_URI:
        raise ValueError("Variável MONGO_URI não encontrada.")
    client = MongoClient(MONGO_URI)
    return client['app_v2'] # Nome do seu banco

def descobrir_todos_ativos(db):
    """Varre o banco para achar todos os ativos únicos cadastrados (Transações + Config)."""
    ativos_set = set()
    
    # Ativos nas transações
    for atv in db.transacoes.distinct("atv"):
        if atv and str(atv).strip().upper() not in ["NAN", "NONE", ""]:
            ativos_set.add(str(atv).strip().upper())
            
    # Ativos nas configurações de carteira
    usuarios = db.usuarios.find({}, {"ativos": 1})
    for u in usuarios:
        for a in u.get("ativos", []):
            atv = a.get("atv")
            if atv and str(atv).strip().upper() not in ["NAN", "NONE", ""]:
                ativos_set.add(str(atv).strip().upper())
                
    # Separa Tesouro de Bolsa
    titulos_td = [a for a in ativos_set if " " in a or "TESOURO" in a]
    ativos_bolsa = [a for a in ativos_set if a not in titulos_td]
    
    return titulos_td, ativos_bolsa

def atualizar_tesouro(db):
    print("=== Iniciando Sincronização do TESOURO DIRETO ===")
    url = "https://www.tesourotransparente.gov.br/ckan/dataset/df56aa42-484a-4a59-8184-7676580c81e3/resource/796d2059-14e9-44e3-80c9-2d9e30b405c1/download/precotaxatesourodireto.csv"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    agora = datetime.now()
    
    try:
        res = requests.get(url, headers=headers, timeout=30)
        res.raise_for_status()
        df = pd.read_csv(io.StringIO(res.text), sep=";", decimal=",")
        
        df['Data Base'] = pd.to_datetime(df['Data Base'], dayfirst=True)
        df['Data Vencimento'] = pd.to_datetime(df['Data Vencimento'], dayfirst=True)
        df['Ano'] = df['Data Vencimento'].dt.year.astype(str)
        df['Titulo_Completo'] = df['Tipo Titulo'].astype(str).str.strip() + " " + df['Ano']
        
        df_recente = df.sort_values('Data Base').groupby('Titulo_Completo').last().reset_index()
        
        for _, row in df_recente.iterrows():
            titulo = row['Titulo_Completo']
            preco_compra = float(row.get('PU Compra Manha', 0.0))
            
            # Atualizamos direto na cotacoes_cache para o utils.py pegar automático
            if preco_compra > 0:
                db.cotacoes_cache.update_one(
                    {"_id": titulo},
                    {"$set": {"preco": preco_compra, "ultima_atualizacao": agora}},
                    upsert=True
                )
        print(f"✅ Tesouro Direto atualizado ({len(df_recente)} títulos).")
    except Exception as e:
        print(f"❌ Erro Tesouro: {e}")

def atualizar_bolsa_rv(db, ativos_bolsa):
    print(f"=== Iniciando Sincronização RV ({len(ativos_bolsa)} ativos) ===")
    if not ativos_bolsa: return
    
    tickers_yf = []
    mapa_tickers = {}
    tem_exterior = False
    agora = datetime.now()
    
    for ativo in ativos_bolsa:
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
        if df_raw.empty: return
        
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
            if ticker == "BRL=X": continue
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
                    preco = s_last.get(p_col)
                    break
                    
            if preco is not None and not pd.isna(preco):
                preco_float = float(preco)
                if not ticker.endswith(".SA"):
                    preco_float *= cotacao_dolar
                    
                ativo_original = mapa_tickers[ticker]
                db.cotacoes_cache.update_one(
                    {"_id": ativo_original},
                    {"$set": {"preco": preco_float, "ultima_atualizacao": agora}},
                    upsert=True
                )
        print("✅ Cotações de RV atualizadas com sucesso.")
    except Exception as e:
        print(f"❌ Erro RV: {e}")

def atualizar_dividendos(db, ativos_bolsa):
    print(f"=== Iniciando Sincronização DIVIDENDOS ({len(ativos_bolsa)} ativos) ===")
    if not ativos_bolsa: return
    
    agora = datetime.now()
    dois_anos_atras = agora - timedelta(days=730)
    
    for ativo in ativos_bolsa:
        ticker = ativo
        if "." not in ticker and re.search(r'\d+$', ticker):
            ticker = f"{ticker}.SA"
            
        try:
            divs_raw = yf.Ticker(ticker).dividends 
            if not divs_raw.empty:
                divs_raw.index = divs_raw.index.tz_localize(None)
                divs_salvar = divs_raw[divs_raw.index >= dois_anos_atras]
                divs_dict = {d.strftime('%Y-%m-%d'): float(v) for d, v in divs_salvar.items()}
                
                db.dividendos_cache.update_one(
                    {"_id": ticker},
                    {"$set": {"dividendos": divs_dict, "ultima_atualizacao": agora}},
                    upsert=True
                )
            else:
                db.dividendos_cache.update_one(
                    {"_id": ticker},
                    {"$set": {"dividendos": {}, "ultima_atualizacao": agora}},
                    upsert=True
                )
        except Exception as e:
            print(f"Erro ao baixar proventos para {ativo}: {e}")
    print("✅ Histórico de Dividendos atualizado.")

if __name__ == "__main__":
    db = get_db()
    
    # 1. Ajuste de fuso horário seguro (UTC - 3)
    agora_utc = datetime.utcnow()
    agora_brt = agora_utc - timedelta(hours=3)
    hora_atual = agora_brt.hour
    
    print(f"Iniciando rotina. Hora atual no Brasil (BRT): {hora_atual}h")
    
    # 2. Descobre todos os ativos no banco
    titulos_td, ativos_bolsa = descobrir_todos_ativos(db)
    
    # 3. O MAESTRO: Decide o que rodar baseado na hora
    
    # Sempre roda RV (Ações, FIIs, ETFs) de hora em hora
    atualizar_bolsa_rv(db, ativos_bolsa)
    
    # Roda Tesouro apenas às 10h e 15h
    if hora_atual in [10, 15]:
        atualizar_tesouro(db)
        
    # Roda Dividendos apenas às 9h da manhã
    if hora_atual == 9:
        atualizar_dividendos(db, ativos_bolsa)
