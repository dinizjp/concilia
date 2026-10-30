#!/usr/bin/env python3
"""Manda o resumo do relatório por e-mail, com link para o artefato publicado.

Uso:
    python3 email_report.py <relatorio.html> --link <url>     # resumo + botão para o artefato
    python3 email_report.py <relatorio.html>                  # sem link: o HTML completo vai em anexo
    python3 email_report.py <relatorio.html> --previa x.html  # só grava o corpo do e-mail, não envia
    python3 email_report.py --aviso "assunto" "texto"         # e-mail simples (falha na rotina)

Configuração (config/.env): SMTP_USUARIO e EMAIL_PARA (vírgula para mais de um). A senha de app do
Gmail vem de SMTP_SENHA ou, no macOS, do Keychain (serviço "concilia-smtp").
"""
import argparse
import html
import json
import os
import re
import smtplib
import subprocess
import sys
from email.message import EmailMessage
from pathlib import Path

INK, INK2, LINE, ACCENT, BOM, RUIM, ALERTA = "#15201c", "#5b6863", "#dfe5e2", "#0f6b55", "#1a7f45", "#b3261e", "#a86400"
FONTE = "-apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]


def brl(c):
    if c is None:
        return "—"
    return ("−" if c < 0 else "") + "R$ " + f"{abs(c) / 100:,.0f}".replace(",", ".")


def pct(x):
    return "—" if x is None else f"{x * 100:.1f}%".replace(".", ",").replace("-", "−")


def e(t):
    return html.escape(str(t))


def secao(titulo, corpo):
    return (f'<tr><td style="padding:26px 0 8px;font:600 13px {FONTE};letter-spacing:.06em;text-transform:uppercase;'
            f'color:{ACCENT}">{e(titulo)}</td></tr><tr><td>{corpo}</td></tr>')


def kpi(rotulo, valor, sub="", cor=INK):
    return (f'<td width="33%" valign="top" style="padding:12px;border:1px solid {LINE};border-radius:8px">'
            f'<div style="font:12px {FONTE};color:{INK2}">{e(rotulo)}</div>'
            f'<div style="font:700 20px {FONTE};color:{cor};margin-top:4px">{valor}</div>'
            f'<div style="font:12px {FONTE};color:{INK2};margin-top:2px">{sub}</div></td>')


def render(D, link=None):
    t = D["foco_agregado"]["total"]
    cmp, ref = D.get("comparacao") or {}, (D.get("cmp_label") or {}).get("ref", "")

    def vs(k):
        return f"média {e(ref)}: {brl(cmp[k]['ref'])}" if cmp.get(k, {}).get("ref") is not None else ""

    partes = []
    if D.get("avisos"):
        itens = "".join(f"<li style='margin:4px 0'>{e(a)}</li>" for a in D["avisos"])
        partes.append(f'<tr><td style="padding:12px 16px;background:#fff4e0;border-left:4px solid {ALERTA};font:13px {FONTE};color:{INK}">'
                      f'<b>Atenção</b><ul style="margin:6px 0 0;padding-left:18px">{itens}</ul></td></tr>')

    partes.append(
        '<tr><td style="padding-top:18px"><table width="100%" cellpadding="0" cellspacing="6"><tr>'
        + kpi("Renda líquida", brl(t["renda_liquida"]), vs("renda_liquida"))
        + kpi("Consumo", brl(t["consumo"]), vs("consumo"))
        + kpi("Sobra", brl(t["sobra_estrutural"]), f"taxa de poupança {pct(D['foco_agregado']['taxa_poupanca'])}",
              BOM if t["sobra_estrutural"] >= 0 else RUIM)
        + '</tr></table></td></tr>')

    if D.get("destaques"):
        lis = "".join(f'<li style="margin:0 0 8px">{e(d)}</li>' for d in D["destaques"])
        partes.append(secao("Destaques", f'<ul style="margin:0;padding-left:20px;font:15px/1.5 {FONTE};color:{INK}">{lis}</ul>'))

    if D.get("pauta"):
        lis = "".join(f'<li style="margin:0 0 8px"><b>{e(p.get("tema", ""))}:</b> {e(p.get("pergunta", ""))}</li>' for p in D["pauta"])
        partes.append(secao("Pauta da conversa", f'<ol style="margin:0;padding-left:20px;font:15px/1.5 {FONTE};color:{INK}">{lis}</ol>'))

    if link:
        partes.append(f'<tr><td align="center" style="padding:28px 0 4px"><a href="{e(link)}" style="display:inline-block;background:{ACCENT};'
                      f'color:#fff;text-decoration:none;font:600 15px {FONTE};padding:12px 22px;border-radius:8px">Abrir o relatório completo</a></td></tr>')
    falhas = [c["nome"] for c in D.get("checagens", []) if not c["ok"]]
    rodape = ("Checagens automáticas ok." if not falhas else "Checagens que falharam: " + "; ".join(falhas) + ".") + (
        "" if link else " O relatório completo está em anexo: abra no navegador.")
    partes.append(f'<tr><td style="padding:20px 0 0;font:12px {FONTE};color:{INK2}">{e(rodape)}</td></tr>')

    nome = (D.get("identidade") or {}).get("titulo", "da casa")
    return (f'<!doctype html><html><body style="margin:0;background:#f4f6f5">'
            f'<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6f5"><tr><td align="center" style="padding:24px 12px">'
            f'<table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#fff;border-radius:12px;padding:28px">'
            f'<tr><td style="font:13px {FONTE};color:{INK2}">Finanças {e(nome)}</td></tr>'
            f'<tr><td style="font:700 26px {FONTE};color:{INK};padding-top:4px">{e(D["titulo"])}</td></tr>'
            + "".join(partes) + '</table></td></tr></table></body></html>')


def senha():
    if os.environ.get("SMTP_SENHA"):
        return os.environ["SMTP_SENHA"]
    try:
        return subprocess.run(["security", "find-generic-password", "-s", "concilia-smtp", "-w"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        sys.exit("ERRO: senha do e-mail não encontrada (SMTP_SENHA ou Keychain 'concilia-smtp').")


def enviar(assunto, corpo_html, anexo=None):
    usuario, para = os.environ.get("SMTP_USUARIO"), os.environ.get("EMAIL_PARA")
    if not (usuario and para):
        sys.exit("ERRO: defina SMTP_USUARIO e EMAIL_PARA em config/.env.")
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = assunto, f"Concilia <{usuario}>", para
    msg.set_content(re.sub(r"\n{3,}", "\n\n", re.sub(r"<[^>]+>", "\n", corpo_html)).strip())
    msg.add_alternative(corpo_html, subtype="html")
    if anexo:
        msg.add_attachment(Path(anexo).read_bytes(), maintype="text", subtype="html", filename=Path(anexo).name)
    with smtplib.SMTP_SSL(os.environ.get("SMTP_HOST", "smtp.gmail.com"), 465, timeout=30) as s:
        s.login(usuario, senha())
        s.send_message(msg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("relatorio", nargs="?")
    ap.add_argument("--link")
    ap.add_argument("--previa")
    ap.add_argument("--aviso", nargs=2, metavar=("ASSUNTO", "TEXTO"))
    a = ap.parse_args()
    if a.aviso:
        enviar(a.aviso[0], f'<p style="font:15px/1.5 {FONTE}">{e(a.aviso[1])}</p>')
        return print("aviso enviado")
    m = re.search(r"const D = (.*?);\n", Path(a.relatorio).read_text(encoding="utf-8"), re.S)
    if not m:
        sys.exit("ERRO: não achei os dados do relatório no HTML.")
    D = json.loads(m.group(1).replace("<\\/", "</"))
    corpo = render(D, a.link)
    if a.previa:
        Path(a.previa).write_text(corpo, encoding="utf-8")
        return print(f"prévia -> {a.previa}")
    foco = D["foco"]
    titulo = f"{MESES[int(foco[0][5:]) - 1]} de {foco[0][:4]}" if len(foco) == 1 else D["titulo"]
    enviar(f"Relatório financeiro · {titulo} · sobra {brl(D['foco_agregado']['total']['sobra_estrutural'])}",
           corpo, None if a.link else a.relatorio)
    print(f"e-mail enviado para {os.environ['EMAIL_PARA']}")


if __name__ == "__main__":
    main()
