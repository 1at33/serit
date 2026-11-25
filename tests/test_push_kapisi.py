"""pre-push kapısı: push edilen commit'in ağacında push_komutu, sonra sağlık.

Her test geçici bir depo kurar (çıplak uzak + serit kancaları + küçük `kod/` paketi) ve gerçek kancayı
`git push` ile koşturur. Hazırlık push'ları `--no-verify` ile yapılır: uzak durumu kasten düşen testle
kurmak için kapı atlanır; sınanan push'lar her zaman kapıdan geçer.
"""
import os

import pytest
from yardimci import commit, depo_kur, g, git_sonuc, kanca_kos

from serit.kanca import ATLANDI, KACIS_DEGISKENI

GECEN = b'def test_kapi():\n    assert True\n'
DUSEN = b'def test_kapi():\n    assert False\n'
AYAR = '''push_komutu = ["{python}", "-m", "pytest", "kod", "-q", "-p", "no:cacheprovider"]
push_yollari = ["kod/", "pyproject.toml"]
'''


def push(repo, *refspecs, kacis=None):
    env = {k: v for k, v in os.environ.items() if k != KACIS_DEGISKENI}
    if kacis is not None:
        env[KACIS_DEGISKENI] = kacis
    return git_sonuc(repo, 'push', 'origin', *refspecs, env=env)


def kurulum_push(repo, *refspecs):
    """Uzak durumu hazırlar; pre-push kapısı bu çağrıda atlanır (--no-verify)."""
    g(repo, 'push', '--no-verify', '-q', 'origin', *refspecs)


def sha(repo, rev='HEAD'):
    return g(repo, 'rev-parse', rev).strip()


def uzak_sha(repo, dal):
    satir = g(repo, 'ls-remote', 'origin', f'refs/heads/{dal}').strip()
    return satir.split()[0] if satir else ''


@pytest.fixture
def push_repo(tmp_path):
    r = depo_kur(tmp_path, ayar=AYAR)
    g(r, 'checkout', '-qb', 'serit/push')
    commit(r, 'push testi', {'kod/test_kapi.py': GECEN, 'pyproject.toml': b'[project]\nname = "x"\n'})
    return r


def test_dusen_test_reddeder(push_repo):
    repo = push_repo
    r = push(repo, 'HEAD:refs/heads/ana')
    assert r.returncode == 0, r.stderr
    base = uzak_sha(repo, 'ana')
    commit(repo, 'kod testi düşer', {'kod/test_kapi.py': DUSEN})
    r = push(repo, 'HEAD:refs/heads/ana')
    assert r.returncode != 0
    assert 'DURDU:' in r.stderr and '1 failed' in r.stderr
    assert f"{KACIS_DEGISKENI}='gerekçe' git push" in r.stderr
    assert uzak_sha(repo, 'ana') == base


def test_gecen_test_ile_push_basarili(push_repo):
    repo = push_repo
    assert push(repo, 'HEAD:refs/heads/ana').returncode == 0
    commit(repo, 'yeni modül, test geçer', {'kod/yeni_modul.py': b'deger = 1\n'})
    r = push(repo, 'HEAD:refs/heads/ana')
    assert r.returncode == 0, r.stderr
    assert 'DURDU:' not in r.stderr
    assert uzak_sha(repo, 'ana') == sha(repo)


@pytest.mark.parametrize('yol', ['kod/yeni_modul.py', 'kod/alt/yardimci.py', 'pyproject.toml'])
def test_izlenen_yol_tek_basina_tam_kapiyi_tetikler(push_repo, yol):
    repo = push_repo
    # Uzakta zaten düşen test var; sınanan push yalnız `yol` dosyasını değiştirir.
    commit(repo, 'kasıtlı düşen test', {'kod/test_kapi.py': DUSEN})
    kurulum_push(repo, 'HEAD:refs/heads/ana')
    base = uzak_sha(repo, 'ana')
    commit(repo, 'yalnız izlenen yol', {yol: b'degisti = 1\n'})
    r = push(repo, 'HEAD:refs/heads/ana')
    assert r.returncode != 0
    assert 'DURDU:' in r.stderr and '1 failed' in r.stderr
    assert ATLANDI not in r.stderr
    assert uzak_sha(repo, 'ana') == base


def test_izlenmeyen_yol_komutu_atlar(push_repo):
    repo = push_repo
    # Düşen test uzakta ve HEAD ağacında; komut koşsaydı push başarısız olurdu.
    commit(repo, 'kasıtlı düşen test', {'kod/test_kapi.py': DUSEN})
    kurulum_push(repo, 'HEAD:refs/heads/ana')
    commit(repo, 'yalnız belge', {'belgeler/x.md': b'not\n'})
    r = push(repo, 'HEAD:refs/heads/ana')
    assert r.returncode == 0, r.stderr
    assert ATLANDI in r.stderr and '1 failed' not in r.stderr
    assert uzak_sha(repo, 'ana') == sha(repo)


def test_izlenmeyen_yol_saglik_dusunce_reddeder(push_repo):
    repo = push_repo
    assert push(repo, 'HEAD:refs/heads/ana').returncode == 0
    base = uzak_sha(repo, 'ana')
    g(repo, 'config', 'branch.main.rebase', 'false')
    commit(repo, 'sağlık bozuk', {'belgeler/x.md': b'not\n'})
    r = push(repo, 'HEAD:refs/heads/ana')
    assert r.returncode != 0
    assert 'DURDU:' in r.stderr and 'HATA: branch.main.rebase' in r.stderr
    assert uzak_sha(repo, 'ana') == base


def test_yeni_dal_izlenmeyen_degisiklikte_de_tam_kapi(push_repo):
    repo = push_repo
    commit(repo, 'kasıtlı düşen test', {'kod/test_kapi.py': DUSEN})
    commit(repo, 'yalnız belge', {'belgeler/x.md': b'not\n'})
    r = push(repo, 'HEAD:refs/heads/yeni')
    assert r.returncode != 0
    assert 'DURDU:' in r.stderr and '1 failed' in r.stderr
    assert uzak_sha(repo, 'yeni') == ''


def test_gerekceli_kacis_calisir(push_repo):
    repo = push_repo
    commit(repo, 'kasıtlı düşen test', {'kod/test_kapi.py': DUSEN})
    r = push(repo, 'HEAD:refs/heads/kacis', kacis='acil kurtarma')
    assert r.returncode == 0, r.stderr
    assert 'gerekçe: acil kurtarma' in r.stderr
    assert uzak_sha(repo, 'kacis') == sha(repo)


def test_uzak_dal_silme_testsiz_gecer(push_repo):
    repo = push_repo
    commit(repo, 'kasıtlı düşen test', {'kod/test_kapi.py': DUSEN})
    kurulum_push(repo, 'HEAD:refs/heads/dal')
    r = push(repo, ':dal')
    assert r.returncode == 0, r.stderr
    assert 'DURDU:' not in r.stderr
    assert uzak_sha(repo, 'dal') == ''


def test_ayni_pushta_izlenen_yol_refi_tum_pushu_reddeder(push_repo):
    repo = push_repo
    base = sha(repo)
    kurulum_push(repo, 'HEAD:refs/heads/a', 'HEAD:refs/heads/b')
    commit(repo, 'yalnız belge', {'belgeler/x.md': b'not\n'})
    kod_disi = sha(repo)
    g(repo, 'checkout', '-q', '--detach', base)
    commit(repo, 'kasıtlı düşen test', {'kod/test_kapi.py': DUSEN})
    kod_yolu = sha(repo)
    r = git_sonuc(repo, 'push', 'origin', f'{kod_disi}:refs/heads/a', f'{kod_yolu}:refs/heads/b')
    assert r.returncode != 0
    assert 'DURDU:' in r.stderr and '1 failed' in r.stderr
    assert uzak_sha(repo, 'a') == base
    assert uzak_sha(repo, 'b') == base


def test_push_edilen_commit_sinanir_calisma_agaci_degil(push_repo):
    repo = push_repo
    (repo / 'kod/test_kapi.py').write_bytes(DUSEN)
    # Commit dışında bozuk, hatta toplanamayan dosya da sonucu etkilemez.
    (repo / 'kod/test_baskasi.py').write_bytes(b'gecersiz python !\n')
    r = push(repo, 'HEAD:refs/heads/gecen')
    assert r.returncode == 0, r.stderr
    assert uzak_sha(repo, 'gecen') == sha(repo)
    assert not list(repo.rglob('__pycache__'))
    commit(repo, 'düşen test', {'kod/test_kapi.py': DUSEN})
    (repo / 'kod/test_kapi.py').write_bytes(GECEN)  # ağaç iyi görünse de push edilen commit bozuk
    (repo / 'kod/test_baskasi.py').unlink()
    r = push(repo, 'HEAD:refs/heads/dusen')
    assert r.returncode != 0 and '1 failed' in r.stderr
    assert uzak_sha(repo, 'dusen') == ''


def test_git_ortamini_temizler(push_repo, monkeypatch):
    repo = push_repo
    commit(repo, 'ortam koruması', {'kod/test_kapi.py': (
        b'import os, subprocess\nfrom pathlib import Path\ndef test_kapi():\n'
        b'    tmp_path = Path(__file__).parent / "gecici"\n'
        b'    tmp_path.mkdir()\n'
        b'    subprocess.run(["git", "init", "-q", "--bare", str(tmp_path / "u.git")], check=True)\n'
        b'    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)\n'
        b'    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "bulasma@ornek.invalid"], check=True)\n'
        b'    assert not any(k.upper().startswith("GIT_") for k in os.environ)\n')})
    once = (repo / '.git/config').read_bytes()
    with monkeypatch.context() as m:
        m.setenv('GIT_DIR', str(repo / '.git'))  # worktree push'ındaki mutlak yol
        m.setenv('GIT_CONFIG_COUNT', '1')
        m.setenv('GIT_CONFIG_KEY_0', 'probe.sentinel')
        m.setenv('GIT_CONFIG_VALUE_0', 'ilk\nGIT_SAHte_9=ikinci')
        m.setenv('GIT_ozel_9', 'deneme')
        r = push(repo, 'HEAD:refs/heads/temiz-ortam')
    assert r.returncode == 0, r.stderr
    assert (repo / '.git/config').read_bytes() == once
    assert g(repo, 'config', '--get', 'core.bare').strip() == 'false'


def test_ayni_sha_bir_kez_silme_atlanir_ve_tmp_temizlenir(push_repo, tmp_path, monkeypatch):
    repo = push_repo
    sayac = tmp_path / 'sayac'
    monkeypatch.setenv('SERIT_TEST_SAYAC', str(sayac))
    gecici = tmp_path / 'kanca-tmp'
    gecici.mkdir()
    for ad in ('TMPDIR', 'TMP', 'TEMP'):
        monkeypatch.setenv(ad, str(gecici))
    commit(repo, 'sayaç', {'kod/test_kapi.py': (
        b'import os\nfrom pathlib import Path\ndef test_kapi():\n'
        b'    p = Path(os.environ["SERIT_TEST_SAYAC"])\n'
        b'    p.write_bytes(p.read_bytes() + b"x" if p.exists() else b"x")\n')})
    r = push(repo, 'HEAD:refs/heads/bir', 'HEAD:refs/heads/iki')
    assert r.returncode == 0, r.stderr
    assert sayac.read_bytes() == b'x'
    assert list(gecici.iterdir()) == []
    r = push(repo, ':refs/heads/bir')
    assert r.returncode == 0, r.stderr
    assert sayac.read_bytes() == b'x'
    g(repo, 'config', 'branch.main.rebase', 'false')
    assert push(repo, 'HEAD:refs/heads/uc').returncode != 0
    assert list(gecici.iterdir()) == []


def test_izlenen_dosya_disari_tasinirsa_tam_kapi(push_repo):
    repo = push_repo
    commit(repo, 'düşen test + modül', {'kod/test_kapi.py': DUSEN, 'kod/tasinan.py': b'x = 1\n'})
    kurulum_push(repo, 'HEAD:refs/heads/tasi')
    (repo / 'belgeler').mkdir()
    g(repo, 'mv', 'kod/tasinan.py', 'belgeler/tasinan.py')
    g(repo, 'commit', '-qm', 'taşıma')
    r = push(repo, 'HEAD:refs/heads/tasi')
    assert r.returncode != 0 and 'DURDU:' in r.stderr and '1 failed' in r.stderr
    assert ATLANDI not in r.stderr


def test_cozulemeyen_uzak_sha_tam_kapi(push_repo):
    repo = push_repo
    commit(repo, 'düşen test', {'kod/test_kapi.py': DUSEN})
    satir = f'refs/heads/x {sha(repo)} refs/heads/x {"ab" * 20}\n'
    r = kanca_kos(repo, 'pre-push', satir)
    assert r.returncode != 0 and 'DURDU:' in r.stderr and '1 failed' in r.stderr
    assert ATLANDI not in r.stderr


def test_force_push_ata_olmayan_uzak_commit_tam_kapi(push_repo):
    repo = push_repo
    taban = sha(repo)
    commit(repo, 'belge', {'belgeler/x.md': b'not\n'})
    kurulum_push(repo, 'HEAD:refs/heads/ayri')
    g(repo, 'checkout', '-q', '--detach', taban)
    commit(repo, 'düşen test', {'kod/test_kapi.py': DUSEN})
    r = push(repo, '--force', 'HEAD:refs/heads/ayri')
    assert r.returncode != 0 and 'DURDU:' in r.stderr and '1 failed' in r.stderr
    assert ATLANDI not in r.stderr


def test_push_komutu_yoksa_yalniz_saglik(tmp_path):
    repo = depo_kur(tmp_path)
    g(repo, 'checkout', '-qb', 'serit/x')
    commit(repo, 'düşen test', {'kod/test_kapi.py': DUSEN})
    r = push(repo, 'HEAD:refs/heads/x')
    assert r.returncode == 0, r.stderr
    g(repo, 'config', 'branch.main.rebase', 'false')
    commit(repo, 'ikinci', {'b.md': b'b\n'})
    r = push(repo, 'HEAD:refs/heads/x')
    assert r.returncode != 0 and 'HATA: branch.main.rebase' in r.stderr


def test_bozuk_ayar_pushu_durdurur(push_repo):
    (push_repo / '.serit.toml').write_text('push_komutu = "tek metin"\n', encoding='utf-8')
    r = push(push_repo, 'HEAD:refs/heads/bozuk')
    assert r.returncode != 0 and 'push_komutu' in r.stderr
