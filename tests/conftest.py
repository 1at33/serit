"""Pytest ortamı: testler yalnız geçici git depolarında çalışır, geliştiricinin git ayarına bağlanmaz.

Git kancaları (pre-push) GIT_DIR, GIT_INDEX_FILE gibi değişkenlerle çalışır. Testler bunları miras alırsa
geçici depoda sandıkları `git init`/`git config` komutları gerçek depoya uygulanır. Bu yüzden GIT_*
değişkenleri içe aktarırken temizlenir.
"""
import os
import sys
from pathlib import Path

import pytest

SRC = str(Path(__file__).resolve().parents[1] / "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

for _ad in [k for k in os.environ if k.upper().startswith("GIT_")]:
    os.environ.pop(_ad, None)


@pytest.fixture(autouse=True)
def serit_ortami(monkeypatch, tmp_path_factory):
    # Kancalar `python -m serit` çağırır; paket kurulu olmasa da src görünsün.
    eski = os.environ.get("PYTHONPATH")
    monkeypatch.setenv("PYTHONPATH", SRC + (os.pathsep + eski if eski else ""))
    for ad in ("SERIT_KAYDET", "SERIT_PUSH_TESTSIZ", "SERIT_PYTHON", "PYTEST_ADDOPTS", "PYTEST_PLUGINS"):
        monkeypatch.delenv(ad, raising=False)
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    # Geliştiricinin genel git ayarı (imzalı commit, genel hooksPath vb.) testlere karışmasın.
    genel = tmp_path_factory.mktemp("gitayar") / "gitconfig"
    genel.write_bytes(b"[user]\n\tname = Test\n\temail = test@ornek.invalid\n[init]\n\tdefaultBranch = main\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(genel))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
