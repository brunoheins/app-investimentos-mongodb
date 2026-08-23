import streamlit as st
import pandas as pd
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi

# --- CONEXÃO COM O MONGODB ---
@st.cache_resource
def init_connection():
    # Pega a chave secreta que vamos colocar no Streamlit
    uri = st.secrets["MONGO_URI"]
    client = MongoClient(uri, server_api=ServerApi('1'))
    return client['app_investimentos']

db = init_connection()

# --- FUNÇÃO DE LEITURA (Substitui a leitura da aba) ---
def get_data_from_mongo(collection_name):
    """
    Lê uma coleção do MongoDB e devolve um DataFrame idêntico ao 
    que vinha da planilha, para não quebrar seus gráficos.
    """
    try:
        # Busca os dados no Mongo e esconde o ID de sistema ("_id": 0)
        data = list(db[collection_name].find({}, {"_id": 0}))
        
        if not data:
            return pd.DataFrame()
            
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"Erro ao ler os dados: {e}")
        return pd.DataFrame()
