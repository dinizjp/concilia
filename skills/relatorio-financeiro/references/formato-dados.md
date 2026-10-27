# Formato do JSON de entrada (`dados/<slug>.json`)

Todos os valores em **centavos inteiros** (use `amount_cents` / `*_cents` do Organizze).
Datas de mês como `AAAA-MM`.

```json
{
  "tipo": "mensal",
  "titulo": "Setembro 2026",
  "gerado_em": "14/10/2026",
  "foco": ["2026-09"],
  "meses_colunas": {
    "meses": ["2026-06", "2026-07", "2026-08", "2026-09"],
    "despesas": { "Aluguel": [162100, 162100, 162100, 162100], "Viagem": [154904, 18980, 120789, 223370] },
    "receitas": { "Salário": [1200000, 1200000, 1200000, 1200000] }
  },
  "meses": {
    "2026-06": { "despesas": { "Aluguel": 162100, "Alimentação": 392338 }, "receitas": { "Salário": 1200000 } },
    "2026-07": { "despesas": { "...": 0 }, "receitas": { "...": 0 } },
    "2026-08": { "despesas": {}, "receitas": {} },
    "2026-09": { "despesas": { "Aluguel": 162100 }, "receitas": { "Salário": 1200000 } }
  },
  "receitas_extras": [
    { "data": "23/09", "descricao": "Presente de aniversário", "conta": "Conta corrente", "valor": 800000, "natureza": "presente/evento" }
  ],
  "saldos": [
    { "conta": "Reserva", "inicio": 3128745, "fim": 3922152 }
  ],
  "patrimonio": { "contas": 5950379, "faturas_abertas": 479280, "liquido": 5471099 },
  "faturas_abertas": [ { "cartao": "Cartão principal", "valor": 447407, "vencimento": "09/11" } ],
  "parcelas": [ { "descricao": "Notebook", "cartao": "Cartão principal", "valor_parcela": 45000, "restantes": 4 } ],
  "assinaturas": [ { "nome": "Spotify", "valor_mensal": 2190 } ],
  "contas_a_vencer_30d": 1200020,
  "empresa": { "saldo_conta": 74732, "fatura_cartao": 27883, "obs": "" },
  "conferencia": { "fonte": "get_categories_report 2026-09", "despesas_total": 1890000, "receitas_total": 1950000 },
  "comparar": { "atual": ["2026-01", "2026-02"], "ref": ["2025-01", "2025-02"] },
  "confirmados": { "salario_baixo": ["2026-06", "2026-07"] },
  "destaques": ["..."],
  "pauta": [ { "tema": "Reserva", "pergunta": "...?", "dado": "..." } ],
  "avisos": ["..."]
}
```

Regras:
- `foco`: lista dos meses do período relatado (1 para mensal, 3 para trimestral, N para panorama).
- Use `meses_colunas` (preferido) OU `meses` (um objeto por mês) — o exemplo mostra os dois só para ilustrar. Ambos cobrem foco + meses de contexto.
  Cada lista em `meses_colunas` tem que ter o mesmo tamanho de `meses`; o script recusa se não tiver. O script usa como referência os meses imediatamente
  anteriores ao foco (mínimo 3 no mensal; mesmo tamanho do foco no trimestral). No panorama
  não inclua contexto: a evolução mês a mês já é a comparação.
- Nomes de categoria exatamente como o Organizze devolve (inclusive espaço final, ex. `"Energia "`).
- `receitas_extras`: itens relevantes do período; o script completa a diferença com "Outras entradas menores".
- No panorama (sem meses de contexto e 6+ meses de foco), o script compara os 3 últimos meses com o resto do ano.
- `patrimonio`/`faturas_abertas`: valores positivos (o Organizze devolve fatura negativa; inverta).
- Campos opcionais podem ser omitidos; a seção some do relatório.
- `conferencia`: totais de despesas e receitas do `get_categories_report` do mesmo período do foco. Obrigatório.
- `comparar` (opcional): força a comparação entre dois conjuntos de meses. Use no panorama de vários anos para comparar o ano atual com os mesmos meses do ano anterior.
- Categorias de `config.dividir_por_conta` entram já separadas em `<nome> (PF)` e `<nome> (PJ)`.
- `receitas_extras`: itens com `natureza` começando por "resgate" (ex.: "resgate de investimento") vão para a tabela de resgates e são conferidos contra a categoria de receita Investimentos (`grupos_receita.resgate`). Resgate lançado em outra categoria: mova o valor do mês para a coluna Investimentos.
- `confirmados` (opcional): fatos já confirmados com o usuário que, sem isso, fariam uma checagem falhar. Hoje: `salario_baixo` (meses com salário < 60% da mediana que são reais).
