"""Ayar: depo kökünde `.serit.toml`, yoksa `pyproject.toml` içindeki `[tool.serit]`, yoksa varsayılanlar."""
import re
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

from .gitci import Hata

AYAR_DOSYASI = '.serit.toml'
TUR_ADI = re.compile(r'^[a-z][a-z0-9-]*$')
VARSAYILAN_TURLER = ('ozellik', 'duzelt', 'belge', 'test', 'yeniden', 'arac', 'karar', 'tasima')


@dataclass(frozen=True)
class Ayar:
    korunan_dal: str = 'main'
    serit_onekleri: tuple = ('serit/',)
    turler: tuple = VARSAYILAN_TURLER
    otomatik_push: tuple = ()
    push_hatirlat: int = 3
    baslik_uzun: int = 72
    test_kapisi: bool = False
    test_onekleri: tuple = ()
    push_komutu: tuple = ()
    push_yollari: tuple = ()
    push_zaman_asimi: int = 600
    ortam_izin: tuple = ()
    kaynak: str = 'varsayılan'


_TURLER = {f.name: f.type for f in fields(Ayar) if f.name != 'kaynak'}


def _deger(ad, deger, kaynak):
    tur = _TURLER[ad]
    if tur is str:
        if not isinstance(deger, str) or not deger.strip() or any(c.isspace() for c in deger):
            raise Hata(f'{kaynak}: {ad} boşluksuz, boş olmayan bir metin olmalı.')
        return deger
    if tur is bool:
        if not isinstance(deger, bool):
            raise Hata(f'{kaynak}: {ad} true ya da false olmalı.')
        return deger
    if tur is int:
        if isinstance(deger, bool) or not isinstance(deger, int) or deger < 1:
            raise Hata(f'{kaynak}: {ad} pozitif tam sayı olmalı.')
        return deger
    if not isinstance(deger, list) or not all(isinstance(x, str) and x for x in deger):
        raise Hata(f'{kaynak}: {ad} boş olmayan metinlerden oluşan bir liste olmalı.')
    return tuple(deger)


def ayar_kur(tablo, kaynak='ayar'):
    """Bir TOML tablosundan doğrulanmış Ayar üretir; bilinmeyen anahtar yazım hatası sayılır."""
    if not isinstance(tablo, dict):
        raise Hata(f'{kaynak}: ayar bir tablo olmalı.')
    bilinmeyen = sorted(set(tablo) - set(_TURLER))
    if bilinmeyen:
        raise Hata(f'{kaynak}: bilinmeyen anahtar: {", ".join(bilinmeyen)}. Geçerli: {", ".join(_TURLER)}.')
    degerler = {ad: _deger(ad, deger, kaynak) for ad, deger in tablo.items()}
    ayar = Ayar(**degerler, kaynak=kaynak)
    if not ayar.turler:
        raise Hata(f'{kaynak}: turler boş olamaz.')
    hatali = [t for t in ayar.turler if not TUR_ADI.match(t)]
    if hatali:
        raise Hata(f'{kaynak}: tür adı küçük harf, rakam ve tireden oluşmalı: {", ".join(hatali)}')
    if len(set(ayar.turler)) != len(ayar.turler):
        raise Hata(f'{kaynak}: turler tekrarlı.')
    disari = [t for t in ayar.otomatik_push if t not in ayar.turler]
    if disari:
        raise Hata(f'{kaynak}: otomatik_push turler listesinde olmayan tür içeriyor: {", ".join(disari)}')
    return ayar


def _toml(dosya):
    try:
        return tomllib.loads(dosya.read_text(encoding='utf-8'))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise Hata(f'{dosya.name} okunamadı: {exc}') from exc


def ayar_oku(root):
    root = Path(root)
    dosya = root / AYAR_DOSYASI
    if dosya.is_file():
        return ayar_kur(_toml(dosya), AYAR_DOSYASI)
    proje = root / 'pyproject.toml'
    if proje.is_file():
        tablo = _toml(proje).get('tool', {}).get('serit')
        if tablo is not None:
            return ayar_kur(tablo, 'pyproject.toml [tool.serit]')
    return Ayar()
