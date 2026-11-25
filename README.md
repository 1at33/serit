# serit

Birden çok ajan oturumunun (ya da insanın) **aynı çalışma ağacına aynı anda** yazdığı depolar için commit
disiplini. Korunan dala (`main`) commit ve birleştirme yalnız `serit` üzerinden gider; şerit dalları serbesttir;
her commit yalnız o oturumun verdiği dosyaları içerir; başlık `tür(kapsam): özet` biçimindedir ve gövdeye
oturum satırı eklenir. Kurallar yazılı rica olarak kalmaz, git kancalarıyla zorlanır.

Yalnız standart kütüphane, Python 3.11+ ve `git`. Model çağrısı yok.

**English summary.** `serit` ("lane") is a dependency-free commit discipline for repositories that several AI
agent sessions write to concurrently in one working tree. The protected branch (default `main`) only accepts
commits made through `serit kaydet` and merges made through `serit birlestir`; lane branches (default `serit/*`)
are free. `serit kaydet` commits only the paths you list (`git commit --only`, so another session's staged
files stay staged), rejects `.`/`-A`/globs/directories, enforces `type(scope): summary` titles from a
configurable type list, appends `Oturum:` (session) and `Co-Authored-By:` lines, auto-pushes configured types,
stops on CRLF/LF flips and half-finished merges, and can run the touched folder's tests first. A pre-push gate
runs a configurable command against the *pushed commit's tree* (not the working tree) plus a health check.
`serit durum` shows pending pushes, uncommitted files (possibly other sessions') and lane branches. Docs and
identifiers are Turkish.

## Ne ve neden

Aynı klasörde birden çok ajan oturumu çalışırken tipik kazalar şunlardır: bir oturum `git add -A` ile
başkasının yarım dosyasını commit'ler; biri `main`'de elle `git merge` deneyip yarım birleştirme bırakır ve
herkesin commit'i durur; Windows'ta metin kipinde yazılan dosya bütünüyle CRLF'e döner ve diff anlamsızlaşır;
"testler geçti" denir ama push edilen commit'te testler düşer. `serit` bunları kurallarla değil, reddederek
engeller:

- **Korunan dal**: `main`'e düz `git commit` ve `git merge` kanca tarafından reddedilir.
- **Şerit dalları**: `serit/<ad>` dallarında commit serbesttir; iş bitince `serit birlestir` ile `--no-ff`
  birleştirilir. Çakışmada birleştirme geri alınır, çözüm şerit dalında yapılır.
- **Yalnız kendi dosyaların**: `serit kaydet ... -- <dosyalar>`; başka oturumun stage'i yerinde kalır.
- **İz**: her commit'in gövdesinde `Oturum: <id>`; hangi oturumun ne yazdığı `git log` ile okunur.

## Kurulum

```
pip install serit                 # yayımlandığında; şimdilik: pip install -e .
pip install -e ".[dev]"           # + pytest, ruff

cd <depon>
serit kur
serit saglik
```

`serit kur` kancaları `.git/serit/hooks/` altına yazar (çalışma ağacına bir şey eklemez), `core.hooksPath`'i oraya
çevirir, korunan dal için `branch.<dal>.mergeoptions --no-ff` ve `branch.<dal>.rebase true` ayarlar. Kancalar
kurulumdaki Python yorumlayıcısının yolunu taşır; sanal ortamı taşırsan ya da silersen `serit kur`'u yeniden
çalıştır (ya da `SERIT_PYTHON` ayarla). Başka bir `core.hooksPath` zaten ayarlıysa `kur` durur; bilerek
değiştirmek için `--zorla`. Her klonda ayrı çalıştırılır. Geri almak: `git config --unset core.hooksPath`.

## Komutlar

```
serit kur [--zorla]
serit kaydet -m "tür(kapsam): özet" [-m gövde] [--oturum <id>] [--yazar "Ad <e-posta>"]
             [--push | --push-yok] [--eol-tamam] [--test-yok "gerekçe"] -- <dosya> ...
serit birlestir <şerit dalı> -m "tür(kapsam): özet" [--oturum <id>] [--push | --push-yok]
serit durum
serit push
serit saglik
```

Hepsi `--repo <yol>` alır (varsayılan: bulunulan dizin). Çıkış kodu 0 tamam, 1 `DURDU:` ile reddedildi,
2 hatalı kullanım.

| Komut | Ne yapar |
|---|---|
| `kaydet` | Yalnız verilen yolları commit'ler (`git commit --only`). `.`, `-A`, `:/`, glob, klasör, depo kökü, depo dışı ve hiçbir yerde olmayan yol reddedilir (sonda `\r` kalmış yol sessizce elenmez). Başlık `tür(kapsam): özet`, tür `turler` listesinden. `--oturum` ve `--yazar` gövdeye satır ekler. Önce `saglik` koşar; HATA varsa commit yok. İzlenen dosya LF↔CRLF dönmüşse durur (`--eol-tamam`). Yarım birleştirmede (MERGE_HEAD) durur, `index.lock` boşalana kadar 60 sn bekler. `otomatik_push` türleri hemen push edilir; diğerleri `push_hatirlat` sayısına ulaşınca hatırlatılır. Hangi dalda olursan ol çalışır. |
| `birlestir` | Korunan daldayken şerit dalını `--no-ff` birleştirir. Çalışma ağacındaki commit'lenmemiş başka işler commit'e girmez. Çakışmada `merge --abort` ile geri alır. |
| `durum` | Bulunulan dal, push bekleyen commit sayısı, commit'lenmemiş değişiklikler (listede başka oturumun dosyaları olabilir; dokunma) ve şerit dallarının korunan dalda olmayan commit sayısı. |
| `push` | Bulunulan dalı upstream'e push eder (pre-push kapısından geçer). |
| `saglik` | Hiçbir şeyi değiştirmeden sekiz kontrol: `core.hooksPath`, üç kancanın varlığı, `mergeoptions --no-ff`, `rebase true`, MERGE_HEAD yok, `core.bare` false. |

Örnek oturum akışı:

```
git switch -c serit/arama-duzeltmesi
# ... iş, şeritte serbest commit'ler ...
git switch main
serit birlestir serit/arama-duzeltmesi -m "duzelt(arama): boş sorguda çökme" --oturum ajan/6f10190b

# ya da doğrudan main'e küçük, tek parça bir iş:
serit kaydet -m "belge(readme): kurulum adımı" --oturum ajan/6f10190b -- README.md
```

## Ayar

Depo kökünde `.serit.toml`; yoksa `pyproject.toml` içinde `[tool.serit]`; o da yoksa varsayılanlar.
Bilinmeyen anahtar ve yanlış tip hatadır (yazım hatası sessizce varsayılana düşmez). Tüm anahtarlar açıklamalı
olarak [`ornek/.serit.toml`](ornek/.serit.toml) dosyasında.

| Anahtar | Varsayılan | Anlamı |
|---|---|---|
| `korunan_dal` | `"main"` | Düz commit/merge'e kapalı dal |
| `serit_onekleri` | `["serit/"]` | Şerit dalı önekleri; `birlestir` yalnız bunları alır, `durum` bunları listeler. Boş: her dal |
| `turler` | `["ozellik", "duzelt", "belge", "test", "yeniden", "arac", "karar", "tasima"]` | Geçerli başlık türleri |
| `otomatik_push` | `[]` | Hemen push edilecek türler (ör. `["karar"]`) |
| `push_hatirlat` | `3` | Bu kadar commit push beklerse hatırlat |
| `baslik_uzun` | `72` | Başlık uzunluğu uyarı eşiği |
| `test_kapisi` | `false` | `kaydet` öncesi, verilen `.py` dosyalarının klasöründe `test_*.py` varsa o klasörde pytest |
| `test_onekleri` | `[]` | Test kapısına girecek yol önekleri; boş: hepsi |
| `push_komutu` | `[]` | Push edilen commit'in ağacında koşacak komut; `"{python}"` yorumlayıcıyla değişir. Boş: yalnız sağlık |
| `push_yollari` | `[]` | Komutu tetikleyen yol önekleri; boş: her push |
| `push_zaman_asimi` | `600` | Push komutu zaman aşımı (sn) |
| `ortam_izin` | `[]` | Push komutuna ve test kapısına geçmesine izin verilen sır adlı değişkenler. Varsayılan: adında key/token/secret/passw/credential/auth geçen her değişken çıkarılır |

Ayar çalışma ağacından okunur; şerit dalında değiştirip birleştirmeden önce korunan dalda geçerli olmaz.

## Kancalar nasıl zorlar

Üç kanca da ince birer `sh` sarmalayıcısıdır (Linux, macOS ve Windows Git Bash'te aynı) ve
`python -P -m serit kanca <ad>` çağırır; ayar tek yerden okunur.

- **pre-commit**: bulunulan dal korunan dalsa reddeder. `serit kaydet` kendi commit'ini `SERIT_KAYDET=1` ile
  yapar ve geçer. Ayrık HEAD (rebase sırasında) serbesttir. Doğmamış korunan dal da korunur; ilk commit'i
  `serit kaydet` ile at. Dal ya da ayar okunamazsa reddeder.
- **pre-merge-commit**: korunan dalda elle birleştirme commit'ini reddeder ve `git merge --abort` der. Git bu
  durumda birleştirmeyi yarım bırakır; `serit kaydet` MERGE_HEAD görünce durup aynı şeyi söyler.
- **pre-push**: `SERIT_PUSH_TESTSIZ='gerekçe'` verilmişse gerekçeyi yazıp geçer. Değilse her push edilen commit
  için (silmeler ve aynı commit'e giden ikinci ref atlanır) `push_komutu` varsa: commit'in ağacını
  `git archive` ile geçici dizine açar ve komutu orada, `GIT_*` değişkenleri temizlenmiş ortamda koşar;
  böylece kirli çalışma ağacı sonucu etkilemez ve komutun içindeki `git init`/`git config` gerçek depoya
  bulaşmaz. `push_yollari` doluysa ve değişen hiçbir yol eşleşmiyorsa komut atlanır; yeni dal, yerelde
  bulunmayan uzak commit (ör. başkasının force-push'u) ya da diff hatası her zaman tam kapıya düşer (fail-closed). Ardından
  `saglik`; HATA varsa push reddedilir.
- `branch.<dal>.rebase true`: korunan dalda `git pull` birleştirme commit'i yerine rebase yapar; kanca
  rebase'i engellemez.

## Sınırlar

- Kancalar bir **ajan davranış korkuluğudur**, güvenlik sınırı değildir. `git commit --no-verify`,
  `SERIT_KAYDET=1 git commit`, `git cherry-pick`/`revert` (pre-commit koşmaz), `git commit-tree` ve
  `git update-ref` kancayı atlar. Sunucu tarafında korumalı dal kuralıyla birlikte kullan.
- Kancalar yalnız `serit kur` çalıştırılmış klonda etkindir; kurulum klonlanınca taşınmaz.
- Aynı çalışma ağacı paylaşıldığı için iki oturum **aynı dosyayı** aynı anda düzenlerse `serit` bunu çözmez;
  yalnız birinin dosyasının ötekinin commit'ine sızmasını önler. Ağır paralel kod işinde oturum başına
  `git worktree` daha uygundur; `serit` worktree'lerde de çalışır (kancalar ortak git dizinindedir).
- `push_komutu` depodaki ayardan gelir ve push sırasında çalışır: depodaki herhangi bir betik kadar güvenilirdir.
  Komuta ve testlere giden ortamdan `GIT_*` ve adı sır kuralına uyan değişkenler (API anahtarı, token, parola)
  çıkarılır; gerekenleri `ortam_izin` ile açın. Komut yine de yalıtılmış değildir (dosya sistemine erişir). Başkasından klonladığınız bir depoda `serit kur` yapmadan önce `.serit.toml`'u okuyun.
- Push komutu tüm ağacın arşiviyle çalışır; çok büyük depolarda yavaş olabilir.
- Windows'ta kancalar Git for Windows'un `sh`'ı ile çalışır; yalnız `cmd`/PowerShell olan ortam desteklenmez.

## Lisans

MIT. Bkz. [LICENSE](LICENSE).
