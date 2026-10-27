#!/bin/zsh
# Instala o concilia neste Mac: config/, atalho ~/concilia, skills no Claude Code e (opcional) a tarefa diária.
#   ./instalar.sh            # config + skills
#   ./instalar.sh --agendar  # também agenda a conciliação diária (launchd)
set -e
ROOT="${0:A:h}"
LABEL="com.concilia.diaria"

if [[ "$ROOT" == "$HOME/Documents"* || "$ROOT" == "$HOME/Desktop"* ]]; then
  echo "Mova a pasta para fora de Documents/Desktop: o macOS bloqueia a tarefa agendada ali."; exit 1
fi

# 1. config/ a partir do exemplo (nunca sobrescreve o seu)
if [[ ! -d "$ROOT/config" ]]; then
  cp -R "$ROOT/config.exemplo" "$ROOT/config" && mv "$ROOT/config/env.exemplo" "$ROOT/config/.env"
  chmod 600 "$ROOT/config/.env"
  echo "Criei config/. Preencha config/.env (credenciais da Pluggy) e config/contas.md."
fi
set -a; source "$ROOT/config/.env"; set +a
CFG="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"; CFG="${CFG/#\~/$HOME}"

# 2. atalho fixo: as skills sempre procuram ~/concilia
[[ "$ROOT" != "$HOME/concilia" ]] && ln -sfn "$ROOT" "$HOME/concilia"

# 3. skills no Claude Code
mkdir -p "$CFG/skills" "$ROOT/conciliacao/log"
for s in "$ROOT"/skills/*(/); do ln -sfn "$s" "$CFG/skills/${s:t}"; done
echo "Skills ligadas em $CFG/skills."

# 4. tarefa diária
if [[ "$1" == "--agendar" ]]; then
  PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
  sed -e "s#__ROOT__#$ROOT#g" -e "s#__HORA__#${CONCILIA_HORA:-20}#g" "$ROOT/conciliacao/launchd.plist" > "$PLIST"
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$PLIST"
  echo "Conciliação diária agendada para ${CONCILIA_HORA:-20}h. Instale em um Mac só."
fi
