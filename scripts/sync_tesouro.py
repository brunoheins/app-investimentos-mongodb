import pandas as pd
import requests
import io
import os
from pymongo import MongoClient
import datetime

def atualizar_tesouro_mongodb():
    print("Iniciando sincronização com o Tesouro Nacional...")
    
    # 1. Pega a senha do MongoDB das variáveis de ambiente (o GitHub vai injetar isso)
    MONGO_URI = os.getenv("MONGO_URI")
    if not MONGO_URI:
        print("❌ ERRO: Variável MONGO_URI não encontrada.")
        return

    # 2. Conecta no MongoDB
    client = MongoClient(MONGO_URI)
    db = client.app_v2 # Substitua pelo nome real do seu banco no Mongo
    colecao = db.tesouro_cache

    # 3. Baixa os dados oficiais
    url = "https://www.tesourotransparente.gov.br/ckan/dataset/df56aa42-484a-4a59-8184-7676580c81e3/resource/796d2059-14e9-44e3-80c9-2d9e30b405c1/download/precotaxatesourodireto.csv"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    try:
        res = requests.get(url, headers=headers, timeout=30)
        res.raise_for_status()
        
        df = pd.read_csv(io.StringIO(res.text), sep=";", decimal=",")
        
        # Tratamento de datas e nomes (A mágica que validamos)
        df['Data Base'] = pd.to_datetime(df['Data Base'], dayfirst=True)
        df['Data Vencimento'] = pd.to_datetime(df['Data Vencimento'], dayfirst=True)
        df['Ano'] = df['Data Vencimento'].dt.year.astype(str)
        df['Titulo_Completo'] = df['Tipo Titulo'].astype(str).str.strip() + " " + df['Ano']
        
        # Pega a cotação mais recente de cada título
        df_recente = df.sort_values('Data Base').groupby('Titulo_Completo').last().reset_index()
        
        agora = datetime.datetime.now()
        
        # 4. Atualiza o MongoDB (Fazendo um Upsert)
        for _, row in df_recente.iterrows():
            titulo = row['Titulo_Completo']
            preco_resgate = float(row.get('PU Venda Manha', 0.0))
            preco_compra = float(row.get('PU Compra Manha', 0.0))
            data_cotacao = row['Data Base']
            
            colecao.update_one(
                {"_id": titulo},
                {"$set": {
                    "preco_resgate": preco_resgate,
                    "preco_compra": preco_compra,
                    "data_cotacao": data_cotacao,
                    "ultima_atualizacao": agora
                }},
                upsert=True
            )
            
        print(f"✅ Sincronização concluída! {len(df_recente)} títulos do Tesouro atualizados no MongoDB.")
        
    except Exception as e:
        print(f"❌ Erro durante a atualização: {e}")

if __name__ == "__main__":
    atualizar_tesouro_mongodb()
