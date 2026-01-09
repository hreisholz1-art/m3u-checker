#!/usr/bin/env python3
"""
M3U Playlist Kombinierer und Tester
Sucht alle M3U-Dateien in einem Verzeichnis, testet die Streams
und fasst alle funktionierenden in einer neuen M3U-Datei zusammen
MIT ORIGINALEN KANALNAMEN
"""

import subprocess
import os
import sys
import json
from pathlib import Path
from urllib.parse import urlparse
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import hashlib

class M3UCombiner:
    def __init__(self, timeout=8, max_workers=15, output_file="combined_working.m3u"):
        self.timeout = timeout
        self.max_workers = max_workers
        self.output_file = output_file
        
        # Für Duplikaterkennung
        self.seen_streams = set()
        self.duplicate_count = 0
        
        # Statistiken
        self.stats = {
            'total_playlists': 0,
            'total_streams_found': 0,
            'streams_tested': 0,
            'streams_working': 0,
            'streams_failed': 0,
            'streams_duplicate': 0,
            'playlists_processed': {}
        }
        
        # Gesammelte funktionierende Streams
        self.working_streams = []
    
    def get_stream_hash(self, url):
        """Erstellt einen Hash für die URL zur Duplikaterkennung"""
        # Normalisiere URL (entferne Query-Parameter die oft variieren)
        parsed = urlparse(url)
        clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        
        # Erstelle MD5-Hash
        return hashlib.md5(clean_url.encode('utf-8')).hexdigest()
    
    def extract_streams_from_m3u(self, m3u_path):
        """Extrahiert alle Streams aus einer M3U-Datei mit Metadaten"""
        streams = []
        
        try:
            with open(m3u_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            
            current_info = None
            for line in lines:
                line = line.strip()
                
                if not line:
                    continue
                
                # EXTINF-Line (Stream Info) - SPEICHERE ORIGINALE INFO
                if line.startswith('#EXTINF:'):
                    current_info = line
                    continue  # Gehe zur nächsten Zeile
                
                # Stream URL (nicht Kommentar)
                if (line and not line.startswith('#') and 
                    (line.startswith('http://') or 
                     line.startswith('https://') or
                     line.startswith('rtmp://') or
                     line.startswith('rtsp://') or
                     line.startswith('udp://') or
                     line.startswith('rtp://'))):
                    
                    # Prüfe auf Duplikate
                    stream_hash = self.get_stream_hash(line)
                    
                    if stream_hash in self.seen_streams:
                        self.duplicate_count += 1
                        self.stats['streams_duplicate'] += 1
                        current_info = None  # Reset für nächsten Stream
                        continue
                    
                    self.seen_streams.add(stream_hash)
                    
                    streams.append({
                        'url': line,
                        'info': current_info if current_info else f"#EXTINF:-1,Unbekannter Kanal",
                        'source_playlist': Path(m3u_path).name,
                        'hash': stream_hash
                    })
                    current_info = None  # Reset nach jedem erfolgreichen Stream
                    
        except Exception as e:
            print(f"  ⚠️ Fehler beim Lesen von {Path(m3u_path).name}: {e}")
            
        return streams
    
    def test_stream(self, stream_info):
        """Testet einen einzelnen Stream mit FFmpeg"""
        url = stream_info['url']
        
        # FFmpeg-Kommando für schnelles Testen
        ffmpeg_cmd = [
            'ffmpeg',
            '-hide_banner',
            '-loglevel', 'error',
            '-timeout', str(self.timeout * 1000000),
            '-i', url,
            '-t', '3',
            '-c', 'copy',
            '-f', 'null',
            '-'
        ]
        
        try:
            process = subprocess.run(
                ffmpeg_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=self.timeout + 1
            )
            
            if process.returncode == 0:
                return {
                    **stream_info,
                    'status': 'working',
                    'error': None,
                    'tested_at': datetime.now().isoformat()
                }
            else:
                error_msg = process.stderr.decode('utf-8', errors='ignore')
                return {
                    **stream_info,
                    'status': 'failed',
                    'error': error_msg[:80] if error_msg else 'Unknown error',
                    'tested_at': datetime.now().isoformat()
                }
                
        except subprocess.TimeoutExpired:
            return {
                **stream_info,
                'status': 'timeout',
                'error': f'Timeout nach {self.timeout} Sekunden',
                'tested_at': datetime.now().isoformat()
            }
        except Exception as e:
            return {
                **stream_info,
                'status': 'error',
                'error': str(e),
                'tested_at': datetime.now().isoformat()
            }
    
    def scan_directory(self, directory_path):
        """Scannt Verzeichnis nach M3U-Dateien"""
        directory = Path(directory_path)
        
        print(f"\n🔍 Scanne Verzeichnis: {directory}")
        
        m3u_files = []
        for ext in ['.m3u', '.m3u8']:
            m3u_files.extend(directory.glob(f'*{ext}'))
        
        print(f"✅ Gefundene Playlists: {len(m3u_files)}")
        return m3u_files
    
    def process_playlists(self, m3u_files):
        """Verarbeitet alle Playlists und testet die Streams"""
        all_streams = []
        
        print(f"\n📋 Extrahiere Streams aus Playlists...")
        
        # Extrahiere Streams aus allen Playlists
        for m3u_file in m3u_files:
            playlist_name = m3u_file.name
            print(f"  📄 {playlist_name}", end="", flush=True)
            
            streams = self.extract_streams_from_m3u(m3u_file)
            
            self.stats['playlists_processed'][playlist_name] = {
                'path': str(m3u_file),
                'streams_found': len(streams),
                'streams_working': 0,
                'streams_failed': 0
            }
            
            all_streams.extend(streams)
            self.stats['total_streams_found'] += len(streams)
            print(f" - {len(streams)} Streams")
        
        if not all_streams:
            print("❌ Keine Streams gefunden!")
            return
        
        print(f"\n🔢 Insgesamt {len(all_streams)} eindeutige Streams gefunden")
        print(f"🔄 Teste Streams (parallel mit {self.max_workers} Workern)...")
        
        # Teste alle Streams parallel
        tested_count = 0
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_stream = {
                executor.submit(self.test_stream, stream): stream 
                for stream in all_streams
            }
            
            for future in as_completed(future_to_stream):
                tested_count += 1
                stream_info = future_to_stream[future]
                result = future.result()
                
                self.stats['streams_tested'] += 1
                
                # Status-Icons
                if result['status'] == 'working':
                    status_icon = "✅"
                    self.stats['streams_working'] += 1
                    self.working_streams.append(result)
                    
                    # Update Playlist-Statistik
                    playlist_name = stream_info['source_playlist']
                    if playlist_name in self.stats['playlists_processed']:
                        self.stats['playlists_processed'][playlist_name]['streams_working'] += 1
                else:
                    status_icon = "❌"
                    self.stats['streams_failed'] += 1
                    
                    # Update Playlist-Statistik
                    playlist_name = stream_info['source_playlist']
                    if playlist_name in self.stats['playlists_processed']:
                        self.stats['playlists_processed'][playlist_name]['streams_failed'] += 1
                
                # Fortschrittsanzeige
                if tested_count % 10 == 0 or tested_count == len(all_streams):
                    progress = (tested_count / len(all_streams)) * 100
                    print(f"  {status_icon} [{tested_count}/{len(all_streams)}] {progress:.1f}% - {self._shorten_url(stream_info['url'])}")
    
    def _shorten_url(self, url):
        """Kürzt URL für bessere Lesbarkeit"""
        if len(url) > 50:
            return url[:25] + "..." + url[-22:]
        return url
    
    def create_combined_m3u(self, output_path=None):
        """Erstellt eine kombinierte M3U-Datei mit allen funktionierenden Streams"""
        if not self.working_streams:
            print("❌ Keine funktionierenden Streams zum Speichern!")
            return None
        
        if output_path:
            output_file = Path(output_path)
        else:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = Path(f"combined_working_{timestamp}.m3u")
        
        print(f"\n💾 Speichere kombinierte Playlist: {output_file.name}")
        
        # Sortiere Streams nach Quelle für bessere Organisation
        self.working_streams.sort(key=lambda x: x['source_playlist'])
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                # M3U-Header
                f.write("#EXTM3U\n")
                f.write(f"# Generated by M3U Combiner at {datetime.now().isoformat()}\n")
                f.write(f"# Total playlists processed: {len(self.stats['playlists_processed'])}\n")
                f.write(f"# Total working streams: {len(self.working_streams)}\n")
                f.write(f"# Duplicate streams filtered: {self.stats['streams_duplicate']}\n")
                f.write("#" + "="*60 + "\n\n")
                
                current_playlist = None
                
                for stream in self.working_streams:
                    # Playlist-Gruppen-Trenner
                    if stream['source_playlist'] != current_playlist:
                        current_playlist = stream['source_playlist']
                        f.write(f"\n# SOURCE: {current_playlist}\n")
                        f.write("#" + "-"*50 + "\n")
                    
                    # ORIGINALE Stream-Info mit Kanalnamen
                    f.write(f"{stream['info']}\n")
                    
                    # Stream-URL
                    f.write(f"{stream['url']}\n")
            
            print(f"✅ Erfolgreich gespeichert! ({len(self.working_streams)} Streams)")
            return output_file
            
        except Exception as e:
            print(f"❌ Fehler beim Speichern: {e}")
            return None
    
    def print_statistics(self):
        """Gibt detaillierte Statistiken aus"""
        print(f"\n" + "="*70)
        print(f"📊 ZUSAMMENFASSUNG")
        print(f"="*70)
        
        print(f"Verarbeitete Playlists: {len(self.stats['playlists_processed'])}")
        print(f"Gefundene Streams (eindeutig): {self.stats['total_streams_found']}")
        print(f"Entfernte Duplikate: {self.stats['streams_duplicate']}")
        print(f"Getestete Streams: {self.stats['streams_tested']}")
        print(f"✅ Funktionierende: {self.stats['streams_working']}")
        print(f"❌ Fehlgeschlagene: {self.stats['streams_failed']}")
        
        if self.stats['streams_tested'] > 0:
            success_rate = (self.stats['streams_working'] / self.stats['streams_tested']) * 100
            print(f"📊 Erfolgsrate: {success_rate:.1f}%")
        
        print(f"\n📁 Playlist-Details:")
        print(f"-"*40)
        
        for playlist, stats in self.stats['playlists_processed'].items():
            print(f"  {playlist}:")
            print(f"    Gefunden: {stats['streams_found']}")
            print(f"    Funktionierend: {stats['streams_working']}")
            if stats['streams_found'] > 0:
                rate = (stats['streams_working'] / stats['streams_found']) * 100
                print(f"    Erfolgsrate: {rate:.1f}%")
            print()
        
        print(f"🎯 Funktionierende Streams gesamt: {len(self.working_streams)}")
        print(f"="*70)
    
    def save_statistics(self):
        """Speichert detaillierte Statistiken als JSON"""
        stats_file = f"m3u_combiner_stats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        try:
            detailed_stats = {
                'timestamp': datetime.now().isoformat(),
                'settings': {
                    'timeout': self.timeout,
                    'max_workers': self.max_workers
                },
                'statistics': self.stats,
                'working_streams_count': len(self.working_streams),
                'working_streams': [
                    {
                        'url': s['url'],
                        'channel_name': s['info'],
                        'source': s['source_playlist'],
                        'tested_at': s.get('tested_at', '')
                    } for s in self.working_streams
                ]
            }
            
            with open(stats_file, 'w', encoding='utf-8') as f:
                json.dump(detailed_stats, f, indent=2, ensure_ascii=False)
            
            print(f"📊 Statistiken gespeichert in: {stats_file}")
            
        except Exception as e:
            print(f"⚠️ Konnte Statistiken nicht speichern: {e}")

def main():
    parser = argparse.ArgumentParser(
        description='Kombiniert alle funktionierenden Streams aus M3U-Playlists in einer Datei',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  python m3u_combiner_fixed.py "C:\\IPTV-master\\m3u"
  python m3u_combiner_fixed.py ./iptv --timeout 5 --workers 20
  python m3u_combiner_fixed.py . --output "alle_streams.m3u"
        """
    )
    
    parser.add_argument('directory', help='Verzeichnis mit M3U-Playlists')
    parser.add_argument('-t', '--timeout', type=int, default=8, 
                       help='Timeout in Sekunden pro Stream (default: 8)')
    parser.add_argument('-w', '--workers', type=int, default=15,
                       help='Maximale parallele Threads (default: 15)')
    parser.add_argument('-o', '--output', default='combined_working.m3u',
                       help='Ausgabe-Dateiname (default: combined_working.m3u)')
    parser.add_argument('--no-stats', action='store_true',
                       help='Keine JSON-Statistik speichern')
    
    args = parser.parse_args()
    
    # Überprüfe FFmpeg
    try:
        subprocess.run(['ffmpeg', '-version'], 
                      stdout=subprocess.DEVNULL, 
                      stderr=subprocess.DEVNULL, 
                      check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ Fehler: FFmpeg ist nicht installiert oder nicht im PATH!")
        print("👉 Installiere FFmpeg:")
        print("   Ubuntu/Debian: sudo apt install ffmpeg")
        print("   macOS: brew install ffmpeg")
        print("   Windows: https://ffmpeg.org/download.html")
        sys.exit(1)
    
    # Starte den Combiner
    print("🚀 M3U Playlist Combiner (MIT ORIGINALEN KANALNAMEN)")
    print("="*50)
    
    combiner = M3UCombiner(
        timeout=args.timeout,
        max_workers=args.workers,
        output_file=args.output
    )
    
    # Scanne Verzeichnis
    m3u_files = combiner.scan_directory(args.directory)
    
    if not m3u_files:
        print(f"❌ Keine M3U-Dateien in {args.directory} gefunden!")
        sys.exit(1)
    
    # Verarbeite Playlists
    combiner.process_playlists(m3u_files)
    
    # Erstelle kombinierte Playlist
    output_file = combiner.create_combined_m3u(args.output)
    
    if output_file:
        # Zeige Dateigröße
        file_size = os.path.getsize(output_file) / 1024  # in KB
        print(f"📏 Dateigröße: {file_size:.1f} KB")
        
        # Pfad ausgeben
        abs_path = os.path.abspath(output_file)
        print(f"📍 Vollständiger Pfad: {abs_path}")
    
    # Statistiken
    combiner.print_statistics()
    
    if not args.no_stats:
        combiner.save_statistics()
    
    print("\n🎉 Fertig! Die kombinierte Playlist enthält alle funktionierenden Streams mit Originalnamen.")

if __name__ == "__main__":
    main()