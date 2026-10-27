"""Instala o concilia no Linux e no Windows (no macOS use ./instalar.sh).

  python3 instalar.py               # config + atalho ~/concilia + skills no Claude Code
  python3 instalar.py --agendar     # também agenda a conciliação diária (cron / Agendador de Tarefas)
  python3 instalar.py --desagendar  # remove a tarefa diária
"""
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HOME = Path.home()
SO = platform.system()  # Linux | Windows
TAREFA = "concilia-diaria"
RODAR = ROOT / "conciliacao" / "rodar.py"


def ler_env():
    env = {}
    for linha in (ROOT / "config" / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in linha and not linha.lstrip().startswith("#"):
            k, v = linha.split("=", 1)
            env[k.strip()] = v.strip().strip('"')
    return env


def ligar(destino: Path, origem: Path):
    """Atalho de pasta: symlink no Linux, junction no Windows (não precisa de admin)."""
    if Path(os.path.realpath(destino)) == origem:
        return
    if destino.is_symlink():
        destino.unlink()
    elif getattr(destino, "is_junction", lambda: False)():
        os.rmdir(destino)  # remove só a junction, não o conteúdo
    elif destino.exists():
        sys.exit(f"{destino} já existe e não é um atalho do concilia. Remova e rode de novo.")
    if SO == "Windows":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(destino), str(origem)], check=True, capture_output=True)
    else:
        destino.symlink_to(origem, target_is_directory=True)


def crontab(sem_tarefa_mais=None):
    atual = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
    linhas = [l for l in atual.splitlines() if TAREFA not in l] + ([sem_tarefa_mais] if sem_tarefa_mais else [])
    subprocess.run(["crontab", "-"], input="".join(l + "\n" for l in linhas), text=True, check=True)


def agendar(hora: int):
    py = sys.executable
    if SO == "Windows":
        subprocess.run(["schtasks", "/Create", "/F", "/SC", "DAILY", "/ST", f"{hora:02d}:00", "/TN", TAREFA,
                        "/TR", f'"{py}" "{RODAR}"'], check=True)
    else:
        crontab(f'0 {hora} * * * "{py}" "{RODAR}" # {TAREFA}')
    print(f"Conciliação diária agendada para {hora}h. Instale em UM computador só.")


def desagendar():
    if SO == "Windows":
        subprocess.run(["schtasks", "/Delete", "/F", "/TN", TAREFA])
    else:
        crontab()
    print("Tarefa diária removida.")


def main():
    if SO == "Darwin":
        sys.exit("No macOS use ./instalar.sh (ou ./instalar.sh --agendar).")
    if "--desagendar" in sys.argv:
        return desagendar()

    # 1. config/ a partir do exemplo (nunca sobrescreve o seu)
    cfg_dir = ROOT / "config"
    if not cfg_dir.exists():
        shutil.copytree(ROOT / "config.exemplo", cfg_dir)
        (cfg_dir / "env.exemplo").rename(cfg_dir / ".env")
        if SO != "Windows":
            (cfg_dir / ".env").chmod(0o600)
        print("Criei config/. Preencha config/.env (credenciais da Pluggy) e config/contas.md.")
    env = ler_env()

    # 2. atalho fixo: as skills sempre procuram ~/concilia
    ligar(HOME / "concilia", ROOT)

    # 3. skills no Claude Code
    claude_dir = Path(os.path.expanduser(env.get("CLAUDE_CONFIG_DIR") or "~/.claude"))
    (claude_dir / "skills").mkdir(parents=True, exist_ok=True)
    (ROOT / "conciliacao" / "log").mkdir(exist_ok=True)
    for skill in sorted(p for p in (ROOT / "skills").iterdir() if p.is_dir()):
        ligar(claude_dir / "skills" / skill.name, skill)
    print(f"Skills ligadas em {claude_dir / 'skills'}.")

    if "--agendar" in sys.argv:
        agendar(int(env.get("CONCILIA_HORA") or 20))


if __name__ == "__main__":
    main()
