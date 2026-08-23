import streamlit as st
import pandas as pd
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi

# -----------------------------------------------------------------------------
# CONEXÃO COM O BANCO DE DADOS MONGODB
# -----------------------------------------------------------------------------
@st.cache_resource
def init_connection():
    """
    Inicializa a conexão com o MongoDB Atlas.
    Usa @st.cache_resource para abrir a conexão apenas uma vez e economizar recursos.
    """
    try:
        # Busca a URI configurada nos secrets do Streamlit
        uri = st.secrets["MONGO_URI"]
        
        # Cria o cliente de conexão
        client = MongoClient(uri, server_api=ServerApi('1'))
        
        # Testa a conexão rapidinho para garantir que a senha está certa
        client.admin.command('ping')
        
        # Retorna o banco de dados que criamos
        return client['app_investimentos']
    
    except Exception as e:
        st.error(f"Erro ao conectar com o MongoDB. Verifique seus Secrets. Detalhe: {e}")
        st.stop()

# Variável db que usaremos nos outros arquivos (ex: from utils import db)
db = init_connection()


# -----------------------------------------------------------------------------
# FUNÇÃO DE LEITURA (Substitui as leituras do Google Sheets)
# -----------------------------------------------------------------------------
def get_data_from_mongo(collection_name):
    """
    Lê uma coleção do MongoDB e retorna os dados como um DataFrame do Pandas.
    Isso garante que os seus gráficos e contas continuem funcionando exatamente como antes!
    """
    try:
        # Busca todos os documentos da coleção. 
        # O parâmetro {"_id": 0} oculta o ID automático do Mongo para a tabela ficar limpa.
        data = list(db[collection_name].find({}, {"_id": 0}))
        
        # Se não tiver nenhum dado na coleção ainda, devolve uma tabela vazia
        if not data:
            return pd.DataFrame()
            
        # Transforma os dados em uma planilha virtual do Pandas
        return pd.DataFrame(data)
        
    except Exception as e:
        st.error(f"Erro ao ler a coleção '{collection_name}': {e}")
        return pd.DataFrame()


# -----------------------------------------------------------------------------
# FUNÇÃO DE ESCRITA (Para facilitar a inserção de dados)
# -----------------------------------------------------------------------------
def insert_data_to_mongo(collection_name, document_dict):
    """
    Salva um novo registro no banco de dados.
    """
    try:
        db[collection_name].insert_one(document_dict)
        return True
    except Exception as e:
        st.error(f"Erro ao salvar dados na coleção '{collection_name}': {e}")
        return False
