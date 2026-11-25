import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest
from yardimci import depo_kur, g, git_sonuc

from serit import cli, gitci, kaydet, kurulum
from serit.gitci import Hata


@pytest.fixture
def repo(tmp_path):
    return depo_kur(tmp_path)


def _kanca_dizini(repo):
    return Path(g(repo, 'config', '--get', 'core.hooksPath').strip())


def test_kur_kancalari_git_dizinine_yazar(repo):
    dizin = _kanca_dizini(repo)
    assert dizin == gitci.ortak_git_dizini(repo) / 'serit' / 'hooks'
    for ad in kurulum.KANCALAR:
        icerik = (dizin / ad).read_bytes()
        assert icerik.startswith(b'#!/bin/sh\n') and b'\r\n' not in icerik
        assert kurulum.ISARET.encode() in icerik and b'@PYTHON@' not in icerik
        assert Path(sys.executable).as_posix().encode() in icerik
        if os.name != 'nt':
            assert (dizin / ad).stat().st_mode & stat.S_IXUSR
    assert g(repo, 'config', '--get', 'branch.main.mergeoptions').strip() == '--no-ff'
    assert g(repo, 'config', '--get', 'branch.main.rebase').strip() == 'true'
    assert g(repo, 'status', '--porcelain') == ''  # kancalar çalışma ağacına girmez


def test_kur_tekrar_calisir_ve_mergeoptions_korunur(repo):
    g(repo, 'config', 'branch.main.mergeoptions', '--log')
    kurulum.kur(repo)
    kurulum.kur(repo)
    assert g(repo, 'config', '--get', 'branch.main.mergeoptions').split() == ['--log', '--no-ff']


def test_kur_baska_hookspathi_ezmez(repo):
    g(repo, 'config', 'core.hooksPath', '.baska-kancalar')
    with pytest.raises(Hata, match='--zorla'):
        kurulum.kur(repo)
    assert kurulum.kur(repo, zorla=True)['kanca_dizini'] == _kanca_dizini(repo).as_posix()


def test_kur_eski_kancalar_icin_uyarir(tmp_path):
    r = tmp_path / 'd'
    r.mkdir()
    g(r, 'init', '-q', '-b', 'main')
    eski = gitci.ortak_git_dizini(r) / 'hooks' / 'pre-commit'
    eski.write_bytes(b'#!/bin/sh\nexit 0\n')
    s = kurulum.kur(r)
    assert any('pre-commit' in u for u in s['uyarilar'])


@pytest.mark.parametrize('ayrisik', [False, True])
def test_duz_merge_korunan_dalda_reddedilir(repo, ayrisik):
    g(repo, 'checkout', '-qb', 'serit/bir')
    (repo / 'serit.md').write_bytes(b'serit\n')
    g(repo, 'add', 'serit.md')
    g(repo, 'commit', '-qm', 'serit')
    g(repo, 'checkout', '-q', 'main')
    if ayrisik:
        (repo / 'main.md').write_bytes(b'main\n')
        kaydet.kaydet(repo, 'belge: main ilerler', ['main.md'], push=False)
    onceki = g(repo, 'rev-parse', 'HEAD')
    sonuc = git_sonuc(repo, 'merge', 'serit/bir')
    assert sonuc.returncode != 0 and 'birlestir' in sonuc.stderr
    assert g(repo, 'rev-parse', 'HEAD') == onceki
    g(repo, 'merge', '--abort')


def test_ilk_commit_kaydet_ile(tmp_path):
    r = tmp_path / 'bos'
    r.mkdir()
    g(r, 'init', '-q', '-b', 'main')
    kurulum.kur(r)
    (r / 'a.md').write_bytes(b'a\n')
    g(r, 'add', 'a.md')
    assert git_sonuc(r, 'commit', '-qm', 'ilk').returncode != 0  # doğmamış main de korunur
    assert kaydet.kaydet(r, 'belge: ilk', ['a.md'])['dosyalar'] == ['a.md']


@pytest.mark.parametrize('bozuk', ['hooksPath', 'pre-commit', 'pre-merge-commit', 'pre-push',
                                   'isaret', 'mergeoptions', 'rebase', 'MERGE_HEAD'])
def test_saglik_her_kontrol_ve_commit_engeli(repo, bozuk, capsys):
    assert kurulum.saglik(repo)['tamam']
    dizin = _kanca_dizini(repo)
    if bozuk == 'hooksPath':
        g(repo, 'config', '--unset', 'core.hooksPath')
    elif bozuk == 'isaret':
        (dizin / 'pre-commit').write_bytes(b'#!/bin/sh\nexit 0\n')
    elif bozuk == 'mergeoptions':
        g(repo, 'config', 'branch.main.mergeoptions', '--ff-only')
    elif bozuk == 'rebase':
        g(repo, 'config', 'branch.main.rebase', 'false')
    elif bozuk == 'MERGE_HEAD':
        (gitci.git_dizini(repo) / 'MERGE_HEAD').write_bytes(b'yarim\n')
    else:
        (dizin / bozuk).unlink()
    sonuc = kurulum.saglik(repo)
    assert not sonuc['tamam'] and len(sonuc['satirlar']) == 8
    hatalar = sum(s.startswith('HATA:') for s in sonuc['satirlar'])
    assert hatalar == (4 if bozuk == 'hooksPath' else 1)
    assert cli.main(['saglik', '--repo', str(repo)]) == 1
    assert 'HATA:' in capsys.readouterr().out
    (repo / 'benim.md').write_bytes(b'benim\n')
    (repo / 'baskasi.md').write_bytes(b'baska\n')
    g(repo, 'add', 'baskasi.md')
    head, index = g(repo, 'rev-parse', 'HEAD'), g(repo, 'diff', '--cached')
    with pytest.raises(Hata, match='Git sağlığı HATA; commit yapılmadı'):
        kaydet.kaydet(repo, 'belge: saglik engeli', ['benim.md'], test_yok='sağlık atlanamaz')
    assert g(repo, 'rev-parse', 'HEAD') == head
    assert g(repo, 'diff', '--cached') == index


@pytest.mark.parametrize('deger', ['true', 'yes', '1'])
def test_saglik_bare_repoyu_yakalar(repo, capsys, deger):
    g(repo, 'config', 'core.bare', deger)
    once = (repo / '.git/config').read_bytes()
    sonuc = kurulum.saglik(repo)
    assert not sonuc['tamam'] and len(sonuc['satirlar']) == 8
    assert [s for s in sonuc['satirlar'] if s.startswith('HATA:')] == [
        'HATA: core.bare != true (bulaşma: git --git-dir=.git config core.bare false)']
    assert cli.main(['saglik', '--repo', str(repo)]) == 1
    assert 'HATA: core.bare != true' in capsys.readouterr().out
    with pytest.raises(Hata, match='Git sağlığı HATA; commit yapılmadı'):
        kaydet.kaydet(repo, 'belge: bare engeli', ['a.md'], test_yok='sağlık atlanamaz')
    assert (repo / '.git/config').read_bytes() == once


def test_saglik_cli_tam_ve_ayar_degistirmez(repo, capsys):
    once = g(repo, 'config', '--local', '--list')
    assert cli.main(['saglik', '--repo', str(repo)]) == 0
    cikti = capsys.readouterr().out
    assert cikti.count('TAMAM:') == 8 and 'TAMAM: core.bare != true' in cikti
    assert g(repo, 'config', '--local', '--list') == once


def test_kanca_python_bulamazsa_reddeder(repo, tmp_path):
    """Kurulumdaki yorumlayıcı yoksa ve SERIT_PYTHON/PATH'te python yoksa commit geçmez (fail-closed)."""
    sh = shutil.which('sh')
    if sh is None:
        pytest.skip('sh yok')
    kanca = tmp_path / 'pre-commit'
    kanca.write_bytes(kurulum.kanca_sablonu('pre-commit').replace(b'\r\n', b'\n'))
    bos = tmp_path / 'bos-path'
    bos.mkdir()
    env = {k: v for k, v in os.environ.items() if k not in ('PATH', 'SERIT_PYTHON')}
    env['PATH'] = str(bos)
    r = subprocess.run([sh, str(kanca)], cwd=repo, capture_output=True, text=True, encoding='utf-8',
                       env=env, check=False)
    assert r.returncode == 1 and 'Python bulamadı' in r.stderr


def test_conftest_git_degiskenlerini_temizler_gercek_repo_bozulmaz(tmp_path):
    """pre-push GIT_DIR ile komut koşturur; testteki `git init --bare` gerçek depoyu bare yapmamalı."""
    gercek = tmp_path / 'gercek'
    gercek.mkdir()
    g(gercek, 'init', '-q')
    once = (gercek / '.git/config').read_bytes()
    deney = tmp_path / 'deney'
    deney.mkdir()
    shutil.copy2(Path(__file__).resolve().parent / 'conftest.py', deney / 'conftest.py')
    (deney / 'test_x.py').write_text(
        'import os, subprocess\nfrom pathlib import Path\n'
        'assert not any(k.upper().startswith("GIT_") and k not in ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM")'
        ' for k in os.environ)\n'
        'def test_x():\n'
        '    tmp_path = Path(__file__).parent / "gecici"\n'
        '    tmp_path.mkdir()\n'
        '    subprocess.run(["git", "init", "-q", "--bare", str(tmp_path / "u.git")], check=True)\n'
        '    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)\n'
        '    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "t@ornek.invalid"], check=True)\n',
        encoding='utf-8')
    # Mutlak GIT_DIR ve rakam/küçük harf içeren diğer GIT_* değişkenleri de temizlenmeli.
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith('GIT_')}
    env['GIT_DIR'] = str(gercek / '.git')
    env.update(GIT_CONFIG_COUNT='1', GIT_CONFIG_KEY_0='probe.sentinel',
               GIT_CONFIG_VALUE_0='ilk\nGIT_SAHte_9=ikinci', GIT_ozel_9='deneme', PYTHONIOENCODING='utf-8')
    r = subprocess.run([sys.executable, '-m', 'pytest', str(deney), '-q', '-p', 'no:cacheprovider'],
                       capture_output=True, text=True, encoding='utf-8', errors='replace', env=env, cwd=deney,
                       check=False)
    assert r.returncode == 0, (r.stdout + r.stderr)[-1500:]
    assert (gercek / '.git/config').read_bytes() == once
    assert g(gercek, 'config', '--get', 'core.bare').strip() == 'false'
    assert git_sonuc(gercek, 'config', '--local', '--get', 'user.email').stdout.strip() == ''
