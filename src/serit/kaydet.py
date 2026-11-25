"""Paralel oturumlar için commit düzeni: kaydet, birlestir, durum, push.

Aynı çalışma ağacına birden çok oturum yazar. `kaydet`:
- yalnız verilen yolları commit'ler (`git commit --only`); başka oturumun stage'i yerinde kalır;
- `.`, `-A`, glob, klasör, depo kökü ve depo dışı yolu reddeder;
- başlığı `tür(kapsam): özet` biçiminde ister, `Oturum:` ve `Co-Authored-By:` satırlarını ekler;
- `otomatik_push` türlerini kendiliğinden push'lar, diğerleri birikir (`push_hatirlat` olunca hatırlatır);
- LF iken CRLF'e dönen (ya da tersi) izlenen dosyada durur (`eol_tamam` ile geçilir);
- başka bir git işlemi sürüyorsa (`index.lock`) bekler, yarım birleştirmede (MERGE_HEAD) durur.
"""
import re
import subprocess
import sys
import time
from pathlib import Path

from .ayar import ayar_oku
from .gitci import Hata, git, git_dizini, kok, sirsiz_ortam
from .kurulum import saglik

BASLIK = re.compile(r'^(?P<tur>[a-z][a-z0-9-]*)(\([^)]+\))?: \S.{2,}$')
BEKLE = 60
TEST_ZAMAN_ASIMI = 300
GENIS = ('.', '-A', '--all', '*', ':/')


def yollari_denetle(repo, yollar):
    """Depo içi, köke göre göreli yol listesi; geniş seçimleri reddeder."""
    if not yollar:
        raise Hata('En az bir yol ver: serit kaydet -m "..." -- <dosyalar>. Tüm ağacı commit\'lemek yasak.')
    root = kok(repo)
    out = []
    for yol in yollar:
        if any(c in yol for c in '*?['):
            raise Hata('Glob yolu verilemez; `git status --porcelain -- <klasör>` ile dosyaları tek tek ver.')
        if yol in GENIS:
            raise Hata(f'"{yol}" geniş seçim; yalnız kendi dosyalarını tek tek ver.')
        tam = (Path(repo) / yol).resolve() if not Path(yol).is_absolute() else Path(yol).resolve()
        if tam == root:
            raise Hata('Depo kökü verilemez; yalnız kendi dosyalarını ver.')
        if not tam.is_relative_to(root):
            raise Hata(f'Depo dışında: {yol}')
        rel = tam.relative_to(root).as_posix()
        izlenen = git(root, 'ls-files', '-z', '--', rel).stdout.split('\0')
        if (tam.is_dir() or any(p and p != rel for p in izlenen)
                or git(root, 'cat-file', '-t', f'HEAD:{rel}', check=False).stdout.strip() == 'tree'):
            raise Hata('Klasör verilemez; `git status --porcelain -- <klasör>` ile dosyaları tek tek ver.')
        out.append(rel)
    return root, out


def baslik_denetle(mesajlar, ayar):
    """İlk paragraf `tür(kapsam): özet`, tür ayardaki listeden. (tür, uyarı|None) döndürür."""
    if not mesajlar or not mesajlar[0].strip():
        raise Hata('-m gerekli: "tür(kapsam): özet"')
    baslik = mesajlar[0].strip().splitlines()[0]
    m = BASLIK.match(baslik)
    if not m or m.group('tur') not in ayar.turler:
        raise Hata(f'Başlık biçimi "tür(kapsam): özet" olmalı; tür: {", ".join(ayar.turler)}. Gelen: "{baslik}"')
    uyari = (f'Başlık {len(baslik)} karakter (öneri ≤{ayar.baslik_uzun}).'
             if len(baslik) > ayar.baslik_uzun else None)
    return m.group('tur'), uyari


def eol_denetle(root, yollar):
    """İzlenen dosyada index LF / dosya CRLF (ya da tersi) farkı varsa liste döndür."""
    bozuk = []
    for line in git(root, 'ls-files', '--eol', '--', *yollar, check=False).stdout.splitlines():
        meta, _, name = line.partition('\t')
        parts = meta.split()
        if len(parts) >= 2 and {parts[0][2:], parts[1][2:]} == {'lf', 'crlf'}:
            bozuk.append(f'{name} (index {parts[0][2:]}, dosya {parts[1][2:]})')
    return bozuk


def mevcut_ya_da_izlenen(root, rel):
    """Ne diskte ne index'te ne HEAD'de olan yol yazım hatasıdır (ör. sonda `\\r`): sessizce eleme, dur."""
    yok = [y for y in rel if not ((root / y).exists()
           or git(root, 'ls-files', '--error-unmatch', '--', y, check=False).returncode == 0
           or git(root, 'cat-file', '-e', f'HEAD:{y}', check=False).returncode == 0)]
    if yok:
        raise Hata('Yol bulunamadı (diskte, index\'te ve HEAD\'de yok): '
                   + ', '.join(repr(y) for y in yok[:5]) + ('…' if len(yok) > 5 else '')
                   + '. Yazımı kontrol et; listeyi dosyadan okuyorsan satır sonundaki \\r\'yi temizle.')
    return list(rel)


def index_bos_bekle(root, bekle=BEKLE):
    if (git_dizini(root) / 'MERGE_HEAD').exists():
        raise Hata('Yarım kalmış bir birleştirme var (MERGE_HEAD): biri korunan dalda elle `git merge` denemiş. '
                   'Senin işin değilse içeriğe dokunma; `git merge --abort` birleştirmeyi geri alır, '
                   'commit\'lenmemiş diğer dosyalar yerinde kalır. Sonra tekrar dene.')
    kilit, son = git_dizini(root) / 'index.lock', time.time() + bekle
    while kilit.exists():
        if time.time() > son:
            raise Hata('index.lock boşalmadı; başka bir git işlemi takılmış olabilir.')
        time.sleep(0.5)


def push_bekleyen(root):
    r = git(root, 'rev-list', '--count', '@{u}..HEAD', check=False)
    return int(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip().isdigit() else None


def pushla(root):
    r = git(root, 'push', '-q', check=False)
    return 'tamam' if r.returncode == 0 else f'başarısız: {(r.stderr or r.stdout).strip()}'


def testleri_calistir(root, yollar, ayar):
    """test_kapisi açıksa, verilen .py yollarının yalnız kendi klasörlerindeki testleri çalıştırır."""
    if not ayar.test_kapisi:
        return None
    dizinler = sorted({Path(y).parent.as_posix() for y in yollar
                       if Path(y).suffix == '.py'
                       and (not ayar.test_onekleri or any(y.startswith(o) for o in ayar.test_onekleri))
                       and any(p.is_file() for p in (root / y).parent.glob('test_*.py'))})
    if not dizinler:
        return None
    komut = [sys.executable, '-m', 'pytest', *dizinler, '-q', '-p', 'no:cacheprovider']
    try:
        r = subprocess.run(komut, cwd=root, env=sirsiz_ortam(ayar.ortam_izin), stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, text=True, encoding='utf-8',
                           errors='replace', timeout=TEST_ZAMAN_ASIMI, check=False)
    except subprocess.TimeoutExpired as exc:
        cikti = exc.stdout or ''
        if isinstance(cikti, bytes):
            cikti = cikti.decode('utf-8', errors='replace')
        raise Hata(f'Test kapısı: pytest zaman aşımı ({TEST_ZAMAN_ASIMI} sn).\n'
                   + '\n'.join(cikti.splitlines()[-15:])) from exc
    except OSError as exc:
        raise Hata(f'Test kapısı: pytest başlatılamadı: {exc}') from exc
    satirlar = r.stdout.strip().splitlines()
    if r.returncode:
        raise Hata(f'Test kapısı: pytest başarısız (çıkış {r.returncode}).\n'
                   + '\n'.join(satirlar[-15:]))
    return satirlar[-1] if satirlar else ''


def _ekler(oturum, yazar, test_yok=None):
    ekler = ([f'Oturum: {oturum}'] if oturum else []) + ([f'Co-Authored-By: {yazar}'] if yazar else [])
    if test_yok is not None:
        ekler.append(f'Test atlandı: {test_yok.strip()}')
    return ekler


def kaydet(repo, mesaj, yollar, oturum=None, push=None, eol_tamam=False, yazar=None, test_yok=None,
           ayar=None):
    """Verilen yolları bulunulan dala commit'ler. push=None → türe göre (otomatik_push)."""
    durum_ = saglik(repo, ayar)  # bare depoda da rapor verir; ayarı o okur
    ayar = durum_['ayar']
    if not durum_['tamam']:
        raise Hata('Git sağlığı HATA; commit yapılmadı. `serit kur` ile kurulumu düzelt.\n'
                   + '\n'.join(durum_['satirlar']))
    root, rel = yollari_denetle(repo, yollar)
    mesajlar = [mesaj] if isinstance(mesaj, str) else list(mesaj or [])
    tur, uyari = baslik_denetle(mesajlar, ayar)
    bozuk = [] if eol_tamam else eol_denetle(root, rel)
    if bozuk:
        raise Hata('Satır sonu değişmiş (çoğu zaman Windows\'ta metin kipinde yazım): '
                   + '; '.join(bozuk) + '. Dosyayı eski satır sonuna çevir ya da --eol-tamam ver.')
    rel = mevcut_ya_da_izlenen(root, rel)
    if test_yok is not None and not test_yok.strip():
        raise Hata('--test-yok için boş olmayan bir gerekçe gerekli.')
    testler = testleri_calistir(root, rel, ayar) if test_yok is None else None
    index_bos_bekle(root)
    # HEAD'de olup index'ten zaten silinen yol tekrar git add'e verilemez.
    eklenecek = [y for y in rel if (root / y).exists()
                 or git(root, 'ls-files', '--error-unmatch', '--', y, check=False).returncode == 0]
    if eklenecek:
        # -A yalnız verilen yollarla sınırlı: yeni, değişen ve silinen dosyayı birlikte alır.
        git(root, 'add', '-A', '--', *eklenecek)
    # -z: boşluklu/Türkçe adlar bölünmesin ya da tırnaklanmasın.
    degisen = [x for x in git(root, 'diff', '--cached', '--name-only', '-z', '--', *rel).stdout.split('\0') if x]
    if not degisen:
        return {'commit': None, 'dosyalar': [], 'push': None, 'uyari': uyari,
                'not': 'Verilen yollarda değişiklik yok.', 'testler': testler}
    args = ['commit', '--only', '-q']
    for parca in mesajlar:
        args += ['-m', parca]
    ekler = _ekler(oturum, yazar, test_yok)
    if ekler:
        args += ['-m', '\n'.join(ekler)]
    git(root, *args, '--', *rel, izinli=True)
    sonuc = {'commit': git(root, 'log', '-1', '--format=%h %s').stdout.strip(), 'dosyalar': degisen,
             'tur': tur, 'uyari': uyari, 'push': None, 'testler': testler}
    if push if push is not None else tur in ayar.otomatik_push:
        sonuc['push'] = pushla(root)
    else:
        bekleyen = push_bekleyen(root)
        if bekleyen is not None and bekleyen >= ayar.push_hatirlat:
            sonuc['hatirlat'] = f'{bekleyen} commit push bekliyor: gözden geçir, `serit push`.'
    return sonuc


def aktif_dal(root):
    """Dal adı; ayrık HEAD'de None. Okunamazsa Hata."""
    r = git(root, 'symbolic-ref', '--short', '-q', 'HEAD', check=False)
    if r.returncode == 0:
        return r.stdout.strip()
    if r.returncode == 1:
        return None
    raise Hata(f'Dal okunamadı: {(r.stderr or r.stdout).strip()}')


def birlestir(repo, dal, mesaj, oturum=None, yazar=None, push=None, ayar=None):
    """Şerit dalını korunan dala --no-ff birleştirir; çalışma ağacındaki başka işlere dokunmaz.

    Çakışmada birleştirme geri alınır (`merge --abort`) ve durulur; çözüm şerit dalında yapılır.
    """
    root = kok(repo)
    ayar = ayar or ayar_oku(root)
    mesajlar = [mesaj] if isinstance(mesaj, str) else list(mesaj or [])
    tur, uyari = baslik_denetle(mesajlar, ayar)
    if aktif_dal(root) != ayar.korunan_dal:
        raise Hata(f'birlestir yalnız {ayar.korunan_dal} üzerindeyken çalışır.')
    if ayar.serit_onekleri and not any(dal.startswith(o) for o in ayar.serit_onekleri):
        raise Hata(f'"{dal}" şerit dalı değil; şerit önekleri: {", ".join(ayar.serit_onekleri)}.')
    if git(root, 'rev-parse', '--verify', '-q', dal, check=False).returncode:
        raise Hata(f'Dal yok: {dal}')
    ekler = _ekler(oturum, yazar)
    govde = '\n\n'.join(mesajlar + (['\n'.join(ekler)] if ekler else []))
    index_bos_bekle(root)
    r = git(root, 'merge', '--no-ff', '-m', govde, dal, check=False, izinli=True)
    if r.returncode:
        git(root, 'merge', '--abort', check=False)
        raise Hata(f'Birleştirme durdu ve geri alındı: {(r.stderr or r.stdout).strip()[-300:]}')
    sonuc = {'commit': git(root, 'log', '-1', '--format=%h %s').stdout.strip(), 'tur': tur, 'uyari': uyari,
             'dosyalar': git(root, 'diff', '--name-only', 'HEAD^1', 'HEAD').stdout.splitlines(), 'push': None}
    if push if push is not None else tur in ayar.otomatik_push:
        sonuc['push'] = pushla(root)
    return sonuc


def durum(repo, ayar=None):
    root = kok(repo)
    ayar = ayar or ayar_oku(root)
    korunan_var = git(root, 'rev-parse', '--verify', '-q', ayar.korunan_dal, check=False).returncode == 0
    seritler = []
    if ayar.serit_onekleri:
        dallar = git(root, 'for-each-ref', '--format=%(refname:short)', 'refs/heads/').stdout.splitlines()
        for dal in dallar:
            if any(dal.startswith(o) for o in ayar.serit_onekleri):
                sayi = None
                if korunan_var:
                    r = git(root, 'rev-list', '--count', f'{ayar.korunan_dal}..{dal}', check=False)
                    sayi = int(r.stdout.strip()) if r.returncode == 0 else None
                seritler.append((dal, sayi))
    return {'dal': aktif_dal(root), 'korunan_dal': ayar.korunan_dal, 'push_bekleyen': push_bekleyen(root),
            'bekleyen_degisiklik': git(root, 'status', '--porcelain').stdout.splitlines(),
            'seritler': seritler}
