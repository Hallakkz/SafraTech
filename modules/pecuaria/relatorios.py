"""Relatórios PDF dos três submódulos de Pecuária (reaproveita utils.relatorio_pdf.Relatorio, padrão do SafraTech).

Os relatórios não acessam os bancos: recebem os resultados já calculados, as premissas e as fontes exibidas na tela.
"""
from __future__ import annotations

from typing import Sequence

import pandas as pd
from reportlab.lib.units import cm

from modules.pecuaria import calculos as calc
from modules.pecuaria.componentes import ROTULO_STATUS, ano_fonte, moeda, num, texto
from utils.relatorio_pdf import Relatorio

RODAPE = "SafraTech IA — Pecuária de Corte · Resultados dependem das premissas informadas. A SafraTech IA não é humana. Pode cometer erros."
COR_VEREDITO = {"viavel": "#2e7d32", "atencao": "#f9a825", "inviavel": "#c62828", "adequado": "#2e7d32",
                "abaixo": "#c62828", "acima": "#ef6c00", "insuficiente": "#607d8b", "divergente": "#8e24aa"}


def _premissas(rel: Relatorio, premissas: Sequence[tuple[str, str, str]]):
    rel.secao("Premissas utilizadas")
    rel.tabela(["Premissa", "Valor", "Origem"], [list(p) for p in premissas], larguras=[5.5 * cm, 5 * cm, 7.5 * cm])


def _linhas_refs(refs: pd.DataFrame) -> list[list[str]]:
    linhas, anterior = [], None
    for r in refs.to_dict("records"):
        cond = r["condições de aplicação"] or "—"
        linhas.append([r["registro"], r["parâmetro"], f"{r['raça/genótipo']} / {r['sexo']} / {r['sistema']}", r["tipo de dado"],
                       f"{r['fonte']} — {r['instituição']} ({r['ano']}), p. {r['página (PDF)'] or '—'}",
                       "mesmas condições do registro anterior" if cond == anterior and cond != "—" else cond])
        anterior = cond
    return linhas


def _fontes(rel: Relatorio, fontes: dict, titulo: str = "Fontes técnicas utilizadas"):
    rel.secao(titulo)
    refs: pd.DataFrame = fontes.get("referencias", pd.DataFrame())
    docs: pd.DataFrame = fontes.get("fontes", pd.DataFrame())
    form: pd.DataFrame = fontes.get("formulas", pd.DataFrame())
    div: pd.DataFrame = fontes.get("divergencias", pd.DataFrame())
    if refs is not None and not refs.empty:
        rel.paragrafo("Referências técnicas do banco usadas na análise:")
        rel.tabela(["Registro", "Parâmetro", "Raça / sexo / sistema", "Tipo de dado", "Fonte, ano e página", "Condições de aplicação"],
                   _linhas_refs(refs),
                   larguras=[2.1 * cm, 3.4 * cm, 3 * cm, 2.3 * cm, 3.6 * cm, 3.6 * cm])
    else:
        rel.paragrafo("Nenhuma referência técnica do banco foi usada como valor de cálculo: os resultados dependem apenas das "
                      "premissas informadas pelo usuário.")
    if form is not None and not form.empty:
        rel.paragrafo("Fórmulas aplicadas (tabela formula_calculo do banco):")
        rel.tabela(["Fórmula", "Expressão", "Fonte"],
                   [[texto(f["nome"]), texto(f["expressao"]), f"{texto(f['fonte_codigo'])}, p. {texto(f['pagina_pdf']) or '—'}"]
                    for f in form.to_dict("records")], larguras=[4.5 * cm, 9 * cm, 4.5 * cm])
    if docs is not None and not docs.empty:
        rel.paragrafo("Documentos de origem:")
        rel.tabela(["Código", "Referência", "Instituição", "Ano"],
                   [[texto(d["fonte_codigo"]), texto(d["referencia_abnt"]) or texto(d["titulo"]), texto(d["instituicao"]),
                     ano_fonte(d["ano_publicacao"])] for d in docs.to_dict("records")],
                   larguras=[3.2 * cm, 9.3 * cm, 3.7 * cm, 1.8 * cm])
    if div is not None and not div.empty:
        rel.paragrafo("Divergências entre fontes registradas no banco para as referências usadas:")
        d = div.drop_duplicates("divergencia_codigo")
        rel.tabela(["Código", "Descrição", "Tratamento"],
                   [[texto(x["divergencia_codigo"]), texto(x["descricao"]), texto(x["tratamento"])] for x in d.to_dict("records")],
                   larguras=[1.8 * cm, 9.2 * cm, 7 * cm])


# =====================================================================================================
def pdf_compra(salvo: dict, premissas, fontes: dict) -> bytes:
    from modules.pecuaria.compra import VEREDITO
    res: calc.ResultadoCompra = salvo["res"]
    e = res.entrada
    rel = Relatorio("SafraTech IA — Análise de Viabilidade de Compra",
                    "Pecuária de corte · banco pecuaria_compra_database · Pergunta: vale a pena comprar este lote?", RODAPE)
    titulo, explicacao = VEREDITO[res.classificacao]
    rel.destaque(titulo, f"{explicacao} Lucro projetado de {moeda(res.lucro)} e margem de {num(res.margem_lucro_pct, 1, '%')} "
                         f"(mínima desejada: {num(e.margem_minima_pct, 1, '%')}).", COR_VEREDITO[res.classificacao])

    rel.secao("Dados do lote")
    rel.pares([("Raça / composição genética", f"{salvo['raca']['nome']} — {salvo['raca']['grupo_genetico']}"),
               ("Sexo / categoria", calc.SEXOS_USUARIO.get(salvo["sexo"], salvo["sexo"])),
               ("Quantidade de animais", str(e.quantidade_animais)),
               ("Peso médio na compra", num(e.peso_medio_compra_kg, 1, " kg PV")),
               ("Peso total na compra", num(res.peso_total_compra_kg, 0, " kg PV")),
               ("Dias de permanência", str(e.dias_permanencia) if e.dias_permanencia else "não informado")])
    rel.secao("Dados de compra")
    rel.pares([("Forma do preço", "por cabeça" if e.modo_preco == "cabeca" else "total do lote"),
               ("Preço informado", moeda(e.preco_compra) + (" por cabeça" if e.modo_preco == "cabeca" else " pelo lote")),
               ("Investimento inicial (aquisição)", moeda(res.custo_aquisicao_lote)),
               ("Custo de aquisição por cabeça", moeda(res.custo_aquisicao_cab))])
    rel.secao("Peso, rendimento de carcaça e arrobas estimadas")
    rel.pares([("Peso médio previsto na venda", num(e.peso_venda_kg, 1, " kg PV")),
               ("Peso total na venda", num(res.peso_total_venda_kg, 0, " kg PV")),
               ("Rendimento de carcaça", f"{num(e.rendimento_venda_pct, 1, '%')} — {salvo['origem_rend']}"),
               ("Peso de carcaça estimado", f"{num(res.peso_carcaca_cab_kg, 1)} kg/cab · {num(res.peso_carcaca_lote_kg, 0)} kg no lote"),
               ("Arrobas estimadas (15 kg de carcaça)", f"{num(res.arrobas_carcaca_cab, 2)} @/cab · {num(res.arrobas_carcaca_lote, 1)} @ no lote"),
               ("Ganho de peso previsto", num(res.ganho_peso_cab_kg, 1, " kg/cab")
                + (f" (GMD implícito {num(res.gmd_implicito_kg_dia, 3)} kg/dia)" if res.gmd_implicito_kg_dia is not None else ""))])
    rel.secao("Custos")
    linhas = [["Aquisição dos animais", moeda(res.custo_aquisicao_lote)]] + [[a, moeda(b)] for a, b in res.custos_detalhados]
    linhas.append(["Custo total do lote", moeda(res.custo_total_lote)])
    rel.tabela(["Item", "Valor no período"], linhas, larguras=[11 * cm, 7 * cm])
    rel.secao("Receita projetada, lucro e margem")
    rel.pares([("Valor da arroba de venda (informado)", moeda(e.preco_venda_arroba) + "/@"),
               ("Receita bruta projetada", moeda(res.receita_bruta)),
               ("Custos adicionais", moeda(res.custo_adicional_total)),
               ("Receita líquida estimada (receita − custos adicionais)", moeda(res.receita_liquida)),
               ("Lucro ou prejuízo projetado", moeda(res.lucro)),
               ("Margem de lucro (sobre a receita)", num(res.margem_lucro_pct, 1, "%")),
               ("Retorno sobre o custo total", num(res.retorno_sobre_custo_pct, 1, "%")),
               ("Preço de equilíbrio da arroba", moeda(res.preco_equilibrio_arroba) + "/@"),
               ("Margem de segurança no preço", num(res.margem_seguranca_preco_pct, 1, "%")),
               ("Rendimento de carcaça de equilíbrio", num(res.rendimento_equilibrio_pct, 1, "%")),
               ("Peso de venda de equilíbrio", num(res.peso_venda_equilibrio_kg, 0, " kg/cab"))])
    rel.grafico_barras(["Receita bruta", "Aquisição", "Custos adicionais", "Lucro/prejuízo"],
                       {"R$": [res.receita_bruta, res.custo_aquisicao_lote, res.custo_adicional_total, res.lucro]},
                       "Receita, custos e resultado do lote (R$)", "R$")
    rel.secao("Conclusão da análise")
    rel.paragrafo(f"{titulo}. {explicacao}")
    for f in calc.fatores_compra(res):
        rel.paragrafo(f"• {f}")
    rel.paragrafo("Critério: inviável quando o lucro projetado é menor ou igual a zero; exige atenção quando há lucro, mas a "
                  "margem fica abaixo da margem mínima desejada; viável quando a margem atinge a mínima desejada.", aviso=True)
    _premissas(rel, premissas)
    rel.paragrafo("1 arroba comercial = 15 kg de carcaça. Arrobas = peso vivo × rendimento de carcaça ÷ 15. O valor da arroba "
                  "é o informado pelo usuário: preços registrados nas publicações são históricos e não foram usados como "
                  "cotação atual.", aviso=True)
    _fontes(rel, fontes)
    return rel.gerar()


# =====================================================================================================
def _linhas_cmp(cmps, unidade: str, casas: int):
    return [[c.parametro,
             (num(c.valor_ref, casas) if c.valor_ref is not None else f"{num(c.ref_min, casas)}–{num(c.ref_max, casas)}") + f" {unidade}",
             (f"{num(c.diferenca, casas)} {unidade}" + (f" ({num(c.diferenca_pct, 1)}%)" if c.diferenca_pct is not None else "")),
             ROTULO_STATUS[c.status], c.justificativa,
             f"{texto(c.registro.get('fonte_codigo'))}, p. {texto(c.registro.get('pagina_pdf')) or '—'}"] for c in cmps]


def pdf_desempenho(r: dict, fontes: dict) -> bytes:
    rel = Relatorio("SafraTech IA — Diagnóstico de Desempenho do Rebanho",
                    "Pecuária de corte · banco pecuaria_desempenho_database · Pergunta: o desempenho é adequado para raça, "
                    "idade, sexo e sistema?", RODAPE)
    st_p, st_g = r["status_peso"], r["status_gmd"]
    resumo = f"Peso: {ROTULO_STATUS[st_p]}" + (f" · GMD: {ROTULO_STATUS[st_g]}" if st_g != "sem_gmd" else " · GMD: não calculado")
    rel.destaque("Situação em relação às referências técnicas compatíveis", resumo, COR_VEREDITO.get(st_p, "#607d8b"))

    rel.secao("Identificação do animal ou lote")
    rel.pares([("Identificação", r["ident"] or "não informada"),
               ("Raça / composição genética", f"{r['raca']['nome']} — {r['raca']['grupo_genetico']}"),
               ("Sexo / condição sexual", calc.SEXOS_USUARIO[r["sexo"]]),
               ("Idade", num(r["idade"], 0, " meses")),
               ("Sistema de criação", r["sistema_reg"]["nome"]),
               ("Fase produtiva", calc.FASES_USUARIO[r["fase"]])])
    rel.secao("Pesagens e ganho médio diário")
    pares = [("Peso atual", f"{num(r['peso_atual'], 1)} kg PV em {r['data_atual']:%d/%m/%Y}")]
    if r["gmd"] is not None:
        pares += [("Peso anterior", f"{num(r['peso_ant'], 1)} kg PV em {r['data_ant']:%d/%m/%Y}"),
                  ("Intervalo entre pesagens", f"{r['dias']} dias"),
                  ("Evolução do peso", f"{num(r['ganho'], 1)} kg ({num(r['ganho'] / r['peso_ant'] * 100, 1)}%)"),
                  ("Ganho médio diário (GMD)", f"{num(r['gmd'], 3)} kg/dia — (peso atual − peso anterior) ÷ dias")]
    else:
        pares.append(("Ganho médio diário (GMD)", "não calculado: pesagem anterior não informada"))
    pares.append(("Unidades animais", f"{num(r['peso_atual'] / 450, 2)} UA (peso vivo ÷ 450)"))
    rel.pares(pares)

    rel.secao("Comparações técnicas — peso")
    if r["cmp_peso"]:
        rel.tabela(["Referência", "Valor", "Diferença", "Situação", "Por que é comparável", "Fonte"], _linhas_cmp(r["cmp_peso"], "kg", 1),
                   larguras=[3.3 * cm, 1.9 * cm, 2.3 * cm, 2.6 * cm, 5.4 * cm, 2.5 * cm])
        refs = [c.valor_ref if c.valor_ref is not None else (c.ref_min or 0) for c in r["cmp_peso"]]
        rel.grafico_barras([c.id_registro for c in r["cmp_peso"]],
                           {"Referência (kg)": refs, "Peso atual (kg)": [r["peso_atual"]] * len(refs)},
                           "Peso atual x referências compatíveis (kg PV)", altura_cm=6)
    else:
        rel.paragrafo("Dados insuficientes: o banco não possui referência de peso vivo para a mesma raça/genótipo, sexo compatível, "
                      "mesmo sistema e idade compatível. Nenhum peso esperado foi estimado.", aviso=True)
    if r["gmd"] is not None:
        rel.secao("Comparações técnicas — GMD")
        if r["cmp_gmd"]:
            rel.tabela(["Referência", "Valor", "Diferença", "Situação", "Por que é comparável", "Fonte"],
                       _linhas_cmp(r["cmp_gmd"], "kg/dia", 3), larguras=[3.3 * cm, 1.9 * cm, 2.3 * cm, 2.6 * cm, 5.4 * cm, 2.5 * cm])
        else:
            rel.paragrafo("Dados insuficientes: não há referência de GMD para a mesma raça/genótipo, sexo compatível, mesmo sistema "
                          "e mesma fase produtiva.", aviso=True)

    rel.secao("Indicadores de desempenho")
    ind = [("Situação do peso", ROTULO_STATUS[st_p]), ("Referências de peso compatíveis", str(len(r["cmp_peso"])))]
    if r["gmd"] is not None:
        ind += [("Situação do GMD", ROTULO_STATUS[st_g]), ("Referências de GMD compatíveis", str(len(r["cmp_gmd"])))]
    ind += [("Critério de idade", f"± {num(r['tol_idade'], 1)} mês(es) em torno da idade citada pela fonte"),
            ("Critério de proximidade", f"± {num(r['tol_pct'], 0)}% do valor médio de referência (faixas usam os limites da fonte)")]
    rel.pares(ind)
    rel.secao("Pontos de atenção")
    if r["atencao"]:
        for p in r["atencao"]:
            rel.paragrafo(f"• {p}")
    else:
        rel.paragrafo("Nenhum ponto de atenção identificado nas comparações realizadas.")
    rel.paragrafo("Regras de comparação: somente referências da mesma raça/genótipo (Nelore PO, Nelore comercial, nelorado e "
                  "cruzados não se misturam), sexo compatível e mesmo sistema de criação; para peso, a fonte precisa citar a "
                  "idade; para GMD, a fase produtiva deve ser a mesma. Resultados experimentais valem nas condições descritas.",
                  aviso=True)
    rel.secao("Informações técnicas da raça e do sistema")
    rel.pares([(r["raca"]["nome"], texto(r["raca"]["descricao"])), (r["sistema_reg"]["nome"], texto(r["sistema_reg"]["descricao"]))])
    _fontes(rel, fontes)
    return rel.gerar()


# =====================================================================================================
def pdf_rentabilidade(salvo: dict, premissas, fontes: dict, comparativo: pd.DataFrame, conclusao: str) -> bytes:
    res: list[calc.ResultadoCenario] = salvo["resultados"]
    e: calc.EntradaRentabilidade = salvo["entrada"]
    rel = Relatorio("SafraTech IA — Simulador de Rentabilidade",
                    "Pecuária de corte · banco pecuaria_rentabilidade_database · Pergunta: vender agora ou esperar?", RODAPE)
    acum = (e.custo_acumulado_brl or 0) > 0
    n_esp = sum(r.indicacao == "esperar" for r in res)
    cor = "#2e7d32" if n_esp == len(res) else ("#ef6c00" if n_esp == 0 else "#f9a825")
    rel.destaque("Vender agora ou esperar?", conclusao, cor)

    rel.secao("Dados do rebanho")
    rel.pares([("Raça / composição genética", f"{salvo['raca']['nome']} — {salvo['raca']['grupo_genetico']}"),
               ("Sexo / categoria", calc.SEXOS_USUARIO.get(salvo["sexo"], salvo["sexo"])),
               ("Quantidade de animais", str(e.quantidade_animais)),
               ("Peso médio atual", num(e.peso_atual_kg, 1, " kg PV")),
               ("Peso atual do rebanho", num(res[0].peso_atual_rebanho_kg, 0, " kg PV")),
               ("Arrobas hoje", f"{num(res[0].arrobas_atual_lote, 1)} @ (rendimento {num(e.rendimento_atual_pct, 1, '%')})"),
               ("Período simulado", f"{e.dias} dias")])
    _premissas(rel, premissas)

    for r in res:
        nome = calc.TIPOS_CENARIO[r.cenario.tipo]
        rel.secao(f"Cenário {nome.lower()}")
        rel.pares([("Premissas", f"arroba futura {moeda(r.cenario.preco_arroba_futuro)}/@ · GMD {num(r.cenario.gmd_kg_dia, 3)} kg/dia · "
                                 f"rendimento {num(r.cenario.rendimento_futuro_pct, 1, '%')} · custo {moeda(r.custo_diario_cab)}/cab/dia"),
                   ("Peso projetado", f"{num(r.peso_projetado_cab_kg, 1)} kg/cab · {num(r.peso_projetado_rebanho_kg, 0)} kg no rebanho"),
                   ("Ganho de peso estimado", f"{num(r.ganho_cab_kg, 1)} kg/cab · {num(r.ganho_rebanho_kg, 0)} kg no rebanho"),
                   ("Arrobas estimadas", f"{num(r.arrobas_futuro_lote, 1)} @ ({num(r.arrobas_produzidas, 1)} @ produzidas na espera)"),
                   ("Receita bruta na venda futura", moeda(r.receita_vender_depois)),
                   ("Custos da espera", moeda(r.custo_adicional_espera)),
                   ("Custos acumulados (total)", moeda(r.custo_acumulado_total_depois)),
                   ("Receita líquida (receita − custo da espera)", moeda(r.receita_liquida_depois)),
                   ("Lucro/prejuízo operacional", moeda(r.margem_operacional_depois) if acum else "não calculado: custos acumulados não informados"),
                   ("Margem operacional", num(r.margem_operacional_depois_pct, 1, "%") if acum else "não calculada: custos acumulados não informados"),
                   ("Diferença: esperar − vender agora", moeda(r.resultado_incremental)),
                   ("Custo por arroba produzida", moeda(r.custo_por_arroba_produzida)),
                   ("Arroba futura de equilíbrio", moeda(r.preco_equilibrio_futuro) + "/@"),
                   ("Indicação pelas premissas", r.indicacao)])

    rel.secao("Comparativo financeiro")
    cols = list(comparativo.columns)
    rel.tabela(cols, comparativo.values.tolist(), larguras=[5.4 * cm] + [3.15 * cm] * (len(cols) - 1))
    rel.secao("Gráficos")
    nomes = [calc.TIPOS_CENARIO[r.cenario.tipo] for r in res]
    rel.grafico_barras(nomes, {"Vender agora (receita)": [r.receita_vender_agora for r in res],
                               "Esperar (receita − custo da espera)": [r.receita_liquida_depois for r in res]},
                       "Receitas: vender agora x esperar (R$)")
    rel.grafico_barras(nomes, {"Custo da espera": [r.custo_adicional_espera for r in res],
                               "Diferença esperar − vender agora": [r.resultado_incremental for r in res]},
                       "Custos da espera e diferença financeira (R$)")
    rel.secao("Custos e receitas")
    rel.tabela(["Cenário"] + [calc.TIPOS_CUSTO[k] for k in calc.TIPOS_CUSTO] + ["Total/cab/dia", "Custo da espera", "Receita futura"],
               [[calc.TIPOS_CENARIO[r.cenario.tipo]] + [moeda(r.cenario.custos_cab_dia.get(k, 0)) for k in calc.TIPOS_CUSTO]
                + [moeda(r.custo_diario_cab), moeda(r.custo_adicional_espera), moeda(r.receita_vender_depois)] for r in res],
               larguras=[2.4 * cm] + [1.9 * cm] * 4 + [2.2 * cm, 2.6 * cm, 3.2 * cm])
    rel.secao("Conclusão")
    rel.paragrafo(conclusao)
    for r in res:
        rel.paragrafo(f"• {calc.TIPOS_CENARIO[r.cenario.tipo]}: esperar compensa se a arroba futura for maior que "
                      f"{moeda(r.preco_equilibrio_futuro)}/@ (premissa usada: {moeda(r.cenario.preco_arroba_futuro)}/@); "
                      f"diferença de {moeda(r.resultado_incremental)}.")
    rel.paragrafo("Os cenários comparam premissas definidas pelo usuário. O SafraTech não faz previsões de preço; as cotações "
                  "registradas nas publicações são históricas e não foram usadas como valores atuais.", aviso=True)
    _fontes(rel, fontes)
    return rel.gerar()
