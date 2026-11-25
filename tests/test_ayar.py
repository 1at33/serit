import pytest

from serit.ayar import AYAR_DOSYASI, VARSAYILAN_TURLER, Ayar, ayar_kur, ayar_oku
from serit.gitci import Hata


def test_dosya_yoksa_varsayilan(tmp_path):
    ayar = ayar_oku(tmp_path)
    assert ayar == Ayar()
    assert ayar.korunan_dal == 'main' and ayar.serit_onekleri == ('serit/',)
    assert ayar.turler == VARSAYILAN_TURLER and ayar.otomatik_push == ()
    assert not ayar.test_kapisi and ayar.push_komutu == ()


def test_serit_toml_okunur(tmp_path):
    (tmp_path / AYAR_DOSYASI).write_text(
        'korunan_dal = "trunk"\nserit_onekleri = ["ajan/", "is/"]\nturler = ["is", "karar"]\n'
        'otomatik_push = ["karar"]\npush_hatirlat = 5\n', encoding='utf-8')
    ayar = ayar_oku(tmp_path)
    assert ayar.korunan_dal == 'trunk' and ayar.serit_onekleri == ('ajan/', 'is/')
    assert ayar.turler == ('is', 'karar') and ayar.otomatik_push == ('karar',)
    assert ayar.push_hatirlat == 5 and ayar.kaynak == AYAR_DOSYASI


def test_pyproject_tool_serit_okunur_serit_toml_oncelikli(tmp_path):
    (tmp_path / 'pyproject.toml').write_text('[project]\nname = "x"\n[tool.serit]\nkorunan_dal = "ana"\n',
                                             encoding='utf-8')
    assert ayar_oku(tmp_path).korunan_dal == 'ana'
    assert 'pyproject.toml' in ayar_oku(tmp_path).kaynak
    (tmp_path / AYAR_DOSYASI).write_text('korunan_dal = "trunk"\n', encoding='utf-8')
    assert ayar_oku(tmp_path).korunan_dal == 'trunk'


def test_tool_serit_olmayan_pyproject_varsayilan(tmp_path):
    (tmp_path / 'pyproject.toml').write_text('[project]\nname = "x"\n', encoding='utf-8')
    assert ayar_oku(tmp_path) == Ayar()


@pytest.mark.parametrize('tablo, eslesme', [
    ({'korunan_dalx': 'main'}, 'bilinmeyen anahtar'),
    ({'korunan_dal': ''}, 'korunan_dal'),
    ({'korunan_dal': 'iki kelime'}, 'korunan_dal'),
    ({'serit_onekleri': 'serit/'}, 'serit_onekleri'),
    ({'turler': []}, 'turler boş'),
    ({'turler': ['Buyuk']}, 'tür adı'),
    ({'turler': ['a', 'a']}, 'tekrarlı'),
    ({'otomatik_push': ['karar'], 'turler': ['is']}, 'otomatik_push'),
    ({'push_hatirlat': 0}, 'push_hatirlat'),
    ({'push_hatirlat': True}, 'push_hatirlat'),
    ({'test_kapisi': 'evet'}, 'test_kapisi'),
    ({'push_komutu': ['pytest', 3]}, 'push_komutu'),
])
def test_hatali_ayar_reddedilir(tablo, eslesme):
    with pytest.raises(Hata, match=eslesme):
        ayar_kur(tablo)


def test_bozuk_toml_reddedilir(tmp_path):
    (tmp_path / AYAR_DOSYASI).write_text('korunan_dal = \n', encoding='utf-8')
    with pytest.raises(Hata, match='okunamadı'):
        ayar_oku(tmp_path)


def test_ornek_ayar_dosyasi_gecerli():
    from pathlib import Path
    ornek = Path(__file__).resolve().parents[1] / 'ornek'
    ayar = ayar_oku(ornek)
    assert ayar.kaynak == AYAR_DOSYASI and ayar.korunan_dal == 'main'


def test_sirsiz_ortam_sirlari_cikarir_izinliyi_korur(monkeypatch):
    from serit.gitci import sirsiz_ortam
    monkeypatch.setenv("ORNEK_API_KEY", "x1")
    monkeypatch.setenv("BENIM_TOKEN", "x2")
    monkeypatch.setenv("GIT_DIR", "/yok")
    monkeypatch.setenv("NORMAL_DEGISKEN", "x3")
    env = sirsiz_ortam(["BENIM_TOKEN"])
    assert "ORNEK_API_KEY" not in env and "GIT_DIR" not in env
    assert env["BENIM_TOKEN"] == "x2" and env["NORMAL_DEGISKEN"] == "x3"


def test_ortam_izin_ayari_okunur():
    from serit.ayar import ayar_kur
    assert ayar_kur({"ortam_izin": ["A_TOKEN"]}).ortam_izin == ("A_TOKEN",)
