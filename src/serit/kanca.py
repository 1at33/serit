"""Git kancalarının gövdesi. `kancalar/` altındaki kabuk dosyaları yalnız `python -m serit kanca <ad>` çağırır."""
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from .ayar import ayar_oku
from .gitci import IZIN_DEGISKENI, Hata, git, kok, sirsiz_ortam
from .kaydet import aktif_dal
from .kurulum import saglik

KACIS_DEGISKENI = 'SERIT_PUSH_TESTSIZ'
ATLANDI = 'push kapısı: izlenen yol değişmedi, push komutu atlandı'


def _yaz(metin):
    print(metin, file=sys.stderr)


def _korunan_dalda_mi(repo):
    """(korunan dalda mı, ayar). Dal ya da ayar okunamazsa güvenli tarafta kalır: Hata yükselir."""
    root = kok(repo)
    ayar = ayar_oku(root)
    return aktif_dal(root) == ayar.korunan_dal, ayar


def pre_commit(repo='.'):
    if os.environ.get(IZIN_DEGISKENI) == '1':
        return 0
    try:
        korunan, ayar = _korunan_dalda_mi(repo)
    except Hata as exc:
        _yaz(f'DURDU: serit kancası dalı ya da ayarı okuyamadı: {exc}')
        return 1
    if not korunan:
        return 0
    _yaz(f'''DURDU: bu depoda `{ayar.korunan_dal}` dalına commit yalnız `serit kaydet` ile yapılır (aynı depoya birden çok oturum yazıyor).
  serit durum
  serit kaydet -m "tür(kapsam): özet" --oturum <oturum> -- <yalnız kendi dosyaların>
  Tür: {' '.join(ayar.turler)}.
  Şerit dalında ({', '.join(o + '<ad>' for o in ayar.serit_onekleri) or 'başka bir dal'}) commit serbesttir.
  git add -A, git add . ve git commit -a kullanma.''')
    return 1


def pre_merge_commit(repo='.'):
    if os.environ.get(IZIN_DEGISKENI) == '1':
        return 0
    try:
        korunan, ayar = _korunan_dalda_mi(repo)
    except Hata as exc:
        _yaz(f'DURDU: serit kancası dalı ya da ayarı okuyamadı: {exc}')
        return 1
    if not korunan:
        return 0
    _yaz(f'''DURDU: `{ayar.korunan_dal}` dalına birleştirme yalnız `serit birlestir <dal> -m "tür(kapsam): özet" --oturum <oturum>` ile.
ŞİMDİ `git merge --abort` çalıştır: git birleştirmeyi yarım bıraktı; böyle kalırsa diğer oturumların commit'i durur.''')
    return 1


def _sifir(sha):
    return not sha or set(sha) == {'0'}


def tam_kapi_gerekli(root, yerel, uzak, yollar):
    """Push komutu koşmalı mı? Yeni ref, çözülemeyen uzak commit ya da diff hatası: evet (fail-closed)."""
    if not yollar or _sifir(uzak) or uzak.startswith('-'):
        return True
    if git(root, 'cat-file', '-e', f'{uzak}^{{commit}}', check=False).returncode:
        return True
    r = git(root, '-c', 'diff.renames=false', 'diff', '--no-renames', '--name-only', '-z',
            f'{uzak}..{yerel}', check=False)
    if r.returncode:
        return True
    return any(y.startswith(o) for y in r.stdout.split('\0') if y for o in yollar)


def _guvenli_ac(arsiv, hedef):
    with tarfile.open(arsiv) as tar:
        if hasattr(tarfile, 'data_filter'):
            tar.extractall(hedef, filter='data')
        else:  # pragma: no cover - süzgeçsiz eski 3.11 yamaları
            for uye in tar.getmembers():
                yol = (Path(hedef) / uye.name).resolve()
                if (not yol.is_relative_to(Path(hedef).resolve()) or uye.issym() or uye.islnk()
                        or not (uye.isfile() or uye.isdir())):
                    raise Hata(f'arşivde güvensiz girdi: {uye.name}')
            tar.extractall(hedef)


def push_komutunu_kos(root, sha, ayar):
    """Push edilen commit'in ağacını geçici dizine açar, push_komutu'nu orada çalıştırır. (tamam, çıktı)."""
    tmp = Path(tempfile.mkdtemp(prefix='serit-push-'))
    try:
        arsiv, agac = tmp / 'arsiv.tar', tmp / 'agac'
        agac.mkdir()
        r = git(root, 'archive', '--format=tar', '-o', str(arsiv), sha, check=False)
        if r.returncode:
            return False, f'git archive başarısız: {(r.stderr or r.stdout).strip()}'
        try:
            _guvenli_ac(arsiv, agac)
        except (tarfile.TarError, OSError, Hata) as exc:
            return False, f'arşiv açılamadı: {exc}'
        komut = [sys.executable if p == '{python}' else p for p in ayar.push_komutu]
        try:
            s = subprocess.run(komut, cwd=agac, env=sirsiz_ortam(ayar.ortam_izin), stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace',
                               timeout=ayar.push_zaman_asimi, check=False)
        except subprocess.TimeoutExpired:
            return False, f'push komutu zaman aşımı ({ayar.push_zaman_asimi} sn)'
        except OSError as exc:
            return False, f'push komutu başlatılamadı: {exc}'
        return s.returncode == 0, s.stdout
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _reddet(cikti=''):
    satirlar = cikti.strip().splitlines()
    if satirlar:
        _yaz('\n'.join(satirlar[-15:]))
    _yaz(f"DURDU: push kapısı başarısız; düzelt. Acil kaçış: {KACIS_DEGISKENI}='gerekçe' git push "
         '(gerekçe stderr\'e yazılır)')
    return 1


def pre_push(repo='.', satirlar=None):
    kacis = os.environ.get(KACIS_DEGISKENI, '').strip()
    if kacis:
        _yaz(f'UYARI: push kapısı atlandı; gerekçe: {kacis}')
        return 0
    try:
        root = kok(repo)
        ayar = ayar_oku(root)
    except Hata as exc:
        return _reddet(str(exc))
    gorulen = []
    for satir in (sys.stdin if satirlar is None else satirlar):
        parca = satir.split()
        if len(parca) < 4 or _sifir(parca[1]):
            continue  # silme (SHA-1 ve SHA-256) test edilmez
        if parca[1] not in [g for g, _ in gorulen]:
            gorulen.append((parca[1], parca[3]))
    if not gorulen:
        return 0
    for yerel, uzak in gorulen:
        if not ayar.push_komutu:
            continue
        if not tam_kapi_gerekli(root, yerel, uzak, ayar.push_yollari):
            _yaz(ATLANDI)
            continue
        tamam, cikti = push_komutunu_kos(root, yerel, ayar)
        if not tamam:
            return _reddet(cikti)
    try:
        sonuc = saglik(root, ayar)
    except Hata as exc:
        return _reddet(str(exc))
    if not sonuc['tamam']:
        return _reddet('\n'.join(sonuc['satirlar']))
    return 0


KANCA_ISLEVLERI = {'pre-commit': pre_commit, 'pre-merge-commit': pre_merge_commit, 'pre-push': pre_push}
