import subprocess
import sys

import pytest
from yardimci import depo_kur, g, git_sonuc

from serit import gitci, kaydet
from serit.ayar import ayar_kur
from serit.gitci import Hata


@pytest.fixture
def repo(tmp_path):
    return depo_kur(tmp_path)


def test_yalniz_verilen_yol_commitlenir_baskasinin_stagei_kalir(repo):
    (repo / 'benim.md').write_bytes(b'b\n')
    (repo / 'baskasi.md').write_bytes(b'c\n')
    g(repo, 'add', 'baskasi.md')  # başka oturum stage'lemiş
    s = kaydet.kaydet(repo, 'belge(test): benim işim', ['benim.md'], oturum='ajan/x', yazar='Ajan <ajan@ornek.invalid>')
    assert s['dosyalar'] == ['benim.md'] and s['push'] is None
    assert g(repo, 'show', '--name-only', '--format=', 'HEAD').split() == ['benim.md']
    govde = g(repo, 'log', '-1', '--format=%B')
    assert 'Oturum: ajan/x' in govde and 'Co-Authored-By: Ajan <ajan@ornek.invalid>' in govde
    assert g(repo, 'diff', '--cached', '--name-only').split() == ['baskasi.md']


@pytest.mark.parametrize('yol', ['.', '-A', '*', ':/'])
def test_genis_secim_reddedilir(repo, yol):
    with pytest.raises(Hata):
        kaydet.kaydet(repo, 'belge: xyz', [yol])


def test_bos_kok_ve_disari_reddedilir(repo, tmp_path_factory):
    for yollar in ([], [str(repo)], [str(tmp_path_factory.mktemp('dis') / 'f.md')]):
        with pytest.raises(Hata):
            kaydet.kaydet(repo, 'belge: xyz', yollar)


@pytest.mark.parametrize('baslik', ['benim işim', 'feat: ingilizce tür', 'belge:bosluksuz',
                                    'gorev: bilinmeyen tür', 'Belge: büyük harf'])
def test_baslik_bicimi_reddedilir(repo, baslik):
    (repo / 'b.md').write_bytes(b'b\n')
    with pytest.raises(Hata, match='biçimi'):
        kaydet.kaydet(repo, baslik, ['b.md'])


def test_tur_listesi_ayardan_gelir(repo):
    (repo / '.serit.toml').write_text('turler = ["is", "not"]\n', encoding='utf-8')
    (repo / 'b.md').write_bytes(b'b\n')
    with pytest.raises(Hata, match='tür: is, not'):
        kaydet.kaydet(repo, 'belge: artık yok', ['b.md'])
    assert kaydet.kaydet(repo, 'not(kapsam): yeni tür', ['b.md'])['tur'] == 'not'


def test_uzun_baslik_uyari_verir(repo):
    (repo / 'b.md').write_bytes(b'b\n')
    assert 'karakter' in kaydet.kaydet(repo, 'belge(x): ' + 'u' * 80, ['b.md'])['uyari']


def test_lf_crlf_donusumu_durdurur(repo):
    (repo / 'a.md').write_bytes(b'a\r\nb\r\n')
    with pytest.raises(Hata, match='Satır sonu'):
        kaydet.kaydet(repo, 'duzelt: satır sonu', ['a.md'])
    assert kaydet.kaydet(repo, 'duzelt: satır sonu', ['a.md'], eol_tamam=True)['dosyalar'] == ['a.md']


def test_silme_alt_klasor_turkce_ad(repo):
    (repo / 'k').mkdir()
    (repo / 'k' / 'Yeni not ğüş.md').write_bytes(b'n\n')
    with pytest.raises(Hata, match='git status --porcelain -- <klasör>'):
        kaydet.kaydet(repo, 'belge: ekle', ['k'])
    assert kaydet.kaydet(repo, 'belge: ekle', ['k/Yeni not ğüş.md'])['dosyalar'] == ['k/Yeni not ğüş.md']
    (repo / 'a.md').unlink()
    assert kaydet.kaydet(repo, 'belge: sil', ['a.md'])['dosyalar'] == ['a.md']


def test_degisiklik_yoksa_commit_yok(repo):
    assert kaydet.kaydet(repo, 'belge: boş', ['a.md'])['commit'] is None


def test_otomatik_push_turu_kendiliginden_pushlanir(repo):
    (repo / '.serit.toml').write_text('otomatik_push = ["karar"]\n', encoding='utf-8')
    (repo / 'k.md').write_bytes(b'k\n')
    assert kaydet.kaydet(repo, 'karar: yeni karar', ['k.md'])['push'] == 'tamam'
    assert kaydet.push_bekleyen(repo) == 0
    (repo / 'n.md').write_bytes(b'n\n')
    assert kaydet.kaydet(repo, 'karar: ama itme', ['n.md'], push=False)['push'] is None
    (repo / 'm.md').write_bytes(b'm\n')
    assert kaydet.kaydet(repo, 'belge: itilmez', ['m.md'])['push'] is None


def test_varsayilan_ayarda_otomatik_push_yok(repo):
    (repo / 'k.md').write_bytes(b'k\n')
    assert kaydet.kaydet(repo, 'karar: yeni karar', ['k.md'])['push'] is None
    assert kaydet.push_bekleyen(repo) == 1


def test_birikince_hatirlatir(repo):
    (repo / '.serit.toml').write_text('push_hatirlat = 2\n', encoding='utf-8')
    for i in range(2):
        (repo / f'r{i}.md').write_bytes(b'r\n')
        s = kaydet.kaydet(repo, f'belge: kayıt {i}', [f'r{i}.md'])
    assert '2 commit' in s['hatirlat']


def test_kanca_korunan_dalda_duz_commiti_reddeder_kaydet_ve_serit_gecer(repo):
    (repo / 'x.md').write_bytes(b'x\n')
    g(repo, 'add', 'x.md')
    r = git_sonuc(repo, 'commit', '-qm', 'belge: elle')
    assert r.returncode != 0 and 'serit kaydet' in r.stderr
    assert kaydet.kaydet(repo, 'belge: kaydet ile', ['x.md'])['dosyalar'] == ['x.md']
    g(repo, 'checkout', '-q', '-b', 'serit/bir')
    (repo / 'y.md').write_bytes(b'y\n')
    g(repo, 'add', 'y.md')
    assert git_sonuc(repo, 'commit', '-qm', 'serbest mesaj').returncode == 0  # şerit dalı serbest


def test_ayrik_head_serbest(repo):
    g(repo, 'checkout', '-q', '--detach')
    (repo / 'y.md').write_bytes(b'y\n')
    g(repo, 'add', 'y.md')
    assert git_sonuc(repo, 'commit', '-qm', 'ayrık').returncode == 0


def test_korunan_dal_ayardan_gelir(tmp_path):
    repo = depo_kur(tmp_path, ayar='korunan_dal = "trunk"\n')
    (repo / 'x.md').write_bytes(b'x\n')
    g(repo, 'add', 'x.md')
    assert git_sonuc(repo, 'commit', '-qm', 'main artık serbest').returncode == 0
    assert g(repo, 'config', '--get', 'branch.trunk.rebase').strip() == 'true'
    g(repo, 'checkout', '-q', '-b', 'trunk')
    (repo / 'z.md').write_bytes(b'z\n')
    g(repo, 'add', 'z.md')
    r = git_sonuc(repo, 'commit', '-qm', 'trunk korunur')
    assert r.returncode != 0 and '`trunk`' in r.stderr


def test_birlestir_yalniz_serit_ile(repo):
    g(repo, 'checkout', '-q', '-b', 'serit/bir')
    (repo / 'y.md').write_bytes(b'y\n')
    g(repo, 'add', 'y.md')
    g(repo, 'commit', '-qm', 'tur 1')
    g(repo, 'checkout', '-q', 'main')
    (repo / 'a.md').write_bytes(b'baska oturumun yarim isi\n')  # commit'lenmemiş başka iş
    r = git_sonuc(repo, 'merge', '--no-ff', '-m', 'elle', 'serit/bir')
    assert r.returncode != 0 and 'serit birlestir' in r.stderr and 'merge --abort' in r.stderr
    # git yarım birleştirme bırakır; kaydet bunu tanır ve ne yapılacağını söyler.
    (repo / 'z.md').write_bytes(b'z\n')
    with pytest.raises(Hata, match='MERGE_HEAD'):
        kaydet.kaydet(repo, 'belge: arada', ['z.md'])
    g(repo, 'merge', '--abort')
    assert (repo / 'a.md').read_bytes() == b'baska oturumun yarim isi\n'  # abort başkasının işini korur
    s = kaydet.birlestir(repo, 'serit/bir', 'arac(serit): birleştir', oturum='ajan/x', push=False)
    assert s['dosyalar'] == ['y.md'] and len(g(repo, 'log', '-1', '--format=%P').split()) == 2
    assert 'Oturum: ajan/x' in g(repo, 'log', '-1', '--format=%B')
    assert (repo / 'a.md').read_bytes() == b'baska oturumun yarim isi\n'  # dokunulmadı, commit'e girmedi
    assert g(repo, 'show', 'HEAD:a.md') == 'a\n'
    with pytest.raises(Hata, match='biçimi'):
        kaydet.birlestir(repo, 'serit/bir', 'serbest mesaj')


def test_birlestir_serit_oneki_ve_dal_denetimi(repo):
    g(repo, 'checkout', '-q', '-b', 'ozel')
    (repo / 'y.md').write_bytes(b'y\n')
    g(repo, 'add', 'y.md')
    g(repo, 'commit', '-qm', 'ozel')
    with pytest.raises(Hata, match='yalnız main üzerindeyken'):
        kaydet.birlestir(repo, 'ozel', 'arac: xyz')
    g(repo, 'checkout', '-q', 'main')
    with pytest.raises(Hata, match='şerit dalı değil'):
        kaydet.birlestir(repo, 'ozel', 'arac: xyz')
    with pytest.raises(Hata, match='Dal yok'):
        kaydet.birlestir(repo, 'serit/yok', 'arac: xyz')
    hepsi = ayar_kur({'serit_onekleri': []})
    assert kaydet.birlestir(repo, 'ozel', 'arac: önek listesi boşsa her dal', ayar=hepsi, push=False)['commit']


def test_birlestir_catismada_geri_alir(repo):
    g(repo, 'checkout', '-q', '-b', 'serit/catisma')
    (repo / 'a.md').write_bytes(b'serit\n')
    g(repo, 'commit', '-qam', 'serit')
    g(repo, 'checkout', '-q', 'main')
    (repo / 'a.md').write_bytes(b'main\n')
    kaydet.kaydet(repo, 'belge: main', ['a.md'])
    onceki = g(repo, 'rev-parse', 'HEAD')
    with pytest.raises(Hata, match='geri alındı'):
        kaydet.birlestir(repo, 'serit/catisma', 'arac: birleştir')
    assert g(repo, 'rev-parse', 'HEAD') == onceki
    assert not (gitci.git_dizini(repo) / 'MERGE_HEAD').exists()


def test_olmayan_yol_sessizce_elenmez(repo):
    (repo / 'b.md').write_bytes(b'b\n')
    with pytest.raises(Hata, match='Yol bulunamadı'):
        kaydet.kaydet(repo, 'belge: satır sonu artığı', ['b.md\r'])
    with pytest.raises(Hata, match='Yol bulunamadı'):
        kaydet.kaydet(repo, 'belge: yazım hatası', ['b.md', 'yok.md'])


@pytest.mark.parametrize('yol', ['k/*', 'a?.md', '[ab].md', ':(glob)**'])
def test_glob_yollari_reddedilir(repo, yol):
    with pytest.raises(Hata, match='git status --porcelain -- <klasör>'):
        kaydet.kaydet(repo, 'belge: glob reddi', [yol])


def test_git_cagrilari_literal_pathspec_kullanir(monkeypatch, tmp_path):
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, '', '')

    monkeypatch.setattr(gitci.subprocess, 'run', run)
    gitci.git(tmp_path, 'add', '--', 'a.md')
    gitci.git(tmp_path, 'commit', '--only', '--', 'a.md', izinli=True)
    assert all(c[:2] == ['git', '--literal-pathspecs'] for c in calls)


def test_stage_silme_headde_izlenen_yol_commitlenir(repo):
    (repo / 'baskasi.md').write_bytes(b'baska\n')
    g(repo, 'add', 'baskasi.md')
    g(repo, 'rm', '-q', 'a.md')
    assert kaydet.mevcut_ya_da_izlenen(repo, ['a.md']) == ['a.md']  # HEAD'de izlenen silme kabul
    with pytest.raises(Hata, match='Yol bulunamadı'):
        kaydet.mevcut_ya_da_izlenen(repo, ['a.md', 'yok.md'])
    sonuc = kaydet.kaydet(repo, 'belge: stage silme', ['a.md'])
    assert sonuc['dosyalar'] == ['a.md']
    assert git_sonuc(repo, 'cat-file', '-e', 'HEAD:a.md').returncode != 0
    assert g(repo, 'diff', '--cached', '--name-only').splitlines() == ['baskasi.md']


@pytest.mark.parametrize('stage_silme', [False, True])
def test_silinmis_klasor_yolu_da_reddedilir(repo, stage_silme):
    (repo / 'k').mkdir()
    (repo / 'k' / 'a.md').write_bytes(b'a\n')
    kaydet.kaydet(repo, 'belge: alt dosya', ['k/a.md'], push=False)
    if stage_silme:
        g(repo, 'rm', '-rq', 'k')
    else:
        (repo / 'k' / 'a.md').unlink()
        (repo / 'k').rmdir()
    with pytest.raises(Hata, match='git status --porcelain -- <klasör>'):
        kaydet.kaydet(repo, 'belge: klasor silme', ['k'])


def test_durum_serit_dallarini_sayar(repo):
    g(repo, 'checkout', '-q', '-b', 'serit/bir')
    (repo / 'y.md').write_bytes(b'y\n')
    g(repo, 'add', 'y.md')
    g(repo, 'commit', '-qm', 'tur 1')
    g(repo, 'checkout', '-q', '-b', 'baska')
    g(repo, 'checkout', '-q', 'main')
    (repo / 'kirli.md').write_bytes(b'k\n')
    d = kaydet.durum(repo)
    assert d['dal'] == 'main' and d['push_bekleyen'] == 0
    assert d['seritler'] == [('serit/bir', 1)]
    assert '?? kirli.md' in d['bekleyen_degisiklik']


# Test kapısı: test_kapisi = true iken verilen .py dosyalarının klasöründeki testler koşar.

@pytest.fixture
def kod_repo(tmp_path):
    repo = depo_kur(tmp_path, ayar='test_kapisi = true\ntest_onekleri = ["kod/"]\n')
    dizin = repo / 'kod' / 'x'
    dizin.mkdir(parents=True)
    (dizin / 'mod.py').write_bytes(b'deger = 1\n')
    (dizin / 'test_mod.py').write_bytes(b'def test_mod():\n    assert True\n')
    return repo


def pytest_cagrilarini_izle(monkeypatch):
    run = subprocess.run
    calls = []

    def izle(args, **kwargs):
        if args[:3] == [sys.executable, '-m', 'pytest']:
            calls.append((args, kwargs))
        return run(args, **kwargs)

    monkeypatch.setattr(kaydet.subprocess, 'run', izle)
    return calls


@pytest.mark.parametrize('baska_stage', [False, True])
def test_dusen_test_commit_ve_indexi_degistirmez(kod_repo, baska_stage):
    repo = kod_repo
    (repo / 'kod/x/test_mod.py').write_bytes(b'def test_mod():\n    assert False\n')
    if baska_stage:
        (repo / 'baskasi.md').write_bytes(b'baska\n')
        g(repo, 'add', 'baskasi.md')
    head = g(repo, 'rev-parse', 'HEAD')
    index = g(repo, 'diff', '--cached')
    with pytest.raises(Hata, match='failed'):
        kaydet.kaydet(repo, 'arac: test kapisi', ['kod/x/mod.py'])
    assert g(repo, 'rev-parse', 'HEAD') == head
    assert g(repo, 'diff', '--cached') == index
    if not baska_stage:
        assert index == ''


def test_gecen_test_commite_izin_verir(kod_repo, monkeypatch):
    calls = pytest_cagrilarini_izle(monkeypatch)
    s = kaydet.kaydet(kod_repo, 'arac: test kapisi', ['kod/x/mod.py', 'kod/x/test_mod.py'])
    assert s['commit'] and 'passed' in s['testler']
    assert g(kod_repo, 'show', '--name-only', '--format=', 'HEAD').splitlines() == s['dosyalar']
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == [sys.executable, '-m', 'pytest', 'kod/x', '-q', '-p', 'no:cacheprovider']
    assert kwargs['cwd'] == kod_repo and kwargs['timeout'] == kaydet.TEST_ZAMAN_ASIMI
    assert kwargs['env']['PYTHONDONTWRITEBYTECODE'] == '1'
    assert kwargs['env']['PYTHONIOENCODING'] == 'utf-8'
    assert not any(k.upper().startswith('GIT_') for k in kwargs['env'])
    assert not list(kod_repo.rglob('__pycache__'))
    assert not (kod_repo / '.pytest_cache').exists()


def test_test_kapisi_kapaliysa_pytest_cagirmaz(tmp_path, monkeypatch):
    repo = depo_kur(tmp_path)
    (repo / 'kod').mkdir()
    (repo / 'kod/mod.py').write_bytes(b'deger = 1\n')
    (repo / 'kod/test_mod.py').write_bytes(b'def test_mod():\n    assert False\n')
    calls = pytest_cagrilarini_izle(monkeypatch)
    assert kaydet.kaydet(repo, 'arac: kapı kapalı', ['kod/mod.py'])['commit']
    assert not calls


def test_test_kapisi_git_ortamini_temizler_gercek_repo_bozulmaz(kod_repo, tmp_path, monkeypatch):
    gercek = tmp_path / 'gercek'
    gercek.mkdir()
    g(gercek, 'init', '-q')
    once = (gercek / '.git/config').read_bytes()
    (kod_repo / 'kod/x/test_mod.py').write_bytes(
        b'import os, subprocess\nfrom pathlib import Path\ndef test_mod():\n'
        b'    tmp_path = Path(__file__).parent / "gecici"\n'
        b'    tmp_path.mkdir()\n'
        b'    subprocess.run(["git", "init", "-q", "--bare", str(tmp_path / "u.git")], check=True)\n'
        b'    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)\n'
        b'    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "t@ornek.invalid"], check=True)\n'
        b'    assert not any(k.upper().startswith("GIT_") for k in os.environ)\n')
    ayar = ayar_kur({'test_kapisi': True})
    with monkeypatch.context() as m:
        m.setenv('GIT_DIR', str(gercek / '.git'))
        m.setenv('GIT_WORK_TREE', str(gercek))
        m.setenv('GIT_INDEX_FILE', str(gercek / '.git/index'))
        m.setenv('GIT_CONFIG_COUNT', '1')
        m.setenv('GIT_CONFIG_KEY_0', 'probe.sentinel')
        m.setenv('GIT_CONFIG_VALUE_0', 'deneme')
        assert '1 passed' in kaydet.testleri_calistir(kod_repo, ['kod/x/mod.py'], ayar)
    assert (gercek / '.git/config').read_bytes() == once
    assert g(gercek, 'config', '--get', 'core.bare').strip() == 'false'
    assert git_sonuc(gercek, 'config', '--local', '--get', 'user.email').returncode == 1
    assert not (gercek / '.git/index').exists()


def test_test_yok_gerekcesi_commit_govdesine_yazilir(kod_repo, monkeypatch):
    calls = pytest_cagrilarini_izle(monkeypatch)
    (kod_repo / 'kod/x/test_mod.py').write_bytes(b'def test_mod():\n    assert False\n')
    s = kaydet.kaydet(kod_repo, 'arac: acil duzeltme', ['kod/x/mod.py'], test_yok='acil')
    assert s['commit'] and not calls
    assert 'Test atlandı: acil' in g(kod_repo, 'log', '-1', '--format=%B')


@pytest.mark.parametrize('gerekce', ['', '   ', '\n\t'])
def test_bos_test_yok_gerekcesi_reddedilir(kod_repo, gerekce):
    head = g(kod_repo, 'rev-parse', 'HEAD')
    with pytest.raises(Hata, match='gerekçe'):
        kaydet.kaydet(kod_repo, 'arac: test kapisi', ['kod/x/mod.py'], test_yok=gerekce)
    assert g(kod_repo, 'rev-parse', 'HEAD') == head
    assert g(kod_repo, 'diff', '--cached') == ''


def test_kod_disi_yol_pytest_cagirmaz(kod_repo, monkeypatch):
    calls = pytest_cagrilarini_izle(monkeypatch)
    (kod_repo / 'notlar').mkdir()
    (kod_repo / 'notlar/a.md').write_bytes(b'not\n')
    assert kaydet.kaydet(kod_repo, 'belge: yeni not', ['notlar/a.md'])['commit']
    # Önek dışındaki .py dosyası da kapıya girmez.
    (kod_repo / 'betik').mkdir()
    (kod_repo / 'betik/b.py').write_bytes(b'x = 1\n')
    (kod_repo / 'betik/test_b.py').write_bytes(b'assert False\n')
    assert kaydet.kaydet(kod_repo, 'arac: önek dışı', ['betik/b.py'])['commit']
    assert not calls


def test_test_dizini_olmayan_kod_pytest_cagirmaz(kod_repo, monkeypatch):
    calls = pytest_cagrilarini_izle(monkeypatch)
    (kod_repo / 'kod/y').mkdir()
    (kod_repo / 'kod/y/mod.py').write_bytes(b'deger = 1\n')
    # Üstteki ve alt klasördeki test dosyaları bu klasörü test dizini yapmaz.
    (kod_repo / 'kod/test_ust.py').write_bytes(b'assert False\n')
    (kod_repo / 'kod/y/alt').mkdir()
    (kod_repo / 'kod/y/alt/test_alt.py').write_bytes(b'assert False\n')
    assert kaydet.kaydet(kod_repo, 'arac: testsiz kod', ['kod/y/mod.py'])['commit']
    assert not calls


@pytest.mark.parametrize('zaman_asimi', [False, True])
def test_test_hatasinda_son_15_satir_ve_index_korunur(kod_repo, monkeypatch, zaman_asimi):
    run = subprocess.run
    satirlar = [f'satir {i}' for i in range(20)]
    cikti = '\n'.join(satirlar) + '\n'

    def hata(args, **kwargs):
        if args[:3] == [sys.executable, '-m', 'pytest']:
            if zaman_asimi:
                # TimeoutExpired text=True olsa da bytes döndürebilir.
                raise subprocess.TimeoutExpired(args, 300, output=cikti.encode('utf-8'))
            return subprocess.CompletedProcess(args, 1, cikti)
        return run(args, **kwargs)

    monkeypatch.setattr(kaydet.subprocess, 'run', hata)
    head = g(kod_repo, 'rev-parse', 'HEAD')
    with pytest.raises(Hata) as exc:
        kaydet.kaydet(kod_repo, 'arac: test kapisi', ['kod/x/mod.py'])
    assert str(exc.value).splitlines()[1:] == satirlar[-15:]
    assert ('zaman aşımı' if zaman_asimi else 'başarısız') in str(exc.value)
    assert g(kod_repo, 'rev-parse', 'HEAD') == head
    assert g(kod_repo, 'diff', '--cached') == ''
