---
name: relatorio-financeiro
description: Gera o relatório financeiro da casa (individual ou casal) a partir do Organizze e publica como artefato HTML, mensal (mês anterior), trimestral ou panorama do ano. Use quando o usuário pedir "relatório do mês", "fechamento financeiro", "como foram nossas finanças em setembro", "panorama do ano", "relatório trimestral", "preparar a conversa de finanças", "reunião financeira", ou quiser ver receita x despesa, taxa de poupança, gastos fixos x variáveis e reservas de um período fechado, mesmo sem dizer "relatório" nem citar o Organizze. Não usar para conciliar fatura ou conta (há skill própria) nem para lançar ou editar transações.
---

# Relatório financeiro

Objetivo: um relatório simples e honesto para sentar e decidir. Mostra como a casa está (sobra
dos salários, para onde foi o dinheiro, reservas, compromissos) e termina numa pauta de 3 a 5
decisões. Um artefato por período, sempre no mesmo formato, para comparar mês a mês.

O script faz as contas. Você coleta os dados, confere e escreve o texto (destaques e pauta). Não
some valores à mão: é aí que relatório financeiro erra.

## Arquivos

Configuração do usuário (raiz `~/concilia`). Leia antes de começar:
- `config/relatorio.json`: identidade (título, empresa), classificação das categorias (fixo,
  variável, patrimônio, evento, empresa), receitas (salários, extras, resgates), contas e cartões.
  Quando surgir categoria nova, edite aqui; o script avisa quando encontra uma sem classificação.
- `config/relatorio-notas.md`: particularidades da casa (empresa, categorias que se dividem por
  quem pagou, ids, casos conhecidos). **Siga essas notas acima das regras gerais.**
- `config/objetivos.md`: objetivos e limites combinados (arquivo vivo).

Na skill:
- `scripts/build_report.py`: agrega, calcula e gera o HTML a partir do template.
- `assets/template.html`: layout fixo. Não reescreva por relatório.
- `references/formato-dados.md`: formato exato do JSON de entrada, com exemplo.

Saída: `~/concilia/dados/<slug>.json`, `~/concilia/relatorios/<slug>.html` e
`~/concilia/indice.md` (relatórios publicados, com link).

## 1. Definir o período

Hoje vem de `organizze:get_account_context` (campo `today`). Só relate períodos fechados.

| Pedido | Foco | Slug | Meses de contexto |
|---|---|---|---|
| mensal (padrão) | mês anterior a hoje | `2026-09` | 3 meses antes do foco |
| trimestral | último trimestre fechado | `2026-T3` | trimestre anterior |
| panorama | 1º de janeiro até o mês anterior | `2026-panorama-set` | nenhum além do foco |
| panorama de vários anos | jan do ano X até o mês anterior | `2025-2026-panorama-set` | nenhum; use `comparar` (mesmos meses do ano anterior) |

Se pedirem um mês ainda aberto, avise que os números são parciais e marque isso em `avisos`.

## 2. Coletar no Organizze (chamadas em paralelo)

As bases do Organizze não se misturam. Categorias são "por lançamento" (incluem cartão, pela data
da compra); totais de caixa incluem pagamento de fatura. Este relatório usa **categorias** para
receitas e despesas e **caixa por conta** só para saldos. Não tente bater um com o outro.

1. **Categorias por mês:** `get_categories_evolution(start_date=<1º mês de contexto>,
   end_date=<fim do foco>, periodicity="monthly", only_parent_category=true)`.
   - Copie para `meses_colunas` (lista de `amount_cents` por categoria, alinhada com os meses). É o
     formato da resposta e evita erro de transcrição.
   - Períodos longos (mais de ~9 meses) estouram a resposta e a ferramenta salva em arquivo. Leia
     esse arquivo com Python (`expenses.categories[].evolution[].amount_cents`), um ano por chamada.
   - **Divisão PF/PJ:** se `relatorio.json` tiver `dividir_por_conta`, separe cada uma dessas
     categorias em `<nome> (PF)` e `<nome> (PJ)` conforme quem pagou (contas e cartões da
     empresa em `relatorio-notas.md`). A soma das duas tem que bater com a original, mês a mês.
2. **Receitas extras em detalhe:** `list_transactions(category_id=<Outras receitas>,
   start_date, end_date, order_by="amount_desc")`, e o mesmo para as outras categorias de receita
   extra que tiveram valor. Liste os itens ≥ R$ 200; o script completa a diferença. Classifique a
   `natureza`: presente/evento, reembolso, rendimento, venda, trabalho extra, outro ou **resgate
   de investimento**.
   - **Resgate não é receita.** É poupança voltando. A categoria de resgate do config vira
     `receita_resgate` e abate do guardado (`aporte_liquido = patrimônio − resgates`). Os itens com
     `natureza` começando por "resgate" vão para a tabela de resgates.
   - Resgate lançado em outra categoria: no JSON, mova o valor daquele mês para a coluna de
     resgate. O total de receitas não muda e a conferência continua batendo. Rendimento (juros)
     continua sendo receita extra.
   - Reembolso de algo já lançado como despesa merece nota em `avisos`, porque a despesa aparece cheia.
3. **Saldos:** para cada conta em `config.contas`, rode
   `transactions_list_results(account_id, start_date=<início do foco>, end_date=<fim do foco>)`:
   `inicio = previous_balance_cents`, `fim = balance_cents`. Pule as contas com 0 nos dois.
4. **Patrimônio e faturas:** `get_balances` → `patrimonio` (contas, faturas_abertas, liquido) e
   `faturas_abertas` por cartão (valor positivo, em centavos).
5. **Compromissos:**
   - `find_installments(end_date=<hoje>)`: `restantes = installments_total − nº de meses em
     months até o fim do foco`. Mantenha só `restantes > 0` e `kind = "parcelado"`; ignore
     "possível parcelamento". A mesma compra pode vir em dois grupos com centavos diferentes: some
     os meses dos dois. Itens de cartão da empresa vão para a observação da empresa.
   - `find_subscriptions()`: só serviços canceláveis e ativos. Deixe de fora aluguel, consórcio,
     plano, transferências e salário, que já estão nos fixos.
   - `get_upcoming_bills(days=30)`: a lista traz compras de cartão como "atrasado há N dias". Isso
     é artefato da ferramenta: compra de cartão não se paga sozinha, o que se paga é a fatura.
     Ignore esses itens. Para `contas_a_vencer_30d`, some com Python só as despesas de **contas**
     com `days_until_due >= 0`.
   - Se algo vier ambíguo, prefira listar menos e avisar a inventar.
6. **Empresa** (se houver em `identidade.empresa_nome`): saldo da conta PJ (passo 3) e fatura do
   cartão PJ (passo 4). Os custos saem sozinhos das categorias do grupo `empresa`.
7. **Conferência (2ª checagem, sempre):** `get_categories_report(start_date, end_date)` do foco
   (um por ano civil se o período for longo). Ponha em `conferencia: {despesas_total, receitas_total}`
   (centavos). O script compara com a soma das colunas e avisa se divergir mais de R$ 1. Não
   publique com divergência sem explicar.

## 3. Montar, rodar, conferir

1. Escreva `~/concilia/dados/<slug>.json` no formato de `references/formato-dados.md`, com
   `destaques` e `pauta` vazios.
2. Rode
   `python3 <skill>/scripts/build_report.py ~/concilia/dados/<slug>.json ~/concilia/relatorios/<slug>.html`.
   O terminal mostra os totais por grupo, a taxa de poupança, as maiores variações, a conferência
   e os avisos.
   - Conceitos: **renda líquida = salários − empresa** e **sobra = renda líquida − (fixos +
     variáveis)**. A taxa de poupança é sobre a renda líquida. Sem empresa, a renda líquida é
     igual aos salários.
3. Confira os **dados** (Checagens A e B).
4. Escreva `destaques` e `pauta` no JSON e rode de novo.
5. Confira o **texto** e o **HTML** (C e D). Só então publique.

## Checagens (precisão vem antes de tudo)

O script sai com código 2 e imprime `NÃO PUBLICAR` quando uma checagem automática falha. Não
publique nesse estado.

**A. Coleta**
- PF + PJ de cada categoria dividida somam exatamente a original, mês a mês. Confira com Python.
- Os totais mensais batem com `get_categories_evolution`.
- Cada receita extra foi achada em `list_transactions` (não de memória) e a natureza está certa.

**B. Saída do script (bloco `CHECAGENS`)**
- A soma das categorias bate com o `get_categories_report`.
- Todas as categorias estão classificadas, e as divididas vieram como PF/PJ.
- Os meses do foco estão completos e em sequência.
- Extras e resgates detalhados não passam do total das categorias.
- Salários dentro do padrão (mês < 60% da mediana falha). Pergunte e, se for real, registre em
  `confirmados.salario_baixo`.
- `PICOS` (categoria num mês > 3× a mediana e > R$ 1.000): abra os lançamentos e explique, ou
  confirme. Pico sem explicação costuma ser lançamento duplicado ou mal categorizado.

**C. Texto**
- O bloco `TEXTO` lista cada valor em R$ ou % dos destaques e da pauta que não bate com nenhum
  número calculado. Para cada `?`, recalcule com Python ou confirme que é conta derivada. Meta:
  zero `?` sem explicação. É rede de segurança, não prova: releia mesmo com zero `?`.
- "Sobra" é renda líquida − consumo (sem extras). "Resultado final" inclui extras e resgates.
  Resgate nunca é chamado de receita.
- Nada de afirmar pendência, atraso ou erro de lançamento sem ter visto o lançamento.

**D. HTML**
- Extraia o `<script>` e rode `node --check`. Abra as duas abas (Relatório e Roteiro da conversa) e
  veja se nada ficou vazio ou quebrado.

## Objetivos

Se `config/objetivos.md` existir, leia antes de escrever o texto. Inclua um destaque com o
andamento de cada objetivo, compare o consumo com os limites combinados e leve para a pauta o
que estiver "a definir" ou fora do ritmo. Quando o usuário contar uma mudança, atualize o
arquivo com a data.

## 4. Destaques e pauta

Use os números que o script imprimiu. Escreva em português, frases curtas, valores em R$.

**Destaques** (3 a 5), do mais importante para o menos:
- Comece pela sobra e pela taxa de poupança contra a referência.
- Depois os 2 ou 3 maiores movimentos de categoria, com o motivo quando os lançamentos mostram.
- Patrimônio ou reserva subindo é sinal bom; diga isso. Grupo `evento` é projeto à parte, não
  "gasto alto".
- Receitas extras grandes: de onde vieram e que não se repetem. Resgates à parte.

**Pauta** (3 a 5 itens no formato `{tema, pergunta, dado}`): cada item é uma decisão concreta
("Definimos teto de R$ 1.500 para Rolês em outubro?"), nunca genérica nem apontando culpa. Sem
meta de poupança definida, um item propõe uma usando a `meta_sugerida` do script. No trimestral e
no panorama, inclua um item olhando para frente.

Tom: neutro e direto. Não amenize déficit nem dramatize. Não atribua gastos a uma pessoa, a menos
que a categoria seja explicitamente individual.

## 5. Publicar

1. Publique `~/concilia/relatorios/<slug>.html` com a ferramenta Artifact (`icon: "chart"`,
   `description` de uma frase com o período e o resultado). Para corrigir um relatório publicado,
   republique o mesmo arquivo (mantém o link). Link direto para a segunda aba: `<link>#roteiro`.
2. Acrescente em `~/concilia/indice.md`:
   `- <slug> · <título> · <link> · sobra <R$> (<taxa>%)`.
3. Resposta ao usuário: link, 3 linhas de resumo (sobra, maior mudança, reserva) e os avisos de
   dados a resolver no Organizze.

Sem a ferramenta Artifact, entregue o HTML como arquivo e diga onde está.

## Modo automático (e-mail mensal)

`conciliacao/rodar-relatorio.sh` (launchd, dias 1 a 3) chama esta skill sem ninguém olhando, só
depois de a conciliação fechar o mês. O próprio script manda o e-mail com o resumo e o link. Nesse modo:

1. Período mensal do slug informado. Siga as seções 1 a 5 normalmente, com todas as checagens.
2. Não há a quem perguntar:
   - salário baixo ou pico sem explicação nos lançamentos vão para `avisos`, sem `confirmados`;
   - categoria nova sem classificação também vai para `avisos`. Não edite `relatorio.json` sozinho.
3. Se o script sair com `NÃO PUBLICAR`, pare. Escreva o motivo em uma linha em
   `~/concilia/relatorios/<slug>.erro` e não publique.
4. Publique o artefato e escreva a linha no `indice.md` com o link, como na seção 5. O e-mail usa
   esse link. Sem link, ele manda o HTML em anexo.
5. Não mande e-mail você mesmo: o script cuida disso.
