"""git çağrıları için ince katman."""
import os
import re
import subprocess
from pathlib import Path

# Korunan dalda pre-commit/pre-merge-commit kancası bu değişken 1 iken geçirir (serit kaydet/birlestir).
IZIN_DEGISKENI = 'SERIT_KAYDET'


class Hata(RuntimeError):
    """İşi durduran, kullanıcıya olduğu gibi gösterilecek hata."""


def git(repo, *args, check=True, izinli=False):
    """`git --literal-pathspecs -C <repo> ...`; izinli=True korunan daldaki kancayı geçirir."""
    env = dict(os.environ, **{IZIN_DEGISKENI: '1'}) if izinli else None
    r = subprocess.run(['git', '--literal-pathspecs', '-C', str(repo), *args], capture_output=True,
                       text=True, encoding='utf-8', env=env, check=False)
    if check and r.returncode:
        raise Hata(f"git {' '.join(args[:2])}: {(r.stderr or r.stdout).strip()}")
    return r


def kok(repo):
    return Path(git(repo, 'rev-parse', '--show-toplevel').stdout.strip()).resolve()


def _mutlak(repo, cikti):
    path = Path(cikti.strip())
    return path if path.is_absolute() else (Path(repo) / path).resolve()


def git_dizini(repo):
    return _mutlak(repo, git(repo, 'rev-parse', '--git-dir').stdout)


def ortak_git_dizini(repo):
    """Worktree'lerin paylaştığı git dizini (kancalar ve ayarlar burada ortak)."""
    return _mutlak(repo, git(repo, 'rev-parse', '--git-common-dir').stdout)


SIR_ADI = re.compile(r'key|token|secret|passw|credential|auth', re.IGNORECASE)


def sirsiz_ortam(izin=(), **ek):
    """Kullanıcı kodunu (push komutu, testler) koşturmak için ortam: GIT_* ve adı sır kuralına uyan
    değişkenler (API anahtarı, token, parola...) çıkarılır; `izin` listesindekiler korunur."""
    izinli = set(izin)
    env = {k: v for k, v in temiz_ortam(**ek).items() if k in izinli or not SIR_ADI.search(k)}
    return env


def temiz_ortam(**ek):
    """GIT_* değişkenleri olmadan ortam.

    Git kancaları GIT_DIR, GIT_INDEX_FILE gibi değişkenlerle çalışır. Kancanın başlattığı testler geçici
    repolarda `git init`/`git config` çalıştırırken bunları miras alırsa komutlar gerçek depoya uygulanır
    (ör. depo `core.bare = true` olur). Alt süreçlere bu yüzden temiz ortam verilir.
    """
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith('GIT_')}
    env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8', **ek)
    return env
