# 🎬 IPTV Filter Tools

Zwei Python-Skripte zum Filtern und Bereinigen von IPTV M3U Playlists:
- **block_domains.py** - Blockt Streams von bekannten Paywall-Domains
- **check_iptv_pro.py** - Testet Streams und erkennt Paywalls per OCR

---

## 📦 Installation

### Voraussetzungen

```bash
# Python Packages
pip install opencv-python numpy pytesseract tqdm

# FFmpeg (muss im PATH sein oder in Skript konfiguriert)
# Windows: choco install ffmpeg
# Linux: sudo apt install ffmpeg
# macOS: brew install ffmpeg

# Tesseract OCR
# Windows: choco install tesseract
# Linux: sudo apt install tesseract-ocr tesseract-ocr-rus
# macOS: brew install tesseract tesseract-lang
```

### Pfade anpassen (Windows)

Falls FFmpeg/Tesseract nicht im PATH sind, passe die Pfade in `check_iptv_pro.py` an:

```python
FFMPEG  = r'C:\ProgramData\chocolatey\bin\ffmpeg.exe'
FFPROBE = r'C:\ProgramData\chocolatey\bin\ffprobe.exe'
TESSERACT = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
```

---

## 🚫 1. Domain Blocker (`block_domains.py`)

Entfernt Streams von bekannten Paywall-Domains aus der M3U-Datei.

### Verwendung

**Interaktiv:**
```bash
python block_domains.py input.m3u

# Dann eingeben:
# cdn.ngenix.net
# zabava-htlive.cdn.ngenix.net
# 158.101.222.193
# ...
```

**Kommandozeile (schneller):**
```bash
python block_domains.py input.m3u --domains cdn.ngenix.net zabava-htlive.cdn.ngenix.net 158.101.222.193
```

**Mit eigenem Output-Namen:**
```bash
python block_domains.py input.m3u -o sauber.m3u --domains cdn.ngenix.net
```

### Was wird geblockt?

- Vollständige URLs: `http://rt-sib-omsk-htlive.cdn.ngenix.net/`
- Domains: `cdn.ngenix.net`
- IP-Adressen: `158.101.222.193`
- Teilstrings in URLs

### Output

Erstellt `input_filtered.m3u` (oder eigenen Namen mit `-o`) und zeigt Statistik:

```
📊 ERGEBNIS:
============================================================
Gesamt:     597 Streams
🚫 Geblockt: 234 Streams (39.2%)
✅ Behalten: 363 Streams (60.8%)
```

---

## ✅ 2. IPTV Checker mit OCR (`check_iptv_pro.py`)

Testet Streams auf Funktion und erkennt Paywall-Bildschirme per OCR.

### Verwendung

**Basis (nur funktionierende Streams):**
```bash
python check_iptv_pro.py input.m3u
```

**Mit Fortschrittsanzeige (empfohlen):**
```bash
python check_iptv_pro.py input.m3u -v
```

**Mit Fake-Erkennung:**
```bash
python check_iptv_pro.py input.m3u --safe -v
```

**Aggressive Paywall-Erkennung:**
```bash
python check_iptv_pro.py input.m3u --aggressive -v
```

**Mehr Worker (schneller):**
```bash
python check_iptv_pro.py input.m3u -w 16 -v
```

### Parameter

| Parameter | Beschreibung | Default |
|-----------|-------------|---------|
| `-o` | Output-Datei | `good_clean.m3u` |
| `-t` | Timeout (Sekunden) | `10` |
| `-w` | Parallele Worker | `8` |
| `--safe` | Fake-Stream-Erkennung aktivieren | aus |
| `--aggressive` | Strenge OCR (1 Keyword reicht) | aus |
| `--no-ocr` | OCR komplett deaktivieren | an |
| `-v` | Verbose (detailliertes Logging) | aus |

### Modi erklärt

**Normal (default):**
- Testet ob Stream läuft (3 Sekunden)
- OCR sucht nach 2+ Paywall-Keywords

**Safe (`--safe`):**
- Wie Normal
- + Erkennt statische Fake-Streams (Logo-Loops)

**Aggressive (`--aggressive`):**
- OCR braucht nur 1 Keyword
- Findet mehr Paywalls, aber mehr False Positives

### OCR Keywords

Das OCR sucht nach folgenden Begriffen in Screenshots:
- `оплат`, `подпис` (Russisch)
- `abonn`, `subscribe`, `payment` (Englisch)
- `expired`, `истек`, `активируй`

### Output

Zeigt Live-Fortschritt und Statistik:

```
📊 ERGEBNIS:
============================================================
Getestet:    363
✅ Working:  187 (51.5%)
❌ Failed:   176
💰 Paywall:  89
🖼️ Fake:     21

📋 Fehlertypen:
   paywall: 89
   fake_stream: 21
   timeout: 45
   ffmpeg_error: 21
```

---

## 🔄 Empfohlener Workflow

### 1️⃣ Domain-Blocklist erstellen

Erst bekannte Paywall-Domains entfernen:

```bash
python block_domains.py original.m3u --domains \
  cdn.ngenix.net \
  zabava-htlive.cdn.ngenix.net \
  rt-sib-omsk-htlive.cdn.ngenix.net \
  158.101.222.193 \
  s97982.cdn.ngenix.net
```

→ Erstellt `original_filtered.m3u`

### 2️⃣ OCR-Check durchführen

Dann Rest mit OCR filtern:

```bash
python check_iptv_pro.py original_filtered.m3u --safe -v -w 16
```

→ Erstellt `good_clean.m3u`

### 3️⃣ Fertig! 🎉

Jetzt hast du eine saubere Playlist ohne:
- ❌ Bekannte Paywall-Domains
- ❌ Paywall-Bildschirme (OCR erkannt)
- ❌ Fake-Streams (statische Logos)
- ❌ Nicht funktionierende Streams

---

## 💡 Tipps

### Performance

- **Mehr Worker**: `-w 20` für schnelleres Testen
- **Kürzerer Timeout**: `-t 5` wenn Streams schnell reagieren
- **Ohne Fake-Check**: Weglassen von `--safe` spart Zeit

### Probleme

**Keine Streams funktionieren?**
```bash
# Teste FFmpeg:
ffmpeg -version
ffprobe -version

# Teste Tesseract:
tesseract --version

# Teste mit verbose:
python check_iptv_pro.py test.m3u -v
```

**OCR findet zu viel?**
- Verwende normalen Modus statt `--aggressive`
- Oder deaktiviere OCR: `--no-ocr`

**OCR findet zu wenig?**
- Verwende `--aggressive` Modus
- Prüfe ob russische Sprachpakete installiert sind: `tesseract --list-langs`

### Domain-Liste erweitern

Domains aus deiner M3U extrahieren:

```bash
# Linux/Mac:
grep -oP '(?<=//)[^/:]+' input.m3u | sort -u > domains.txt

# Windows PowerShell:
Select-String -Path input.m3u -Pattern 'https?://([^/:]+)' | 
  ForEach-Object { $_.Matches.Groups[1].Value } | 
  Sort-Object -Unique > domains.txt
```

Dann durchsehen welche Paywall sind und mit `--domains` blocken.

---

## 📊 Beispiel-Session

```bash
# 1. Domains blocken
python block_domains.py iptv_raw.m3u --domains cdn.ngenix.net zabava.net
# → iptv_raw_filtered.m3u (500 Streams)

# 2. OCR-Check
python check_iptv_pro.py iptv_raw_filtered.m3u --safe -w 16 -v
# → good_clean.m3u (245 Streams)

# 3. Fertig!
# Von 750 auf 245 funktionierende, saubere Streams
```

---

## 🐛 Support

Bei Problemen:
1. Prüfe ob FFmpeg und Tesseract installiert sind
2. Teste mit `-v` für detaillierte Ausgabe
3. Prüfe Encoding der M3U (sollte UTF-8 sein)

---

## 📝 Lizenz

Diese Tools sind für den privaten Gebrauch. Respektiere Copyright und Nutzungsbedingungen der Stream-Anbieter.