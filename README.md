# Agente de Screening para Revisão Sistemática

Este projeto implementa um agente inteligente baseado em **LangGraph** (v1.0.8) e **LangChain** (v1.2.7) projetado para automatizar a triagem (screening) de artigos em revisões sistemáticas de literatura. O sistema utiliza modelos de linguagem (LLMs) para avaliar títulos e resumos contra critérios de inclusão e exclusão definidos pelo pesquisador.

## 🚀 Funcionalidades

- **Triagem Automatizada**: Avaliação rigorosa de artigos baseada em critérios customizáveis.
- **Execução Paralela Assíncrona**: Processamento concorrente via `asyncio` com controle de concorrência por `Semaphore`.
- **Arquitetura de Grafo de Estado**: Implementado com LangGraph para separação clara entre lógica de decisão e parsing de resultados.
- **Suporte Multi-Provedor**: Compatível com Google Gemini, Ollama (local) e vLLM.
- **Checkpointer em Memória**: Mantém o histórico de execução por artigo utilizando `thread_id` por corrotina.
- **Processamento em Lote**: Carrega artigos de planilhas `.xlsx`/`.xls` e exporta resultados detalhados com justificativas.

## 🛠️ Stack Tecnológica

- **Core**: Python 3.10+
- **Orquestração**: [LangGraph v1.0.8](https://github.com/langchain-ai/langgraph)
- **Modelos**: LangChain Core & Google/Ollama integrations
- **Dados**: Pandas, OpenPyXL, XLRD
- **Ambiente**: Python-dotenv

## 📋 Arquitetura do Sistema

O fluxo de screening é estruturado como um grafo de estado compilado (`CompiledStateGraph`), executado de forma assíncrona:

1. **Agent Node** (`async`): Recebe a mensagem humana (Título + Resumo + Critérios), instancia o LLM via `get_llm(provider)` e faz `await agent.ainvoke()` com o prompt de sistema.
2. **Parser Node**: Extrai via Regex a decisão (`ACCEPTED`/`REJECTED`), discriminantes e justificativa do texto cru do modelo.
3. **State Management**: `ScreeningState` (mensagens) → `OutputState` (decisão estruturada) como schema de saída do grafo.
4. **Concorrência**: `main.py` dispara todas as corrotinas com `asyncio.gather`, limitadas por `asyncio.Semaphore(--concurrency)`.

## ⚙️ Configuração

1. Clone o repositório:
   ```bash
   git clone git@github.com:ynaponte/revisao-sistematica-com-agentes.git
   cd revisao-sistematica-com-agentes
   ```

2. Instale as dependências e o ambiente virtual:
   ```bash
   # Sincroniza o ambiente conforme o pyproject.toml
   uv sync
   
   # Ativar o ambiente para execução manual
   # Linux/macOS: source .venv/bin/activate
   # Windows: .\.venv\Scripts\activate
   ```

3. Configure as variáveis de ambiente:
   Crie um arquivo `.env` baseado no `.env.example`:
   ```env
   GEMINI_API_KEY=sua_chave_aqui
   # Se usar Ollama
   OLLAMA_BASE_URL=http://localhost:11434
   ```

## 🖥️ Como Usar

A execução é feita via CLI através do módulo `screening`:

```bash
python -m src.screening.main \
    --input "caminho/para/seus_artigos.xlsx" \
    --inclusion "Critério 1" "Critério 2" \
    --exclusion "Critério de Exclusão 1" \
    --provider gemini \
    --rows "1-50" \
    --concurrency 5
```

### Argumentos Principais:
- `--input (-i)`: Caminho da planilha de entrada.
- `--inclusion`: Lista de critérios de inclusão.
- `--exclusion`: Lista de critérios de exclusão.
- `--provider (-p)`: Provedor do modelo (`gemini`, `ollama`, `vllm`).
- `--rows (-r)`: Range de linhas para processar (ex: "1-100").
- `--concurrency (-c)`: Número de artigos processados simultaneamente (default: `1`).
- `--delay`: Delay em segundos após cada chamada dentro do semaphore (default: `4.0`).

## 📊 Saída de Dados

O agente gera uma nova planilha contendo:
- Decisão Final (`ACCEPTED` ou `REJECTED`).
- IDs dos critérios que causaram a exclusão.
- Justificativa textual baseada estritamente no resumo/título.
- Metadados da execução (Modelo utilizado, data, etc).

## 📄 Licença

Este projeto está sob a licença MIT. Veja o arquivo [LICENSE](LICENSE) para detalhes.
