import subprocess
import sys

import pytest
from yardimci import depo_kur, g

from serit import __version__, cli


@pytest.fixture
def repo(tmp_path):
    return depo_kur(tmp_path)


def test_kaydet_cli_cift_tire_ve_cikti(repo, capsys):
    (repo / 'b.md').write_bytes(b'b\n')
    (repo / 'c.md').write_bytes(b'c\n')
    kod = cli.main(['kaydet', '--repo', str(repo), '-m', 'belge(cli): iki dosya', '-m', 'gövde paragrafı',
                    '--oturum', 'ajan/1', '--', 'b.md', 'c.md'])
    assert kod == 0
    cikti = capsys.readouterr().out
    assert 'Commit:' in cikti and '(2 dosya)' in cikti
    assert g(repo, 'show', '--name-only', '--format=', 'HEAD').split() == ['b.md', 'c.md']
    govde = g(repo, 'log', '-1', '--format=%B')
    assert 'gövde paragrafı' in govde and 'Oturum: ajan/1' in govde


def test_kaydet_cli_hata_durdu_yazar(repo, capsys):
    assert cli.main(['kaydet', '--repo', str(repo), '-m', 'serbest', '--', 'a.md']) == 1
    assert 'DURDU:' in capsys.readouterr().err


def test_kaydet_cli_mesajsiz_argparse_hatasi(repo):
    with pytest.raises(SystemExit) as exc:
        cli.main(['kaydet', '--repo', str(repo), '--', 'a.md'])
    assert exc.value.code == 2


def test_test_yok_gerekcesi_cliden_iletilir(tmp_path):
    repo = depo_kur(tmp_path, ayar='test_kapisi = true\n')
    (repo / 'kod').mkdir()
    (repo / 'kod/mod.py').write_bytes(b'deger = 1\n')
    (repo / 'kod/test_mod.py').write_bytes(b'def test_mod():\n    assert False\n')
    assert cli.main(['kaydet', '--repo', str(repo), '-m', 'arac: acil', '--test-yok', 'acil',
                     '--', 'kod/mod.py']) == 0
    assert 'Test atlandı: acil' in g(repo, 'log', '-1', '--format=%B')


def test_birlestir_ve_durum_cli(repo, capsys):
    g(repo, 'checkout', '-qb', 'serit/bir')
    (repo / 'y.md').write_bytes(b'y\n')
    g(repo, 'add', 'y.md')
    g(repo, 'commit', '-qm', 'tur 1')
    g(repo, 'checkout', '-q', 'main')
    assert cli.main(['durum', '--repo', str(repo)]) == 0
    cikti = capsys.readouterr().out
    assert 'serit/bir: 1' in cikti and 'Push bekleyen commit: 0' in cikti
    assert cli.main(['birlestir', 'serit/bir', '--repo', str(repo), '-m', 'arac: birleştir', '--push']) == 0
    assert 'Push: tamam' in capsys.readouterr().out
    assert cli.main(['durum', '--repo', str(repo)]) == 0
    assert 'serit/bir: 0' in capsys.readouterr().out


def test_modul_olarak_calisir_ve_surum():
    r = subprocess.run([sys.executable, '-m', 'serit', '--surum'], capture_output=True, text=True, check=False)
    assert r.returncode == 0 and __version__ in r.stdout
