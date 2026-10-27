#!/usr/bin/env python3
"""
Diff por multiset de valores entre o extrato do banco (CSV da fatura Nubank) e a
fatura do Organizze. NUNCA compara por descricao ou data - so por valor, porque as
descricoes e datas quase nunca batem 1 para 1 entre as duas fontes.

Uso:
    python3 diff_by_value.py Nubank_YYYY-MM-DD.csv organizze.json

Formato esperado do CSV (o que o Nubank manda por email):
    date,title,amount
    2026-10-20,Supermercado Campelo,"12,99"
    2026-10-06,Pagamento recebido,"- 7.355,46"

Formato legado (bank.json, lista de objetos do openfinance_list_transactions,
pode ser colado direto o campo "results") ainda e aceito:
    [
      {"date": "2026-07-16", "description": "...", "amount": "102.79", "type": "DEBIT", "status": "POSTED"},
      {"date": "2026-07-14", "description": "...", "amount": "-10.00", "type": "CREDIT", "status": "PENDING"},
      ...
    ]

Formato esperado de organizze.json (lista de objetos do get_credit_card_invoice,
pode ser colado direto o campo "transactions"):
    [
      {"description": "...", "amount": "R$ -102,79", "date": "16/07/2026", ...},
      ...
    ]

Saida: valores no banco sem par no Organizze (candidatos a lancar) e valores no
Organizze sem par no banco (podem ser lancamentos antigos, parcelas futuras
projetadas, ou itens do ciclo anterior). SEMPRE revise manualmente essa saida
contra os "falsos positivos conhecidos" descritos no SKILL.md antes de reportar
qualquer coisa como faltando pro usuario.
"""
import csv
import json
import sys
from collections import Counter


def parse_brl(s):
    """'R$ -102,79' ou '-102.79' ou '102,79' -> float"""
    s = str(s).strip()
    neg = s.strip().startswith("-") or s.strip().startswith("R$ -")
    s = s.replace("R$", "").replace(" ", "").replace("-", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    val = float(s)
    return -val if neg else val


def load_bank(path):
    if path.lower().endswith(".csv"):
        with open(path, newline="", encoding="utf-8-sig") as f:
            return [{
                "date": r["date"][:10],
                "description": r["title"],
                "amount": round(parse_brl(r["amount"]), 2),
                "status": "",
                "type": "",
            } for r in csv.DictReader(f)]

    with open(path) as f:
        data = json.load(f)
    items = data.get("results", data) if isinstance(data, dict) else data
    rows = []
    for r in items:
        amt = parse_brl(r["amount"])
        # DEBIT = despesa (positivo na conta de credito), CREDIT = credito/estorno
        rows.append({
            "date": r.get("date", "")[:10],
            "description": r.get("description", ""),
            "amount": round(amt, 2),
            "status": r.get("status", ""),
            "type": r.get("type", ""),
        })
    return rows


def load_organizze(path):
    with open(path) as f:
        data = json.load(f)
    items = data.get("transactions", data) if isinstance(data, dict) else data
    rows = []
    for r in items:
        amt = parse_brl(r["amount"])
        rows.append({
            "date": r.get("date", ""),
            "description": r.get("description", ""),
            "amount": round(amt, 2),
        })
    return rows


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)

    bank = load_bank(sys.argv[1])
    org = load_organizze(sys.argv[2])

    # despesas: valores positivos no banco (DEBIT) vs valores negativos no organizze
    bank_expenses = Counter(r["amount"] for r in bank if r["amount"] > 0)
    org_expenses = Counter(round(-r["amount"], 2) for r in org if r["amount"] < 0)

    # receitas/creditos: valores negativos no banco (CREDIT) vs valores positivos no organizze
    bank_credits = Counter(round(-r["amount"], 2) for r in bank if r["amount"] < 0)
    org_credits = Counter(r["amount"] for r in org if r["amount"] > 0)

    missing_expenses = bank_expenses - org_expenses
    extra_org_expenses = org_expenses - bank_expenses
    missing_credits = bank_credits - org_credits
    extra_org_credits = org_credits - bank_credits

    def rows_for(values_counter, source_rows, positive_in_source):
        remaining = Counter(values_counter)
        out = []
        for r in source_rows:
            v = r["amount"]
            key = round(v, 2) if positive_in_source else round(-v, 2)
            if remaining.get(key, 0) > 0 and (v > 0) == positive_in_source:
                out.append(r)
                remaining[key] -= 1
        return out

    print("=== DESPESAS no banco SEM par no Organizze (candidatos a lancar) ===")
    for r in rows_for(missing_expenses, bank, True):
        print(f"  {r['date']}  {r['description']:<35} R$ {r['amount']:.2f}  [{r['status']}]")

    print("\n=== DESPESAS no Organizze SEM par no banco (revisar - pode ser falso positivo) ===")
    for v, c in sorted(extra_org_expenses.items()):
        print(f"  R$ {v:.2f} x{c}")

    print("\n=== CREDITOS/ESTORNOS no banco SEM par no Organizze ===")
    for r in rows_for(missing_credits, bank, False):
        print(f"  {r['date']}  {r['description']:<35} R$ {-r['amount']:.2f}  [{r['status']}]")

    print("\n=== CREDITOS no Organizze SEM par no banco ===")
    for v, c in sorted(extra_org_credits.items()):
        print(f"  R$ {v:.2f} x{c}")

    total_bank = sum(v * c for v, c in bank_expenses.items()) - sum(v * c for v, c in bank_credits.items())
    total_org = sum(v * c for v, c in org_expenses.items()) - sum(v * c for v, c in org_credits.items())
    print(f"\nTotal liquido banco (periodo consultado): R$ {total_bank:.2f}")
    print(f"Total liquido Organizze (fatura): R$ {total_org:.2f}")
    print("(Esses dois totais NAO precisam bater exatamente - o banco pode cobrir um periodo")
    print(" diferente do ciclo de fatura. O que importa e a lista de candidatos acima.)")


if __name__ == "__main__":
    main()
