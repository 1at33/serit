"""Testler için geçici git deposu yardımcıları."""
import os
import subprocess
import sys

from serit import kurulum


def g(repo, *args):
    return subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True,
                          encoding='utf-8', check=True).stdout


def git_sonuc(repo, *args, env=None, input=None):
    return subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True,
                          encoding='utf-8', env=env, input=input, check=False)


def depo_kur(tmp_path, ayar=None, ad='depo'):
    """Çıplak uzak depo + `main` üzerinde tek commit'li çalışma deposu; serit kurulu."""
    uzak = tmp_path / f'{ad}-uzak.git'
    g(tmp_path, 'init', '-q', '--bare', str(uzak))
    r = tmp_path / ad
    r.mkdir()
    g(r, 'init', '-q', '-b', 'main')
    g(r, 'config', 'core.autocrlf', 'false')
    (r / 'a.md').write_bytes(b'a\n')
    g(r, 'add', 'a.md')
    if ayar is not None:
        (r / '.serit.toml').write_text(ayar, encoding='utf-8')
        g(r, 'add', '.serit.toml')
    g(r, 'commit', '-qm', 'taban')
    g(r, 'remote', 'add', 'origin', str(uzak))
    g(r, 'push', '-q', '-u', 'origin', 'main')
    kurulum.kur(r)
    return r


def commit(repo, mesaj, yazimlar):
    for yol, icerik in yazimlar.items():
        dosya = repo / yol
        dosya.parent.mkdir(parents=True, exist_ok=True)
        dosya.write_bytes(icerik)
        g(repo, 'add', yol)
    g(repo, 'commit', '-qm', mesaj)


def kanca_kos(repo, ad, girdi='', env=None):
    """Kancanın Python gövdesini ayrı süreçte koşturur (kabuk sarmalayıcısı olmadan)."""
    return subprocess.run([sys.executable, '-m', 'serit', 'kanca', ad], cwd=repo, input=girdi,
                          capture_output=True, text=True, encoding='utf-8',
                          env=env if env is not None else dict(os.environ), check=False)
