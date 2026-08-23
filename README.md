# 📈 App Investimentos v2.0

Um aplicativo completo para gestão de portfólio, acompanhamento de rentabilidade real e rebalanceamento inteligente de carteira. Desenvolvido em **Python** com **Streamlit**, utilizando **Google Sheets** como banco de dados dinâmico.

## 🌟 Principais Funcionalidades

### 🔐 Sistema de Autenticação e Segurança (`app.py`)
O sistema possui suporte a múltiplos usuários com isolamento de dados.
* **Login Seguro:** Acesso restrito via E-mail e Senha.
* **Gestão de Acesso:** Novos cadastros entram com status "Pendente" e requerem aprovação do administrador para visualizar dados.
* **Recuperação de Senha:** Sistema automatizado de envio de token de 6 dígitos por e-mail para redefinição de senha segura.

### 💼 Visão Geral e Dashboards
* **Resumo da Aplicação (`resumo.py`):** 
  * Consolidação do **Total Investido** (soma real de depósitos) versus **Valor Atual** (marcação a mercado).
  * Cálculo dinâmico da rentabilidade global e evolução percentual.
  * Gráfico de Distribuição interativo (Pizza) com os pesos reais de Ações, FIIs, Renda Fixa, etc.
  * *Fallback Inteligente:* Integração com cotações ao vivo. Se um ativo não possui cotação online (ex: CDBs), o sistema protege o patrimônio utilizando o preço de custo.
* **Evolução do Saldo (`saldo.py`):** 
  * Gráfico de linha do tempo cruzando o **Dinheiro Aportado** (bolso) e o **Valor de Mercado** acumulados mês a mês.
  * Motor de auditoria temporal: impede projeções distorcidas tratando datas futuras e garantindo o fechamento preciso no mês atual ("Hoje").

### 🎯 Operacional e Rebalanceamento
* **Guia de Aportes Inteligente (`aportes.py`):**
  * O "cérebro" do sistema. O usuário informa o valor do aporte e em quantas compras deseja dividir.
  * O algoritmo cruza o patrimônio atual, as cotações ao vivo e as metas cadastradas pelo usuário.
  * Gera uma lista de **Ordens de Compra Sugeridas**, priorizando as categorias e ativos mais defasados em relação à estratégia, calculando automaticamente a quantidade exata de cotas a comprar.
* **Central de Lançamentos (`lancamentos.py`):**
  * Interface para registrar entradas de **Dinheiro Novo** (Depósitos/Aportes na corretora).
  * Interface para registrar **Ordens de Compra**, atrelando o ativo à sua respectiva categoria, quantidade e preço pago.
* **Configuração da Carteira (`configuracao.py`):**
  * Definição da estratégia pessoal. Permite configurar o peso ideal (%) de Renda Variável vs Renda Fixa, exposição Brasil vs Exterior, e o peso individual de cada ativo na carteira alvo.

---

## 🏗️ Estrutura Técnica e Módulos

O projeto adota uma arquitetura modular baseada no roteamento nativo (`st.navigation`) do Streamlit:

* `app.py`: Ponto de entrada, roteamento e autenticação.
* `utils.py`: Motor de utilidades. Contém funções vitais como conexão com API do Google (gspread), motor de cotações em tempo real, formatação de padrão numérico brasileiro e envio de e-mails via SMTP.
* `menu/`: Pacote contendo as regras de visualização e interface de cada tela da aplicação.
* `.streamlit/config.toml`: Configurações de tema e layout do framework.

## 🚀 Tecnologias Utilizadas

* **Python 3.x**
* **Streamlit:** Framework de interface e roteamento.
* **Pandas:** Processamento de DataFrames e regras de negócio.
* **Plotly:** Geração dos gráficos interativos de evolução e distribuição.
* **Gspread / Oauth2client:** Comunicação segura de leitura e escrita com o banco de dados (Google Sheets).

## 🛠️ Como executar localmente

1. Clone o repositório.
2. Instale as dependências executando: 
   ```bash
   pip install -r requirements.txt
3. Configure os segredos do Google (Service Account) e provedor de E-mail nos Secrets do Streamlit (.streamlit/secrets.toml).
4. Inicie o servidor local do Streamlit:
    ```bash
    streamlit run app.py
