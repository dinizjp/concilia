#!/bin/zsh
# Conciliação diária: chamada pelo launchd (instalado pelo instalar.sh).
# Resultado legível: log/AAAA-MM-DD_HHMM.md. Saída bruta do Claude: execucoes.log.
ROOT="${0:A:h:h}"
set -a; source "$ROOT/config/.env"; set +a
export CLAUDE_CONFIG_DIR="${CLAUDE_CONFIG_DIR/#\~/$HOME}"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
cd "$ROOT" || exit 1

{
  echo "=== $(date '+%Y-%m-%d %H:%M') ==="
  claude -p "Rode a skill conciliacao em modo diário automático, para todas as contas de ~/concilia/config/contas.md. Use caminhos absolutos, sem cd. Termine escrevendo o log num arquivo novo em ~/concilia/conciliacao/log/ (AAAA-MM-DD_HHMM.md)." \
    --allowedTools "Skill" "ToolSearch" "Read" "Write" "Edit" "Bash(python3 *)" "Bash(ls *)" "mcp__claude_ai_organizze"
  echo
} >> conciliacao/execucoes.log 2>&1

# Aviso no Mac quando sobrar pendência (o lembrete do SessionStart só aparece ao abrir o Claude).
# ponytail: display alert nativo em vez de notificação, porque notificação do osascript não aceita clique.
P=$(sed -n 's/^- pendencias_abertas: *//p' "$(ls -1 conciliacao/log/*.md | tail -1)")
if [[ -n "$P" && "$P" != nenhum* ]]; then
  afplay /System/Library/Sounds/Glass.aiff &
  R=$(osascript -e "display alert \"Conciliação: ficaram pendências\" message \"${P//\"/}\" buttons {\"Depois\", \"Conciliar agora\"} default button 2 giving up after 7200" 2>/dev/null)
  CMD="cd '$ROOT' && CLAUDE_CONFIG_DIR='$CLAUDE_CONFIG_DIR' claude concilia"
  if [[ "$R" == *"Conciliar agora"* ]]; then
    if [[ -d /Applications/Ghostty.app ]]; then open -na Ghostty --args -e zsh -ic "$CMD"
    else osascript -e "tell app \"Terminal\" to do script \"$CMD\"" -e 'tell app "Terminal" to activate'; fi
  fi
fi
