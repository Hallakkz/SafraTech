# Bancos de dados agronômicos SAFRATECH — versão 1.0.0 (01/11/2026)

Três bancos **independentes** em PostgreSQL, com a mesma padronização de campos, construídos **exclusivamente** a partir dos documentos da pasta `Banco de dados SAFRATECH` (a única fonte externa é o dicionário de dados oficial do MAPA, usado só para decodificar os códigos da tábua de risco do ZARC).

| Banco | Conteúdo | Registros |
|---|---|---|
| `solo_database` | Interpretação de análise de solo, calagem, gessagem, adubação N-P-K-S-micronutrientes, equações, amostragem, métodos laboratoriais | **551** registros + **61** métodos analíticos catalogados |
| `nutricao_database` | Faixas de suficiência foliar, exigência/exportação, sintomas, interações, amostragem foliar, métodos de diagnose (ChM, IBK, DRIS, CND) — soja, milho, algodão e gergelim | **321** registros + matriz de cobertura com **192** células (ausências explícitas) |
| `plantio_database` | ZARC 2026/2027 oficial (MAPA) + exigências climáticas, hídricas, fenologia e arranjo de plantio | **957.490** indicações ZARC (= linhas do CSV; 9.219.372 pares decêndio × risco) + **104** registros técnicos |

## Estrutura de pastas

```
Banco de dados SAFRATECH/
├── solo_database/       dados/ (registro.csv|json, metodo_analitico.csv, solo_database.dump)
│                        estrutura/ (01_estrutura.sql, 02_carga.sql, dicionario_de_dados.md, consultas_exemplo.sql)
│                        fontes/ (fonte.csv, divergencia.csv, divergencia_registro.csv, unidade.csv, mapa_paginas.csv)
├── nutricao_database/   (mesma organização; + cultura.csv, nutriente.csv, cobertura_cultura_nutriente.csv)
├── plantio_database/    (mesma organização; + zarc_indicacao.csv.gz, municipio.csv, portaria.csv, zarc_cultura.csv,
│                         dominio_codigo.csv, decendio.csv)
├── documentacao/        inventario_dos_arquivos/ · referencias_bibliograficas/ · relatorio_de_validacao/
└── ferramentas/         construir_bancos.py · testes/ (pytest) · curadoria/ (registros curados e geradores, para auditoria)
```

## Como instalar

**Opção A — restaurar os dumps (mais rápido):**
```
createdb -U postgres solo_database     && pg_restore -U postgres -d solo_database     solo_database/dados/solo_database.dump
createdb -U postgres nutricao_database && pg_restore -U postgres -d nutricao_database nutricao_database/dados/nutricao_database.dump
createdb -U postgres plantio_database  && pg_restore -U postgres -d plantio_database  plantio_database/dados/plantio_database.dump
```
**Opção B — reconstruir a partir dos CSV** (PostgreSQL ≥ 13 e `psql` no PATH; Python 3):
```
python ferramentas/construir_bancos.py --host localhost --user postgres --recriar
```
**Testes automatizados** (pytest): `cd ferramentas/testes` e `pytest -q`. Para conferir os números com os documentos originais, defina `SAFRATECH_FONTES` com a pasta que contém os PDFs/ePubs/CSV originais (requer `pdftotext`).

Os CSV/JSON em `dados/` podem ser usados sem PostgreSQL.

## Padronização comum (tabela `<banco>.registro`)

`registro_id` · `categoria` · `parametro` / `nutriente` + `nutriente_codigo` · `cultura` · `regiao` · `tipo_solo` · `camada` · `estagio` · `parte_planta` · `metodo` · `valor` · `valor_min` + `operador_min` · `valor_max` + `operador_max` · `unidade` (como na fonte) + `unidade_base` (vocabulário controlado, validado por chave estrangeira) · `classificacao` · `texto` · `texto_original` · `condicoes` · `causas` · `observacoes` · `divergencia_ids` · `fonte_id` · `secao` · `pagina_pdf` · `pagina_impressa` · `tipo_dado` (oficial / referência técnica / histórico / ilustrativo) · `status_validacao` · `hash_conteudo` (único — impede duplicidade) · `versao_registro`.

Esquema `meta` (repetido em cada banco): `fonte` (autores, instituição, ano, ISBN/ISSN, SHA-256 do arquivo, referência ABNT), `unidade`, `divergencia`, `versao`, `historico_alteracao` (auditoria automática de UPDATE/DELETE por gatilho).

## Regras respeitadas
- Nenhum valor inventado; células vazias ("-") e informações inexistentes viram **ausência registrada** (`ausencia_dado`, `nutricao.v_ausencias`).
- Culturas nunca misturadas: cada faixa foliar é de uma cultura, uma fonte e uma condição de amostragem; restrições SQL impedem faixa sem cultura/nutriente/parte da planta.
- Métodos nunca misturados: P Mehlich-1 × resina × P-rem, pH água × CaCl2, K em mg/dm³ × mg/kg ficam em registros separados.
- Divergências: todas as versões mantidas e vinculadas em `meta.divergencia` (21 divergências).
- Decêndios do ZARC mantidos como números 1–36 (não convertidos em datas); riscos 20/30/40 exatamente como no CSV.

## Atualização futura
Novos registros: inserir em `<banco>.registro` com novo `registro_id`, `fonte_id` cadastrado em `meta.fonte` e `unidade_base` existente em `meta.unidade` (as restrições rejeitam dados inválidos e duplicados). Alterações ficam em `meta.historico_alteracao`. Registrar cada liberação em `meta.versao`. Nova safra do ZARC: carregar o novo CSV em `plantio.zarc_indicacao` (a chave inclui `safra_ini`).

Detalhes: `documentacao/relatorio_de_validacao/relatorio_validacao.md`.
