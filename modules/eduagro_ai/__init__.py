"""EduAgro AI — plataforma inteligente de ensino do agronegócio, integrada ao SafraTech (5º módulo do menu principal).

Lógica (sem Streamlit, testável):
    deepseek_client.py      camada própria de comunicação com a API da DeepSeek (erros, saldo, limites, streaming)
    knowledge_retrieval.py  recuperação de conhecimento nos 6 bancos do SafraTech e nos documentos da Biblioteca (RAG)
    prompts.py              instruções enviadas à IA
    tutor.py                Tutor Agro: montagem das mensagens, citações e conversas
    cursos.py               catálogo, aulas, rascunhos de aula e conclusão de cursos
    biblioteca.py           cadastro de materiais, extração por página e trechos
    avaliacoes.py           geração, validação e correção de exercícios e avaliações
    exercicios_calculo.py   exercícios numéricos com as fórmulas dos bancos (resposta calculada pelo app)
    progresso.py            indicadores de Meu Aprendizado
    armazenamento.py        persistência local (SQLite) — os bancos do SafraTech continuam somente leitura
Interface (Streamlit):
    interface.py            página do módulo e navegação entre as 5 áreas
    paginas/                telas de cada área
    estilo.py               CSS do módulo (identidade visual do SafraTech)
"""
