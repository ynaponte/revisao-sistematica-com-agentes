# Agente de Screening para Revisão Sistemática

Este projeto implementa um agente inteligente projetado para automatizar a triagem (screening) de artigos em revisões sistemáticas de literatura. O sistema utiliza modelos de linguagem (LLMs) como Gemini e Ollama para avaliar títulos e resumos contra critérios de inclusão e exclusão definidos pelo pesquisador.

Recentemente refatorado para uma **Aplicação Web (SPA) Dockerizada**, permitindo fácil uso através de um painel interativo.

## 🚀 Funcionalidades

- **Dashboard Web Interativo**: Interface moderna (Jinja2 + TailwindCSS) em uma Single Page Application para configuração de critérios, upload de planilhas e monitoramento de triagem em tempo real.
- **Triagem Automatizada**: Avaliação rigorosa de artigos baseada em critérios customizáveis usando agentes baseados em LangGraph.
- **Execução Paralela Assíncrona**: Processamento concorrente via background tasks do FastAPI com controle configurável de concorrência.
- **Botão E-STOP**: Parada de emergência durante a execução com salvamento automático do progresso parcial alcançado.
- **Suporte Multi-Provedor**: Compatível com Google Gemini, Ollama (local) e vLLM, com detecção automática de ambiente Docker para modelos locais.
- **Ambiente Conteinerizado**: Deploy fácil através de `docker-compose`, mantendo toda a aplicação leve e independente.

## 🛠️ Stack Tecnológica

- **Backend**: FastAPI (Python 3.12)
- **Orquestração AI**: [LangGraph v1.0.8](https://github.com/langchain-ai/langgraph) / LangChain Core
- **Frontend**: HTML5, Vanilla JS, TailwindCSS (via CDN)
- **Infraestrutura**: Docker & Docker Compose
- **Gerenciador de Dependências**: `uv`

## ⚙️ Configuração e Execução

### 1. Pré-requisitos
- [Docker](https://docs.docker.com/get-docker/) instalado.
- Chave de API do Google Gemini (se for utilizar o Gemini).
- Ollama instalado e rodando na sua máquina Host (se for utilizar o Ollama local).

### 2. Configuração do Ambiente
Clone o repositório e crie o seu arquivo `.env`:

```bash
git clone git@github.com:ynaponte/revisao-sistematica-com-agentes.git
cd revisao-sistematica-com-agentes
cp .env.example .env
```

Edite o `.env` com suas chaves de API. Se você for usar modelos locais (Ollama), a aplicação dentro do Docker já está configurada automaticamente para acessar a sua máquina Host através de `host.docker.internal`.

### 3. Subindo a Aplicação

Inicie o container de forma otimizada com o Docker Compose:

```bash
docker-compose up -d --build
```

Acesse o sistema pelo seu navegador no endereço: **http://localhost:8000**

### 4. Requisitos da Planilha (Upload)
Para que a aplicação consiga extrair os dados adequadamente, a sua planilha (`.xlsx`, `.xls` ou `.csv`) deve conter uma linha de cabeçalho com, obrigatoriamente, as seguintes colunas (a ordem não importa):
- **Título**: O cabeçalho deve conter a palavra `title`, `título` ou `titulo`.
- **Resumo**: O cabeçalho deve conter a palavra `abstract` ou `resumo`.

*Opcional*: Se houver uma coluna de identificação (cabeçalho com `id`, `identificador`, ou `key`), o sistema usará esse ID. Caso contrário, o número da linha será usado como ID.

## 🖥️ Como Usar a Plataforma

1. Na tela inicial, faça o upload da sua planilha (`.xlsx` ou `.xls`).
2. Adicione os Critérios de Inclusão e Exclusão.
3. Escolha a LLM (Gemini ou Ollama) e o nível de Concorrência (quantidade de requisições simultâneas).
4. Clique em **Start Screening**. O painel alternará dinamicamente para o *Dashboard* de processamento.
5. Acompanhe a tabela sendo preenchida em tempo real com as decisões (ACCEPTED / REJECTED) do agente.
6. Ao finalizar (ou caso deseje interromper com segurança via E-STOP), baixe a nova planilha processada clicando em *Download Results*.

## 📊 Saída de Dados

A planilha Excel gerada para download contém:
- **Decisão Final** (`ACCEPTED` ou `REJECTED`, ou `CANCELLED`).
- **Motivos** (IDs e Resumos dos critérios que causaram exclusão).
- **Justificativa** textual detalhada do LLM baseada estritamente no resumo/título em contraste com seus critérios.

## 📄 Licença

Este projeto está sob a licença MIT. Veja o arquivo [LICENSE](LICENSE) para detalhes.
