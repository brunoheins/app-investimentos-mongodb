"""
=====================================================================================
Sincronizador de Dados Financeiros e Caches (ETL)
=====================================================================================
Descrição:
    Script responsável por gerenciar e atualizar os caches no MongoDB, incluindo cotações
    diárias de Renda Variável, Tesouro Direto, histórico de dividendos e o histórico 
    mensal de preços de fechamento para os gráficos de evolução patrimonial.

Como executar via terminal:
    python scripts/sync_cache.py --modo [MODO]

Modos de Execução Disponíveis (--modo):
    - auto        : Executa o fluxo padrão automatizado (respeita regras de hora/dia do cron).
    - tudo        : Executa uma carga completa (One-Shot) forçando a atualização de todos os caches.
    - rv          : Atualiza apenas as cotações atuais de Renda Variável (Bolsa).
    - tesouro     : Atualiza apenas os preços dos títulos do Tesouro Direto.
    - dividendos  : Atualiza apenas o histórico de proventos/dividendos dos ativos.
    - historico   : Atualiza o histórico mensal de preços de fechamento (últimos 5 anos).

Variáveis de Ambiente Necessárias:
    - MONGO_URI   : String de conexão com o banco de dados MongoDB Atlas.
=====================================================================================
"""

import os
import re
import io
import pandas as pd
import requests
import yfinance as yf
from pymongo import MongoClient
from datetime import datetime, timedelta
import argparse

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

def atualizar_historico_mensal_ativos(db, ativos_bolsa):
    """Baixa e consolida todo o histórico mensal de preços de fechamento (últimos 5 anos) para o MongoDB."""
    print(f"=== Iniciando Sincronização do HISTÓRICO MENSAL DE PREÇOS ({len(ativos_bolsa)} ativos) ===")
    if not ativos_bolsa: return

    hoje = datetime.now()
    data_inicio = (hoje - timedelta(days=365 * 5)).strftime('%Y-%m-01')
    data_fim = hoje.strftime('%Y-%m-%d')

    for ativo in ativos_bolsa:
        ticker = ativo
        if "." not in ticker and re.search(r'\d+$', ticker):
            ticker = f"{ticker}.SA"

        try:
            df_yf = yf.download(ticker, start=data_inicio, end=data_fim, interval='1mo', progress=False)
            if not df_yf.empty and 'Close' in df_yf.columns:
                df_close = df_yf['Close']
                if isinstance(df_close, pd.DataFrame):
                    df_close = df_close.iloc[:, 0]
                if df_close.index.tz is not None:
                    df_close.index = df_close.index.tz_localize(None)

                precos_mensais = {}
                for idx_date, val in df_close.items():
                    m_str = str(idx_date)[:7] # Formato YYYY-MM
                    if pd.notna(val):
                        precos_mensais[m_str] = float(val)

                if precos_mensais:
                    db.historico_mensal_cache.update_one(
                        {"_id": ativo},
                        {"$set": {"precos_mensais": precos_mensais, "ultima_atualizacao": hoje}},
                        upsert=True
                    )
            print(f"📊 Histórico mensal sincronizado para: {ativo}")
        except Exception as e:
            print(f"❌ Erro ao atualizar histórico mensal de {ativo}: {e}")
            
    print("✅ Histórico Mensal de Ativos atualizado com sucesso no MongoDB.")

if __name__ == "__main__":
    db = get_db()
    
    parser = argparse.ArgumentParser(description="Sincronizador de Caches Financeiros")
    parser.add_argument("--modo", type=str, default="auto", choices=["auto", "tudo", "rv", "tesouro", "dividendos", "historico"],
                        help="Escolha o modo de execução: 'auto' (padrão do cron), 'tudo' (one-shot), ou um cache específico.")
    args = parser.parse_args()

    titulos_td, ativos_bolsa = descobrir_todos_ativos(db)

    if args.modo == "tudo":
        print("🚀 Executando carga completa ONE-SHOT de todos os caches...")
        atualizar_bolsa_rv(db, ativos_bolsa)
        atualizar_tesouro(db)
        atualizar_dividendos(db, ativos_bolsa)
        atualizar_historico_mensal_ativos(db, ativos_bolsa)
        print("✅ Carga completa one-shot finalizada com sucesso!")
        
    elif args.modo == "rv":
        atualizar_bolsa_rv(db, ativos_bolsa)
        
    elif args.modo == "tesouro":
        atualizar_tesouro(db)
        
    elif args.modo == "dividendos":
        atualizar_dividendos(db, ativos_bolsa)
        
    elif args.modo == "historico":
        atualizar_historico_mensal_ativos(db, ativos_bolsa)
        
    else:
        # Modo automático (respeita a regra de horário/dia para o cron)
        agora_utc = datetime.utcnow()
        agora_brt = agora_utc - timedelta(hours=3)
        hora_atual = agora_brt.hour
        dia_atual = agora_brt.day
        
        print(f"Iniciando rotina automática. Data/Hora BRT: Dia {dia_atual}, {hora_atual}h")
        
        atualizar_bolsa_rv(db, ativos_bolsa)
        
        if hora_atual in [10, 15]:
            atualizar_tesouro(db)
            
        if hora_atual == 9:
            atualizar_dividendos(db, ativos_bolsa)

        if dia_atual == 1 and hora_atual == 4:
            atualizar_historico_mensal_ativos(db, ativos_bolsa)
