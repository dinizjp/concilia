"""Leitura dos dados do Meu Pluggy (somente leitura — não grava nada em lugar nenhum).

  python3 pluggy.py contas                          # bancos, contas, cartões, saldos e ids
  python3 pluggy.py faturas <accountId>             # faturas de um cartão
  python3 pluggy.py fatura <accountId> <billId>     # lançamentos de uma fatura
  python3 pluggy.py transacoes <accountId> <de> [ate]   # extrato (datas YYYY-MM-DD)
  python3 pluggy.py csv <accountId> [billId]        # fatura no formato do CSV do Nubank (sem billId = aberta)

Credenciais em ../config/.env: PLUGGY_CLIENT_ID, PLUGGY_CLIENT_SECRET,
PLUGGY_ITEM_IDS (itemIds do Dashboard, separados por vírgula)
Saída em JSON.
"""
import json
import sys
import urllib.request
from datetime import date, timedelta
from pathlib import Path

API = "https://api.pluggy.ai"


def env():
    path = Path(__file__).resolve().parent.parent / "config" / ".env"
    pairs = (l.split("=", 1) for l in path.read_text().splitlines() if "=" in l and not l.startswith("#"))
    return {k.strip(): v.strip().strip('"') for k, v in pairs}


def call(path, key=None, body=None):
    req = urllib.request.Request(f"{API}{path}", data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json", **({"X-API-KEY": key} if key else {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def cursor_all(key, path):
    page = call(path, key)
    out, base = page["results"], path.split("?")[0]
    while page.get("next"):
        page = call(base + page["next"], key)
        out += page["results"]
    return out


def slim(t):
    cc = t.get("creditCardMetadata") or {}
    return {
        "id": t["id"], "data": t["date"][:10], "descricao": t.get("description"),
        # compra internacional: amount vem na moeda original (USD); o valor em R$ fica em amountInAccountCurrency
        "valor": t.get("amountInAccountCurrency") or t["amount"],
        **({"original": f"{t['currencyCode']} {t['amount']}"} if t.get("currencyCode", "BRL") != "BRL" else {}),
        "tipo": t["type"], "categoria": t.get("category"), "status": t["status"],
        **({"parcela": f"{cc['installmentNumber']}/{cc['totalInstallments']}"} if (cc.get("totalInstallments") or 1) > 1 else {}),
        **({"billId": cc["billId"]} if cc.get("billId") else {}),
        # data que o Nubank mostra no app/CSV (a "data" da Pluggy é o instante da compra em UTC)
        **({"data_fatura": cc["billPostDate"][:10]} if cc.get("billPostDate") else {}),
    }


def transacoes(key, acc, de, ate=None):
    q = f"/v2/transactions?accountId={acc}&dateFrom={de}" + (f"&dateTo={ate}" if ate else "")
    return [slim(t) for t in cursor_all(key, q)]


def main(cmd, *args):
    e = env()
    key = call("/auth", body={"clientId": e["PLUGGY_CLIENT_ID"], "clientSecret": e["PLUGGY_CLIENT_SECRET"]})["apiKey"]
    if cmd == "contas":
        out = []
        # plano grátis não lista items (LIST_ITEMS_FEATURE_NOT_ENABLED): ids vêm do Dashboard
        for item in (call(f"/items/{i.strip()}", key) for i in e["PLUGGY_ITEM_IDS"].split(",")):
            accs = call(f"/accounts?itemId={item['id']}", key)["results"]
            out.append({
                "banco": (item.get("connector") or {}).get("name"), "itemId": item["id"],
                "status": item["status"], "atualizado": item.get("lastUpdatedAt"),
                "contas": [{"accountId": a["id"], "tipo": a["subtype"], "nome": a["name"], "saldo": a["balance"],
                            **({"limite_disponivel": (a.get("creditData") or {}).get("availableCreditLimit")}
                               if a["type"] == "CREDIT" else {})} for a in accs],
            })
    elif cmd == "faturas":
        out = call(f"/bills?accountId={args[0]}", key)["results"]
    elif cmd == "fatura":
        bill = call(f"/bills/{args[1]}", key)
        # ponytail: janela de 1 ano antes do fechamento pega parcelas antigas; aumentar se faltar parcela longa
        de = str(date.fromisoformat(bill["billClosingDate"][:10]) - timedelta(days=365))
        txs = [t for t in transacoes(key, args[0], de) if t.get("billId") == args[1]]
        out = {"fatura": bill, "total_lancamentos": round(sum(t["valor"] for t in txs), 2), "lancamentos": txs}
    elif cmd == "transacoes":
        out = transacoes(key, *args)
    elif cmd == "csv":
        if len(args) > 1:
            bill = call(f"/bills/{args[1]}", key)
            de = str(date.fromisoformat(bill["billClosingDate"][:10]) - timedelta(days=365))
            txs = [t for t in transacoes(key, args[0], de) if t.get("billId") == args[1]]
        else:
            # ponytail: fatura aberta = sem billId e data <= hoje (parcelas futuras vêm sem billId com data futura)
            txs = [t for t in transacoes(key, args[0], str(date.today() - timedelta(days=60)))
                   if not t.get("billId") and t["data"] <= str(date.today())]
        print(to_nubank_csv(txs), end="")
        return
    else:
        sys.exit(__doc__)
    print(json.dumps(out, ensure_ascii=False, indent=1))


def brl(v):
    s = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"- {s}" if v < 0 else s


def to_nubank_csv(txs):
    """Mesmo formato do CSV que o Nubank manda por email (date,title,amount)."""
    lines = ["date,title,amount"]
    for t in sorted(txs, key=lambda t: t.get("data_fatura") or t["data"], reverse=True):
        d = t.get("data_fatura") or t["data"]
        p = t.get("parcela")
        title = t["descricao"].replace(f" {p}", "") + f" - Parcela {p}" if p else t["descricao"]
        lines.append(f'{d},{title.replace(",", " ")},"{brl(t["valor"])}"')
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main(*sys.argv[1:]) if len(sys.argv) > 1 else sys.exit(__doc__)
