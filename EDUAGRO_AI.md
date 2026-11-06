# EduAgro AI — Plataforma Inteligente de Ensino do Agronegócio

Módulo de ensino integrado ao SafraTech (5º item do menu principal: **🎓 EduAgro AI**). Usa a mesma arquitetura, a
mesma identidade visual, os mesmos bancos técnicos e a mesma infraestrutura do aplicativo — não é um aplicativo separado.

## 1. Instalação

1. Atualize as dependências (entraram `requests` e `pypdf`):

   ```bash
   .venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Configure a DeepSeek no arquivo `.env` (o mesmo dos bancos; modelo em `.env.example`):

   ```
   DEEPSEEK_API_KEY=sua_chave
   DEEPSEEK_BASE_URL=https://api.deepseek.com
   DEEPSEEK_MODEL=deepseek-chat
   ```

   Opcionais: `DEEPSEEK_TIMEOUT_S` (90), `DEEPSEEK_MAX_REQ_MIN` (20 perguntas por minuto no processo),
   `DEEPSEEK_MAX_TOKENS` (4000 por resposta) e `EDUAGRO_DADOS_DIR` (pasta dos dados do EduAgro).
   As mesmas variáveis também podem ficar em `.streamlit/secrets.toml`.

3. Execute o aplicativo como antes: `streamlit run main.py`.

4. Valide a integração real com a DeepSeek (usa a chave do `.env` e os bancos reais; consome poucos créditos):

   ```bash
   python tests/validar_deepseek.py
   ```

   O relatório fica em `dados_eduagro/validacao_deepseek.md`.

### Busca na internet e fonte das respostas

Com `TAVILY_API_KEY=tvly-...` no `.env` (conta gratuita em tavily.com: 1.000 buscas por mês), o Tutor tem um seletor
**Fonte das respostas**:

- **🔗 Somente internet** (padrão): cada pergunta é pesquisada direto na internet e a resposta usa só essas páginas,
  com o link de cada uma [W#]. Os bancos do SafraTech não são consultados. Cada pergunta usa 1 crédito do Tavily.
- **📚 Bancos do SafraTech (internet só se não achar)**: procura primeiro nos 6 bancos e na Biblioteca; só pesquisa na
  internet se nada for encontrado neles. Nesse modo aparece o botão **🔗 Procurar também na internet**.

A fonte inicial pode ser definida no `.env` com `EDUAGRO_FONTE_TUTOR=internet` ou `bancos`. Para desligar totalmente a
internet: `EDUAGRO_BUSCA_INTERNET=0`. A barra lateral mostra o estado da busca, o número de buscas do mês e o botão
**Testar busca** (usa 1 crédito). As páginas da internet são sempre mostradas como fontes externas, não verificadas pelo
SafraTech.

## 2. Segurança da chave

- A chave é lida **somente** de variáveis de ambiente / `.env` / `st.secrets` (`deepseek_client.carregar_config`).
- As chamadas são feitas pelo **backend Python** (`requests`); a chave vai apenas no cabeçalho `Authorization` da
  requisição para a API e nunca é enviada ao navegador, exibida na tela ou gravada em log (as mensagens de erro passam
  por um filtro que substitui a chave por `***`).
- `.env` e `dados_eduagro/` estão no `.gitignore`. Um teste automatizado procura chaves no código.

## 3. Arquitetura

```
modules/eduagro_ai/
├── __init__.py
├── interface.py            página do módulo, perfil de estudante, nível, status da IA e navegação das 5 áreas
├── deepseek_client.py      camada própria da API (configuração, erros, novas tentativas, limite, streaming, saldo)
├── web_search.py           busca na internet (Tavily), usada só quando os bancos não têm a informação
├── knowledge_retrieval.py  base de conhecimento dos 6 bancos + trechos da Biblioteca; busca BM25; contexto [S#]/[D#]
├── prompts.py              instruções do tutor, de exercícios, de correção e de rascunho de aula
├── tutor.py                lógica do tutor e persistência das conversas
├── cursos.py               catálogo de cursos, aulas, rascunhos com IA, conclusão
├── biblioteca.py           cadastro de materiais, extração de texto por página, trechos, materiais do SafraTech
├── avaliacoes.py           geração/validação de questões, correção e registro das avaliações
├── exercicios_calculo.py   exercícios numéricos com fórmulas dos bancos (resposta calculada pelo app)
├── progresso.py            indicadores de Meu Aprendizado
├── armazenamento.py        SQLite local (dados_eduagro/eduagro.db)
├── estilo.py               CSS (verde-escuro, Syne/Inter, cartões; destaque do item no menu)
└── paginas/                tutor_ui, cursos_ui, biblioteca_ui, avaliacoes_ui, progresso_ui, componentes
database/eduagro_queries.py consultas somente leitura usadas para montar a base de conhecimento
```

**Por que SQLite?** Os seis bancos do SafraTech são abertos sempre em modo somente leitura e nunca são alterados pelo
aplicativo. Conversas, progresso, aulas cadastradas e a biblioteca são dados do usuário e ficam em
`dados_eduagro/eduagro.db` (biblioteca padrão do Python, sem servidor). Os testes conferem, por hash, que o conteúdo dos
seis bancos não muda.

**Login.** O SafraTech não possui autenticação. O EduAgro não cria um sistema de login: há um *perfil de estudante*
(apenas um nome, na barra lateral) que separa o progresso de quem usa o mesmo computador.

## 4. As cinco áreas

### 🤖 Tutor Agro Inteligente
- Chat com histórico de conversas (salvas), nova conversa, exclusão, sugestões de perguntas, indicador de processamento
  e resposta em tempo real (streaming). Fórmulas em LaTeX são renderizadas.
- **Nível** (Iniciante / Intermediário / Avançado, na barra lateral) muda a profundidade das explicações.
- Botões **Explicar de forma mais simples**, **Explicação mais aprofundada** e **Gerar exercícios sobre este assunto**.
- A cada pergunta, o tutor busca nos bancos do SafraTech (e, se marcado, na Biblioteca) e envia à IA os trechos
  numerados. A resposta é organizada em seções que separam:
  - **📚 O que os bancos do SafraTech informam** — só dados do contexto, com citação [S#]/[D#];
  - **🧠 Explicação do tutor (IA)**;
  - **🧮 Exemplo hipotético (somente para ensinar)** — números fictícios, cálculo passo a passo;
  - **⚠️ Erros comuns**, **✅ Verifique seu aprendizado** (perguntas) e **➡️ Para continuar**.
- Abaixo de cada resposta, **📚 Referências consultadas** lista os registros reais entregues à IA (banco, registro,
  publicação, instituição, ano, página). O app confere as citações: se a IA citar um rótulo inexistente, aparece um alerta.
- Sem referência nos bancos, a IA é instruída a dizer isso e a não inventar valores, recomendações ou referências.

### 📘 Cursos e Trilhas
- Catálogo com as 22 trilhas pedidas (Agricultura 8, Pecuária 9, Gestão Rural 5) — nome, descrição (escopo), categoria,
  nível e objetivos. **Nenhuma aula vem pronta**: o catálogo é a estrutura.
- Em cada curso: aulas (conteúdo, resumo, exemplos, referências), progresso, **Referências do SafraTech** relacionadas
  (registros reais dos bancos), avaliação final e **Gerenciar conteúdo**:
  - cadastrar aulas com conteúdo próprio ou material técnico cadastrado;
  - **rascunho de aula com IA** baseado só nas referências recuperadas — salvo como "Rascunho gerado por IA" e
    "não revisado" até alguém marcá-lo como revisado;
  - gerar as questões da avaliação final (com referência obrigatória).
- Conclusão do curso: todas as aulas concluídas e, se houver avaliação final, nota ≥ 70%.

### 📚 Biblioteca de Conhecimento Agro
- Upload de PDF, TXT e MD com tipo (PDF, apostila, manual técnico, publicação científica, material da Embrapa, guia de
  estudo, documento próprio), categoria (Agricultura, Pecuária, Solo, Nutrição vegetal, Clima, Gestão rural, Economia
  agropecuária), autores, instituição, ano e referência.
- O texto é extraído **por página** e dividido em trechos com sobreposição; o tutor cita documento e página (RAG).
- **📦 Materiais do SafraTech**: importa as publicações da Embrapa que deram origem aos bancos de pecuária (já estão na
  pasta do projeto).
- Limitação: PDFs digitalizados como imagem (sem camada de texto) ficam com status "sem texto extraível" — OCR não faz
  parte desta versão. A tabela `trecho` já tem a coluna `embedding`, para uma futura busca vetorial.

### 📝 Exercícios e Avaliações
- **🧮 Treino de cálculos (bancos)**: GMD, rendimento de carcaça, arrobas de carcaça, peso projetado, unidade animal,
  taxas de prenhez e mortalidade, margem bruta, soma de bases, CTC, V% e dose de gesso — com a fórmula registrada no
  banco, fonte e página. A resposta correta é **calculada pelo aplicativo**; os números são hipotéticos.
- **🤖 Exercícios gerados por IA**: múltipla escolha, verdadeiro/falso, práticas e estudos de caso, só a partir das
  referências recuperadas (e das aulas revisadas do curso escolhido). Questões sem referência válida são descartadas.
  Todas são identificadas como "geradas por IA para estudo (não é questão oficial de nenhuma instituição)".
- Após responder: resultado, resposta correta, explicação, justificativa técnica, referências e **assuntos para estudar
  novamente** (com atalho para revisar com o tutor). Respostas abertas são corrigidas pela IA; se ela estiver
  indisponível, nada é registrado e o app mostra a resposta esperada.

### 📈 Meu Aprendizado
Cursos iniciados/concluídos, aulas concluídas, exercícios, acerto médio, notas das avaliações, perguntas ao tutor,
progresso por categoria, evolução das notas, desempenho por tema, assuntos a revisar, meus cursos e histórico.

## 5. Erros e indisponibilidade da IA

| Situação | Mensagem ao usuário |
|---|---|
| Chave ausente | IA não configurada (definir `DEEPSEEK_API_KEY` no `.env`) |
| HTTP 401 | Chave recusada (inválida ou revogada) |
| HTTP 402 | Conta DeepSeek **sem saldo** |
| HTTP 429 / limite local | Muitas requisições — aguarde (o app tenta de novo respeitando `Retry-After`) |
| HTTP 500/503, rede, tempo esgotado | Serviço indisponível / sem conexão / demorou demais (até 2 novas tentativas) |
| Resposta vazia ou JSON inválido | Formato inesperado — tentar novamente |

Nunca há resposta simulada: em qualquer falha a pergunta não é registrada e os demais recursos continuam funcionando.
A barra lateral tem **Testar conexão** (consulta o saldo e faz uma chamada mínima ao modelo).

## 6. Testes

```bash
pip install -r requirements-dev.txt
pytest -q tests                      # automatizados (inclui os módulos existentes)
python tests/validar_deepseek.py     # validação REAL da API (chave do .env)
```

No Windows, o atalho **`validar_eduagro.bat`** (duplo clique na pasta do projeto) confere as dependências, roda a validação
real da DeepSeek e toda a bateria do pytest, e grava os resultados em `dados_eduagro/` (`validacao_deepseek.md`,
`resultado_pytest.txt`, `resumo_validacao.txt`). Ele usa o usuário/senha de `SOLO_DATABASE_URL` para o cliente `psql`
dos testes de integração (o executor de testes envia o SQL ao `psql` pela entrada padrão, em UTF-8, para que acentos e
símbolos funcionem também no Windows).

Arquivos novos: `test_eduagro_deepseek.py` (camada da API: configuração, chave, erros 401/402/429/5xx, rede, limite,
streaming, JSON), `test_eduagro_conhecimento.py` (busca nos 6 bancos: fósforo, GMD, rentabilidade, carcaça, ZARC,
deficiência/toxidez, filtro de área, banco indisponível), `test_eduagro_logica.py` (cursos, aulas, conclusão, exercícios de
cálculo conferidos com `modules/pecuaria/calculos.py`, validação das questões da IA, biblioteca com PDF de várias
páginas, progresso individual) e `test_eduagro_ui.py` (menu com 5 módulos, áreas, português, tutor, erros da IA,
exercícios, cursos, biblioteca, funcionamento sem bancos e preservação dos outros módulos).
Nos testes automatizados a API é substituída por uma sessão HTTP falsa apenas para provocar cada erro sem gastar
créditos; a prova de que a integração funciona é o `validar_deepseek.py`.
