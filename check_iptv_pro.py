#!/usr/bin/env python3
import subprocess, os, sys, re, argparse, tempfile
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

import cv2
import numpy as np
import pytesseract
from tqdm import tqdm

if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

FFMPEG  = r'C:\ProgramData\chocolatey\bin\ffmpeg.exe'
FFPROBE = r'C:\ProgramData\chocolatey\bin\ffprobe.exe'
TESSERACT = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
pytesseract.pytesseract.tesseract_cmd = TESSERACT

PAY_PATTERNS = [
    r'оплат', r'подпис', r'abonn',
    r'subscribe', r'payment', r'expired',
    r'истек', r'активируй'
]


class IPTVFilter:

    def __init__(self, timeout, workers, mode, use_ocr, verbose):
        self.timeout = timeout
        self.workers = workers
        self.mode = mode
        self.use_ocr = use_ocr
        self.verbose = verbose
        self.stats = dict(tested=0, working=0, paywall=0, failed=0, fake=0)
        self.fail_reasons = defaultdict(int)
        self.pbar = None

    def log(self, msg, force=False):
        if self.verbose or force:
            if self.pbar:
                self.pbar.write(msg)
            else:
                print(msg)

    # ---------- Parsing ----------

    def extract_streams(self, path):
        out, info = [], None
        with open(path, encoding='utf-8', errors='ignore') as f:
            for l in f:
                l = l.strip()
                if not l:
                    continue
                if l.startswith('#EXTINF'):
                    info = l
                elif not l.startswith('#') and l.startswith(('http', 'udp', 'rtmp', 'rtsp')):
                    out.append({'url': l, 'info': info or '#EXTINF:-1,Unknown'})
                    info = None
        return out

    # ---------- Technical checks ----------

    def test_stream_basic(self, url):
        """Einfacher FFmpeg-Test wie m3u_combiner (3 Sekunden grabben)"""
        try:
            result = subprocess.run(
                [FFMPEG, '-hide_banner', '-loglevel', 'error',
                 '-timeout', str(self.timeout * 1_000_000),
                 '-i', url,
                 '-t', '3',
                 '-c', 'copy',
                 '-f', 'null', '-'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=self.timeout + 2
            )
            
            if result.returncode == 0:
                self.log(f"✓ Stream OK: {url[:60]}")
                return True
            else:
                error = result.stderr.decode('utf-8', errors='ignore')
                self.log(f"❌ Stream Error: {error[:50]}")
                self.fail_reasons['ffmpeg_error'] += 1
                return False
                
        except subprocess.TimeoutExpired:
            self.log(f"⏱️ Timeout: {url[:60]}")
            self.fail_reasons['timeout'] += 1
            return False
        except Exception as e:
            self.log(f"❌ Exception: {str(e)[:40]}")
            self.fail_reasons['exception'] += 1
            return False

    # ---------- Frame / Fake ----------

    def grab_frame(self, url, sec):
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
            try:
                subprocess.run(
                    [FFMPEG, '-hide_banner', '-loglevel', 'panic',
                     '-ss', str(sec), '-i', url,
                     '-frames:v', '1', '-y', tmp.name],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=self.timeout
                )
                img = cv2.imread(tmp.name)
                return img
            except:
                return None
            finally:
                if os.path.exists(tmp.name):
                    os.unlink(tmp.name)

    def is_fake(self, url):
        """Erkennt statische Bilder (Fake-Streams)"""
        try:
            self.log(f"🔍 Fake-Check: {url[:60]}")
            
            f1 = self.grab_frame(url, 2)
            f2 = self.grab_frame(url, 5)
            
            if f1 is None or f2 is None:
                self.log(f"  ⚠️ Konnte keine Frames grabben")
                return False
            
            # Vergleiche Frames
            diff = np.mean(cv2.absdiff(f1, f2))
            
            if diff > 2.0:  # Bewegung erkannt
                self.log(f"  ✓ Nicht statisch (diff={diff:.2f})")
                return False
            
            # Statisch - prüfe Audio
            self.log(f"  🖼️ Statisch erkannt, prüfe Audio...")
            
            try:
                out = subprocess.check_output(
                    [FFMPEG, '-hide_banner', '-i', url, '-t', '5',
                     '-af', 'astats=metadata=1:reset=1',
                     '-f', 'null', '-'],
                    stderr=subprocess.STDOUT,
                    timeout=self.timeout
                ).decode().lower()

                has_audio = 'rms level' in out
                if has_audio:
                    self.log(f"  🎵 Hat Audio - vermutlich kein Fake")
                    return False
                else:
                    self.log(f"  🚫 FAKE erkannt (statisch + kein Audio)")
                    return True
            except:
                return False
            
        except Exception as e:
            self.log(f"  ⚠️ Fake-Check Fehler: {str(e)[:40]}")
            return False

    # ---------- OCR ----------

    def paywall_ocr(self, url, aggressive=False):
        """Erkennt Paywall-Bildschirme per OCR"""
        try:
            self.log(f"💰 OCR-Check: {url[:60]}")
            
            img = self.grab_frame(url, 3)
            if img is None:
                self.log(f"  ⚠️ Kein Frame für OCR")
                return False

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # Schwarzer Bildschirm?
            if np.mean(gray) < 15:
                self.log(f"  ⚠️ Schwarzer Bildschirm")
                return aggressive  # Im aggressive mode als Paywall werten

            # Nur mittleren Bereich analysieren (außer aggressive)
            if not aggressive:
                h, w = gray.shape
                gray = gray[h//4:3*h//4, w//4:3*w//4]

            # OCR
            text = pytesseract.image_to_string(
                gray, lang='rus+eng', config='--psm 6'
            ).lower()

            # Suche nach Paywall-Keywords
            hits = sum(bool(re.search(p, text)) for p in PAY_PATTERNS)
            threshold = 1 if aggressive else 2
            
            if hits >= threshold:
                self.log(f"  💰 PAYWALL erkannt ({hits} Treffer)!")
                self.log(f"     Text: {text[:80]}", force=True)
                return True
            else:
                self.log(f"  ✓ Kein Paywall-Text erkannt")
                return False
                
        except Exception as e:
            self.log(f"  ⚠️ OCR Fehler: {str(e)[:40]}")
            return False

    # ---------- Decision ----------

    def test_stream(self, s):
        url_short = s['url'][:70] + '...' if len(s['url']) > 70 else s['url']
        
        try:
            # Phase 1: Basis-Test (EINZIGER Connectivity-Test)
            if not self.test_stream_basic(s['url']):
                self.fail_reasons['basic_test_failed'] += 1
                return None

            # Phase 2: Fake-Erkennung (nur im safe mode)
            if self.mode == 'safe':
                if self.is_fake(s['url']):
                    self.fail_reasons['fake_stream'] += 1
                    return None

            # Phase 3: Paywall-Erkennung (wenn OCR aktiviert)
            if self.use_ocr:
                if self.paywall_ocr(s['url'], aggressive=(self.mode == 'aggressive')):
                    self.fail_reasons['paywall'] += 1
                    return None

            # SUCCESS!
            self.log(f"✅ WORKING: {url_short}", force=True)
            return s

        except Exception as e:
            self.log(f"❌ Exception: {str(e)[:40]}")
            self.fail_reasons['exception'] += 1
            return None

    # ---------- Main ----------

    def run(self, inp, outp):
        print(f"\n{'='*60}")
        print(f"IPTV Stream Checker PRO")
        print(f"{'='*60}")
        print(f"Modus: {self.mode}")
        print(f"Timeout: {self.timeout}s")
        print(f"Worker: {self.workers}")
        print(f"OCR: {'AN' if self.use_ocr else 'AUS'}")
        print(f"Fake-Check: {'AN' if self.mode == 'safe' else 'AUS'}")
        print(f"{'='*60}\n")
        
        streams = self.extract_streams(inp)
        print(f"📋 {len(streams)} Streams geladen\n")
        
        good = []
        self.pbar = tqdm(total=len(streams), desc="Teste Streams", 
                         unit="stream", ncols=100,
                         bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]')

        with ThreadPoolExecutor(self.workers) as pool:
            futures = {pool.submit(self.test_stream, s): s for s in streams}
            
            for future in as_completed(futures):
                self.stats['tested'] += 1
                result = future.result()
                
                if result:
                    self.stats['working'] += 1
                    good.append(result)
                else:
                    self.stats['failed'] += 1
                
                # Update progress bar
                self.pbar.set_postfix({
                    'OK': self.stats['working'],
                    'Fehler': self.stats['failed']
                })
                self.pbar.update(1)

        self.pbar.close()

        # Schreibe Output
        with open(outp, 'w', encoding='utf-8') as f:
            f.write('#EXTM3U\n')
            f.write(f'# Gefiltert am: {datetime.now()}\n')
            f.write(f'# Mode: {self.mode}\n')
            f.write(f'# Original: {len(streams)} | Working: {len(good)}\n')
            for s in good:
                f.write(s['info'] + '\n' + s['url'] + '\n')

        # Statistik
        print(f"\n{'='*60}")
        print("📊 ERGEBNIS:")
        print(f"{'='*60}")
        print(f"Getestet:    {self.stats['tested']}")
        print(f"✅ Working:  {self.stats['working']} ({self.stats['working']/max(1,self.stats['tested'])*100:.1f}%)")
        print(f"❌ Failed:   {self.stats['failed']}")
        
        if self.use_ocr:
            print(f"💰 Paywall:  {self.fail_reasons.get('paywall', 0)}")
        if self.mode == 'safe':
            print(f"🖼️ Fake:     {self.fail_reasons.get('fake_stream', 0)}")
        
        if self.fail_reasons:
            print(f"\n📋 Fehlertypen:")
            for reason, count in sorted(self.fail_reasons.items(), key=lambda x: -x[1]):
                print(f"   {reason}: {count}")
        
        print(f"\n💾 Gespeichert in: {outp}")
        print(f"{'='*60}\n")


def main():
    ap = argparse.ArgumentParser(description='IPTV Stream Checker mit OCR Paywall-Erkennung')
    ap.add_argument('input', help='Input M3U Datei')
    ap.add_argument('-o', '--output', default='good_clean.m3u', help='Output Datei')
    ap.add_argument('-t', '--timeout', type=int, default=10, help='Timeout in Sekunden')
    ap.add_argument('-w', '--workers', type=int, default=8, help='Anzahl paralleler Worker')
    ap.add_argument('--safe', action='store_true', help='Safe Modus (mit Fake-Erkennung)')
    ap.add_argument('--aggressive', action='store_true', help='Aggressive OCR-Modus')
    ap.add_argument('--no-ocr', action='store_true', help='OCR deaktivieren')
    ap.add_argument('-v', '--verbose', action='store_true', help='Detaillierte Ausgabe')
    args = ap.parse_args()

    mode = 'normal'
    if args.safe:
        mode = 'safe'
    if args.aggressive:
        mode = 'aggressive'

    IPTVFilter(
        args.timeout,
        args.workers,
        mode,
        use_ocr=not args.no_ocr,
        verbose=args.verbose
    ).run(args.input, args.output)


if __name__ == '__main__':
    main()