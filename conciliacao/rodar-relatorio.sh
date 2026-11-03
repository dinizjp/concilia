#!/bin/zsh
# Relatório mensal por e-mail: chamado pelo launchd nos dias 1, 2 e 3, depois da conciliação diária.
# Sai assim que a conciliação fechar o mês anterior (conciliado_ate >= último dia do mês). No dia 3
# sai de qualquer jeito, com aviso de que o fim do mês pode mudar. Uma vez enviado, não repete.
ROOT="${0:A:h:h}"
set -a; source "$ROOT/config/.env"; set +a
export CLAUDE_CONFIG_DIR="${CLAUDE_CONFIG_DIR/#\~/$HOME}"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
cd "$ROOT" || exit 1

SLUG=$(date -v1d -v-1m +%Y-%m)
FIM=$(date -v1d -v-1d +%Y-%m-%d)
DIA=$(date +%-d)
LOG=conciliacao/execucoes.log
[[ -e relatorios/$SLUG.enviado ]] && exit 0

ULTIMO=$(ls -1 conciliacao/log/*.md 2>/dev/null | tail -1)
ATE=$(sed -n 's/^- conciliado_ate: //p' "$ULTIMO" 2>/dev/null | tail -1)
AVISO=""
if [[ "$ATE" < "$FIM" ]]; then
  if (( DIA < 3 )); then
    echo "=== relatório $SLUG $(date '+%Y-%m-%d %H:%M'): conciliação só até ${ATE:-?}, espero o mês fechar ===" >> $LOG
    exit 0
  fi
  AVISO="A conciliação só está fechada até ${ATE:-?} (pendências no log $ULTIMO). Ponha isso em avisos: os números do fim do mês ainda podem mudar."
fi

rm -f relatorios/$SLUG.erro
MARCA=$(mktemp)
{
  echo "=== relatório $SLUG $(date '+%Y-%m-%d %H:%M') ==="
  claude -p "Rode a skill relatorio-financeiro em modo automático (e-mail mensal): relatório mensal de $SLUG. $AVISO Use caminhos absolutos, sem cd." \
    --allowedTools "Skill" "ToolSearch" "Read" "Write" "Edit" "Artifact" "Bash(python3 *)" "Bash(node *)" "Bash(ls *)" "mcp__claude_ai_organizze"
  echo

  if [[ relatorios/$SLUG.html -nt $MARCA && ! -e relatorios/$SLUG.erro ]]; then
    LINK=$(grep "^- $SLUG " indice.md | grep -o 'https://claude.ai/[^ ]*' | tail -1)
    python3 skills/relatorio-financeiro/scripts/email_report.py relatorios/$SLUG.html ${LINK:+--link "$LINK"} \
      && touch relatorios/$SLUG.enviado
  else
    FALHA=1
    if (( DIA >= 3 )); then
      python3 skills/relatorio-financeiro/scripts/email_report.py --aviso "Relatório financeiro de $SLUG não saiu" \
        "A rotina do dia $DIA não conseguiu gerar o relatório. Motivo: $(cat relatorios/$SLUG.erro 2>/dev/null || echo 'ver conciliacao/execucoes.log'). Peça no Claude: relatório do mês."
    fi
  fi
} >> $LOG 2>&1
rm -f $MARCA

# Checagem falhou: avisa no Mac na hora (e-mail só sai sozinho quando tudo passa).
if [[ -n "$FALHA" ]]; then
  M=$(cat relatorios/$SLUG.erro 2>/dev/null || echo "ver conciliacao/execucoes.log")
  R=$(osascript -e "display dialog \"${M//\"/}\" with title \"Relatório $SLUG não saiu\" with icon (POSIX file \"$ROOT/conciliacao/icone.png\") buttons {\"Depois\", \"Resolver agora\"} default button 2 giving up after 7200" 2>/dev/null)
  CMD="cd '$ROOT' && CLAUDE_CONFIG_DIR='$CLAUDE_CONFIG_DIR' claude 'relatório do mês $SLUG'"
  if [[ "$R" == *"Resolver agora"* ]]; then
    if [[ -d /Applications/Ghostty.app ]]; then open -na Ghostty --args -e zsh -ic "$CMD"
    else osascript -e "tell app \"Terminal\" to do script \"$CMD\"" -e 'tell app "Terminal" to activate'; fi
  fi
fi
