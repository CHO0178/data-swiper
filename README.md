# Data Swiper: ruční klasifikace PDF

MVP pro prohlížení PDF v mobilním prohlížeči a binární rozhodnutí nad **celým dokumentem**. Vlevo znamená `0`, vpravo `1`. Po každém rozhodnutí se ihned uloží CSV a otevře další nerozhodnutý dokument. Při návratu se původní výsledek přepíše.

## Instalace na Raspberry Pi

Použijte 64bitový Raspberry Pi OS s Pythonem **3.11 nebo novějším**. Ověřte přímo na Pi:

```bash
python3 --version
uname -m  # očekává se aarch64
```

V kořeni repozitáře:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Pro spuštění testů navíc:

```bash
python -m pip install -e '.[test]'
python -m pytest -q
```

`requirements.txt` nainstaluje tento projekt v editovatelném režimu; přesné běhové závislosti jsou uvedené na jednom místě v `pyproject.toml`. Webový klient Flet se stahuje jako oficiální wheel z PyPI s SHA-256, protože zdejší piwheels mirror poskytoval wheel bez webových souborů. FastAPI je připnuté na kompatibilní verzi: novější 0.162.0 způsobilo při startu Fletu chybu `openapi_prefix`.

## Spuštění

Repozitář obsahuje dvě ukázková PDF ve složce `documents`; po vyzkoušení do ní můžete zkopírovat vlastní soubory. Výstupní složka pro CSV vznikne automaticky při prvním rozhodnutí. Nová PDF jsou ignorována pravidlem `*.pdf`; ukázky již uložené v Gitu tím zůstanou sledované a změny v nich je třeba při budoucím commitu výslovně vynechat. Příklad pro Raspberry Pi v domácí síti:

```bash
PDF_REVIEW_DOCUMENTS=/home/pi/documents \
PDF_REVIEW_RESULTS=/home/pi/results/results.csv \
PDF_REVIEW_RECURSIVE=true \
PDF_REVIEW_HOST=0.0.0.0 \
PDF_REVIEW_PORT=8000 \
FLET_FORCE_WEB_SERVER=true \
python main.py
```

Na telefonu ve stejné síti otevřete `http://<IP-adresa-Pi>:8000`. IP adresu zjistíte příkazem `hostname -I`. Výchozí host je `127.0.0.1`, port `8000`, složka `documents`, rekurze vypnutá a výstup `results/results.csv` relativně k pracovnímu adresáři. Poslouchání na `0.0.0.0` zapínejte pouze záměrně. Pro vzdálený přístup použijte VPN, například Tailscale; aplikace nemá přihlášení a nemá být přímo vystavena internetu.

Pro vývoj lze použít i dynamický Flet server s obnovou při změnách:

```bash
PDF_REVIEW_HOST=0.0.0.0 PDF_REVIEW_PORT=8000 \
flet run --web --host '*' --port 8000 main.py
```

`flet run` je vývojový režim. Pro běžný provoz použijte `python main.py` pod správcem služby; Flet pro dynamický web používá ASGI/Uvicorn. Nastavte pracovní adresář služby na kořen projektu a jeden serverový proces pro daný CSV soubor.

## Ovládání

- Na PDF použijte dva prsty k přiblížení a po přiblížení obraz posouvejte. Tlačítka **Přiblížit**, **Oddálit** a **Obnovit zoom** jsou také dostupná. **Vyšší kvalita** znovu vykreslí aktuální stránku v 200 DPI.
- Tlačítka **◀ Stránka** / **Stránka ▶** mění stránku PDF; nerozhodují o klasifikaci.
- Tlačítka **← 0** a **1 →** zůstávají dostupná i při zoomu.
- Při základním zoomu klasifikuje vodorovný tah alespoň 90 px přes PDF vlevo/vpravo, pokud výrazně převáží nad svislým pohybem. Stejné gesto je dostupné v modrém pruhu pod obrázkem. Po zoomu je klasifikační gesto vypnuté až do **Obnovit zoom**; tah pak posouvá obraz.
- **Předchozí dokument** umožní opravu. **Další nerozhodnutý** aktuální dokument přeskočí bez zápisu; na konci seznamu lze nerozhodnuté znovu projít.

Po opětovném otevření prohlížeče vznikne nová relace a otevře se první dokument, jehož název není v CSV. Každé připojení drží vlastní pozici. MVP předpokládá jednoho aktivního klasifikujícího uživatele a jeden serverový proces; souběh více procesů nad stejným CSV není podporován.

## Data a architektura

CSV používá UTF-8 a přesně dva sloupce:

```csv
filename,label
paper_001.pdf,0
subfolder/paper_002.pdf,1
```

`filename` je relativní cesta k PDF s `/`, takže stejné názvy v různých podsložkách zůstanou jedinečné. Zápis používá dočasný soubor ve stejné složce, `fsync` a atomické `os.replace`. Po chybě zápisu zůstává aktuální dokument otevřený. Zdrojové PDF se nemění. Chybné CSV (hlavička, štítek, duplicita) aplikace ohlásí a nepřepíše. Chybějící nebo poškozené PDF lze zkusit znovu či přeskočit bez přiřazení štítku.

`main.py` sestavuje porty `DocumentRetriever`, `ResultStore`, `PageRenderer` a `ReviewUI`. Aplikační vrstva (`ReviewApplication`, `ReviewSession`) neimportuje Flet ani PyMuPDF. Adaptéry jsou ve `src/pdf_review/adapters`; změna retrieveru, úložiště nebo UI vyžaduje jejich nahrazení v `main.py`, nikoli změnu klasifikační logiky. Renderer vykresluje pouze aktuální stránku v 150 DPI a odmítá snímky nad 12 milionů pixelů.

## Ověření a omezení

Automatické testy pokrývají klasifikaci, obnovení, opravy, chyby, CSV, bezpečné čtení složky, vykreslení jedno- a dvoustránkových PDF, sestavení obrazovky s instalovaným Flet API, asynchronní start Fletu, cestu od UI akce k uložení a test směru a prahu gesta. Na Raspberry Pi 5 / Linux ARM64 / Python 3.13 prošla čistá instalace a 16 testů; lokální Flet server vrátil HTTP 200. **Mobilní prohlížeč nebyl k dispozici**. Headless Chromium v tomto prostředí spadl s kódem 133 a Firefox zachytil jen úvodní obrazovku Fletu. Zobrazení hotového UI v telefonu, pinch-to-zoom a souběh gest proto nebyly ručně ověřeny. Klasifikační tlačítka a samostatný pruh zůstávají záložním ovládáním. Před nasazením projděte ruční scénář z `context.md`, zejména zoom, gesto, opravu a obnovení relace.

Dokumentace API: [Flet InteractiveViewer](https://flet.dev/docs/controls/interactiveviewer/), [Flet GestureDetector](https://flet.dev/docs/controls/gesturedetector/), [dynamický Flet web](https://flet.dev/docs/publish/web/dynamic-website/), [PyMuPDF renderování](https://pymupdf.readthedocs.io/en/latest/recipes-images.html).
