#!/usr/bin/env python3
"""
IPTV Domain Blocker - Entfernt Streams mit bestimmten Domains/URLs
"""
import sys
import argparse
from urllib.parse import urlparse

if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')


class M3UDomainBlocker:
    
    def __init__(self, input_file, output_file):
        self.input_file = input_file
        self.output_file = output_file
        self.blocked_domains = set()
        self.blocked_patterns = set()
    
    def normalize_domain(self, url):
        """Extrahiert Domain aus URL"""
        try:
            # Wenn keine Schema, füge http:// hinzu
            if not url.startswith(('http://', 'https://', 'udp://')):
                url = 'http://' + url
            
            parsed = urlparse(url)
            domain = parsed.netloc or parsed.path.split('/')[0]
            
            # Entferne Port
            if ':' in domain:
                domain = domain.split(':')[0]
            
            return domain.lower()
        except:
            return url.lower()
    
    def add_block_entry(self, entry):
        """Fügt eine URL/Domain zur Blockliste hinzu"""
        # Als Pattern (für direkte Suche in URL)
        self.blocked_patterns.add(entry.lower())
        
        # Als Domain
        domain = self.normalize_domain(entry)
        if domain:
            self.blocked_domains.add(domain)
    
    def is_blocked(self, url):
        """Prüft ob URL geblockt werden soll"""
        url_lower = url.lower()
        
        # 1. Prüfe exakte Pattern-Matches
        for pattern in self.blocked_patterns:
            if pattern in url_lower:
                return True
        
        # 2. Prüfe Domain-Matches
        domain = self.normalize_domain(url)
        if domain in self.blocked_domains:
            return True
        
        return False
    
    def interactive_input(self):
        """Interaktive Eingabe von zu blockenden URLs/Domains"""
        print("\n" + "="*60)
        print("🚫 IPTV Domain Blocker")
        print("="*60)
        print("Gib URLs oder Domains ein, die geblockt werden sollen.")
        print("Beispiele:")
        print("  - cdn.ngenix.net")
        print("  - http://158.101.222.193:88/")
        print("  - zabava-htlive.cdn.ngenix.net")
        print("="*60 + "\n")
        
        while True:
            entry = input("🔗 URL/Domain eingeben (oder ENTER zum Beenden): ").strip()
            
            if not entry:
                break
            
            self.add_block_entry(entry)
            print(f"   ✓ Hinzugefügt: {entry}")
            
            # Frage nach weiterer Eingabe
            another = input("   Noch eine? (Y/N): ").strip().upper()
            if another != 'Y':
                break
        
        if not self.blocked_domains and not self.blocked_patterns:
            print("\n❌ Keine Domains angegeben. Abbruch.")
            sys.exit(1)
        
        print(f"\n📋 Blockliste erstellt:")
        print(f"   Patterns: {len(self.blocked_patterns)}")
        print(f"   Domains: {len(self.blocked_domains)}")
        for domain in sorted(self.blocked_domains):
            print(f"     - {domain}")
        print()
    
    def filter_m3u(self):
        """Filtert die M3U Datei"""
        try:
            with open(self.input_file, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
        except FileNotFoundError:
            print(f"❌ Fehler: Datei '{self.input_file}' nicht gefunden!")
            sys.exit(1)
        
        filtered = []
        current_extinf = None
        
        stats = {
            'total': 0,
            'blocked': 0,
            'kept': 0
        }
        
        print("🔍 Filtere M3U Datei...")
        
        for line in lines:
            line_stripped = line.strip()
            
            # M3U Header
            if line_stripped.startswith('#EXTM3U'):
                filtered.append(line)
                continue
            
            # Kommentare (außer EXTINF)
            if line_stripped.startswith('#') and not line_stripped.startswith('#EXTINF'):
                filtered.append(line)
                continue
            
            # EXTINF Zeile - zwischenspeichern
            if line_stripped.startswith('#EXTINF'):
                current_extinf = line
                continue
            
            # Leere Zeilen
            if not line_stripped:
                filtered.append(line)
                continue
            
            # URL Zeile
            if line_stripped.startswith(('http', 'udp', 'rtmp', 'rtsp')):
                stats['total'] += 1
                
                if self.is_blocked(line_stripped):
                    # Stream blocken - EXTINF + URL werden nicht hinzugefügt
                    stats['blocked'] += 1
                    print(f"🚫 Geblockt: {line_stripped[:70]}...")
                    current_extinf = None
                else:
                    # Stream behalten
                    stats['kept'] += 1
                    if current_extinf:
                        filtered.append(current_extinf)
                    filtered.append(line)
                    current_extinf = None
        
        # Schreibe gefilterte Datei
        with open(self.output_file, 'w', encoding='utf-8') as f:
            f.writelines(filtered)
        
        # Statistik
        print("\n" + "="*60)
        print("📊 ERGEBNIS:")
        print("="*60)
        print(f"Gesamt:     {stats['total']} Streams")
        print(f"🚫 Geblockt: {stats['blocked']} Streams ({stats['blocked']/max(1,stats['total'])*100:.1f}%)")
        print(f"✅ Behalten: {stats['kept']} Streams ({stats['kept']/max(1,stats['total'])*100:.1f}%)")
        print(f"\n💾 Gespeichert: {self.output_file}")
        print("="*60 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description='Blockt IPTV Streams basierend auf Domains/URLs',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  python block_domains.py input.m3u
  python block_domains.py input.m3u -o clean.m3u
  python block_domains.py input.m3u --domains cdn.ngenix.net zabava-htlive.cdn.ngenix.net
        """
    )
    
    parser.add_argument('input', help='Input M3U Datei')
    parser.add_argument('-o', '--output', help='Output M3U Datei (default: input_filtered.m3u)')
    parser.add_argument('--domains', nargs='+', help='Domains zum Blocken (überspringt interaktive Eingabe)')
    
    args = parser.parse_args()
    
    # Output Dateiname
    if args.output:
        output = args.output
    else:
        output = args.input.rsplit('.', 1)[0] + '_filtered.m3u'
    
    # Blocker erstellen
    blocker = M3UDomainBlocker(args.input, output)
    
    # Domains hinzufügen
    if args.domains:
        # Non-interaktiv: Domains aus Kommandozeile
        print("\n" + "="*60)
        print("🚫 IPTV Domain Blocker (Kommandozeilen-Modus)")
        print("="*60)
        for domain in args.domains:
            blocker.add_block_entry(domain)
            print(f"✓ Hinzugefügt: {domain}")
        print()
    else:
        # Interaktiv: Domains abfragen
        blocker.interactive_input()
    
    # Filtere die M3U
    blocker.filter_m3u()


if __name__ == '__main__':
    main()