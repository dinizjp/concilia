---
name: conciliacao
description: Concilia cartões de crédito e contas correntes com o Organizze. Puxa o extrato real pela Pluggy (Meu Pluggy, script local), compara por valor com o que já está lançado, sugere categorias e lança via Organizze MCP. Também tem um modo diário automático, uma tarefa agendada que lança só o que for de alta confiança e registra log. Use quando o usuário pedir para "conciliar a fatura", "puxar a fatura", "conciliar a conta", "conciliar tudo", "conferir o que falta lançar no Organizze", "bater o extrato com o Organizze", "puxar a fatura do email", ver o log da conciliação ou mencionar reconciliação bancária ou de cartão, mesmo sem citar os conectores. Não usar para relatórios de período (há skill própria).
---

# Conciliação banco x Organizze

Compara o extrato real (Pluggy) com o que está lançado no Organizze e aponta só o que falta lançar.

## Antes de tudo: leia a configuração do usuário

A raiz do projeto é `~/concilia`. Leia sempre:

- `~/concilia/config/contas.md`: contas e cartões conciliados, ids no Organizze, `pluggy_account_id`,
  ciclo do cartão e plano B.
- `~/concilia/config/categorias.md`: regras de categoria confirmadas pelo usuário, incluindo o que
  **nunca** lançar sozinho.
- `~/concilia/config/regras.md`: casos especiais desta casa (assinaturas com IOF, agrupamentos
  manuais etc.).

Se `config/` não existir, o projeto não foi instalado: peça para rodar `~/concilia/instalar.sh`.

**Regra de ouro (modo conversa): mostre a lista do que falta ANTES de lançar qualquer coisa.** Nunca
use `mass_create_transactions` sem aprovação explícita nesta conversa, mesmo que o padrão pareça
óbvio. A exceção é o modo diário automático (no fim), que só lança o que for de alta confiança e
registra tudo no log.

## Pluggy: comandos

```
P=~/concilia/pluggy/pluggy.py
python3 -I $P contas                          # conexões, contas, saldos, horário da última atualização
python3 -I $P csv <accountId> > <tmp>/f.csv   # fatura ABERTA de um cartão (formato date,title,amount)
python3 -I $P faturas <accountId>             # faturas FECHADAS (id, fechamento, vencimento, total)
python3 -I $P csv <accountId> <billId>        # uma fatura fechada
python3 -I $P transacoes <accountId> <de>     # extrato de conta (JSON; valor negativo = saída)
```

O que saber sobre os dados da Pluggy:
- **Ela atualiza 1x a cada 24h.** Compras de hoje podem não estar lá. Quando o total não bater,
  mostre o horário da última atualização (`contas` → `atualizado`, em UTC).
- **Compra internacional:** a API manda `amount` na moeda original (USD). O script já usa
  `amountInAccountCurrency` (R$). Se mexer no script, não quebre isso.
- **IOF arredondado:** a Pluggy pode mandar 4,00 onde o banco cobrou 3,99. O banco **trunca**
  3,5% da compra: `IOF = floor(compra × 0,035 × 100) / 100`. Use esse valor no Organizze.
- **Datas:** no cartão, a data do app/fatura é `creditCardMetadata.billPostDate` (o script já
  usa). O `date` cru é o instante da compra em UTC e varia de 0 a 2 dias.
- O plano grátis não lista as conexões pela API: os itemIds ficam em `PLUGGY_ITEM_IDS` no
  `config/.env`. Banco novo = itemId novo copiado do Dashboard da Pluggy.

## Cartão de crédito

### 1. Extrato
Fatura aberta: `pluggy.py csv <accountId>`. Fechada: `faturas` para achar o `billId`, depois
`csv <accountId> <billId>`. A saída tem o mesmo formato do CSV que o Nubank manda por email
(incluindo "Pagamento recebido" e "Nome - Parcela N/M").

**Plano B (cartões Nubank, se a Pluggy falhar):** o usuário pede o CSV da fatura no app e ele
chega por email (`from:nubank subject:"Extrato da fatura" has:attachment newer_than:7d`). Baixe
com `Gmail:get_message(messageId, messageFormat="RAW")`. O resultado é grande e é salvo em
arquivo; depois rode:
`python3 -I <skill>/scripts/extract_email_attachment.py <arquivo_salvo.txt> ~/Downloads`. A
primeira chamada RAW às vezes devolve "Internal error"; tente de novo uma vez. O nome
`Nubank_AAAA-MM-DD.csv` traz o **vencimento**.

Formato: `date,title,amount`, valores pt-BR entre aspas (`"1.234,56"`), créditos com espaço
depois do sinal (`"- 3,99"`). Despesa é positiva; crédito e pagamento são negativos.

### 2. Fatura do Organizze
`organizze:get_credit_card_invoice(credit_card="<nome>", month=M, year=A)`, com o mês e o ano do
**vencimento**. A fatura aberta vence no mês seguinte ao último fechamento (ciclo em
`config/contas.md`); para fatura fechada, use o `dueDate` de `pluggy.py faturas`.

Guarde `invoice.id`, `starting_date`, `closing_date`, `amount`, `transactions` e
`navigation.previous_invoice_id`. **Sanity check:** a soma de `transactions` tem que bater com
`invoice.amount`. Se não bater, pare e avise.

### 3. Diff por valor (nunca por descrição ou data)
As descrições do banco (`Ifd*Cd Pizzas`, `Mp *Buser`) quase nunca batem com as do usuário no
Organizze, e as datas variam de 0 a 2 dias. **O único critério confiável é o valor.** Use
`python3 -I <skill>/scripts/diff_by_value.py <fatura.csv> <organizze.json>` (veja
`references/usage.md`). Quando o diff apontar um valor repetido, confira as descrições: o script
pega a primeira linha com aquele valor, que pode não ser a que falta.

### 4. Descarte os falsos positivos antes de reportar
- **"Pagamento recebido"** (negativo grande):
  1. Bate com o total da fatura anterior: é o pagamento dela. Confirme com
     `get_credit_card_invoice(invoice_id=previous_invoice_id)` (`status: paid`, valor em
     `payment_transactions`). Nada a lançar.
  2. Não bate e o valor é "quebrado": quita compras específicas do ciclo pagas de outra conta. Ache
     o subconjunto que soma o valor e não lance essas compras.
  3. Não bate e o valor é redondo: é abatimento parcial. Pergunte de onde veio o dinheiro, lance a
     receita na conta de origem e `register_invoice_payment` parcial. Busca de subconjunto para
     valor redondo grande dá falso positivo.
- **IOF + estorno de IOF:** confira com o IOF truncado. Veja se `config/regras.md` diz como o
  usuário lança a assinatura.
- **Lançamentos agregados:** 2+ linhas no banco podem ser 1 no Organizze, ou o inverso. Confira a
  soma.
- **Diferença de 1 a 5 centavos** entre valores parecidos não é o mesmo lançamento por padrão.
  Pergunte.
- **Parcelas com numeração diferente do banco** podem ser intencionais (`config/regras.md`).
- **Item datado antes de `starting_date`:** se está no extrato da fatura, é desta fatura. O
  Organizze roteia pela data e pode jogar o item na fatura anterior. Depois de lançar, confira e
  mova com `update_transaction(transaction_id, credit_card_invoice_id=<invoice.id>)`.

## Conta corrente

1. Extrato: `pluggy.py transacoes <accountId> <AAAA-MM-01>`. A data é o campo `data`.
2. Organizze: `list_transactions(account_id=<id>, list_mode="all_transactions", start_date, end_date)`.
   Já traz recorrências, pagamentos de fatura e transferências.
3. Diff por valor. Depois confira os agrupamentos manuais (veja `config/regras.md`).
4. Transferência entre contas próprias (`Same person transfer`, "MESMA TIT.") e dinheiro que só
   passa pela conta (entra X e sai X no mesmo dia ou no seguinte) **não são despesa nem receita**.
   Não lance sem perguntar.
5. Feche comparando o saldo do banco (`pluggy.py contas`) com o do Organizze (`list_accounts`) e
   reporte a diferença que sobrar.

## Categorias e lançamento

- Siga `config/categorias.md` primeiro. Para o resto, use `organizze:suggest_categories`. Se a
  confiança vier baixa ou a descrição for ambígua (nome de pessoa, valor redondo demais), **não
  chute**: marque como incerto e pergunte.
- Apresente a lista final (data, descrição, valor, categoria) e o total esperado. Só lance depois
  do sim.
- `mass_create_transactions` com `account="<nome no Organizze>"`. **Bug de centavos:** o servidor
  trunca por float, então mande `amount` com casas extras (`67.7105`).
- Compra parcelada nova vai em `create_transaction` com `times: N` e `amount` = valor **total**
  (parcela × N).
- `update_transaction` só aceita id numérico vindo de `search_transactions`/`list_*` no mesmo turno.
- **Segunda checagem:** releia a fatura ou o saldo e confirme que bate. Feche com **Pendências**
  (id, problema, motivo), ou "nenhuma".
- Quando o usuário confirmar ou corrigir uma categoria, atualize `config/categorias.md`.

## Log e Estado

O log fica em `~/concilia/conciliacao/log/AAAA-MM-DD_HHMM.md`, **um arquivo por rodada**. Nunca leia
a pasta inteira. Para revisar com o usuário, liste com `ls -1` e abra só o período pedido.

Formato:

```
## AAAA-MM-DD HH:MM

### Lançado
| Conta | Data | Banco | Lançado como | Valor | Categoria | Por quê |
|---|---|---|---|---|---|---|

### Pendências (não lancei)
| Conta | Data | Banco | Valor | Motivo / sugestão |
|---|---|---|---|---|

### Saldos
<conta>: banco R$ X / Organizze R$ Y · ...

### Estado
- conciliado_ate: AAAA-MM-DD
- diferencas_conhecidas: ...
- aguardando: ...
- pendencias_abertas: ...
```

**Fechando uma conciliação em conversa:** grave um log da sessão com `conciliado_ate` = hoje.
É assim que a próxima rodada automática sabe onde parou.

## Modo diário automático

`~/concilia/conciliacao/rodar.sh`, agendado pelo `instalar.sh`, chama esta skill sem ninguém
olhando. Nesse modo:

1. **Leia o estado:** o último arquivo de `ls -1 ~/concilia/conciliacao/log/` (a ordem alfabética
   é cronológica). Leia **só o bloco `### Estado`**:
   - `conciliado_ate`: itens sem par até essa data já foram revisados. Não lance e não liste.
   - `diferencas_conhecidas`: só reporte o saldo se a diferença mudar.
   - `aguardando`: confira se já apareceu no banco.
   - `pendencias_abertas`: repita até o usuário resolver.
2. Concilie **todas as contas de `config/contas.md`**, do dia 1º do mês anterior até hoje (cartão:
   fatura aberta).
3. **Lance sozinho só o que for de alta confiança:**
   - regra explícita em `config/categorias.md`;
   - merchant que já aparece no Organizze com a mesma categoria;
   - `suggest_categories` com `confidence ≥ 0.9` e `source: user_edit`.
4. **Não lance** (vira pendência):
   - a lista "nunca lançar sozinho";
   - qualquer receita;
   - PIX para pessoa física fora das regras;
   - valores repetidos ambíguos;
   - compra parcelada nova;
   - ajustes de lançamentos existentes;
   - casos de `config/regras.md` marcados como pendência.
5. **Anti-duplicata:** rode o diff de novo logo antes do `mass_create`. Use `idempotency_key` =
   `diario-<conta>-<AAAA-MM-DD>`.
6. Nunca apague nem edite lançamentos existentes, só crie.
7. **Escreva um log novo** (Write em arquivo novo). O bloco Estado é sempre obrigatório.
   `conciliado_ate` só avança para hoje se não sobrar pendência; se sobrar, mantenha a data e
   carregue as pendências. Tire de `aguardando` o que já apareceu.
