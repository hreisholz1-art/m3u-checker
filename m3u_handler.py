import os
import shutil
import zipfile
import asyncio
import subprocess
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

COMBINER_SCRIPT = "m3u_combiner_fixed.py"

async def process_m3u_document(update, context):
    """Hauptlogik für den Empfang und die Verarbeitung von M3U-Dateien."""
    doc = update.message.document
    file_name = doc.file_name or "input.m3u"
    
    # Validierung der Endung
    if not any(file_name.lower().endswith(ext) for ext in ['.m3u', '.m3u8', '.txt']):
        return

    # Temporäres Verzeichnis erstellen
    uid = update.effective_user.id
    timestamp_fs = datetime.now().strftime("%f")
    temp_dir = f"temp_{uid}_{timestamp_fs}"
    os.makedirs(temp_dir, exist_ok=True)
    
    try:
        status_msg = await update.message.reply_text("⏳ M3U wird verarbeitet...")
        
        # Download
        tg_file = await doc.get_file()
        input_path = os.path.join(temp_dir, file_name)
        await tg_file.download_to_drive(input_path)
        
        # Externes Skript ausführen (im Thread, da blockierend)
        output_m3u = os.path.join(temp_dir, "output.m3u")
        success = await asyncio.to_thread(_run_external_combiner, temp_dir, output_m3u)
        
        if success:
            # ZIP Erstellung
            zip_filename = f"m3u_{datetime.now().strftime('%Y%m%d_%H%M')}.zip"
            zip_path = os.path.join(temp_dir, zip_filename)
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                zipf.write(output_m3u, arcname="output.m3u")
            
            # Versand
            with open(zip_path, 'rb') as f:
                await update.message.reply_document(document=f, filename=zip_filename)
            await status_msg.delete()
        else:
            await status_msg.edit_text("❌ Fehler: Ergebnisdatei zu klein oder Skript-Fehler.")

    except Exception as e:
        logger.error(f"M3U Handler Error: {e}")
        if 'status_msg' in locals():
            await status_msg.edit_text("⚠️ Interner Fehler bei der Verarbeitung.")
    finally:
        # Aufräumen
        shutil.rmtree(temp_dir, ignore_errors=True)

def _run_external_combiner(input_dir: str, output_file: str) -> bool:
    """Führt den m3u_combiner_fixed.py Prozess aus."""
    cmd = [
        "python3", COMBINER_SCRIPT,
        input_dir,
        "-w", "4",
        "-t", "15",
        "-o", output_file
    ]
    try:
        # Wir setzen ein Timeout von 5 Minuten
        subprocess.run(cmd, check=True, timeout=300)
        return os.path.exists(output_file) and os.path.getsize(output_file) > 200
    except Exception as e:
        logger.error(f"Subprocess Fehler: {e}")
        return False