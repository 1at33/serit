"""serit komut satırı.

    serit kur [--zorla]
    serit kaydet -m "tür(kapsam): özet" [-m gövde] [--oturum <id>] [--yazar "Ad <e-posta>"]
                 [--push | --push-yok] [--eol-tamam] [--test-yok "gerekçe"] -- <dosyalar>
    serit birlestir <dal> -m "tür(kapsam): özet" [--oturum <id>] [--push | --push-yok]
    serit durum | push | saglik
"""
import argparse
import sys
from pathlib import Path

from . import __version__
from .gitci import Hata, kok
from .kanca import KANCA_ISLEVLERI
from .kaydet import birlestir, durum, kaydet, pushla
from .kurulum import kur, saglik


def _ortak(p):
    p.add_argument('--repo', type=Path, default=Path('.'), help='depo yolu (varsayılan: bulunulan dizin)')


def _mesaj_secenekleri(p):
    p.add_argument('-m', '--mesaj', action='append', required=True,
                   help='"tür(kapsam): özet"; git gibi tekrarlanabilir (paragraf)')
    p.add_argument('--oturum', help='oturum kimliği, ör. ajan/6f10190b; commit gövdesine "Oturum:" satırı')
    p.add_argument('--yazar', help='Co-Authored-By satırı, ör. "Ajan <ajan@ornek.invalid>"')
    grup = p.add_mutually_exclusive_group()
    grup.add_argument('--push', dest='push', action='store_true', default=None, help='türden bağımsız push et')
    grup.add_argument('--push-yok', dest='push', action='store_false', help='otomatik push türünde bile etme')


def parser_kur():
    parser = argparse.ArgumentParser(prog='serit', description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--surum', action='version', version=f'serit {__version__}')
    alt = parser.add_subparsers(dest='komut', required=True, metavar='komut')

    p = alt.add_parser('kur', help='kancaları etkinleştir, korunan dal ayarlarını yap')
    p.add_argument('--zorla', action='store_true', help='başka bir core.hooksPath ayarının üzerine yaz')
    _ortak(p)

    p = alt.add_parser('kaydet', help='yalnız verilen dosyaları commit\'le')
    _mesaj_secenekleri(p)
    p.add_argument('--eol-tamam', action='store_true', help='satır sonu değişikliği bilerek yapıldı')
    p.add_argument('--test-yok', help='test kapısını gerekçeyle atla; gerekçe commit gövdesine yazılır')
    p.add_argument('yollar', nargs='*')
    _ortak(p)

    p = alt.add_parser('birlestir', help='şerit dalını korunan dala --no-ff birleştir')
    p.add_argument('dal')
    _mesaj_secenekleri(p)
    _ortak(p)

    for ad, yardim in (('durum', 'push bekleyenler, commit\'lenmemiş dosyalar, şerit dalları'),
                       ('push', 'bulunulan dalı upstream\'e push et'),
                       ('saglik', 'kurulumu değiştirmeden denetle')):
        _ortak(alt.add_parser(ad, help=yardim))

    p = alt.add_parser('kanca', help='git kancalarının iç girişi')
    p.add_argument('ad', choices=sorted(KANCA_ISLEVLERI))
    p.add_argument('kanca_argumanlari', nargs='*')
    return parser


def _durum_yaz(d):
    print(f"Dal: {d['dal'] or '(ayrık HEAD)'} (korunan: {d['korunan_dal']})")
    print(f"Push bekleyen commit: {d['push_bekleyen']}")
    print('Commit\'lenmemiş değişiklikler (başka oturumun olabilir; kendinin değilse ekleme):')
    print('\n'.join('  ' + x for x in d['bekleyen_degisiklik']) or '  (yok)')
    print(f"Şerit dalları ({d['korunan_dal']} dalında olmayan commit):")
    print('\n'.join(f'  {dal}: {"?" if n is None else n}' for dal, n in d['seritler']) or '  (yok)')


def _sonuc_yaz(s):
    if s.get('uyari'):
        print('UYARI:', s['uyari'])
    if s.get('testler'):
        print('Testler:', s['testler'])
    if not s['commit']:
        print(s['not'])
        return 0
    print(f"Commit: {s['commit']} ({len(s['dosyalar'])} dosya)")
    for name in s['dosyalar']:
        print('  ' + name)
    if s['push']:
        print(f"Push: {s['push']}")
    if s.get('hatirlat'):
        print(s['hatirlat'])
    return 0 if not s['push'] or s['push'] == 'tamam' else 1


def main(argv=None):
    for kanal in (sys.stdout, sys.stderr):
        if hasattr(kanal, 'reconfigure'):
            kanal.reconfigure(encoding='utf-8')
    a = parser_kur().parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if a.komut == 'kanca':
            return KANCA_ISLEVLERI[a.ad]()
        if a.komut == 'kur':
            s = kur(a.repo, zorla=a.zorla)
            for u in s['uyarilar']:
                print('UYARI:', u)
            print('core.hooksPath =', s['kanca_dizini'])
            print(f"Korunan dal: {s['korunan_dal']} (mergeoptions --no-ff, rebase true)")
            return 0
        if a.komut == 'saglik':
            d = saglik(a.repo)
            print('\n'.join(d['satirlar']))
            return int(not d['tamam'])
        if a.komut == 'durum':
            _durum_yaz(durum(a.repo))
            return 0
        if a.komut == 'push':
            sonuc = pushla(kok(a.repo))
            print('Push:', sonuc)
            return 0 if sonuc == 'tamam' else 1
        if a.komut == 'birlestir':
            s = birlestir(a.repo, a.dal, a.mesaj, a.oturum, a.yazar, a.push)
        else:
            s = kaydet(a.repo, a.mesaj, a.yollar, a.oturum, a.push, a.eol_tamam, a.yazar, test_yok=a.test_yok)
    except Hata as exc:
        print(f'DURDU: {exc}', file=sys.stderr)
        return 1
    return _sonuc_yaz(s)
