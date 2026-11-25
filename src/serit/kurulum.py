"""`serit kur` ve `serit saglik`: kancaları etkinleştirir, git düzenini değiştirmeden denetler."""
import sys
from importlib import resources
from pathlib import Path

from .ayar import ayar_oku
from .gitci import Hata, git, git_dizini, kok, ortak_git_dizini

KANCALAR = ('pre-commit', 'pre-merge-commit', 'pre-push')
ISARET = 'serit-kanca'


def kanca_sablonu(ad):
    return resources.files('serit').joinpath('kancalar', ad).read_bytes()


def _sh_tirnak(metin):
    return metin.replace("'", "'\\''")


def _kanca_dizini(root):
    deger = git(root, 'config', '--get', 'core.hooksPath', check=False).stdout.strip()
    if not deger:
        return None, ''
    yol = Path(deger)
    return (yol if yol.is_absolute() else root / yol), deger


def _ayni_yol(a, b):
    try:
        return Path(a).resolve() == Path(b).resolve()
    except OSError:
        return False


def kur(repo, zorla=False, python=None):
    """Kancaları `<ortak git dizini>/serit/hooks` altına yazar ve depo yerel ayarlarını yapar.

    Geri almak: `git config --unset core.hooksPath`.
    """
    root = kok(repo)
    ayar = ayar_oku(root)
    hedef = ortak_git_dizini(root) / 'serit' / 'hooks'
    mevcut, ham = _kanca_dizini(root)
    if mevcut is not None and not _ayni_yol(mevcut, hedef) and not zorla:
        raise Hata(f'core.hooksPath zaten "{ham}" gösteriyor; oradaki kancalar çalışmaz hale gelir. '
                   'Bilerek değiştiriyorsan --zorla ver.')
    uyarilar = []
    eski = ortak_git_dizini(root) / 'hooks'
    if mevcut is None and eski.is_dir():
        etkin = sorted(p.name for p in eski.iterdir() if p.is_file() and not p.name.endswith('.sample'))
        if etkin:
            uyarilar.append(f'{eski.as_posix()} içindeki kancalar artık çalışmayacak: {", ".join(etkin)}')
    python = Path(python or sys.executable).as_posix()
    hedef.mkdir(parents=True, exist_ok=True)
    for ad in KANCALAR:
        icerik = kanca_sablonu(ad).replace(b'\r\n', b'\n')
        icerik = icerik.replace(b'@PYTHON@', _sh_tirnak(python).encode('utf-8'))
        dosya = hedef / ad
        dosya.write_bytes(icerik)
        dosya.chmod(0o755)
    git(root, 'config', 'core.hooksPath', hedef.as_posix())
    secenek = f'branch.{ayar.korunan_dal}.mergeoptions'
    onceki = git(root, 'config', '--get', secenek, check=False).stdout.split()
    if '--no-ff' not in onceki:
        git(root, 'config', secenek, ' '.join([*onceki, '--no-ff']))
    git(root, 'config', f'branch.{ayar.korunan_dal}.rebase', 'true')
    return {'kanca_dizini': hedef.as_posix(), 'korunan_dal': ayar.korunan_dal, 'uyarilar': uyarilar}


def saglik(repo, ayar=None):
    """Git düzenini değiştirmeden denetler; her kontrol için bir TAMAM/HATA satırı döndürür."""
    bare = git(repo, 'config', '--bool', '--get', 'core.bare', check=False).stdout.strip() == 'true'
    # Bare iken show-toplevel çalışmaz; verilen yoldan raporla, diskteki ayara dokunma.
    root = Path(repo).resolve() if bare else kok(repo)
    ayar = ayar or ayar_oku(root)
    dal = ayar.korunan_dal
    satirlar = []

    def kontrol(tamam, ad):
        satirlar.append(('TAMAM: ' if tamam else 'HATA: ') + ad)

    def deger(ad):
        return git(root, 'config', '--get', ad, check=False).stdout.strip()

    dizin, _ = _kanca_dizini(root)
    kontrol(dizin is not None, 'core.hooksPath ayarlı (serit kur)')
    for ad in KANCALAR:
        dosya = dizin / ad if dizin is not None else None
        try:
            var = dosya is not None and dosya.is_file() and ISARET.encode() in dosya.read_bytes()
        except OSError:
            var = False
        kontrol(var, f'serit kancası mevcut: {ad}')
    kontrol('--no-ff' in deger(f'branch.{dal}.mergeoptions').split(), f'branch.{dal}.mergeoptions --no-ff içerir')
    kontrol(deger(f'branch.{dal}.rebase') == 'true', f'branch.{dal}.rebase == true')
    kontrol(not (git_dizini(root) / 'MERGE_HEAD').exists(),
            'MERGE_HEAD yok (yarım birleştirme varsa git merge --abort)')
    kontrol(not bare, 'core.bare != true (bulaşma: git --git-dir=.git config core.bare false)')
    return {'tamam': all(s.startswith('TAMAM:') for s in satirlar), 'satirlar': satirlar, 'ayar': ayar}
