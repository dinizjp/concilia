# Como usar os scripts

## extract_email_attachment.py

1. `Gmail:get_message(messageId, messageFormat="RAW")` — o resultado é grande e o Claude Code
   salva em arquivo (o caminho vem na resposta).
2. Rode:
   ```
   python3 -I scripts/extract_email_attachment.py <arquivo_salvo.txt> ~/Downloads
   ```
3. Saída: caminho do `Nubank_YYYY-MM-DD.csv` salvo e tamanho.

## diff_by_value.py

1. Depois de chamar `organizze:get_credit_card_invoice`, salve o array `transactions`
   (ou o objeto inteiro) em um JSON no scratchpad, ex: `organizze.json`.
2. Rode:
   ```
   python3 -I scripts/diff_by_value.py ~/Downloads/Nubank_YYYY-MM-DD.csv organizze.json
   ```
   (O script ainda aceita o `bank.json` antigo do Open Finance no lugar do CSV.)
3. A saída te dá 4 blocos:
   - **Despesas no banco sem par no Organizze** → esses são os candidatos reais a lançar.
   - **Despesas no Organizze sem par no banco** → geralmente não é problema (lançamento manual
     feito antes da compra aparecer, item fora do período do CSV), mas vale olhar.
   - **Créditos/estornos** → mesma lógica, para receitas e estornos. O "Pagamento recebido" da
     fatura anterior sempre aparece aqui — trate pela seção 4 do SKILL.md.
4. **Sempre passe a lista de "candidatos a lançar" pelos filtros da seção 4 do SKILL.md**
   antes de mostrar para o usuário, e confira valores repetidos (o script escolhe a primeira
   linha com aquele valor, que pode não ser a que está faltando de verdade).

Os scripts não lançam nada — só leem e comparam. Lançar é sempre um passo separado, com
`organizze:mass_create_transactions`, e só depois de o usuário confirmar a lista.
