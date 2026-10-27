#!/usr/bin/env python3
"""Monta o relatório financeiro a partir de um JSON de dados brutos.

Uso:
    python3 build_report.py <dados.json> <saida.html> [--config ~/concilia/config/relatorio.json]

O JSON de entrada é montado pelo Claude a partir do Organizze (formato em
references/formato-dados.md). Este script faz TODA a conta: agrupa categorias,
soma por mês, calcula sobra/taxa de poupança, médias e variações, e injeta o
resultado no template HTML. Valores sempre em centavos (int).
"""
import argparse
import json
import re
import statistics
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
MESES_PT = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
GRUPOS_DESPESA = ["fixo", "variavel", "patrimonio", "evento", "empresa"]


def label_mes(chave):
    ano, mes = chave.split("-")
    return f"{MESES_PT[int(mes) - 1]}/{ano[2:]}"


def classificar(config):
    mapa_desp, mapa_rec = {}, {}
    for grupo, info in config["grupos_despesa"].items():
        for cat in info["categorias"]:
            mapa_desp[cat.strip().lower()] = grupo
    for grupo, info in config["grupos_receita"].items():
        for cat in info["categorias"]:
            mapa_rec[cat.strip().lower()] = grupo
    for cat in config.get("dividir_por_conta", {}).get("categorias", []):
        mapa_desp[cat.strip().lower()] = "__dividir__"
    return mapa_desp, mapa_rec


def resumo_mes(dados_mes, mapa_desp, mapa_rec, avisos):
    r = {g: 0 for g in GRUPOS_DESPESA}
    r["receita_recorrente"] = 0
    r["receita_extra"] = 0
    r["receita_resgate"] = 0
    for cat, v in dados_mes.get("despesas", {}).items():
        grupo = mapa_desp.get(cat.strip().lower())
        if grupo is None:
            grupo = "variavel"
            avisos.add(f"Categoria de despesa sem classificação: '{cat}' (contada como Variável). Ajuste em config/relatorio.json.")
        elif grupo == "__dividir__":
            grupo = "fixo"
            if int(v):
                avisos.add(f"Categoria '{cat.strip()}' veio sem dividir por conta (contada como Fixo). Separe em '{cat.strip()} (PF)' e '{cat.strip()} (PJ)'.")
        r[grupo] += int(v)
    for cat, v in dados_mes.get("receitas", {}).items():
        grupo = mapa_rec.get(cat.strip().lower())
        if grupo is None:
            grupo = "extra"
            avisos.add(f"Categoria de receita sem classificação: '{cat}' (contada como Extra). Ajuste em config/relatorio.json.")
        key = {"recorrente": "receita_recorrente", "resgate": "receita_resgate"}.get(grupo, "receita_extra")
        r[key] += int(v)
    r["consumo"] = r["fixo"] + r["variavel"]
    # resgate é dinheiro guardado voltando: abate do aporte, não é renda nova
    r["aporte_liquido"] = r["patrimonio"] - r["receita_resgate"]
    # salário pode entrar bruto numa conta PJ; os custos da empresa saem dele antes do consumo
    r["renda_liquida"] = r["receita_recorrente"] - r["empresa"]
    r["sobra_estrutural"] = r["renda_liquida"] - r["consumo"]
    r["sobra_total"] = (r["receita_recorrente"] + r["receita_extra"] + r["receita_resgate"]) - sum(r[g] for g in GRUPOS_DESPESA)
    r["taxa_poupanca"] = round(r["sobra_estrutural"] / r["renda_liquida"], 4) if r["renda_liquida"] > 0 else None
    return r


def media(valores):
    valores = [v for v in valores if v is not None]
    return round(sum(valores) / len(valores)) if valores else None


def variacao(atual, ref):
    if ref in (None, 0) or atual is None:
        return None
    return round((atual - ref) / abs(ref), 4)


def categorias_periodo(meses_dados, foco, cmp_atual, ref_meses, mapa_desp):
    """Por categoria: média mensal no foco; variação = média em cmp_atual vs média em ref_meses."""
    nomes = set()
    for m in foco + ref_meses:
        nomes.update(meses_dados.get(m, {}).get("despesas", {}).keys())
    linhas = []
    for nome in nomes:
        foco_vals = [int(meses_dados.get(m, {}).get("despesas", {}).get(nome, 0)) for m in foco]
        ref_vals = [int(meses_dados.get(m, {}).get("despesas", {}).get(nome, 0)) for m in ref_meses]
        atual_vals = [int(meses_dados.get(m, {}).get("despesas", {}).get(nome, 0)) for m in cmp_atual]
        total = sum(foco_vals)
        media_foco = round(total / len(foco)) if foco else 0
        media_atual = round(sum(atual_vals) / len(atual_vals)) if atual_vals else 0
        media_ref = round(sum(ref_vals) / len(ref_vals)) if ref_vals else None
        if total == 0 and not media_ref:
            continue
        linhas.append({
            "nome": nome.strip(),
            "grupo": mapa_desp.get(nome.strip().lower(), "variavel"),
            "total": total,
            "media_mensal": media_foco,
            "media_atual": media_atual,
            "media_ref": media_ref,
            "delta": (media_atual - media_ref) if media_ref is not None else None,
            "delta_pct": variacao(media_atual, media_ref),
            "por_mes": foco_vals,
        })
    linhas.sort(key=lambda x: -x["total"])
    return linhas


def sugerir_meta(taxas):
    """Meta inicial = mediana das taxas positivas do histórico, arredondada para baixo em 5 p.p., piso 10%."""
    validas = [t for t in taxas if t is not None]
    if not validas:
        return None
    med = statistics.median(validas)
    base = max(0.10, int(med * 100 // 5) * 5 / 100)
    return {"mediana_historica": round(med, 4), "meta_sugerida": round(base, 2)}


NUM_RE = re.compile(r"(R\$\s*)?([−+-]?)(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d+))?\s*(mil\b|k\b|%)?")


def coletar_valores(obj, dinheiro, taxas, chave=""):
    """Junta todo número do relatório calculado: centavos → reais; chaves de taxa/pct → pontos percentuais."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            coletar_valores(v, dinheiro, taxas, k)
    elif isinstance(obj, list):
        for v in obj:
            coletar_valores(v, dinheiro, taxas, chave)
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        if any(s in chave for s in ("pct", "taxa", "mediana", "meta_sugerida")):
            taxas.add(round(abs(obj) * 100, 2))
        elif chave not in ("restantes", "n", "ano"):
            dinheiro.add(abs(obj) / 100)


def checar_texto(textos, saida):
    """Acha valores em R$ e % nos destaques/pauta que não aparecem em nenhum número calculado.
    Não prova erro: lista o que o Claude precisa recalcular com Python antes de publicar."""
    dinheiro, taxas = set(), set()
    fora = ("destaques", "pauta", "avisos", "checagens", "serie", "grupos", "meta")
    coletar_valores({k: v for k, v in saida.items() if k not in fora}, dinheiro, taxas)
    # da série mensal, só os indicadores que o texto costuma citar por mês
    for r in saida["serie"]:
        coletar_valores({k: r[k] for k in ("receita_recorrente", "renda_liquida", "consumo", "sobra_estrutural", "taxa_poupanca")}, dinheiro, taxas)
    if saida["meta"]:
        taxas.update({round(saida["meta"]["meta_sugerida"] * 100, 2), round(saida["meta"]["mediana_historica"] * 100, 2)})
    # diferenças da comparação (ex.: "subiu R$ 2,3 mil/mês")
    for c in (saida["comparacao"] or {}).values():
        if isinstance(c.get("atual"), int) and isinstance(c.get("ref"), int):
            dinheiro.add(abs(c["atual"] - c["ref"]) / 100)
    achados, soltos = 0, []
    for t in textos:
        for mt in NUM_RE.finditer(t):
            rs, _, inteiro, dec, unid = mt.groups()
            if not rs and not unid:
                continue  # número solto (ano, contagem de meses, dia)
            v = float(inteiro.replace(".", "") + ("." + dec if dec else ""))
            casas = len(dec) if dec else 0
            if unid == "%":
                tol = 0.5 * 10 ** -casas + 0.05
                ok = any(abs(v - x) <= tol for x in taxas)
            else:
                mult = 1000 if unid in ("mil", "k") else 1
                v *= mult
                tol = max(0.5 * 10 ** -casas * mult, v * 0.005, 1)
                ok = any(abs(v - x) <= tol for x in dinheiro)
            achados += 1
            if not ok:
                soltos.append((mt.group(0).strip(), t[:70]))
    return achados, soltos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dados")
    ap.add_argument("saida")
    ap.add_argument("--config", default=str(Path.home() / "concilia" / "config" / "relatorio.json"))
    ap.add_argument("--template", default=str(SKILL_DIR / "assets" / "template.html"))
    args = ap.parse_args()

    dados = json.loads(Path(args.dados).read_text(encoding="utf-8"))
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    mapa_desp, mapa_rec = classificar(config)
    avisos = set(dados.get("avisos", []))

    meses_dados = dados.get("meses", {})
    col = dados.get("meses_colunas")
    if col:
        # formato colunar, espelho do get_categories_evolution: listas alinhadas com col["meses"]
        for i, m in enumerate(col["meses"]):
            md = meses_dados.setdefault(m, {"despesas": {}, "receitas": {}})
            for tipo in ("despesas", "receitas"):
                for cat, vals in col.get(tipo, {}).items():
                    if len(vals) != len(col["meses"]):
                        sys.exit(f"ERRO: '{cat}' tem {len(vals)} valores para {len(col['meses'])} meses")
                    if vals[i]:
                        md.setdefault(tipo, {})[cat] = int(vals[i])
    todos = sorted(meses_dados.keys())
    foco = sorted(dados["foco"])
    faltando = [m for m in foco if m not in meses_dados]
    if faltando:
        sys.exit(f"ERRO: meses do foco sem dados: {faltando}")

    # referência: mesmo número de meses imediatamente antes do foco (mín. 3 para mensal)
    antes = [m for m in todos if m < foco[0]]
    n_ref = max(3, len(foco)) if len(foco) == 1 else len(foco)
    ref_meses = antes[-n_ref:]

    serie = []
    for m in todos:
        r = resumo_mes(meses_dados[m], mapa_desp, mapa_rec, avisos)
        r["mes"] = m
        r["label"] = label_mes(m)
        r["no_foco"] = m in foco
        serie.append(r)
    por_mes = {r["mes"]: r for r in serie}

    def agrega(meses):
        if not meses:
            return None
        chaves = ["receita_recorrente", "renda_liquida", "receita_extra", "receita_resgate", "aporte_liquido",
                  "consumo", "sobra_estrutural", "sobra_total"] + GRUPOS_DESPESA
        tot = {k: sum(por_mes[m][k] for m in meses) for k in chaves}
        med = {k: round(tot[k] / len(meses)) for k in chaves}
        taxa = round(tot["sobra_estrutural"] / tot["renda_liquida"], 4) if tot["renda_liquida"] > 0 else None
        return {"meses": meses, "total": tot, "media": med, "taxa_poupanca": taxa}

    foco_ag = agrega(foco)
    # Mensal/trimestral: foco vs meses anteriores. Panorama (sem contexto): últimos 3 meses vs o resto do ano.
    if dados.get("comparar"):
        # comparação explícita, ex.: jan–set/26 vs jan–set/25 num panorama de vários anos
        cmp_atual, ref_meses = sorted(dados["comparar"]["atual"]), sorted(dados["comparar"]["ref"])
    elif not ref_meses and len(foco) >= 6:
        cmp_atual, ref_meses = foco[-3:], foco[:-3]
    else:
        cmp_atual = foco
    atual_ag, ref_ag = agrega(cmp_atual), agrega(ref_meses)
    comparacao = None
    if ref_ag:
        comparacao = {k: {"atual": atual_ag["media"][k], "ref": ref_ag["media"][k],
                          "delta_pct": variacao(atual_ag["media"][k], ref_ag["media"][k])}
                      for k in atual_ag["media"]}
        comparacao["taxa_poupanca"] = {"atual": atual_ag["taxa_poupanca"], "ref": ref_ag["taxa_poupanca"]}

    def faixa(meses):
        return label_mes(meses[0]) if len(meses) == 1 else f"{label_mes(meses[0])}–{label_mes(meses[-1])}"
    cmp_label = {"atual": faixa(cmp_atual), "ref": faixa(ref_meses)} if ref_meses else None

    anos = []
    for ano in sorted({m[:4] for m in foco}):
        ag = agrega([m for m in foco if m.startswith(ano)])
        anos.append({"ano": ano, "n": len(ag["meses"]), "faixa": faixa(ag["meses"]), "media": ag["media"],
                     "total": ag["total"], "taxa_poupanca": ag["taxa_poupanca"]})

    # segunda checagem: totais do get_categories_report do mesmo período têm que bater com a soma das colunas
    conf = dados.get("conferencia")
    conferencia = None
    if conf:
        desp = sum(foco_ag["total"][g] for g in GRUPOS_DESPESA)
        rec = foco_ag["total"]["receita_recorrente"] + foco_ag["total"]["receita_extra"] + foco_ag["total"]["receita_resgate"]
        conferencia = {"despesas": [desp, conf.get("despesas_total")], "receitas": [rec, conf.get("receitas_total")]}
        for nome, (calc, ref) in conferencia.items():
            if ref is not None and abs(calc - int(ref)) > 100:
                avisos.add(f"Conferência: {nome} somam {calc/100:,.2f} nas categorias, mas o relatório do Organizze dá {int(ref)/100:,.2f}. Falta ou sobra categoria na coleta.")
        conferencia["ok"] = all(r is None or abs(c - int(r)) <= 100 for c, r in conferencia.values())

    cats = categorias_periodo(meses_dados, foco, cmp_atual, ref_meses, mapa_desp)
    movers = sorted([c for c in cats if c["delta"] is not None and c["grupo"] in ("fixo", "variavel")],
                    key=lambda c: -abs(c["delta"]))[:6]

    # itens detalhados: natureza "resgate..." vai para resgates; o resto é receita extra de verdade
    todos_itens = list(dados.get("receitas_extras", []))
    extras = [r for r in todos_itens if not str(r.get("natureza", "")).lower().startswith("resgate")]
    resgates = [r for r in todos_itens if str(r.get("natureza", "")).lower().startswith("resgate")]
    detalhe_ok = True
    for lista, chave, nome, resto_txt in ((extras, "receita_extra", "Receitas extras", "Outras entradas menores"),
                                          (resgates, "receita_resgate", "Resgates", "Outros resgates/rendimentos de investimento")):
        if not lista and not foco_ag["total"][chave]:
            continue
        resto = foco_ag["total"][chave] - sum(int(r["valor"]) for r in lista)
        if resto > 0 and lista:
            lista.append({"descricao": resto_txt, "valor": resto, "natureza": "vários"})
        elif resto < -100:
            detalhe_ok = False
            avisos.add(f"{nome} detalhados somam {(-resto)/100:,.2f} a mais que o total da categoria: algum item está com natureza errada (resgate x extra) ou fora da categoria.")

    saldos = dados.get("saldos", [])
    contas_cfg = config["contas"]
    for s in saldos:
        s["tipo"] = next((t for t, lst in contas_cfg.items() if s["conta"] in lst), "outra")
        if s.get("inicio") is not None and s.get("fim") is not None:
            s["delta"] = s["fim"] - s["inicio"]

    parcelas = dados.get("parcelas", [])
    assin = dados.get("assinaturas", [])
    compromissos = {
        "parcelas": parcelas,
        "parcelas_mensal": sum(int(p.get("valor_parcela", 0)) for p in parcelas),
        "parcelas_saldo": sum(int(p.get("valor_parcela", 0)) * int(p.get("restantes", 0)) for p in parcelas),
        "assinaturas": assin,
        "assinaturas_mensal": sum(int(a.get("valor_mensal", 0)) for a in assin),
        "faturas_abertas": dados.get("faturas_abertas", []),
        "contas_a_vencer_30d": dados.get("contas_a_vencer_30d"),
    }
    if foco_ag["media"]["renda_liquida"] > 0:
        compromissos["comprometido_pct"] = round(
            (compromissos["parcelas_mensal"] + compromissos["assinaturas_mensal"]) / foco_ag["media"]["renda_liquida"], 4)

    # ---------- checagens automáticas (vão para o relatório e para o terminal) ----------
    checagens = []

    def checa(nome, ok, detalhe=""):
        checagens.append({"nome": nome, "ok": bool(ok), "detalhe": detalhe})

    checa("Soma das categorias = relatório de categorias do Organizze",
          conferencia and conferencia["ok"], "" if conferencia else "conferência não preenchida")
    sem_classe = [a for a in avisos if "sem classificação" in a or "sem dividir" in a]
    checa("Todas as categorias classificadas (e impostos/contabilidade/assinaturas divididos PF x PJ)",
          not sem_classe, f"{len(sem_classe)} pendente(s)" if sem_classe else "")

    def seguinte(m):
        a, mm = int(m[:4]), int(m[5:])
        return f"{a + mm // 12}-{mm % 12 + 1:02d}"
    lacunas = [b for a, b in zip(foco, foco[1:]) if seguinte(a) != b]
    checa("Meses do período completos e em sequência", not lacunas, f"salto antes de {lacunas}" if lacunas else "")
    checa("Receitas extras e resgates detalhados batem com o total das categorias", detalhe_ok)

    confirmados = dados.get("confirmados", {})
    rec_foco = [por_mes[m]["receita_recorrente"] for m in foco]
    med_rec = statistics.median(rec_foco) if rec_foco else 0
    sal_fora = [m for m in foco if med_rec and por_mes[m]["receita_recorrente"] < 0.6 * med_rec
                and m not in confirmados.get("salario_baixo", [])]
    checa("Salários dentro do padrão (ou já confirmados com o usuário)", not sal_fora,
          f"confirmar: {', '.join(label_mes(m) for m in sal_fora)}" if sal_fora else "")
    vazios = [m for m in foco if not meses_dados[m].get("despesas")]
    checa("Nenhum mês sem despesas", not vazios, ", ".join(vazios))

    # picos: mês com categoria > 3x a mediana dela e > R$ 1.000 — precisa de explicação nos destaques
    picos = []
    for c in cats:
        if c["grupo"] not in ("fixo", "variavel"):
            continue
        base = statistics.median(c["por_mes"]) if c["por_mes"] else 0
        for m, v in zip(foco, c["por_mes"]):
            if v > 100000 and v > 3 * max(base, 1):
                picos.append((c["nome"], m, v, base))

    saida = {
        "tipo": dados.get("tipo", "mensal"),
        "titulo": dados.get("titulo") or " – ".join(sorted({label_mes(foco[0]), label_mes(foco[-1])})),
        "gerado_em": dados.get("gerado_em"),
        "foco": foco,
        "ref_meses": ref_meses,
        "grupos": {g: {"label": i["label"], "descricao": i["descricao"]} for g, i in config["grupos_despesa"].items()},
        "serie": serie,
        "foco_agregado": foco_ag,
        "ref_agregado": ref_ag,
        "comparacao": comparacao,
        "cmp_label": cmp_label,
        "cmp_atual": cmp_atual,
        "anos": anos,
        "conferencia": conferencia,
        "meta": sugerir_meta([r["taxa_poupanca"] for r in serie]),
        "categorias": cats,
        "movers": movers,
        "receitas_extras": extras,
        "resgates": resgates,
        "checagens": checagens,
        "saldos": saldos,
        "patrimonio": dados.get("patrimonio"),
        "compromissos": compromissos,
        "empresa": dados.get("empresa"),
        "identidade": config.get("identidade", {}),
        "destaques": dados.get("destaques", []),
        "pauta": dados.get("pauta", []),
        "avisos": sorted(avisos),
    }

    tpl = Path(args.template).read_text(encoding="utf-8")
    payload = json.dumps(saida, ensure_ascii=False).replace("</", "<\\/")
    html = tpl.replace("__REPORT_DATA__", payload).replace("__REPORT_TITLE__", f"Finanças {config.get('identidade', {}).get('titulo', 'da casa')} · {saida['titulo']}")
    Path(args.saida).parent.mkdir(parents=True, exist_ok=True)
    Path(args.saida).write_text(html, encoding="utf-8")

    # resumo no terminal para o Claude conferir os números antes de escrever destaques/pauta
    fa = foco_ag
    print(f"OK -> {args.saida}")
    print(f"Foco {foco[0]}..{foco[-1]} ({len(foco)} mês/meses) | comparação {cmp_atual} vs {ref_meses}")
    for k in ["receita_recorrente", "renda_liquida", "receita_extra", "receita_resgate", "fixo", "variavel", "patrimonio",
              "aporte_liquido", "evento", "empresa", "consumo", "sobra_estrutural", "sobra_total"]:
        print(f"  {k:18} total {fa['total'][k]/100:>12,.2f}  média/mês {fa['media'][k]/100:>11,.2f}")
    print(f"  taxa de poupança estrutural: {fa['taxa_poupanca']}")
    if saida["meta"]:
        print(f"  meta sugerida: {saida['meta']}")
    print("  maiores variações vs referência:")
    for c in movers:
        print(f"    {c['nome']:24} {c['media_atual']/100:>10,.2f} vs {c['media_ref']/100:>10,.2f}  ({c['delta']/100:+,.2f})")
    if comparacao:
        print(f"  taxa de poupança {cmp_label['atual']}: {comparacao['taxa_poupanca']['atual']} vs {cmp_label['ref']}: {comparacao['taxa_poupanca']['ref']}")
    if len(anos) > 1:
        print("  por ano:")
        for y in anos:
            print(f"    {y['ano']} ({y['faixa']}): renda líq. {y['media']['renda_liquida']/100:,.0f}/mês, consumo {y['media']['consumo']/100:,.0f}/mês, sobra {y['total']['sobra_estrutural']/100:,.0f}, taxa {y['taxa_poupanca']}")
    if conferencia:
        print(f"  conferência com o Organizze: {'OK' if conferencia['ok'] else 'DIVERGE'} {conferencia}")
    else:
        print("  conferência com o Organizze: NÃO FEITA (preencha 'conferencia' no JSON)")
    for a in sorted(avisos):
        print(f"  AVISO: {a}")

    print("\nCHECAGENS")
    for c in checagens:
        print(f"  [{'OK' if c['ok'] else 'FALHA'}] {c['nome']}{' — ' + c['detalhe'] if c['detalhe'] else ''}")
    if picos:
        print("  PICOS (explique nos destaques ou confirme o lançamento):")
        for nome, m, v, base in sorted(picos, key=lambda p: -p[2])[:10]:
            print(f"    {nome} em {label_mes(m)}: {v/100:,.2f} (mediana {base/100:,.2f})")
    textos = list(saida["destaques"]) + [f"{p.get('pergunta', '')} {p.get('dado', '')}" for p in saida["pauta"]]
    if textos:
        n, soltos = checar_texto(textos, saida)
        print(f"  TEXTO: {n} valores citados, {len(soltos)} sem correspondência nos números calculados")
        for val, ctx in soltos:
            print(f"    ? {val:>14}  em: {ctx}…")
    falhas = [c for c in checagens if not c["ok"]]
    if falhas:
        print(f"\nNÃO PUBLICAR: {len(falhas)} checagem(ns) falharam.")
        sys.exit(2)


if __name__ == "__main__":
    main()
