```
 ██████╗ ██████╗ ███╗   ██╗ ██████╗██╗██╗     ██╗ █████╗
██╔════╝██╔═══██╗████╗  ██║██╔════╝██║██║     ██║██╔══██╗
██║     ██║   ██║██╔██╗ ██║██║     ██║██║     ██║███████║
██║     ██║   ██║██║╚██╗██║██║     ██║██║     ██║██╔══██║
╚██████╗╚██████╔╝██║ ╚████║╚██████╗██║███████╗██║██║  ██║
 ╚═════╝ ╚═════╝ ╚═╝  ╚═══╝ ╚═════╝╚═╝╚══════╝╚═╝╚═╝  ╚═╝
```

**Suas finanças conciliadas sozinhas, todo dia.** O Claude Code puxa o extrato real dos seus
bancos pelo Open Finance (Pluggy), confere com o que está no Organizze, lança o que falta e te
entrega um log do que decidiu. Uma vez por mês, gera um relatório para você (ou o casal) sentar e
decidir.

Sem baixar fatura, sem abrir email, sem digitar compra por compra.

---

## O que ele faz

| | |
|---|---|
| 🔌 **Puxa o extrato real** | Cartões e contas via [Meu Pluggy](https://www.pluggy.ai/meu-pluggy), grátis para uso pessoal, com atualização a cada 24h |
| 🧮 **Concilia por valor** | Compara banco x Organizze por valor, não por descrição. Pega fatura aberta, parcelas, compras em dólar (com IOF) e pagamentos de fatura |
| 🏷️ **Categoriza com as suas regras** | Aprende com você: cada categoria confirmada vira regra em `config/categorias.md` |
| 🌙 **Roda sozinho às 20h** | Lança só o que for de alta confiança; o resto vira pendência no log para você decidir |
| 📒 **Log com memória** | Um arquivo por rodada, e cada um termina com o *Estado*: até onde está conciliado e o que está pendente |
| 📊 **Relatório do mês** | Sobra, taxa de poupança, fixos x variáveis, reservas e uma pauta de decisões, publicado como página |

## Como funciona

```
 Bancos ──Open Finance──▶ Pluggy ──pluggy.py──▶ Claude Code ◀──MCP──▶ Organizze
                                                    │
                                    skills: conciliacao · relatorio-financeiro
                                                    │
                                  conciliacao/log/AAAA-MM-DD_HHMM.md  (+ ### Estado)
```

## Requisitos

- **macOS** (a tarefa diária usa o launchd) e **Python 3** (só biblioteca padrão)
- **[Claude Code](https://claude.com/claude-code)** logado na sua conta Claude
- **[Organizze](https://www.organizze.com.br)**, com o **conector do Organizze** ativado na sua
  conta Claude (Configurações → Conectores). É por ele que o Claude lê e lança no Organizze.
- **Conta no [Meu Pluggy](https://meu.pluggy.ai)** e no **[Dashboard da Pluggy](https://dashboard.pluggy.ai)**.
  É grátis para as suas próprias contas (até 5 conexões do mesmo titular).

## Instalação

### 1. Pluggy (≈10 min)

O passo a passo oficial, com vídeo, está em **https://www.pluggy.ai/meu-pluggy**. Em resumo:

1. Crie a conta no **meu.pluggy.ai** e conecte seus bancos.
2. Crie a conta no **dashboard.pluggy.ai** e crie **uma** aplicação.
3. Na aplicação, crie uma conexão escolhendo o conector **"MeuPluggy"**, não o do banco nem o
   Sandbox. Se ele não aparecer, habilite nas configurações de conectores da aplicação. **Faça
   isso uma vez para cada banco.** É o passo que mais gente pula.
4. Anote o **Client ID**, o **Client Secret** (aba Aplicação) e o **Item ID** de cada conexão. O
   plano grátis não lista as conexões pela API, por isso os Item IDs vão no `.env`.

### 2. Projeto

```bash
git clone https://github.com/dinizjp/concilia.git ~/concilia
cd ~/concilia && ./instalar.sh
```

O instalador cria `config/` a partir de `config.exemplo/` e liga as skills no Claude Code.
Depois preencha:

| Arquivo | O quê |
|---|---|
| `config/.env` | Client ID, Client Secret e Item IDs da Pluggy |
| `config/contas.md` | Cartões e contas a conciliar. Rode `python3 pluggy/pluggy.py contas` para ver os ids |
| `config/categorias.md` | Suas regras de categoria (comece pelo exemplo; o Claude completa com você) |
| `config/relatorio.json` | Nomes e classificação das categorias para o relatório |

> Clone fora de `~/Documents` e `~/Desktop`: o macOS bloqueia a tarefa agendada nessas pastas.

### 3. Primeira conciliação (com você olhando)

Abra o Claude Code e peça:

```
concilia tudo
```

Ele mostra o que falta e só lança depois do seu ok. Ao final, grava o log com o *Estado*.

### 4. Ligar a tarefa diária

```bash
./instalar.sh --agendar
```

Roda todo dia às 20h (troque em `CONCILIA_HORA` no `.env`). **Instale em um Mac só**, senão
duas máquinas lançam em dobro. Para desligar:
`launchctl bootout gui/$(id -u)/com.concilia.diaria`.

## Uso no dia a dia

| Peça ao Claude | O que acontece |
|---|---|
| `concilia a fatura` | Fatura aberta do cartão: o que falta, com categoria sugerida |
| `concilia a conta` / `concilia tudo` | Conta corrente, ou todas de `config/contas.md` |
| `me mostra o log de hoje` | Lê só o arquivo de hoje (nunca a pasta inteira) |
| `resolve as pendências` | Passa pelo que a tarefa automática não lançou |
| `Gelo Bom Mix é Mercado` | Corrige o lançamento e a regra; a próxima rodada já sai certa |
| `relatório do mês` | Gera e publica o relatório do mês anterior |

## O que aprendemos sobre os dados da Pluggy

- **Compra internacional:** `amount` vem em dólar; o valor em reais está em
  `amountInAccountCurrency`. O `pluggy.py` já trata.
- **IOF:** vem arredondado (4,00); o banco trunca 3,5% da compra (3,99).
- **Data da fatura:** é `creditCardMetadata.billPostDate`. O `date` é o instante da compra em UTC
  e varia de 0 a 2 dias.
- **Fatura aberta:** são as transações sem `billId`. O `/bills` só devolve faturas fechadas.
- No cartão Nubank, a fatura gerada pela Pluggy bateu centavo por centavo com o CSV oficial.

## Estrutura

```
concilia/
├── instalar.sh              # config, atalho ~/concilia, skills e tarefa diária
├── pluggy/pluggy.py         # leitura da Pluggy (só leitura, só stdlib)
├── skills/
│   ├── conciliacao/         # concilia cartão e conta, modo diário automático
│   └── relatorio-financeiro/ # relatório mensal/trimestral/anual em HTML
├── conciliacao/             # rodar.sh, launchd.plist e log/ (seu, não versionado)
├── config.exemplo/          # modelo do config/
└── config/                  # SEU: credenciais, contas, regras (fica no .gitignore)
```

## Privacidade

- Tudo roda no seu Mac.
- As credenciais ficam em `config/.env`, que está no `.gitignore`.
- O Claude só lança no Organizze o que as suas regras permitem.
- O `pluggy.py` só lê, nunca escreve.

---

Feito por [@dinizjp](https://github.com/dinizjp) com Claude Code. Este repositório é a versão
aberta do sistema que uso nas minhas finanças e é atualizado sempre que o meu melhora.
