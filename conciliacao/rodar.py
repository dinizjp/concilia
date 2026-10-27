"""Conciliação diária no Linux e no Windows: chamada pela tarefa agendada (instalar.py --agendar).
No macOS quem roda é o rodar.sh (zsh, via launchd).

Resultado legível: log/AAAA-MM-DD_HHMM.md (escrito pelo Claude). Saída bruta: execucoes.log.
"""
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROMPT = ("Rode a skill conciliacao em modo diário automático, para todas as contas de "
          "~/concilia/config/contas.md. Use caminhos absolutos, sem cd. Termine escrevendo o log num "
          "arquivo novo em ~/concilia/conciliacao/log/ (AAAA-MM-DD_HHMM.md).")
FERRAMENTAS = ["Skill", "ToolSearch", "Read", "Write", "Edit", "Bash(python3 *)", "Bash(python *)",
               "Bash(py *)", "Bash(ls *)", "Bash(dir *)", "mcp__claude_ai_organizze"]

for linha in (ROOT / "config" / ".env").read_text(encoding="utf-8").splitlines():
    if "=" in linha and not linha.lstrip().startswith("#"):
        k, v = linha.split("=", 1)
        os.environ[k.strip()] = os.path.expanduser(v.strip().strip('"'))

# tarefas agendadas rodam com PATH mínimo: inclui os lugares comuns do claude
extra = [Path.home() / ".local" / "bin", Path("/opt/homebrew/bin"), Path("/usr/local/bin"),
         Path(os.environ.get("APPDATA", "")) / "npm"]
os.environ["PATH"] = os.pathsep.join([*map(str, extra), os.environ.get("PATH", "")])
claude = shutil.which("claude") or "claude"

with open(ROOT / "conciliacao" / "execucoes.log", "a", encoding="utf-8") as log:
    log.write(f"=== {datetime.now():%Y-%m-%d %H:%M} ===\n")
    log.flush()
    subprocess.run([claude, "-p", PROMPT, "--allowedTools", *FERRAMENTAS],
                   cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    log.write("\n")
