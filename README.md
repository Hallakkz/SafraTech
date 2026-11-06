# SafraTech IA — aplicativo integrado aos bancos agronômicos e de pecuária de corte

Aplicativo Streamlit do SafraTech, **exclusivamente em português brasileiro**, organizado em duas áreas e com o módulo
de ensino EduAgro AI.

**🌱 Agricultura** (navegação principal — cinco módulos):

1. **🧪 Diagnóstico do Solo** — consulta o `solo_database`.
2. **🍃 Diagnóstico Nutricional** — consulta o `nutricao_database` (soja, milho, algodão e gergelim).
3. **🗓️ Simulação de Plantio** — consulta o `plantio_database` (ZARC oficial e referências técnicas).
4. **🐂 Pecuária** — abre a área de pecuária de corte.
5. **🎓 EduAgro AI** — plataforma de ensino: Tutor Agro com a DeepSeek apoiado nos 6 bancos, cursos e trilhas,
   biblioteca técnica (RAG por trechos), exercícios e avaliações, e Meu Aprendizado. Documentação completa em
   [`docs/EDUAGRO_AI.md`](docs/EDUAGRO_AI.md).

**🐂 Pecuária de Corte** (a navegação passa a mostrar):

1. **💵 Análise de Viabilidade de Compra** — `pecuaria_compra_database`: vale a pena comprar este lote?
2. **📈 Diagnóstico de Desempenho do Rebanho** — `pecuaria_desempenho_database`: o desempenho é adequado para raça, idade, sexo e sistema?
3. **📊 Simulador de Rentabilidade** — `pecuaria_rentabilidade_database`: vender agora ou esperar?
4. **🌱 Agricultura** — volta para a área agrícola (na última página aberta).

A identidade visual foi mantida: fundo verde-escuro, fontes Syne e Inter, cartões arredondados, métricas, botões com
gradiente verde e a mesma barra lateral. O módulo Recomendação, o seletor de idioma e a pecuária antiga (baseada em
`safratech ia pecuaria.csv`) foram removidos.

---

## 1. Estrutura

```
SAFRATECH/
├── main.py                     configuração, estilo, navegação Agricultura/Pecuária e status dos 6 bancos
├── requirements.txt            dependências do app
├── requirements-dev.txt        + pytest e pdfplumber (testes)
├── .env.example                modelo das 6 variáveis de conexão (sem senhas reais)
├── .streamlit/secrets.toml.example
├── sql/
│   ├── criar_usuario_leitura.sql       usuário somente leitura para os 6 bancos (instalação nova)
│   └── conceder_leitura_pecuaria.sql   concede leitura nos 3 bancos de pecuária a um usuário já existente
├── database/
│   ├── connections.py          6 conexões independentes, somente leitura, pool, timeout
│   ├── solo_queries.py / nutricao_queries.py / plantio_queries.py
│   ├── pecuaria_queries.py     consultas parametrizadas aos 3 bancos de pecuária (tabelas e views existentes)
│   └── eduagro_queries.py      leitura dos registros técnicos dos 6 bancos para o tutor do EduAgro AI
├── core/                       regras agronômicas determinísticas (sem Streamlit)
├── modules/
│   ├── eduagro_ai/             EduAgro AI (tutor, cursos, biblioteca, avaliações, progresso, cliente DeepSeek, RAG)
│   ├── _comum.py               componentes de interface compartilhados
│   ├── diagnostico_solo.py
│   ├── diagnostico_nutricional.py
│   ├── simulacao_plantio.py
│   └── pecuaria/
│       ├── calculos.py         fórmulas puras (iguais às views dos bancos) — testáveis sem Streamlit
│       ├── componentes.py      cards, seleção de referências, fontes, preços históricos, gráficos
│       ├── compra.py           módulo 1
│       ├── desempenho.py       módulo 2
│       ├── rentabilidade.py    módulo 3
│       └── relatorios.py       relatórios PDF dos 3 módulos
├── utils/
│   ├── textos.py               textos da interface (português)
│   ├── formatacao.py · validacoes.py · referencias.py · historico.py
│   └── relatorio_pdf.py        relatórios PDF (reportlab), agora com caixa de conclusão e gráfico de barras
├── tests/                      testes automatizados (pytest) + validar_deepseek.py (validação real da API)
├── docs/EDUAGRO_AI.md          instalação e uso do EduAgro AI
├── dados_eduagro/              (criada pelo app) conversas, progresso e biblioteca do EduAgro — fora do Git
└── Banco de dados SAFRATECH/   pacote dos bancos agronômicos (sem alterações)
```

Os bancos de pecuária ficam no pacote `BANCO_DE_DADOS_SAFRATECH_PECUARIA` (SQL, CSV, JSON, documentação e fontes).

---

## 2. Instalação

### 2.1 Python

Python 3.10 ou superior.

```bash
python -m venv .venv
.venv\Scripts\activate             # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

Bibliotecas: `streamlit`, `plotly`, `pandas`, `sqlalchemy` 2.x, `psycopg[binary]` 3.x, `reportlab` e `python-dotenv`.
A integração da pecuária não exigiu bibliotecas novas (os gráficos dos PDFs usam o próprio reportlab).

### 2.2 Bancos agronômicos

Dentro da pasta `Banco de dados SAFRATECH/`:

```bash
createdb -U postgres solo_database     && pg_restore -U postgres -d solo_database     solo_database/dados/solo_database.dump
createdb -U postgres nutricao_database && pg_restore -U postgres -d nutricao_database nutricao_database/dados/nutricao_database.dump
createdb -U postgres plantio_database  && pg_restore -U postgres -d plantio_database  plantio_database/dados/plantio_database.dump
```

### 2.3 Bancos de pecuária (se ainda não estiverem instalados)

Cada banco é instalado **de dentro da própria pasta** (o `03_carregar_dados.sql` usa caminhos relativos):

```bash
cd BANCO_DE_DADOS_SAFRATECH_PECUARIA/pecuaria_compra_database
createdb -U postgres pecuaria_compra_database
psql -U postgres -d pecuaria_compra_database -v ON_ERROR_STOP=1 -f estrutura/instalar.sql

cd ../pecuaria_desempenho_database
createdb -U postgres pecuaria_desempenho_database
psql -U postgres -d pecuaria_desempenho_database -v ON_ERROR_STOP=1 -f estrutura/instalar.sql

cd ../pecuaria_rentabilidade_database
createdb -U postgres pecuaria_rentabilidade_database
psql -U postgres -d pecuaria_rentabilidade_database -v ON_ERROR_STOP=1 -f estrutura/instalar.sql
```

Verificação: `psql -U postgres -d pecuaria_compra_database -c "SELECT chave, valor FROM metadados_banco;"`

O aplicativo **nunca** cria, apaga, reconstrói ou altera os bancos.

### 2.4 Usuário somente leitura (recomendado)

Instalação nova (6 bancos):

```bash
psql -U postgres -v senha="'uma_senha_forte'" -f sql/criar_usuario_leitura.sql
```

Se o usuário `safratech_leitura` já existe (criado antes da pecuária), conceda apenas a leitura nos novos bancos:

```bash
psql -U postgres -f sql/conceder_leitura_pecuaria.sql
```

Mesmo sem esse usuário, toda sessão aberta pelo app usa `default_transaction_read_only=on`.

---

## 3. Configurar as conexões

As senhas **não** ficam no código. Cada banco tem sua própria variável (o EduAgro AI usa ainda `DEEPSEEK_API_KEY`,
`DEEPSEEK_BASE_URL` e `DEEPSEEK_MODEL` — veja `docs/EDUAGRO_AI.md`):

| Variável | Banco |
|---|---|
| `SOLO_DATABASE_URL` | solo_database |
| `NUTRICAO_DATABASE_URL` | nutricao_database |
| `PLANTIO_DATABASE_URL` | plantio_database |
| `PECUARIA_COMPRA_DATABASE_URL` | pecuaria_compra_database |
| `PECUARIA_DESEMPENHO_DATABASE_URL` | pecuaria_desempenho_database |
| `PECUARIA_RENTABILIDADE_DATABASE_URL` | pecuaria_rentabilidade_database |

Formas de defini-las (escolha uma): arquivo `.env` (copie de `.env.example`), `.streamlit/secrets.toml` (copie de
`secrets.toml.example`) ou variáveis de ambiente do sistema. Formato: `postgresql://usuario:senha@host:5432/nome_do_banco`.

A barra lateral mostra, em **🗄️ Bancos de dados**, o estado de cada um dos 6 bancos, separados em Agricultura e
Pecuária. Se um banco faltar ou cair, apenas o módulo dele exibe o aviso (com o nome da variável a configurar); os
demais continuam funcionando.

---

## 4. Executar

```bash
streamlit run main.py
```

---

## 5. Pecuária de corte — como os resultados são obtidos

### Regras gerais

- **1 arroba = 15 kg de carcaça.** Peso vivo só vira arroba com um rendimento de carcaça: `arrobas = peso vivo × rendimento ÷ 15`
  (fórmula `ARROBAS_CARCACA_DE_PESO_VIVO`, F05 p.21). Nunca há rendimento fixo: o valor é informado pelo produtor ou
  escolhido entre as referências do banco da **mesma raça/genótipo e sexo compatível** (ou referências gerais, marcadas
  como tal). Referências de outra raça não são oferecidas.
- **Preços históricos não são preços atuais.** As cotações de `preco_arroba` e `preco_insumo` aparecem com data,
  natureza (`historico_publicacao`) e uso permitido, apenas como consulta. O valor da arroba é sempre informado pelo usuário.
- **Nenhum valor econômico vem pré-preenchido.** Pesos, quantidades e preços começam vazios.
- **Rastreabilidade:** cada resultado tem a seção *📚 Fontes e referências técnicas* com o registro usado, tipo de dado,
  fonte, instituição, ano, página, condições de aplicação, fórmulas da tabela `formula_calculo` e divergências
  (`divergencia`) — o mesmo conteúdo vai para o PDF.
- **As fórmulas são as das views.** `vw_lote_compra_viabilidade`, `vw_gmd_lote`, `vw_gmd_lote_x_referencia` e
  `vw_projecao_cenario` trabalham sobre tabelas de entrada (`lote_compra`, `lote_rebanho`, `cenario_venda`...). Como o app
  é somente leitura e não grava dados do produtor, `modules/pecuaria/calculos.py` aplica as mesmas expressões; o teste
  `tests/test_pecuaria_views.py` insere casos numa transação, lê as views, compara com o Python e faz ROLLBACK.

### Módulo 1 — Viabilidade de compra

Entradas: raça, sexo, quantidade, peso médio na compra, preço **por cabeça ou total do lote** (só um é contabilizado),
peso previsto na venda, dias de permanência, valor da arroba de venda, rendimento de carcaça, custos adicionais
(transporte por lote, alimentação por cabeça/dia, manejo e sanidade por cabeça, outros por lote) e margem mínima desejada.

Saídas: investimento inicial, peso total, peso de carcaça, arrobas, receita bruta, custos adicionais, receita líquida
(receita − custos adicionais), lucro/prejuízo, margem, retorno sobre o custo, preço, rendimento e peso de venda de
equilíbrio, sensibilidade e fatores que mais influenciaram o resultado.

Conclusão (determinada pelos cálculos): **inviável** se o lucro projetado ≤ 0; **exige atenção** se há lucro mas a
margem fica abaixo da margem mínima informada; **viável** se a margem atinge a mínima.

### Módulo 2 — Desempenho do rebanho

Entradas: identificação, raça, sexo (macho inteiro, macho castrado, fêmea), idade, peso atual, sistema, fase produtiva e,
opcionalmente, peso e data da pesagem anterior (para o GMD).

Comparação somente com referências compatíveis:
- **mesma raça/genótipo** (Nelore PO, Nelore comercial, nelorado e cruzados nunca se misturam);
- **sexo compatível** (referências "macho" sem condição sexual definida são aceitas e sinalizadas);
- **mesmo sistema de criação**;
- **peso:** a fonte precisa citar a idade (ex.: "Peso aos 18 meses", "corrigido para 205 dias"), com tolerância ajustável;
- **GMD:** mesma fase produtiva; quando a fonte define o período de idade ("do nascimento aos 18 meses") ou o mês, o
  período entre as pesagens precisa estar dentro dele.

Sem referência compatível, o resultado é **dados insuficientes** — nenhum peso esperado é estimado. As referências não
usadas aparecem com o motivo. A faixa "próximo da referência" (± %) e a tolerância de idade são critérios do SafraTech,
ajustáveis na tela e impressos no relatório.

### Módulo 3 — Rentabilidade

Entradas: raça, sexo, quantidade, peso atual, período (dias), valor atual da arroba, custos já acumulados (opcional),
rendimento de carcaça, GMD esperado (próprio ou referência) e custos diários (alimentação, suplementação, manejo, outros).

Três cenários (conservador, intermediário, otimista) com arroba futura, GMD, rendimento futuro e custo diário próprios.
Campos em branco usam a premissa base (por exemplo, arroba futura = arroba atual), e isso fica registrado como premissa —
o app não faz previsões de mercado.

Saídas: peso atual e projetado, ganho de peso, arrobas, receita bruta, custos da espera e acumulados, receita líquida,
lucro e margem operacional (quando os custos acumulados são informados), diferença esperar − vender agora, custo por
arroba produzida, arroba futura de equilíbrio e indicação por cenário, com gráficos.

### Relatórios PDF

Cada submódulo gera um PDF com conclusão em destaque, dados de entrada, cálculos, premissas, gráficos (rentabilidade e
compra), pontos de atenção (desempenho) e fontes técnicas.

---

## 6. Testes

Os testes de integração usam os bancos reais através do cliente `psql` (no `PATH`, servidor em `localhost`, usuário
`postgres`; ajuste com `PGHOST` e `PGUSER`). Se o PostgreSQL não estiver acessível, eles são pulados.

```bash
pip install -r requirements-dev.txt
pytest -q tests
python tests/validar_deepseek.py     # EduAgro AI: validação real da DeepSeek com a chave do .env
```

O que é testado:

- **Navegação:** menu agrícola (Solo, Nutricional, Plantio, Pecuária), troca para o menu de pecuária (Compra, Desempenho,
  Rentabilidade, Agricultura) e retorno à última página.
- **Remoções:** ausência da Recomendação, do seletor de idioma, de textos em inglês (telas, resultados e PDFs) e da pecuária antiga.
- **Conexões:** 6 bancos independentes, variáveis de ambiente, ausência de senhas no código, somente leitura, sem `SELECT *`.
- **Indisponibilidade:** cada banco de pecuária fora do ar isoladamente; banco agrícola fora do ar; app sem nenhum banco.
- **Cálculos da pecuária:** peso vivo × carcaça, rendimento, arrobas, custos, margens, equilíbrio, GMD, idade das
  referências, compatibilidade (inclusive Nelore puro × cruzados) e cenários.
- **Equivalência com as views** dos bancos (transação com ROLLBACK).
- **Dados técnicos e fontes:** referências rastreáveis, preços marcados como históricos, fontes com instituição/ano/página.
- **Fluxos completos e PDFs** dos 3 submódulos de pecuária e dos 3 módulos agrícolas, com conferência do texto.
- **Integridade:** contagem e hash do conteúdo dos 6 bancos antes e depois da sessão de testes.

A interface é testada com um substituto do Streamlit (`tests/stub_streamlit.py`) que executa o `main.py` de verdade,
inclusive cliques, callbacks de navegação e downloads.

---

## 7. Agricultura — como os resultados são obtidos

- **Nenhum limite é criado pelo app.** Valores de corte, operadores e unidades vêm dos registros dos bancos.
- **Status possíveis:** Adequado · Atenção · Abaixo da referência · Acima da referência · Dados insuficientes ·
  Referências divergentes · Classe da fonte.
- **Solo:** só referências do mesmo método do laudo; faixas condicionadas a argila, P-rem, CTC, textura, camada ou sistema
  exigem esses dados; referências do Cerrado dependem da resposta sobre o bioma; não há recomendação de calagem ou adubação.
- **Nutrição:** só faixas da cultura e estádio compatíveis; sem faixa aparece *"Não há dados de referência disponíveis no
  banco para esta combinação."*; sintomas são indícios, não diagnóstico.
- **ZARC:** 20, 30 e 40 são níveis de risco; **0 é "sem indicação"**, não risco zero; decêndios pelo número (1–36);
  portaria e data vêm do banco; não é previsão do tempo.

## 8. Limitações conhecidas

- Agricultura: sem faixa de **N no solo**; **gergelim** sem faixas foliares nem ZARC; **bioma** e **datas dos decêndios**
  não constam nos bancos.
- Pecuária: os bancos não têm **cotação atual** da arroba nem de insumos (só históricos de publicações); as referências de
  peso por idade cobrem principalmente Nelore comercial (MS, semi-intensivo) e F1 Pardo Suíço × Nelore (experimento F09) —
  outras combinações tendem a resultar em "dados insuficientes", por desenho.
- As tabelas de entrada dos bancos de pecuária (`lote_compra`, `lote_rebanho`, `cenario_venda`...) não são preenchidas pelo
  app, que é somente leitura; as análises ficam no histórico da sessão (e, opcionalmente, em `historico/analises.jsonl`).
