#!/usr/bin/env python3
"""
Extrai os anexos de um email do Gmail baixado com get_message(messageFormat="RAW").

Uso:
    python3 -I extract_email_attachment.py <resultado_get_message.txt> <pasta_destino>

O arquivo de entrada e o JSON que o Claude Code salva quando o resultado do RAW e
grande demais para o contexto: {"id": ..., "raw": "<base64url do MIME>", ...}.
Salva cada anexo em <pasta_destino>/<nome do anexo> e imprime caminho e tamanho.
"""
import base64
import email
import json
import os
import sys
from email import policy


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)

    with open(sys.argv[1]) as f:
        data = json.load(f)
    raw = data["raw"]
    raw += "=" * (-len(raw) % 4)
    msg = email.message_from_bytes(base64.urlsafe_b64decode(raw), policy=policy.default)

    found = False
    for part in msg.iter_attachments():
        name = os.path.basename(part.get_filename() or "anexo.bin")
        out = os.path.join(sys.argv[2], name)
        payload = part.get_payload(decode=True)
        with open(out, "wb") as f:
            f.write(payload)
        print(f"{out}  {len(payload)} bytes")
        found = True

    if not found:
        print("Nenhum anexo encontrado no email.")
        sys.exit(2)


if __name__ == "__main__":
    main()
