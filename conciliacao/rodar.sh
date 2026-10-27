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
