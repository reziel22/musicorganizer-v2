# -*- coding: utf-8 -*-
import os
import sys
import logging
import time
import shutil
import tempfile
from typing import List, Optional, Tuple, Dict, Any, Union # Added Union
from dataclasses import dataclass, field
import math

# --- Check and Handle NumPy Requirement FIRST ---
try:
    import numpy as np
    _numpy_installed = True
except ImportError:
    print("ERRORE CRITICO: Libreria 'numpy' non trovata. È richiesta da 'soundfile' e 'pyloudnorm'.")
    print("Installala con 'pip install numpy'")
    print("La normalizzazione audio e potenzialmente la riproduzione non funzioneranno.")
    _numpy_installed = False
    # sys.exit(1) # Exit early if needed

# --- Librerie Audio e Normalizzazione (Depend on NumPy) ---
_soundfile_installed = False
_pyloudnorm_installed = False
if _numpy_installed:
    try:
        import soundfile as sf
        _soundfile_installed = True
    except ImportError:
        print("AVVISO: Libreria 'soundfile' non trovata. Installala con 'pip install soundfile'")
        print("La normalizzazione audio non funzionerà.")
    except Exception as e:
        print(f"ERRORE CARICAMENTO soundfile (anche con numpy): {e}")

    try:
        import pyloudnorm as pyln
        _pyloudnorm_installed = True
    except ImportError:
        print("AVVISO: Libreria 'pyloudnorm' non trovata. Installala con 'pip install pyloudnorm'")
        print("La normalizzazione audio non funzionerà.")
    except Exception as e:
        print(f"ERRORE CARICAMENTO pyloudnorm (anche con numpy): {e}")
else:
     print("AVVISO: Installazione 'soundfile' e 'pyloudnorm' saltata perchè 'numpy' non è installato.")


# --- Librerie Base e UI ---
try:
    import vlc
    _vlc_installed = True
except ImportError:
    print("ERRORE CRITICO: Libreria python-vlc non trovata. Installala con 'pip install python-vlc'")
    print("La riproduzione audio non funzionerà.")
    _vlc_installed = False
except OSError as e:
    print(f"ERRORE CRITICO: Impossibile caricare la libreria VLC (libvlc). {e}")
    print("Assicurati che VLC media player (versione 64bit se Python è 64bit) sia installato correttamente e accessibile nel PATH di sistema.")
    _vlc_installed = False

try:
    import mutagen
    from mutagen import MutagenError
    _mutagen_installed = True
except ImportError:
    print("AVVISO: Libreria mutagen non trovata. Installala con 'pip install mutagen'.")
    print("Il caricamento della durata dei brani sarà disabilitato.")
    _mutagen_installed = False

try:
    import pythoncom
    _pywin32_installed = True
except ImportError:
    _pywin32_installed = False
    if os.name == 'nt':
        print("AVVISO: Modulo 'pywin32' non trovato (pip install pywin32). COM init per VLC su Windows sarà saltata.")

# --- PyQt5 Import ---
try:
    from PyQt5 import QtWidgets, QtGui, QtCore
    from PyQt5.QtWidgets import (QApplication, QMainWindow, QFileDialog, QVBoxLayout,
                                 QHBoxLayout, QLabel, QListWidget, QPushButton,
                                 QLineEdit, QWidget, QMessageBox, QStyleFactory,
                                 QListWidgetItem, QStatusBar, QAbstractItemView,
                                 QCheckBox, QSlider, QComboBox, QFrame, QStyle,
                                 QProgressDialog) # Added QProgressDialog (Optional)
    from PyQt5.QtCore import QSettings, Qt, QEvent, QTimer, QSize, QThread, pyqtSignal, QObject # Added QThread, pyqtSignal, QObject
    _pyqt5_installed = True
except ImportError:
     print("ERRORE CRITICO: Libreria 'PyQt5' non trovata. Installala con 'pip install PyQt5'")
     _pyqt5_installed = False
     sys.exit(1) # Need to exit if GUI library is missing


# --- Configuration ---
APP_NAME = "MusicOrganizerProDJ_MT" # Added MT for MultiThreaded
ORG_NAME = "BennyC"
SETTINGS_INPUT_PATH = "paths/inputPath"
SETTINGS_OUTPUT_PATH = "paths/baseOutputPath"
SETTINGS_RECURSIVE_SCAN = "options/recursiveScan"
SETTINGS_RECENT_FOLDERS = "folders/recentSubfolders"
SETTINGS_LAST_VOLUME = "audio/lastVolume"
SETTINGS_TARGET_LUFS = "audio/targetLUFS"
MAX_RECENT_FOLDERS = 20
TARGET_LUFS_DEFAULT = -14.0
FULL_PATH_ROLE = Qt.UserRole + 1
STATUS_BAR_TIMEOUT = 4000
PROGRESS_TIMER_INTERVAL = 250

# --- Logging Setup ---
log_formatter = logging.Formatter('%(asctime)s [%(threadName)s:%(levelname)s] %(message)s') # Added threadName
log_file_path = os.path.join(os.path.expanduser("~"), f"{APP_NAME}_debug.log")

log_file_handler = None
try:
    # Use 'w' mode to start fresh log each time for easier debugging during dev
    log_file_handler = logging.FileHandler(log_file_path, mode='w', encoding='utf-8')
    log_file_handler.setFormatter(log_formatter)
    log_file_handler.setLevel(logging.DEBUG) # Log DEBUG level and above to file
except Exception as e:
    print(f"ATTENZIONE: Impossibile creare file di log a '{log_file_path}': {e}")

log_console_handler = logging.StreamHandler(sys.stdout)
log_console_handler.setFormatter(log_formatter)
log_console_handler.setLevel(logging.INFO) # Log INFO level and above to console

# Configure root logger - Set level to DEBUG to catch everything, handlers will filter
logging.basicConfig(level=logging.DEBUG, handlers=[log_console_handler] + ([log_file_handler] if log_file_handler else []))
logging.info(f"--- Avvio {APP_NAME} ---")
logging.info(f"Log file: {log_file_path}")
logging.info(f"Stato Librerie: NumPy={_numpy_installed}, SoundFile={_soundfile_installed}, "
             f"PyLoudnorm={_pyloudnorm_installed}, Mutagen={_mutagen_installed}, "
             f"python-vlc={_vlc_installed}, PyQt5={_pyqt5_installed}, "
             f"pywin32={_pywin32_installed} (OS: {os.name})")


# --- Data Structure for Music Files ---
@dataclass
class MusicFileData:
    full_path: str
    filename: str
    display_name: str = field(init=False)
    duration_ms: int = 0
    measured_lufs: Optional[float] = None

    def __post_init__(self):
        safe_filename = self.filename if self.filename else "N/A"
        self.display_name = safe_filename
        if not self.display_name: self.display_name = "Nome file non disponibile"


# --- Helper Function ---
def format_time(milliseconds: Optional[int]) -> str:
    if milliseconds is None or milliseconds <= 0: return "00:00"
    seconds_total = round(milliseconds / 1000)
    mins = seconds_total // 60
    secs = seconds_total % 60
    return f"{mins:02d}:{secs:02d}"

# --- File Management & Normalization ---
class FileManager:
    """Gestisce caricamento file, metadati (durata), normalizzazione (WAV), spostamento."""
    def __init__(self):
        self.input_directory: Optional[str] = None
        logging.info("FileManager istanziato.")
        # LUFS meter is now created and managed in MainWindow for easier thread passing

    def set_input_directory(self, directory: str):
        self.input_directory = directory

    def load_music_files(self, directory: str, recursive: bool = False) -> Tuple[List[MusicFileData], str]:
        """Carica file MP3, estrae durata. Eseguito nel worker thread."""
        if not os.path.isdir(directory):
            msg = f"Cartella input non trovata o non è una directory: {directory}"
            logging.error(msg)
            return [], msg
        self.input_directory = directory # Store the currently scanned directory
        music_files_data: List[MusicFileData] = []
        files_processed_count = 0
        found_mp3_count = 0
        start_time = time.time()
        logging.info(f"Avvio scansione (thread: {QThread.currentThread().objectName()}) in '{directory}' (Ricorsiva: {recursive})...")

        # Check for cancellation periodically
        thread = QThread.currentThread()
        if thread and hasattr(thread, 'isInterruptionRequested') and thread.isInterruptionRequested():
            logging.info("Scansione interrotta.")
            return [], "Scansione interrotta dall'utente."

        try:
            if recursive:
                for root, _, files in os.walk(directory, topdown=True):
                     if thread and hasattr(thread, 'isInterruptionRequested') and thread.isInterruptionRequested():
                        logging.info("Scansione ricorsiva interrotta (walk).")
                        return [], "Scansione interrotta dall'utente."
                     logging.debug(f"Scansione: {root}")
                     for filename in files:
                         files_processed_count += 1
                         if filename.lower().endswith('.mp3') and not filename.startswith('._'):
                             full_path = os.path.join(root, filename)
                             try:
                                 if os.path.isfile(full_path):
                                     # Minimal I/O check before deeper processing
                                     if not os.access(full_path, os.R_OK):
                                        logging.warning(f"Permesso lettura negato per: {filename} in {root}")
                                        continue
                                     file_data = self._process_file(full_path, filename)
                                     if file_data:
                                         music_files_data.append(file_data)
                                         found_mp3_count += 1
                                 # else: logging.debug(f"Ignorato elemento non file: {full_path}") # Too verbose
                             except OSError as e: logging.warning(f"Errore OS accesso a {full_path}: {e}")
                             except Exception as e: logging.warning(f"Errore imprevisto processando {filename}: {e}")
                         # Yield control briefly (optional, might slightly slow down but improves responsiveness to interruption)
                         # if files_processed_count % 100 == 0: QThread.yieldCurrentThread()

            else: # Non-recursive scan
                for filename in os.listdir(directory):
                    if thread and hasattr(thread, 'isInterruptionRequested') and thread.isInterruptionRequested():
                        logging.info("Scansione non-ricorsiva interrotta.")
                        return [], "Scansione interrotta dall'utente."
                    files_processed_count += 1
                    full_path = os.path.join(directory, filename)
                    if filename.lower().endswith('.mp3') and not filename.startswith('._') and os.path.isfile(full_path):
                        try:
                            if not os.access(full_path, os.R_OK):
                                logging.warning(f"Permesso lettura negato per: {filename}")
                                continue
                            file_data = self._process_file(full_path, filename)
                            if file_data:
                                music_files_data.append(file_data)
                                found_mp3_count += 1
                        except OSError as e: logging.warning(f"Errore OS accesso a {full_path}: {e}")
                        except Exception as e: logging.warning(f"Errore imprevisto processando {filename}: {e}")

            end_time = time.time()
            duration = end_time - start_time
            logging.info(f"Scansione completata in {duration:.3f} sec. Trovati {found_mp3_count} MP3 ({files_processed_count} elementi esaminati).")

            if not music_files_data:
                return [], "Nessun file MP3 valido trovato."

            music_files_data.sort(key=lambda x: x.filename.lower())
            return music_files_data, f"Caricati {found_mp3_count} MP3."

        except OSError as e:
             err_msg = f"Errore OS durante scansione cartella {directory}: {e}"
             logging.error(err_msg)
             return [], err_msg
        except Exception as e:
             err_msg = f"Errore imprevisto caricamento file da {directory}: {e}"
             logging.error(err_msg, exc_info=True)
             return [], err_msg


    def _process_file(self, full_path: str, filename: str) -> Optional[MusicFileData]:
        """Processa UN file: estrae durata. Eseguito nel worker thread."""
        duration_ms = 0
        if _mutagen_installed:
            try:
                # Access check done before calling this now
                audio_meta = mutagen.File(full_path, easy=False)
                if audio_meta and hasattr(audio_meta, 'info') and hasattr(audio_meta.info, 'length'):
                    try: duration_ms = int(audio_meta.info.length * 1000)
                    except (TypeError, ValueError): logging.debug(f"Valore durata non valido per {filename}")
                else:
                    logging.debug(f"Nessuna info durata trovata (Mutagen) per: {filename}")
            except MutagenError as e:
                 # Log sync errors as DEBUG, they are often non-critical but can indicate issues
                 if "sync" in str(e).lower(): logging.debug(f"Errore sync Mutagen (ignoro) '{filename}': {e}")
                 else: logging.warning(f"Altro Errore Mutagen lettura '{filename}': {e}")
            except OSError as e: logging.warning(f"Errore OS lettura info (Mutagen) '{filename}': {e}")
            except Exception as e: logging.warning(f"Errore imprevisto lettura info (Mutagen) '{filename}': {e}", exc_info=False) # Keep log concise
        else:
             logging.debug("Mutagen non installato, durata non estratta.")
             # Still return the file data even without duration
             return MusicFileData(full_path, filename, duration_ms=0) # Set duration to 0 explicitly

        return MusicFileData(full_path, filename, duration_ms=duration_ms)


    def normalize_and_save(self, lufs_meter: pyln.Meter, target_lufs: float, source_path: str, destination_path: str) -> Tuple[bool, str, Optional[float]]:
        """Normalizza (al target LUFS) e salva come WAV. Eseguito nel worker thread."""
        measured_lufs: Optional[float] = None
        if not lufs_meter or not _soundfile_installed or not _numpy_installed:
            return False, "Librerie audio necessarie (pyloudnorm/soundfile/numpy) non disponibili.", measured_lufs
        if not os.path.isfile(source_path):
            return False, f"File sorgente non trovato: {os.path.basename(source_path)}", measured_lufs

        # Check for cancellation before heavy processing
        thread = QThread.currentThread()
        if thread and hasattr(thread, 'isInterruptionRequested') and thread.isInterruptionRequested():
            logging.info("Normalizzazione interrotta prima dell'inizio.")
            return False, "Operazione interrotta.", None

        try:
            start_time = time.time()
            filename = os.path.basename(source_path)
            dest_filename = os.path.basename(destination_path)
            logging.info(f"Avvio normalizzazione (Thread: {QThread.currentThread().objectName()}) per: {filename} -> Target {target_lufs:.1f} LUFS -> Dest: {dest_filename}")

            # 1. Leggi file audio
            logging.debug(f"  - Lettura file: {source_path}")
            try:
                audio_data, rate = sf.read(source_path, dtype='float32') # Always read as float32
            except Exception as sf_read_err:
                 logging.error(f"  - Errore SoundFile lettura '{filename}': {sf_read_err}")
                 err_str = str(sf_read_err).lower(); msg = f"Errore lettura audio: {sf_read_err}"
                 if 'format not recognised' in err_str: msg = f"Formato audio non riconosciuto"
                 elif 'permission denied' in err_str: msg = f"Permesso negato lettura audio"
                 elif 'no data' in err_str: msg = f"File audio senza dati (o corrotto)"
                 return False, f"{msg}: {filename}", measured_lufs

            logging.debug(f"  - File letto: {audio_data.shape}, Rate: {rate} Hz")

            if audio_data is None or audio_data.size == 0:
                 logging.warning(f"  - Dati audio vuoti/invalidi per '{filename}'. Salto.")
                 return False, "Dati audio vuoti o invalidi.", None

            # Ensure meter rate matches file rate
            if lufs_meter.rate != rate:
                try:
                    lufs_meter.rate = rate # Re-initialize meter if rate is different (or handle error)
                    logging.debug(f"  - Aggiornato rate LUFS Meter a {rate} Hz.")
                except Exception as meter_rate_err:
                     logging.error(f"  - Errore critico impostazione rate pyln.Meter ({rate} Hz): {meter_rate_err}. Normalizzazione annullata.")
                     return False, f"Errore init LUFS meter (rate {rate}Hz)", None

            # 2. Misura loudness
            # Use mono or first channel if stereo for LUFS measurement (common practice)
            data_for_lufs = audio_data[:, 0] if audio_data.ndim > 1 else audio_data
            logging.debug(f"  - Misurazione LUFS...")
            try:
                 measured_lufs = lufs_meter.integrated_loudness(data_for_lufs)
            except Exception as lufs_err:
                 logging.error(f"  - Errore calcolo LUFS per '{filename}': {lufs_err}", exc_info=True)
                 # Potrebbe essere MemoryError su file enormi/corrotti
                 if isinstance(lufs_err, MemoryError):
                      return False, "Errore Memoria calcolo LUFS", None
                 return False, f"Errore calcolo LUFS", None # Don't leak exception details to UI message
            logging.info(f"  - LUFS Misurato: {measured_lufs:.2f} LUFS")


            # Check for cancellation again after measurement
            if thread and hasattr(thread, 'isInterruptionRequested') and thread.isInterruptionRequested():
                logging.info("Normalizzazione interrotta dopo misurazione LUFS.")
                return False, "Operazione interrotta.", measured_lufs # Return measured LUFS if available

            # 3. Gestione Silenzio / LUFS non finito
            # Check includes -inf which pyloudnorm returns for digital silence
            if not np.isfinite(measured_lufs) or measured_lufs < -70.0: # Treat very quiet as silence
                 log_reason = "silenzio" if measured_lufs < -70.0 else "LUFS non finito"
                 logging.warning(f"  - LUFS non valido ({measured_lufs:.2f} - {log_reason}) per {filename}. Salto gain, copio come WAV.")
                 try:
                     logging.debug(f"  - Scrittura file (silenzioso) come WAV Float: {destination_path}")
                     dest_dir = os.path.dirname(destination_path); os.makedirs(dest_dir, exist_ok=True)
                     # Use Float subtype for direct copy to avoid potential clipping if original was > int range
                     sf.write(destination_path, audio_data, rate, format='WAV', subtype='FLOAT')
                     logging.info(f"  - Copia (WAV) completata (file {log_reason}) in {time.time() - start_time:.2f} sec.")
                     return True, f"Copiato come WAV ({log_reason})", measured_lufs
                 except Exception as write_err_silence:
                     msg = f"Scrittura file ({log_reason}) fallita: {write_err_silence}"
                     logging.error(f"  - {msg}")
                     return False, msg, measured_lufs


            # 4. Calcola e Applica Gain
            gain_db = target_lufs - measured_lufs
            logging.info(f"  - Gain dB da applicare: {gain_db:.2f}")
            # Apply gain using linear amplitude multiplication
            gain_linear = 10.0**(gain_db / 20.0)
            # Ensure calculation is done in float64 for precision before casting back
            normalized_audio = (audio_data.astype(np.float64) * gain_linear).astype(np.float32)


            # 5. Controllo e Gestione Clipping
            max_amplitude = np.max(np.abs(normalized_audio))
            logging.debug(f"  - Picco post-gain: {max_amplitude:.4f} (prima del limite a 1.0)")
            did_clip = max_amplitude > 1.0 # Float range is typically [-1.0, 1.0]

            if did_clip:
                 logging.warning(f"  - CLIPPING RILEVATO post-gain (picco: {max_amplitude:.3f}). Normalizzo picco a -0.2 dBFS.")
                 # Apply peak normalization factor - target a bit below 0dBFS (e.g., -0.2dBFS = 10**(-0.2/20) = ~0.977)
                 peak_norm_factor = 0.977 / max_amplitude
                 # Apply normalization factor again in float64 for precision
                 normalized_audio = (normalized_audio.astype(np.float64) * peak_norm_factor).astype(np.float32)
                 max_amplitude = np.max(np.abs(normalized_audio)) # Recalculate peak after normalization
                 logging.info(f"  - Nuovo picco dopo norm. picco: {max_amplitude:.3f}")

            # Ensure data is clipped to [-1.0, 1.0] regardless, SF may handle this but safer to do it explicitly
            np.clip(normalized_audio, -1.0, 1.0, out=normalized_audio)

            # Check for cancellation before writing file
            if thread and hasattr(thread, 'isInterruptionRequested') and thread.isInterruptionRequested():
                logging.info("Normalizzazione interrotta prima della scrittura.")
                return False, "Operazione interrotta.", measured_lufs


            # 6. Scrivi File Normalizzato
            logging.debug(f"  - Scrittura file WAV Float normalizzato: {destination_path}")
            try:
                 dest_dir = os.path.dirname(destination_path); os.makedirs(dest_dir, exist_ok=True)
                 # Saving as FLOAT preserves the normalized dynamic range without requantization issues
                 sf.write(destination_path, normalized_audio, rate, format='WAV', subtype='FLOAT')
            except Exception as write_err:
                 msg = f"Scrittura file normalizzato fallita: {write_err}"
                 logging.error(f"  - {msg}")
                 # Attempt to clean up partially written file
                 if os.path.exists(destination_path):
                     try: os.remove(destination_path)
                     except OSError: pass
                 return False, msg, measured_lufs

            completion_msg = f"Normalizzato{' (con peak limiting)' if did_clip else ''} e salvato"
            logging.info(f"  - Normalizzazione/Scrittura completata in {time.time() - start_time:.2f} sec.")
            return True, completion_msg, measured_lufs

        except sf.SoundFileError as e:
             msg = f"Errore SoundFile (generico) '{os.path.basename(source_path)}': {e}"
             logging.error(msg)
             return False, f"Errore I/O audio: {e}", measured_lufs
        except MemoryError:
             msg = f"Errore Memoria processando '{os.path.basename(source_path)}'."
             logging.error(msg)
             return False, "Errore Memoria", measured_lufs
        except Exception as e:
             logging.error(f"Errore imprevisto normalizzazione '{os.path.basename(source_path)}': {e}", exc_info=True)
             return False, f"Errore imprevisto normalizzazione", measured_lufs


    def move_or_delete_original(self, source_full_path: str, destination_folder: Optional[str] = None) -> Tuple[bool, str]:
        """Sposta l'originale (se destination_folder fornito) o lo elimina.
           Eseguito nel worker thread DOPO normalizzazione riuscita."""
        if not os.path.isfile(source_full_path):
            msg = f"Sorgente non trovato per spostamento/elim.: {os.path.basename(source_full_path)}"
            logging.error(msg); return False, msg

        file_basename = os.path.basename(source_full_path)

        if destination_folder: # Modalità Spostamento (NON usata nello script principale ora, ma tenuta per flessibilità)
            if not os.path.isdir(destination_folder):
                msg = f"Destinazione per spostamento originale non valida: {destination_folder}"
                logging.error(msg); return False, msg

            destination_full_path = os.path.join(destination_folder, file_basename)
            if os.path.exists(destination_full_path):
                msg = f"Spostamento orig. saltato: '{file_basename}' esiste già in destinazione."; logging.warning(msg); return False, msg

            try:
                logging.info(f"Tentativo spostamento (rename) originale '{file_basename}' a '{destination_folder}'")
                os.rename(source_full_path, destination_full_path)
                msg = f"Spostato (originale): {file_basename}"; logging.info(msg); return True, msg
            except OSError as e:
                # Handle cross-device link error
                if e.errno == 18 or 'cross-device' in str(e).lower() or 'different filesystem' in str(e).lower():
                    logging.warning(f"Rename fallito (cross-device): {e}. Tento copia+elimina per originale...")
                    try:
                        shutil.copy2(source_full_path, destination_full_path) # Copy data and metadata
                        os.remove(source_full_path) # Remove original ONLY after successful copy
                        msg = f"Spostato (originale, copia+elimina): {file_basename}"; logging.info(msg); return True, msg
                    except Exception as copy_e:
                        msg = f"Fallback copia+elimina per originale fallito: {copy_e}"; logging.error(msg, exc_info=True)
                        # Cleanup potentially copied file if deletion failed AFTER copy attempt
                        if os.path.exists(destination_full_path):
                            try:
                                os.remove(destination_full_path)
                                logging.info(f"Pulito file originale copiato parzialmente: {destination_full_path}")
                            except OSError as rm_err:
                                logging.error(f"Impossibile pulire file originale copiato parzialmente {destination_full_path}: {rm_err}")
                        return False, msg
                else:
                     # Other OS error during rename
                     msg = f"Errore OS durante spostamento (rename) originale '{file_basename}': {e}"; logging.error(msg); return False, msg
            except Exception as e:
                 msg = f"Errore imprevisto spostamento originale '{file_basename}': {e}"; logging.error(msg, exc_info=True); return False, msg

        else: # Modalità Eliminazione (usata dallo script principale)
             logging.info(f"Tentativo eliminazione originale '{file_basename}'...")
             try:
                 os.remove(source_full_path)
                 msg = f"Originale eliminato: {file_basename}"; logging.info(msg); return True, msg
             except OSError as e:
                 delete_error_msg = f"Errore OS eliminazione originale '{file_basename}': {e}"; logging.error(delete_error_msg); return False, delete_error_msg
             except Exception as e:
                 delete_error_msg = f"Errore imprevisto eliminazione originale '{file_basename}': {e}"; logging.error(delete_error_msg, exc_info=True); return False, delete_error_msg


# --- Music Player (VLC Based) ---
# Classe MusicPlayer (praticamente invariata, ma gestione init/release leggermente più robusta)
class MusicPlayer:
    """Gestisce la riproduzione audio con VLC."""
    def __init__(self):
        self.instance: Optional[vlc.Instance] = None
        self.player: Optional[vlc.MediaPlayer] = None
        self._com_initialized_here = False
        self.vlc_error: Optional[str] = None
        self._lock = QObject() # For potential future finer-grained locking if needed

        if not _vlc_installed:
            self.vlc_error = "Libreria python-vlc non trovata."
            logging.critical(self.vlc_error)
            return

        vlc_args = [
            '--quiet',               # Suppress most VLC messages
            '--no-video',            # Explicitly disable video output
            '--no-metadata-network-access', # Prevent fetching metadata online
            '--intf', 'dummy',       # No native interface
            '--no-plugins-cache',    # Try avoiding cache issues
            # '--verbose', '1'         # Increase verbosity for debugging if needed
            ]
        log_level = logging.getLogger().getEffectiveLevel()
        if log_level <= logging.DEBUG:
             # vlc_args.extend(['--verbose', '2']) # VLC debug level
             pass # Avoid too much VLC spam unless really needed

        try:
            # COM Initialization for Windows (best effort)
            if os.name == 'nt' and _pywin32_installed:
                try:
                    pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
                    self._com_initialized_here = True
                    logging.info("COM Initialized (Multi-Threaded).")
                except Exception as com_e:
                    logging.warning(f"COM Initialization failed (ignoro): {com_e}.")

            logging.debug(f"Creazione istanza VLC con args: {vlc_args}")
            self.instance = vlc.Instance(vlc_args)
            if not self.instance:
                # This often means libvlc.dll/so/dylib is missing or wrong architecture
                raise vlc.VLCException("Creazione istanza VLC fallita (Instance() ha restituito None). Controlla installazione VLC e PATH.")

            self.player = self.instance.media_player_new()
            if not self.player:
                raise vlc.VLCException("Creazione media player VLC fallita (media_player_new() ha restituito None).")

            logging.info("Istanza VLC e media player creati con successo.")
            self.set_volume(70) # Default volume

        except vlc.VLCException as vle:
            self.vlc_error = f"Errore inizializzazione VLC: {vle}."
            logging.critical(self.vlc_error, exc_info=True)
            self.release() # Clean up partially created objects
        except Exception as e:
            # Catch other potential errors during init (e.g., OSError if libvlc is missing)
            self.vlc_error = f"Errore imprevisto inizializzazione VLC: {e}."
            logging.critical(self.vlc_error, exc_info=True)
            self.release()

    def is_ready(self) -> bool:
        # Check both player and instance are valid
        return self.player is not None and self.instance is not None

    def get_init_error(self) -> Optional[str]:
        return self.vlc_error

    def play(self, file_path: str) -> bool:
        if not self.is_ready():
            logging.error("Play fallito: Player non inizializzato correttamente.")
            return False
        if not file_path or not os.path.isfile(file_path):
            logging.error(f"Play fallito: File non trovato o non valido: '{file_path}'")
            return False

        try:
            # Use correct path encoding for VLC
            # On Windows, default ANSI encoding might fail with non-ASCII paths.
            # Try forcing UTF-8 URI conversion
            try:
                uri = vlc.PathCodec.path_to_uri(file_path, encoding='utf-8')
            except Exception as path_codec_err:
                logging.warning(f"vlc.PathCodec fallito (riprovo semplice path): {path_codec_err}")
                uri = file_path # Fallback for simple paths

            logging.debug(f"Creazione Media per URI: {uri}")
            media = self.instance.media_new(uri) # media_new_path is deprecated

            if not media:
                logging.error(f"Creazione vlc.Media fallita per: {uri} (path: {file_path})")
                return False

            # Set HWND for Windows (optional, might help some audio drivers?)
            # if os.name == 'nt' and hasattr(self._lock, 'winId'):
            #    self.player.set_hwnd(self._lock.winId())

            self.player.set_media(media)
            media.release() # Media object can be released after set_media

            # Ensure previous state is stopped cleanly
            current_state = self.get_state()
            if current_state not in [vlc.State.Stopped, vlc.State.Ended, vlc.State.Error]:
                logging.debug(f"Stato player prima di play(): {current_state}. Chiamo stop() preventivamente.")
                self.player.stop()
                time.sleep(0.05) # Brief pause to allow stop command to process

            logging.debug(f"Chiamo player.play() per '{os.path.basename(file_path)}'")
            result = self.player.play()
            if result == -1:
                logging.error(f"player.play() ha restituito -1 (fallito) per '{os.path.basename(file_path)}'. Stato: {self.get_state()}")
                return False
            else:
                # Success might still be async, wait briefly to check state
                time.sleep(0.1)
                final_state = self.get_state()
                logging.info(f"Riproduzione avviata (stato VLC: {final_state}): {os.path.basename(file_path)}")
                if final_state not in [vlc.State.Opening, vlc.State.Buffering, vlc.State.Playing]:
                     logging.warning(f"Player.play() ha avuto successo ma lo stato finale è {final_state}, riproduzione potrebbe non essere attiva.")
                     # Consider returning False if state isn't Playing/Opening/Buffering soon after
                return True

        except Exception as e:
            logging.error(f"Eccezione durante il tentativo di playback di {os.path.basename(file_path)}: {e}", exc_info=True)
            return False


    def pause(self) -> None:
        if self.is_ready():
            # Pause toggles state. 0: pause, 1: play
            logging.debug(f"Chiamo player.pause(). Stato attuale: {self.get_state()}")
            self.player.pause()
            # State change might be slightly delayed
            QTimer.singleShot(50, lambda: logging.info(f"Pausa/Riprendi eseguito. Nuovo stato (atteso): {self.get_state()}"))
        else:
            logging.warning("Pause ignorato: Player non pronto.")

    def stop(self) -> None:
         if self.is_ready():
             current_state = self.get_state()
             if current_state != vlc.State.Stopped:
                  logging.debug(f"Invio comando Stop a VLC. Stato attuale: {current_state}")
                  self.player.stop()
                  # Allow VLC time to process stop, especially important before release()
                  # Checking state immediately might still show Playing
                  QTimer.singleShot(50, lambda: logging.info(f"Riproduzione fermata. Nuovo stato (atteso): {self.get_state()}"))
             else:
                 logging.debug("Stop ignorato: Player già fermo.")
         elif not self.is_ready():
             logging.warning("Stop ignorato: Player non pronto.")

    def set_volume(self, volume: int) -> None:
        if self.is_ready():
            clamped_vol = max(0, min(100, volume))
            # audio_set_volume returns 0 on success, -1 on failure
            if self.player.audio_set_volume(clamped_vol) == 0:
                logging.debug(f"Volume VLC impostato a {clamped_vol}")
            else:
                # This can fail if no audio output module is loaded (e.g., driver issues)
                logging.warning(f"Fallito tentativo impostazione volume VLC a {clamped_vol}")
        # else: logging.debug("Set Volume ignorato: Player non pronto.") # Too verbose

    def get_volume(self) -> int:
        return self.player.audio_get_volume() if self.is_ready() else 0

    def set_position(self, position: float) -> None:
        """ Set position as float between 0.0 and 1.0 """
        if self.is_ready():
            if self.player.is_seekable():
                clamped_pos = max(0.0, min(1.0, position))
                if self.player.set_position(clamped_pos) == 0: # set_position also returns 0/-1 but seems less reliable
                    logging.debug(f"Posizione VLC impostata a {clamped_pos:.3f}")
                else:
                     logging.warning(f"Fallito tentativo impostazione posizione VLC a {clamped_pos:.3f}")

            else:
                logging.warning("Media non seekable, set_position ignorato.")
        # else: logging.warning("Set Position ignorato: Player non pronto.") # Too verbose

    def get_position(self) -> float:
        """ Get position as float between 0.0 and 1.0 """
        return self.player.get_position() if self.is_ready() and self.player.get_media() else 0.0

    def get_length(self) -> int:
        """ Get length in milliseconds """
        # Can return 0 or -1 if length is unknown or not yet determined
        return self.player.get_length() if self.is_ready() and self.player.get_media() else -1

    def get_state(self) -> vlc.State:
        """ Get current playback state """
        # Added check for player validity before calling get_state
        if self.player:
            try:
                return self.player.get_state()
            except Exception as e:
                logging.error(f"Errore ottenimento stato VLC: {e}")
                return vlc.State.Error # Treat error as Error state
        return vlc.State.Error # Return Error if player is None

    def release(self) -> None:
        logging.debug("Avvio rilascio risorse VLC...")
        start_time = time.time()
        try:
            if self.player:
                player_instance = self.player
                self.player = None # Prevent further calls
                if player_instance.is_playing(): # Check using the instance we captured
                    logging.debug("Fermo il player prima del rilascio.")
                    player_instance.stop()
                    time.sleep(0.1) # Allow stop command to be processed
                logging.debug("Rilascio media player VLC.")
                player_instance.release()

            if self.instance:
                instance_instance = self.instance
                self.instance = None # Prevent further calls
                logging.debug("Rilascio istanza VLC.")
                instance_instance.release()

            if self._com_initialized_here:
                if os.name == 'nt' and _pywin32_installed:
                    try:
                        pythoncom.CoUninitialize()
                        logging.info("COM Deinizializzato.")
                    except Exception as com_e:
                        # This can sometimes fail if COM is still in use by other threads/libs
                        logging.warning(f"Errore CoUninitialize (ignoro): {com_e}")
                self._com_initialized_here = False

        except Exception as e:
            logging.error(f"Errore durante il rilascio delle risorse VLC: {e}", exc_info=True)
        finally:
            logging.debug(f"Rilascio VLC completato in {time.time() - start_time:.3f} sec.")


# --- Stile QSS (Dark Theme DJ) ---
DARK_QSS = """
QMainWindow { background-color: #2c3e50; color: #ecf0f1; }
QWidget { color: #ecf0f1; } /* Default widget text color */
QLabel { color: #ecf0f1; padding-bottom: 2px; }
QLabel#StatusLabel { padding: 0 5px; margin: 0; color: #bdc3c7; } /* Specific for status bar */
QLabel#VolumeValueLabel { color: #ecf0f1; } /* Ensure volume label uses default */
QLabel:disabled { color: #7f8c8d; }
QLineEdit { background-color: #34495e; border: 1px solid #566573; padding: 4px; border-radius: 3px; color: #ecf0f1; }
QLineEdit:read-only { background-color: #405060; }
QLineEdit:disabled { background-color: #304050; color: #7f8c8d; }
QCheckBox { spacing: 5px; color: #ecf0f1; }
QCheckBox::indicator { width: 13px; height: 13px; }
QCheckBox::indicator:unchecked { border: 1px solid #7f8c8d; background-color: #34495e; border-radius: 3px; }
QCheckBox::indicator:checked { background-color: #3498db; border: 1px solid #2980b9; border-radius: 3px; }
QCheckBox::indicator:disabled { border: 1px solid #44505a; background-color: #304050; }
QCheckBox:disabled { color: #7f8c8d; }
QPushButton { background-color: #3498db; color: white; border: 1px solid #2980b9; padding: 6px 12px; border-radius: 4px; min-width: 80px; }
QPushButton:hover { background-color: #4aa3df; border: 1px solid #3498db; }
QPushButton:pressed { background-color: #2980b9; }
QPushButton:disabled { background-color: #566573; color: #95a5a6; border: 1px solid #44505a; }
QPushButton#PreviewButton { /* No change needed if toggle works */ }
QPushButton#PreviewButton:checked { background-color: #e67e22; border: 1px solid #d35400; color: white; } /* Orange when active */
QPushButton#PreviewButton:checked:hover { background-color: #f39c12; }
QListWidget { background-color: #34495e; border: 1px solid #566573; border-radius: 3px; alternate-background-color: #3a5064; outline: 0; color: #ecf0f1; }
QListWidget::item { padding: 5px 3px; border-bottom: 1px solid #405060; } /* Add subtle line between items */
QListWidget::item:alternate { background-color: #3a5064; }
QListWidget::item:selected { background-color: #3498db; color: white; border: none; }
QListWidget::item:disabled { color: #7f8c8d; background-color: #304050; } /* Style for disabled items if needed */
QComboBox { background-color: #34495e; border: 1px solid #566573; border-radius: 3px; padding: 4px 18px 4px 5px; min-width: 6em; color: #ecf0f1; }
QComboBox:!editable { background: #34495e; }
QComboBox:on { /* shift the text when the popup opens */ padding-top: 4px; padding-left: 5px; background-color: #4a6175; border: 1px solid #3498db; }
QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 15px; border-left-width: 1px; border-left-color: #566573; border-left-style: solid; border-top-right-radius: 3px; border-bottom-right-radius: 3px; background-color: #34495e; }
QComboBox::down-arrow { border: solid #bdc3c7; border-width: 0 2px 2px 0; display: inline-block; padding: 2px; transform: rotate(45deg); -webkit-transform: rotate(45deg); margin: 0px 2px 3px 0px; }
QComboBox QAbstractItemView { border: 1px solid #3498db; background-color: #34495e; color: #ecf0f1; selection-background-color: #3498db; selection-color: white; outline: 0; }
QComboBox:disabled { background-color: #304050; color: #7f8c8d; border: 1px solid #44505a; }
QComboBox::down-arrow:disabled { border-top-color: #7f8c8d; /* Make arrow dimmer when disabled */ }
QSlider::groove:horizontal { border: 1px solid #44505a; height: 6px; background: #2c3e50; margin: 2px 0; border-radius: 3px; }
QSlider::handle:horizontal { background: #3498db; border: 1px solid #2980b9; width: 16px; height: 16px; margin: -6px 0; /* handle is placed based on the groove */ border-radius: 8px; }
QSlider::handle:horizontal:hover { background: #4aa3df; border: 1px solid #3498db; }
QSlider::handle:horizontal:pressed { background: #2980b9; border: 1px solid #2980b9; }
QSlider::add-page:horizontal { background: #566573; border: 1px solid #44505a; border-radius: 3px; }
QSlider::sub-page:horizontal { background: #3498db; border: 1px solid #44505a; border-radius: 3px; }
QSlider::handle:horizontal:disabled { background: #566573; border: 1px solid #44505a; }
QSlider::groove:horizontal:disabled { background: #405060; border: 1px solid #44505a; }
QStatusBar { background-color: #1e2b37; color: #bdc3c7; border-top: 1px solid #3a5064; }
QStatusBar::item { border: none; } /* Remove borders between items if any */
QFrame[frameShape="4"], QFrame[frameShape="5"] { /* HLine, VLine */ border: none; background-color: #566573; min-height: 1px; max-height: 1px; min-width: 1px; max-width: 1px; }
QToolTip { background-color: #4a6175; color: #ecf0f1; border: 1px solid #566573; padding: 5px; border-radius: 3px; opacity: 230; /* Opacity might require specific style setup */ }
/* Progress Dialog Style (Optional) */
QProgressDialog { background-color: #2c3e50; color: #ecf0f1; border: 1px solid #566573; }
QProgressDialog QLabel { color: #ecf0f1; }
QProgressDialog QPushButton { /* Use default button style above */ min-width: 60px; }
/* QProgressBar embedded in QProgressDialog */
QProgressDialog QProgressBar { text-align: center; background-color: #34495e; border: 1px solid #566573; border-radius: 3px; color: #ecf0f1; }
QProgressDialog QProgressBar::chunk { background-color: #3498db; border-radius: 3px; }
"""

# --- Worker Threads ---

class WorkerSignals(QObject):
    """Defines signals available from worker threads."""
    finished = pyqtSignal(object) # Emits result object on success
    error = pyqtSignal(str)       # Emits error message string on failure
    progress = pyqtSignal(str)    # Emits progress string
    cancelled = pyqtSignal(str)   # Emits cancellation message

class FileScannerWorker(QObject):
    """Worker to scan files in a separate thread."""
    signals = WorkerSignals()

    def __init__(self, file_manager: FileManager, directory: str, recursive: bool):
        super().__init__()
        self.file_manager = file_manager
        self.directory = directory
        self.recursive = recursive
        self.setObjectName(f"FileScannerWorker-{id(self)}") # For logging ID
        logging.debug(f"Worker {self.objectName()} istanziato per {directory}")

    @QtCore.pyqtSlot()
    def run(self):
        logging.info(f"Avvio {self.objectName()}...")
        thread = QThread.currentThread() # Get reference to the QThread running this worker
        if not thread:
            logging.error("Impossibile ottenere QThread corrente per FileScannerWorker.")
            self.signals.error.emit("Errore interno avvio worker.")
            return

        try:
            self.signals.progress.emit(f"Scansione '{os.path.basename(self.directory)}'...")
            music_data_list, status_msg = self.file_manager.load_music_files(self.directory, self.recursive)

            # Check if cancelled *during* the operation
            if thread.isInterruptionRequested():
                logging.info(f"{self.objectName()} interrotto durante esecuzione.")
                self.signals.cancelled.emit("Scansione annullata.")
                return # Don't emit finished or error

            if "errore" in status_msg.lower() or "trovato" in status_msg.lower() or "validi" in status_msg.lower():
                # Treat messages indicating failure or empty results as potential "errors" or warnings for UI
                 if not music_data_list and "interrotta" not in status_msg: # If list is empty AND not explicitly cancelled
                    logging.warning(f"{self.objectName()} terminato ma con stato: {status_msg}")
                    self.signals.error.emit(status_msg) # Emit as error if no files found
                 else: # Files found or explicitly cancelled (already handled), just log
                    logging.info(f"{self.objectName()} terminato. Stato: {status_msg}")
                    self.signals.finished.emit(music_data_list)
            else:
                # Normal successful completion
                logging.info(f"{self.objectName()} terminato con successo. Stato: {status_msg}")
                self.signals.finished.emit(music_data_list)

        except Exception as e:
            error_msg = f"Errore non gestito in {self.objectName()}: {e}"
            logging.error(error_msg, exc_info=True)
            # Check again for cancellation in case the error occurred during shutdown
            if thread.isInterruptionRequested():
                 self.signals.cancelled.emit("Scansione annullata (durante errore).")
            else:
                 self.signals.error.emit(error_msg)
        finally:
            logging.debug(f"{self.objectName()} run() terminato.")


class NormalizeWorker(QObject):
    """Worker for normalization (Preview or Move)."""
    signals = WorkerSignals()

    # Result structure for normalization
    @dataclass
    class NormalizeResult:
        success: bool
        message: str
        measured_lufs: Optional[float] = None
        output_path: Optional[str] = None       # Path to the normalized file (temp or final)
        original_source_path: Optional[str] = None # Keep track of the source MP3
        # For Move operations:
        delete_success: Optional[bool] = None
        delete_message: Optional[str] = None

    def __init__(self,
                 file_manager: FileManager,
                 lufs_meter: pyln.Meter,
                 target_lufs: float,
                 source_path: str,
                 destination_path: str,
                 is_preview: bool = False, # True if generating temp preview file
                 delete_original_on_success: bool = False): # True for move operation
        super().__init__()
        self.file_manager = file_manager
        self.lufs_meter = lufs_meter
        self.target_lufs = target_lufs
        self.source_path = source_path
        self.destination_path = destination_path
        self.is_preview = is_preview
        self.delete_original = delete_original_on_success
        self.setObjectName(f"NormalizeWorker-{('Preview' if is_preview else 'Move')}-{os.path.basename(source_path)}")
        logging.debug(f"Worker {self.objectName()} istanziato.")

    @QtCore.pyqtSlot()
    def run(self):
        logging.info(f"Avvio {self.objectName()}...")
        thread = QThread.currentThread()
        if not thread:
            logging.error("Impossibile ottenere QThread corrente per NormalizeWorker.")
            self.signals.error.emit("Errore interno avvio worker normalizzazione.")
            return

        norm_result = self.NormalizeResult(
            success=False, message="Inizio",
            original_source_path=self.source_path,
            output_path=None
        )

        try:
            # --- 1. Normalize and Save ---
            action_verb = "Anteprima" if self.is_preview else "Normalizzazione"
            self.signals.progress.emit(f"{action_verb} '{os.path.basename(self.source_path)}'...")

            norm_success, norm_message, measured_lufs = self.file_manager.normalize_and_save(
                self.lufs_meter, self.target_lufs, self.source_path, self.destination_path
            )

            # Check for cancellation *during* normalization
            if thread.isInterruptionRequested():
                logging.info(f"{self.objectName()} interrotto durante normalizzazione.")
                self.signals.cancelled.emit(f"{action_verb} annullata.")
                # Attempt to cleanup potentially created destination file if cancelled
                if os.path.exists(self.destination_path):
                     try:
                         os.remove(self.destination_path)
                         logging.info(f"Pulito file destinazione '{self.destination_path}' dopo annullamento.")
                     except OSError as e:
                         logging.warning(f"Impossibile pulire file destinazione '{self.destination_path}' dopo annullamento: {e}")
                return

            # Store normalization result
            norm_result.success = norm_success
            norm_result.message = norm_message
            norm_result.measured_lufs = measured_lufs
            if norm_success:
                 norm_result.output_path = self.destination_path # Store output path only on success
            else:
                # Normalization failed, emit error and stop
                logging.error(f"{self.objectName()} fallita: {norm_message}")
                self.signals.error.emit(f"Errore {action_verb.lower()}: {norm_message}")
                return

            # --- 2. Delete Original (Only for Move operation, after successful normalization) ---
            if not self.is_preview and self.delete_original and norm_success:
                logging.info(f"{self.objectName()}: Normalizzazione OK, procedo con eliminazione originale.")
                self.signals.progress.emit(f"Eliminazione originale '{os.path.basename(self.source_path)}'...")

                delete_success, delete_message = self.file_manager.move_or_delete_original(self.source_path, destination_folder=None)

                norm_result.delete_success = delete_success
                norm_result.delete_message = delete_message

                if not delete_success:
                    # Log warning, but the overall operation might still be considered 'finished' (with warning)
                    logging.warning(f"{self.objectName()}: Eliminazione originale fallita: {delete_message}")
                    # Modify the main message to include the warning
                    norm_result.message += f" (ATTENZIONE: {delete_message})"
                    # Do not mark overall success as False here, let MainWindow decide based on delete_success
            elif not self.is_preview and self.delete_original and not norm_success:
                 logging.warning(f"{self.objectName()}: Normalizzazione fallita, salto eliminazione originale.")
            else:
                logging.debug(f"{self.objectName()}: Nessuna eliminazione originale richiesta o applicabile.")


            # --- 3. Emit Final Result ---
            if thread.isInterruptionRequested():
                 # Should have been caught earlier, but double-check before emitting 'finished'
                 logging.info(f"{self.objectName()} interrotto prima di emettere 'finished'.")
                 self.signals.cancelled.emit(f"{action_verb} annullata (finale).")
            else:
                logging.info(f"{self.objectName()} terminato. Successo Norm: {norm_result.success}, Successo Elim: {norm_result.delete_success}")
                self.signals.finished.emit(norm_result) # Emit the result object


        except Exception as e:
            error_msg = f"Errore non gestito in {self.objectName()}: {e}"
            logging.error(error_msg, exc_info=True)
            if thread.isInterruptionRequested():
                 self.signals.cancelled.emit(f"{action_verb} annullata (durante errore).")
            else:
                self.signals.error.emit(f"Errore {action_verb.lower()}: {error_msg}")
        finally:
             logging.debug(f"{self.objectName()} run() terminato.")



# --- Main Application Window ---
class MainWindow(QMainWindow):
    """Finestra principale (ora con gestione multithreading)."""
    # Define signals this window might emit if needed elsewhere (optional)
    # library_updated = pyqtSignal()

    def __init__(self):
        super().__init__()
        # Prerequisite Checks
        if not _pyqt5_installed: sys.exit(1)
        if not _vlc_installed: self._show_critical_error("Libreria python-vlc non trovata.", "Installala e assicurati che VLC sia nel PATH."); sys.exit(1)
        # NumPy is implicitly required by audio libs, but check specifically
        if not _numpy_installed: self._show_critical_error("Libreria numpy non trovata.", "Normalizzazione/Anteprima/Riproduzione potrebbero non funzionare."); # Don't exit, but warn severely

        self.setWindowTitle(f"{APP_NAME} - by BENNY C. DJ - PRODUCER")
        self.setGeometry(100, 100, 1000, 780)
        self.setMinimumSize(850, 650) # Slightly larger min size

        # Settings and Managers
        self.settings = QSettings(ORG_NAME, APP_NAME)
        self.file_manager = FileManager() # Manages file operations logic
        self.music_player = MusicPlayer() # Manages playback

        # Check Music Player Init
        if not self.music_player.is_ready():
            error_msg = self.music_player.get_init_error() or "Errore sconosciuto inizializzazione VLC."
            detailed_text = ("Assicurati VLC Player sia installato (stessa architettura Python: 64bit o 32bit) e che le sue librerie (libvlc.dll/so/dylib) siano accessibili (nel PATH di sistema o nella cartella dell'app).\n"
                           f"Dettaglio errore: {error_msg}")
            self._show_critical_error("Errore Inizializzazione Player VLC", detailed_text)
            sys.exit(1) # Exit if player is critical and failed

        # LUFS Meter (created once, passed to workers)
        self.lufs_meter: Optional[pyln.Meter] = None
        self.target_lufs = TARGET_LUFS_DEFAULT # Default value
        if _pyloudnorm_installed and _numpy_installed and _soundfile_installed:
            try:
                 # Initialize with a common sample rate, will be adjusted in normalize_and_save if needed
                 self.lufs_meter = pyln.Meter(44100)
                 logging.info("Meter LUFS (pyloudnorm) inizializzato centralmente.")
            except Exception as e:
                 logging.error(f"Errore critico creazione pyln.Meter: {e}. Normalizzazione disabilitata.")
                 self.lufs_meter = None
                 QMessageBox.critical(self, "Errore Inizializzazione Audio", f"Impossibile inizializzare il meter LUFS (pyloudnorm): {e}\n\nLa normalizzazione audio sarà disabilitata.")
        else:
             logging.warning("Normalizzazione audio non disponibile (librerie NumPy/Soundfile/PyLoudNorm mancanti).")
             self.lufs_meter = None


        # Internal State
        self.current_input_dir: Optional[str] = None
        self.current_base_output_dir: Optional[str] = None
        self.loaded_music_data: List[MusicFileData] = [] # Master list of scanned data
        self.list_item_map: Dict[str, QListWidgetItem] = {} # Map full_path -> QListWidgetItem
        self.recent_folders: List[str] = []
        self.currently_playing_item: Optional[QListWidgetItem] = None
        self.current_playing_file_path: Optional[str] = None # Path actually being played (original or temp preview)
        self.current_media_duration_ms: int = -1
        self.is_progress_slider_dragging: bool = False
        self.is_preview_playing: bool = False
        self.current_preview_temp_path: Optional[str] = None # Path to the temporary preview WAV file
        self.original_file_for_preview: Optional[str] = None # Keep track of the original MP3 path for the active preview
        self.active_worker_thread: Optional[QThread] = None # Keep track of the running thread
        self.worker_object: Optional[QObject] = None # Keep track of the worker object

        # Fonts
        self.default_font = self.font()
        self.playing_font = QtGui.QFont(self.default_font)
        self.playing_font.setBold(True)

        self._init_ui()
        self._init_timers()
        self._load_settings() # This loads paths, volume, LUFS target and might trigger initial scan
        self._update_button_states() # Initial state based on loaded settings
        self.statusBar().showMessage("Pronto.", STATUS_BAR_TIMEOUT)
        logging.info("Interfaccia Utente Inizializzata.")

        # Check optional library status after UI init
        if not _soundfile_installed or not _pyloudnorm_installed or not self.lufs_meter:
            QMessageBox.warning(self, "Librerie Mancanti o Errore Init", "NumPy/Soundfile/PyLoudNorm mancanti o errore inizializzazione Meter LUFS.\nNormalizzazione e Anteprima Normalizzata non disponibili.")
        if not _mutagen_installed:
            QMessageBox.warning(self, "Libreria Mancante", "Mutagen non trovato.\nLa durata dei brani non verrà caricata.")

        self._set_busy(False) # Ensure UI is not busy initially


    def _show_critical_error(self, title: str, message: str):
        """Utility to show critical error message box even if main window fails."""
        # Ensure QApplication exists
        app = QApplication.instance()
        if not app:
            app = QApplication(sys.argv) # Create a temporary one if needed

        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Critical)
        msg_box.setWindowTitle(title)
        msg_box.setText(f"<b>{title}</b>")
        msg_box.setInformativeText(message)
        msg_box.setStandardButtons(QMessageBox.Ok)
        try:
            # Apply stylesheet if possible, to make it look consistent
             msg_box.setStyleSheet(DARK_QSS)
        except Exception:
             pass # Ignore style errors for critical messages
        msg_box.exec_()


    def _init_ui(self):
        """Crea e dispone i widget UI (invariato nella struttura base)."""
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(12, 12, 12, 12)
        self.setStyleSheet(DARK_QSS) # Apply the custom dark style

        # --- 1. Configurazione Percorsi ---
        config_group_layout = QVBoxLayout()

        # Input Path
        input_layout = QHBoxLayout()
        self.folder_input_label = QLabel("Cartella Input:")
        self.folder_input_edit = QLineEdit(self)
        self.folder_input_edit.setReadOnly(True)
        self.folder_input_edit.setPlaceholderText("Nessuna cartella input selezionata")
        self.browse_input_button = QPushButton("Sfoglia...")
        self.browse_input_button.setToolTip("Seleziona la cartella contenente i file MP3")
        self.browse_input_button.clicked.connect(self._browse_input_folder)
        input_layout.addWidget(self.folder_input_label)
        input_layout.addWidget(self.folder_input_edit, 1) # Stretch edit field
        input_layout.addWidget(self.browse_input_button)
        config_group_layout.addLayout(input_layout)

        # Input Options (Recursive Scan)
        input_options_layout = QHBoxLayout()
        self.recursive_scan_checkbox = QCheckBox("Includi Sottocartelle")
        self.recursive_scan_checkbox.setToolTip("Seleziona per scansionare anche tutte le sottocartelle")
        self.recursive_scan_checkbox.stateChanged.connect(self._trigger_reload_music_list) # Reload when checkbox changes
        input_options_layout.addStretch(1) # Push checkbox to the right
        input_options_layout.addWidget(self.recursive_scan_checkbox)
        config_group_layout.addLayout(input_options_layout)

        # Output Path
        output_layout = QHBoxLayout()
        self.folder_output_label = QLabel("Cartella Base Output:")
        self.folder_output_edit = QLineEdit(self)
        self.folder_output_edit.setReadOnly(True)
        self.folder_output_edit.setPlaceholderText("Seleziona la cartella dove salvare i file normalizzati")
        self.browse_output_button = QPushButton("Sfoglia...")
        self.browse_output_button.setToolTip("Seleziona la cartella radice per l'output organizzato")
        self.browse_output_button.clicked.connect(self._browse_base_output_folder)
        output_layout.addWidget(self.folder_output_label)
        output_layout.addWidget(self.folder_output_edit, 1) # Stretch edit field
        output_layout.addWidget(self.browse_output_button)
        config_group_layout.addLayout(output_layout)

        main_layout.addLayout(config_group_layout)

        # Separator
        separator1 = QFrame()
        separator1.setFrameShape(QFrame.HLine); separator1.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(separator1)

        # --- 2. Lista File e Filtro ---
        list_filter_layout = QVBoxLayout()

        # Filter Controls
        filter_layout = QHBoxLayout()
        self.filter_label = QLabel("Filtra:")
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Cerca per nome file...")
        self.filter_edit.setToolTip("Digita per filtrare l'elenco dei brani")
        self.filter_edit.textChanged.connect(self._filter_music_list)
        self.clear_filter_button = QPushButton("Pulisci")
        self.clear_filter_button.setToolTip("Rimuovi il filtro di ricerca")
        self.clear_filter_button.clicked.connect(lambda: self.filter_edit.clear())
        self.clear_filter_button.setFixedWidth(80)
        filter_layout.addWidget(self.filter_label)
        filter_layout.addWidget(self.filter_edit, 1) # Stretch edit field
        filter_layout.addWidget(self.clear_filter_button)
        list_filter_layout.addLayout(filter_layout)

        # Music List Widget
        self.music_list_widget = QListWidget(self)
        self.music_list_widget.setToolTip("Elenco dei file MP3 trovati. Doppio click per riprodurre l'originale.")
        self.music_list_widget.setSelectionMode(QAbstractItemView.SingleSelection) # Only one selection at a time
        self.music_list_widget.setAlternatingRowColors(True) # Improves readability
        self.music_list_widget.currentItemChanged.connect(self._on_current_item_changed) # Update state on selection change
        self.music_list_widget.itemDoubleClicked.connect(self._play_selected_music_from_item) # Play on double click
        list_filter_layout.addWidget(self.music_list_widget, 1) # Allow list to stretch vertically

        main_layout.addLayout(list_filter_layout, 1) # Allow this section to stretch

        # Separator
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.HLine); separator2.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(separator2)

        # --- 3. Spostamento Interattivo / Azioni ---
        move_controls_layout = QVBoxLayout()
        move_controls_layout.setSpacing(8)

        # Recent Folder Selection
        recent_folder_layout = QHBoxLayout()
        self.recent_folder_label = QLabel("Sposta in Recente:")
        self.recent_folder_combo = QComboBox()
        self.recent_folder_combo.setToolTip("Seleziona una sottocartella usata di recente")
        self.recent_folder_combo.setMaxCount(MAX_RECENT_FOLDERS + 5) # Limit dropdown size
        self.recent_folder_combo.setInsertPolicy(QComboBox.NoInsert) # Items are managed programmatically
        self.recent_folder_combo.addItem("--- Seleziona Recente ---") # Placeholder
        self.recent_folder_combo.setCurrentIndex(0)
        self.recent_folder_combo.currentIndexChanged.connect(self._recent_folder_selected) # Update edit field when selected
        recent_folder_layout.addWidget(self.recent_folder_label)
        recent_folder_layout.addWidget(self.recent_folder_combo, 1) # Stretch combo box
        move_controls_layout.addLayout(recent_folder_layout)

        # Subfolder Input and Move Button
        move_action_layout = QHBoxLayout()
        self.subfolder_label = QLabel("o Nuova/Specifica:")
        self.subfolder_edit = QLineEdit()
        self.subfolder_edit.setPlaceholderText("es. House/Deep House o Techno/Peak Time")
        self.subfolder_edit.setToolTip("Inserisci il percorso relativo della sottocartella di destinazione (verrà creata se non esiste)")
        self.subfolder_edit.textChanged.connect(self._update_button_states) # Enable/disable move button based on input
        self.move_to_subfolder_button = QPushButton("📁 Normalizza e Sposta")
        self.move_to_subfolder_button.setToolTip("Normalizza il file selezionato al Target LUFS, lo salva come WAV nella sottocartella specificata e cancella l'MP3 originale")
        self.move_to_subfolder_button.clicked.connect(self._move_selected_to_subfolder)
        self.move_to_subfolder_button.setIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton)) # Use save icon
        move_action_layout.addWidget(self.subfolder_label)
        move_action_layout.addWidget(self.subfolder_edit, 1) # Stretch edit field
        move_action_layout.addWidget(self.move_to_subfolder_button)
        move_controls_layout.addLayout(move_action_layout)

        main_layout.addLayout(move_controls_layout)

        # Separator
        separator3 = QFrame()
        separator3.setFrameShape(QFrame.HLine); separator3.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(separator3)

        # --- 4. Controlli Riproduzione ---
        playback_group_layout = QVBoxLayout()
        playback_group_layout.setSpacing(6)

        # Progress Bar Area
        progress_layout = QHBoxLayout()
        progress_layout.setSpacing(8)
        self.current_time_label = QLabel("00:00")
        self.current_time_label.setFixedWidth(45)
        self.current_time_label.setAlignment(Qt.AlignCenter)
        self.progress_slider = QSlider(Qt.Horizontal)
        self.progress_slider.setToolTip("Barra di avanzamento / Clicca o trascina per cercare")
        self.progress_slider.setRange(0, 1000) # Use a fixed range (0-1000) for position (0.0-1.0)
        self.progress_slider.setValue(0)
        # Connect slider signals for seeking
        self.progress_slider.sliderPressed.connect(self._progress_slider_pressed)
        self.progress_slider.sliderReleased.connect(self._progress_slider_released)
        self.progress_slider.sliderMoved.connect(self._progress_slider_moved)
        self.total_time_label = QLabel("00:00")
        self.total_time_label.setFixedWidth(45)
        self.total_time_label.setAlignment(Qt.AlignCenter)
        progress_layout.addWidget(self.current_time_label)
        progress_layout.addWidget(self.progress_slider, 1) # Stretch slider
        progress_layout.addWidget(self.total_time_label)
        playback_group_layout.addLayout(progress_layout)

        # Buttons and Volume Area
        controls_volume_layout = QHBoxLayout()
        controls_volume_layout.setSpacing(15)

        # Playback Buttons
        playback_buttons_layout = QHBoxLayout()
        playback_buttons_layout.setSpacing(6)
        self.play_button = QPushButton("▶ Play Orig.")
        self.play_button.setToolTip("Riproduci il file MP3 originale selezionato (Spazio)")
        self.play_button.setShortcut(Qt.Key_Space) # Keyboard shortcut
        self.play_button.clicked.connect(self._play_selected_music)
        self.play_button.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        # Preview Button (Checkable)
        self.preview_button = QPushButton("🎧 Preview Norm.")
        self.preview_button.setToolTip("Genera e ascolta un'anteprima normalizzata (WAV temporaneo) (Ctrl+P)")
        self.preview_button.setShortcut(QtGui.QKeySequence(Qt.CTRL | Qt.Key_P)) # Keyboard shortcut
        self.preview_button.setCheckable(True) # Make it a toggle button
        self.preview_button.setObjectName("PreviewButton") # For specific styling (e.g., :checked)
        self.preview_button.toggled.connect(self._toggle_preview_normalization) # Handle toggle state changes
        self.preview_button.setIcon(self.style().standardIcon(QStyle.SP_MediaVolume)) # Use volume icon for preview
        # Pause Button
        self.pause_button = QPushButton("❚❚ Pausa")
        self.pause_button.setToolTip("Metti in pausa / Riprendi la riproduzione (P)")
        self.pause_button.setShortcut(Qt.Key_P) # Keyboard shortcut
        self.pause_button.clicked.connect(self._toggle_pause)
        self.pause_button.setIcon(self.style().standardIcon(QStyle.SP_MediaPause))
        # Stop Button
        self.stop_button = QPushButton("■ Stop")
        self.stop_button.setToolTip("Ferma la riproduzione (S)")
        self.stop_button.setShortcut(Qt.Key_S) # Keyboard shortcut
        self.stop_button.clicked.connect(self._stop_playback)
        self.stop_button.setIcon(self.style().standardIcon(QStyle.SP_MediaStop))

        playback_buttons_layout.addWidget(self.play_button)
        playback_buttons_layout.addWidget(self.preview_button)
        playback_buttons_layout.addWidget(self.pause_button)
        playback_buttons_layout.addWidget(self.stop_button)
        playback_buttons_layout.addStretch(1) # Push buttons to the left
        controls_volume_layout.addLayout(playback_buttons_layout)

        # Volume Control
        volume_layout = QHBoxLayout()
        volume_layout.setSpacing(5)
        self.volume_label = QLabel("🔊")
        self.volume_label.setToolTip("Volume")
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setToolTip("Regola il volume di riproduzione")
        self.volume_slider.valueChanged.connect(self._set_volume) # Connect to set volume
        self.volume_slider.setFixedWidth(150) # Fixed width for volume slider
        self.volume_value_label = QLabel("70%") # Initial display value
        self.volume_value_label.setObjectName("VolumeValueLabel") # For potential specific styling
        self.volume_value_label.setFixedWidth(35)
        self.volume_value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.volume_slider.valueChanged.connect(lambda value: self.volume_value_label.setText(f"{value}%")) # Update label text
        volume_layout.addWidget(self.volume_label)
        volume_layout.addWidget(self.volume_slider)
        volume_layout.addWidget(self.volume_value_label)
        controls_volume_layout.addLayout(volume_layout) # Add volume to the right side

        playback_group_layout.addLayout(controls_volume_layout)
        main_layout.addLayout(playback_group_layout)

        # --- 5. Signature ---
        signature_layout = QHBoxLayout()
        signature_label = QLabel("Developed by BENNY C. DJ - PRODUCER")
        font = signature_label.font()
        font.setPointSize(8)
        font.setItalic(True)
        signature_label.setFont(font)
        signature_label.setAlignment(Qt.AlignRight)
        signature_layout.addWidget(signature_label)
        main_layout.addLayout(signature_layout)

        # --- 6. Status Bar ---
        self.status_bar = QStatusBar(self)
        self.setStatusBar(self.status_bar)
        # Permanent widget for LUFS target display
        self.lufs_status_label = QLabel(f"Target: {self.target_lufs:.1f} LUFS")
        self.lufs_status_label.setObjectName("StatusLabel") # For styling
        self.lufs_status_label.setToolTip("Livello LUFS target per la normalizzazione")
        self.status_bar.addPermanentWidget(self.lufs_status_label)
        # Placeholder for dynamic status messages
        self.status_message_label = QLabel("Pronto.")
        self.status_message_label.setObjectName("StatusLabel")
        self.status_bar.addWidget(self.status_message_label, 1) # Make it stretch


    def _init_timers(self):
        """Inizializza QTimer per aggiornamento progresso UI (playback)."""
        self.progress_timer = QTimer(self)
        self.progress_timer.setInterval(PROGRESS_TIMER_INTERVAL) # Update ~4 times per second
        self.progress_timer.timeout.connect(self._update_progress)
        logging.debug("Timer Progresso UI inizializzato.")

        # Timer for clearing status bar messages
        self.status_clear_timer = QTimer(self)
        self.status_clear_timer.setSingleShot(True)
        self.status_clear_timer.timeout.connect(lambda: self.status_message_label.setText("Pronto."))


    # --- Thread Management & UI State ---

    def _set_busy(self, busy: bool, message: str = ""):
        """Mette la UI in stato 'occupato' durante operazioni worker."""
        if busy:
            if not message:
                message = "Operazione in corso..."
            self.show_status_message(message, persistent=True) # Show persistent message
            # Disable critical controls during background tasks
            self.browse_input_button.setEnabled(False)
            self.browse_output_button.setEnabled(False)
            self.recursive_scan_checkbox.setEnabled(False)
            self.music_list_widget.setEnabled(False) # Prevent selection changes
            self.filter_edit.setEnabled(False)
            self.clear_filter_button.setEnabled(False)
            self.recent_folder_combo.setEnabled(False)
            self.subfolder_edit.setEnabled(False)
            self.move_to_subfolder_button.setEnabled(False)
            self.play_button.setEnabled(False)
            self.preview_button.setEnabled(False) # Disable starting new preview
            # Keep playback controls enabled if something is ALREADY playing
            is_playing = self.music_player.get_state() in [vlc.State.Playing, vlc.State.Paused]
            self.pause_button.setEnabled(is_playing)
            self.stop_button.setEnabled(is_playing)
            self.progress_slider.setEnabled(is_playing)
            self.setCursor(Qt.WaitCursor)
        else:
            self.unsetCursor()
            self.music_list_widget.setEnabled(True) # Re-enable list first
            self._update_button_states() # Re-enable controls based on current state
            if self.status_message_label.text() == message or message == "Operazione in corso...":
                 # If the persistent message is still shown, clear it after a delay
                 self.show_status_message("Pronto.", timeout=STATUS_BAR_TIMEOUT)


    def start_worker(self, worker: QObject, slot_function: callable, message: str = ""):
        """Helper per avviare un worker in un thread."""
        if self.active_worker_thread and self.active_worker_thread.isRunning():
            logging.warning("Tentativo di avviare un nuovo worker mentre uno è già attivo.")
            QMessageBox.warning(self, "Operazione in Corso", "Attendere il completamento dell'operazione corrente.")
            return False

        thread = QThread(self)
        thread.setObjectName(f"WorkerThread-{worker.objectName()}")
        worker.moveToThread(thread)
        self.worker_object = worker # Store reference to worker
        self.active_worker_thread = thread # Store reference to thread

        # Connect signals
        worker.signals.finished.connect(self._on_worker_finished)
        worker.signals.error.connect(self._on_worker_error)
        worker.signals.progress.connect(lambda msg: self.show_status_message(msg, persistent=True))
        worker.signals.cancelled.connect(self._on_worker_cancelled)

        # Connect thread lifecycle signals
        thread.started.connect(slot_function) # Call the worker's run method
        # Clean up when thread finishes (runs in main thread context)
        thread.finished.connect(self._on_thread_finished)

        # Start the thread
        thread.start()
        self._set_busy(True, message if message else f"Avvio {worker.objectName()}...")
        logging.info(f"Thread {thread.objectName()} avviato per worker {worker.objectName()}.")
        return True

    def _on_worker_finished(self, result: Any):
        """Slot generico chiamato al completamento con successo del worker."""
        logging.info(f"Worker {self.sender().objectName()} finished successfully.")
        # Determine which worker finished and call specific handler
        if isinstance(self.sender(), FileScannerWorker):
            self._on_scan_finished(result)
        elif isinstance(self.sender(), NormalizeWorker):
             if self.sender().is_preview:
                 self._on_preview_generated(result)
             else:
                 self._on_normalize_move_finished(result)
        else:
            logging.warning(f"Segnale 'finished' ricevuto da worker sconosciuto: {self.sender()}")

        # Reset busy state (thread finished signal will handle actual cleanup)
        # self._set_busy(False) # Done in _on_thread_finished


    def _on_worker_error(self, error_message: str):
        """Slot generico chiamato quando un worker emette un errore."""
        worker_name = self.sender().objectName() if self.sender() else "Sconosciuto"
        logging.error(f"Errore dal worker {worker_name}: {error_message}")
        QMessageBox.critical(self, f"Errore Operazione ({worker_name})", f"Si è verificato un errore:\n\n{error_message}\n\nVedi il file di log per dettagli.")
        # Reset busy state (thread finished signal will handle actual cleanup)
        # self._set_busy(False, "Errore.") # Done in _on_thread_finished


    def _on_worker_cancelled(self, cancel_message: str):
        """Slot generico chiamato quando un worker viene annullato."""
        worker_name = self.sender().objectName() if self.sender() else "Sconosciuto"
        logging.info(f"Worker {worker_name} annullato: {cancel_message}")
        self.show_status_message(f"Operazione annullata.", timeout=STATUS_BAR_TIMEOUT * 2)
        # Reset busy state (thread finished signal will handle actual cleanup)
        # self._set_busy(False, "Annullato.") # Done in _on_thread_finished

    def _on_thread_finished(self):
        """Slot chiamato quando il QThread termina (dopo worker.run())."""
        thread = self.sender()
        if thread and thread == self.active_worker_thread:
            logging.info(f"Thread {thread.objectName()} terminato.")
            # Allow Qt event loop to process deletion later to avoid issues
            if self.worker_object:
                self.worker_object.deleteLater()
                self.worker_object = None
            thread.deleteLater()
            self.active_worker_thread = None
            # --- Important: Reset busy state AFTER thread is fully finished ---
            self._set_busy(False, "Operazione completata.")
            self._update_button_states() # Ensure UI state is correct after worker finishes
        else:
            logging.warning(f"Segnale finished ricevuto da thread sconosciuto o non attivo: {thread}")


    def request_worker_stop(self):
         """Richiede l'interruzione del thread worker attivo (se esiste)."""
         if self.active_worker_thread and self.active_worker_thread.isRunning():
              logging.info(f"Richiesta interruzione per thread {self.active_worker_thread.objectName()}...")
              self.active_worker_thread.requestInterruption()
              self.show_status_message("Interruzione operazione in corso...", persistent=True)
              # Non aspettare qui, la gestione dell'interruzione è nel worker
              # Potremmo disabilitare il bottone "Stop" temporaneamente
         else:
              logging.debug("Nessun worker attivo da interrompere.")


    # --- UI Actions & Handlers ---

    def show_status_message(self, message: str, timeout: int = STATUS_BAR_TIMEOUT, persistent: bool = False):
        """Mostra messaggio nella status bar, con opzione timeout o persistente."""
        self.status_message_label.setText(message)
        if self.status_clear_timer.isActive():
             self.status_clear_timer.stop() # Stop previous timer if any
        if not persistent and timeout > 0:
             self.status_clear_timer.start(timeout)

    def _set_playback_controls_enabled(self, enabled: bool):
         """Abilita/disabilita controlli relativi alla riproduzione ATTIVA."""
         # Always respect the global busy state
         global_busy = self.active_worker_thread is not None and self.active_worker_thread.isRunning()

         self.progress_slider.setEnabled(enabled and not global_busy)
         self.pause_button.setEnabled(enabled and not global_busy)
         self.stop_button.setEnabled(enabled and not global_busy)

         if not enabled:
             # Reset playback UI only if not explicitly busy
             if not global_busy:
                 self.progress_slider.setValue(0)
                 self.current_time_label.setText("00:00")
                 self.total_time_label.setText("00:00")
             self.current_media_duration_ms = -1 # Always reset duration info
             # Reset pause button appearance
             self.pause_button.setText("❚❚ Pausa")
             self.pause_button.setToolTip("Metti in pausa / Riprendi la riproduzione (P)")
             self.pause_button.setIcon(self.style().standardIcon(QStyle.SP_MediaPause))

    def _browse_input_folder(self):
        """Apre dialog per selezionare cartella input."""
        if self.active_worker_thread and self.active_worker_thread.isRunning(): return # Don't browse if busy
        start_dir = self.current_input_dir or os.path.expanduser("~")
        directory = QFileDialog.getExistingDirectory(self, "Seleziona Cartella Input MP3", start_dir, QFileDialog.ShowDirsOnly)
        if directory:
            normalized_dir = os.path.normpath(directory)
            if normalized_dir != self.current_input_dir:
                logging.info(f"Nuova Cartella Input selezionata: {normalized_dir}")
                self.current_input_dir = normalized_dir
                self.folder_input_edit.setText(self.current_input_dir)
                self.settings.setValue(SETTINGS_INPUT_PATH, self.current_input_dir)
                self.show_status_message(f"Cartella Input impostata: {os.path.basename(self.current_input_dir)}", timeout=STATUS_BAR_TIMEOUT)
                self._load_music_list() # Trigger scan (async)
            else:
                logging.debug("Cartella input selezionata è la stessa già caricata.")

    def _browse_base_output_folder(self):
        """Apre dialog per selezionare cartella base output."""
        if self.active_worker_thread and self.active_worker_thread.isRunning(): return # Don't browse if busy
        start_dir = self.current_base_output_dir or os.path.expanduser("~")
        directory = QFileDialog.getExistingDirectory(self, "Seleziona Cartella Base Output", start_dir, QFileDialog.ShowDirsOnly)
        if directory:
            normalized_dir = os.path.normpath(directory)
            if normalized_dir != self.current_base_output_dir:
                logging.info(f"Nuova Cartella Base Output selezionata: {normalized_dir}")
                self.current_base_output_dir = normalized_dir
                self.folder_output_edit.setText(self.current_base_output_dir)
                self.settings.setValue(SETTINGS_OUTPUT_PATH, self.current_base_output_dir)
                self.show_status_message(f"Cartella Output Base impostata: {os.path.basename(self.current_base_output_dir)}", timeout=STATUS_BAR_TIMEOUT)
                self._update_button_states()
            else:
                logging.debug("Cartella output selezionata è la stessa già impostata.")

    def _trigger_reload_music_list(self):
        """Ricarica lista file (es. cambio ricorsività), se non occupato."""
        if self.active_worker_thread and self.active_worker_thread.isRunning():
             logging.warning("Tentativo di ricaricare la lista mentre un'operazione è in corso.")
             # Reset checkbox to previous state to avoid confusion? Or just ignore.
             # self.recursive_scan_checkbox.blockSignals(True)
             # self.recursive_scan_checkbox.setChecked(not self.recursive_scan_checkbox.isChecked())
             # self.recursive_scan_checkbox.blockSignals(False)
             return
        if not self.current_input_dir:
             logging.debug("Nessuna cartella input, ricarica ignorata.")
             return

        logging.info("Trigger reload music list (es. cambio ricorsività).")
        self.settings.setValue(SETTINGS_RECURSIVE_SCAN, self.recursive_scan_checkbox.isChecked())
        self._load_music_list()

    def _load_music_list(self):
        """Avvia la scansione dei file in un thread separato."""
        if self.active_worker_thread and self.active_worker_thread.isRunning():
             logging.warning("Tentativo di avviare scansione mentre un'operazione è in corso.")
             QMessageBox.warning(self, "Operazione in Corso", "Attendere il completamento dell'operazione corrente prima di avviare una nuova scansione.")
             return

        # Stop playback before reloading list
        self._stop_playback()
        # Clear current list immediately
        self.music_list_widget.clear()
        self.loaded_music_data = []
        self.list_item_map = {}
        self._reset_playing_indicator()
        self._update_button_states() # Reflect empty list state

        if not self.current_input_dir:
            self.show_status_message("Seleziona prima una cartella input.", timeout=STATUS_BAR_TIMEOUT)
            return
        if not os.path.isdir(self.current_input_dir):
             QMessageBox.warning(self, "Errore Percorso Input", f"La cartella Input specificata non è valida o non accessibile:\n{self.current_input_dir}")
             self.current_input_dir = None
             self.folder_input_edit.clear()
             self.settings.remove(SETTINGS_INPUT_PATH)
             self.show_status_message("Percorso input invalido rimosso.", timeout=STATUS_BAR_TIMEOUT)
             self._update_button_states()
             return

        logging.info(f"Avvio scansione asincrona per: {self.current_input_dir}")
        self.show_status_message(f"Avvio scansione in '{os.path.basename(self.current_input_dir)}'...", persistent=True)

        recursive = self.recursive_scan_checkbox.isChecked()
        scanner_worker = FileScannerWorker(self.file_manager, self.current_input_dir, recursive)
        # Use the helper to start the worker and manage thread
        self.start_worker(scanner_worker, scanner_worker.run, f"Scansione '{os.path.basename(self.current_input_dir)}'...")

    def _on_scan_finished(self, music_data_list: List[MusicFileData]):
        """Slot chiamato quando FileScannerWorker ha finito con successo."""
        logging.info(f"Scansione completata, ricevuti {len(music_data_list)} elementi.")
        self.loaded_music_data = music_data_list

        if not self.loaded_music_data:
            self.show_status_message("Nessun file MP3 valido trovato nella cartella.", timeout=STATUS_BAR_TIMEOUT * 2)
        else:
            # Populate the list widget (in main thread)
            self.music_list_widget.setUpdatesEnabled(False) # Optimize adding many items
            try:
                self.list_item_map.clear() # Clear old map
                for file_data in self.loaded_music_data:
                    item = QListWidgetItem(file_data.display_name)
                    item.setData(FULL_PATH_ROLE, file_data.full_path)
                    # Create tooltip
                    tooltip_parts = []
                    duration_str = format_time(file_data.duration_ms) if file_data.duration_ms > 0 else "N/D"
                    tooltip_parts.append(f"Durata: {duration_str}")
                    # Add relative path info for context if recursive scan
                    try:
                        if self.current_input_dir and self.recursive_scan_checkbox.isChecked():
                            relative_dir = os.path.relpath(os.path.dirname(file_data.full_path), self.current_input_dir)
                            relative_dir = "" if relative_dir == '.' else f"...{os.sep}{relative_dir}{os.sep}"
                            tooltip_parts.append(f"Posizione: {relative_dir}{file_data.filename}")
                        else:
                             tooltip_parts.append(f"File: {file_data.filename}")
                    except ValueError: # Handle potential path issues
                        tooltip_parts.append(f"File: {file_data.filename}")

                    item.setToolTip("\n".join(tooltip_parts))
                    item.setFont(self.default_font) # Ensure default font initially
                    self.music_list_widget.addItem(item)
                    self.list_item_map[file_data.full_path] = item # Update map
            finally:
                self.music_list_widget.setUpdatesEnabled(True)

            # Apply filter immediately after loading
            self._filter_music_list() # This also updates status bar with counts

        # Update UI state now that list is populated/cleared
        self._update_button_states() # Important to re-enable controls correctly

        # Log memory usage (optional debug)
        # try:
        #      import psutil
        #      process = psutil.Process(os.getpid())
        #      mem_mb = process.memory_info().rss / (1024 * 1024)
        #      logging.debug(f"Memoria dopo scansione: {mem_mb:.2f} MB")
        # except ImportError: pass


    def _filter_music_list(self):
        """Filtra la lista UI basandosi sul testo nel filter_edit."""
        filter_text = self.filter_edit.text().lower().strip()
        visible_count = 0
        total_items = len(self.loaded_music_data)
        logging.debug(f"Applicazione filtro: '{filter_text}'")

        self.music_list_widget.setUpdatesEnabled(False)
        try:
            for i in range(self.music_list_widget.count()): # Iterate through widget items directly
                item = self.music_list_widget.item(i)
                full_path = item.data(FULL_PATH_ROLE)
                # Find corresponding file data (should always exist if map is correct)
                file_data = next((fd for fd in self.loaded_music_data if fd.full_path == full_path), None)

                if item and file_data:
                     # Check filename (and potentially other fields later)
                    match = not filter_text or filter_text in file_data.filename.lower()
                    item.setHidden(not match)
                    if match:
                         visible_count += 1
                elif item:
                     # Item exists but no data? Hide it.
                     logging.warning(f"Item '{item.text()}' senza dati corrispondenti nel filtro.")
                     item.setHidden(True)

        finally:
            self.music_list_widget.setUpdatesEnabled(True)

        # Update status bar with filter results
        if filter_text:
            self.show_status_message(f"Mostrati {visible_count} di {total_items} file.", timeout=STATUS_BAR_TIMEOUT * 2)
        elif total_items > 0:
             self.show_status_message(f"{total_items} file caricati.", timeout=STATUS_BAR_TIMEOUT)
        else:
             # If no filter and no items, show "Pronto" or specific message
             base_msg = "Pronto." if not self.current_input_dir else "Nessun file trovato."
             self.show_status_message(base_msg, timeout=STATUS_BAR_TIMEOUT)

        self._update_button_states() # Update buttons based on filter/selection


    def _on_current_item_changed(self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem]):
        """Gestisce cambio selezione nella lista."""
        # Don't log excessively if selection changes rapidly during filtering/loading
        # logging.debug(f"Selezione cambiata. Corrente: {current.text() if current else 'None'}")

        if self.is_preview_playing and self.original_file_for_preview:
             # Stop preview if selection changes away from the item being previewed
             original_item = self.list_item_map.get(self.original_file_for_preview)
             if current != original_item:
                 logging.info("Selezione cambiata durante riproduzione anteprima -> fermo anteprima.")
                 self._stop_playback() # This will also untoggle the button

        # Always update button states based on the new selection
        self._update_button_states()


    def _get_selected_item_data(self) -> Tuple[Optional[QListWidgetItem], Optional[str], Optional[MusicFileData]]:
        """Ottiene l'item selezionato (se visibile), il suo path e i dati associati."""
        item = self.music_list_widget.currentItem()
        if item and not item.isHidden(): # Crucially, check if the item is visible
            full_path = item.data(FULL_PATH_ROLE)
            if full_path:
                # Find the data using the path - more reliable than assuming index sync
                file_data = next((fd for fd in self.loaded_music_data if fd.full_path == full_path), None)
                if file_data:
                    return item, full_path, file_data
                else:
                    logging.warning(f"Item selezionato '{item.text()}' ha path '{full_path}' ma dati non trovati in loaded_music_data!")
                    # Potentially remove item or mark as invalid here? For now, return None.
                    return item, full_path, None # Return item/path but no data
            else:
                logging.warning(f"Item selezionato '{item.text()}' non ha FULL_PATH_ROLE data.")
        return None, None, None # No selection or hidden item selected

    def _get_selected_item_data_for_item(self, item: QListWidgetItem) -> Tuple[Optional[QListWidgetItem], Optional[str], Optional[MusicFileData]]:
        """Ottiene i dati per un item specifico (passato come argomento)."""
        if item and not item.isHidden():
            full_path = item.data(FULL_PATH_ROLE)
            if full_path:
                file_data = next((fd for fd in self.loaded_music_data if fd.full_path == full_path), None)
                if file_data:
                    return item, full_path, file_data
                else:
                    logging.warning(f"Item (specifico) '{item.text()}' path '{full_path}' dati non trovati.")
                    return item, full_path, None
            else:
                 logging.warning(f"Item (specifico) '{item.text()}' non ha FULL_PATH_ROLE data.")
        return None, None, None


    # --- Playback Handling ---

    def _set_playing_indicator(self, item_to_mark: Optional[QListWidgetItem], path_being_played: Optional[str], is_preview: bool):
        """Aggiorna UI per indicare traccia in play (originale o preview)."""
        logging.debug(f"Setting playing indicator: Item={item_to_mark.text() if item_to_mark else 'None'}, Path={os.path.basename(path_being_played or 'None')}, Preview={is_preview}")
        self._reset_playing_indicator() # Clear previous indicator first

        self.currently_playing_item = item_to_mark
        self.current_playing_file_path = path_being_played # This is the actual file VLC is playing (original or temp)
        self.is_preview_playing = is_preview
        # Important: Track the *original* MP3 path if playing a preview
        self.original_file_for_preview = item_to_mark.data(FULL_PATH_ROLE) if is_preview and item_to_mark else None

        if self.currently_playing_item and self.current_playing_file_path:
            # Check if the item still exists in the list widget
            item_row = self.music_list_widget.row(self.currently_playing_item)
            if item_row >= 0:
                 # Apply visual indicator (bold font)
                self.currently_playing_item.setFont(self.playing_font)
                # Ensure the item is visible
                self.music_list_widget.scrollToItem(self.currently_playing_item, QAbstractItemView.EnsureVisible)

                # Update status bar
                original_path_for_status = self.original_file_for_preview if is_preview else self.current_playing_file_path
                status_display_name = "Brano sconosciuto"
                if original_path_for_status:
                    file_data = next((fd for fd in self.loaded_music_data if fd.full_path == original_path_for_status), None)
                    status_display_name = file_data.display_name if file_data else os.path.basename(original_path_for_status)

                prefix = "ANTEPRIMA: " if is_preview else "Play Orig: "
                self.show_status_message(f"{prefix}{status_display_name}", persistent=True) # Keep message until stopped/changed

                # Get duration and enable controls shortly after play starts
                QTimer.singleShot(150, self._update_duration_and_controls) # Use timer to allow VLC to load
            else:
                 logging.warning(f"Tentativo di marcare come 'in play' un item ('{self.currently_playing_item.text()}') non più presente nella lista.")
                 # Reset state as if stopped
                 self.currently_playing_item = None
                 self.current_playing_file_path = None
                 self.is_preview_playing = False
                 self.original_file_for_preview = None
                 self._set_playback_controls_enabled(False)
                 if self.progress_timer.isActive(): self.progress_timer.stop()
                 self._cleanup_preview_file() # Ensure temp file is removed if its item vanished

        else:
             # Called with None, means playback stopped
             self._set_playback_controls_enabled(False)
             if self.progress_timer.isActive(): self.progress_timer.stop()
             # Update status bar only if it wasn't updated by _set_busy or filter
             current_status = self.status_message_label.text()
             if "Play Orig:" in current_status or "ANTEPRIMA:" in current_status or "Pausa" in current_status:
                  self.show_status_message("Pronto.", timeout=STATUS_BAR_TIMEOUT)


    def _reset_playing_indicator(self):
        """Resetta lo stile (font) dell'item che era precedentemente in riproduzione."""
        if self.currently_playing_item:
            try:
                 # Check if item still exists before trying to change font
                 if self.music_list_widget.row(self.currently_playing_item) >= 0:
                     if self.currently_playing_item.font() == self.playing_font: # Only reset if it was bold
                         self.currently_playing_item.setFont(self.default_font)
                         logging.debug(f"Reset indicatore 'in play' per: {self.currently_playing_item.text()}")
                 else:
                     logging.debug("Item precedentemente in play non trovato nella lista per il reset.")
            except RuntimeError:
                 # Can happen if the list widget is being modified heavily
                 logging.warning("RuntimeError durante il reset dell'indicatore 'in play'.")
            except Exception as e:
                 logging.warning(f"Errore generico reset indicatore 'in play': {e}")
        # Clear the reference regardless of success
        self.currently_playing_item = None


    def _update_duration_and_controls(self):
        """Ottiene la durata dal player e abilita/disabilita controlli UI correlati."""
        if not self.music_player or not self.music_player.is_ready():
             logging.warning("Tentativo update durata ma player non pronto.")
             return

        current_state = self.music_player.get_state()
        logging.debug(f"Update durata/controlli richiesto. Stato VLC: {current_state}")

        # Only proceed if playing or paused
        if current_state in [vlc.State.Playing, vlc.State.Paused]:
             self.current_media_duration_ms = self.music_player.get_length()
             logging.debug(f"Durata media ottenuta da VLC: {self.current_media_duration_ms} ms")

             if self.current_media_duration_ms > 0:
                 # Update total time label
                 self.total_time_label.setText(format_time(self.current_media_duration_ms))
                 # Enable playback controls (slider, pause, stop)
                 self._set_playback_controls_enabled(True)
                 # Start progress timer only if actually playing
                 if current_state == vlc.State.Playing and not self.progress_timer.isActive():
                      logging.debug("Avvio timer aggiornamento progresso.")
                      self.progress_timer.start()
             else:
                  # Length not available (-1 or 0) - might still be opening/buffering
                  logging.warning(f"Durata media non disponibile ({self.current_media_duration_ms} ms). Stato VLC: {current_state}")
                  self.total_time_label.setText("--:--")
                  # Still enable controls, assuming playback might start soon or seeking is possible
                  self._set_playback_controls_enabled(True)
                  # Try starting timer anyway if state is 'playing', might get length later
                  if current_state == vlc.State.Playing and not self.progress_timer.isActive():
                       logging.debug("Avvio timer (anche senza durata iniziale).")
                       self.progress_timer.start()

             # Update pause button text based on current state AFTER enabling controls
             self._update_ui_for_player_state()

        else: # Stopped, Ended, Error etc.
             logging.debug("Stato VLC non Playing/Paused, disabilito controlli.")
             self._set_playback_controls_enabled(False)
             if self.progress_timer.isActive():
                  logging.debug("Fermo timer progresso (stato non attivo).")
                  self.progress_timer.stop()


    def _play_selected_music_from_item(self, item: QListWidgetItem):
        """Gestore doppio click su item: riproduce originale."""
        logging.debug(f"Doppio click su: {item.text()}")
        # Ensure item is valid and pass it to the main play function
        self._play_selected_music(item_override=item)


    def _play_selected_music(self, item_override: Optional[QListWidgetItem] = None):
        """Riproduce l'MP3 originale selezionato o l'item specificato."""
        if self.active_worker_thread and self.active_worker_thread.isRunning():
             QMessageBox.warning(self, "Operazione in Corso", "Impossibile avviare la riproduzione mentre un'altra operazione è attiva.")
             return
        if not self.music_player or not self.music_player.is_ready():
            QMessageBox.critical(self, "Errore Player", self.music_player.get_init_error() or "Player audio non disponibile.")
            return

        item, file_path, file_data = self._get_selected_item_data_for_item(item_override) if item_override else self._get_selected_item_data()

        if item and file_path and file_data:
            logging.info(f"Richiesta riproduzione ORIGINALE per: {file_data.display_name}")

            # Stop any current playback (original or preview) cleanly
            self._stop_playback()
            time.sleep(0.1) # Brief pause to ensure stop is processed before new play

            # Verify file exists before attempting to play
            if os.path.isfile(file_path):
                if self.music_player.play(file_path):
                    # Success: Update UI indicator
                    self._set_playing_indicator(item, file_path, is_preview=False)
                else:
                    # Play command failed
                    QMessageBox.warning(self, "Errore Riproduzione", f"Impossibile avviare la riproduzione per:\n{file_data.display_name}\n\nControlla il file e i log.")
                    self._set_playing_indicator(None, None, False) # Ensure UI reflects stopped state
            else:
                 # File selected in list but not found on disk!
                 logging.error(f"File selezionato ma non trovato su disco: {file_path}")
                 QMessageBox.critical(self, "Errore File Mancante", f"Il file selezionato non è stato trovato:\n{file_path}\n\nPotrebbe essere stato spostato o eliminato.\nRimuovo l'elemento dalla lista.")
                 self._remove_item_from_list(item) # Remove invalid item
                 self._set_playing_indicator(None, None, False) # Ensure stopped state

        elif not item and self.sender() == self.play_button:
             # If play button clicked but no item selected (and visible)
             QMessageBox.information(self, "Nessuna Selezione", "Seleziona un brano dalla lista prima di premere Play.")
        elif not item:
             logging.debug("Play ignorato: nessun item valido selezionato/visibile.")


        self._update_button_states()


    def _toggle_preview_normalization(self, checked: bool):
        """Gestisce il click sul bottone checkable 'Preview Norm.'."""
        logging.debug(f"Preview Toggled. Nuovo stato CheckBox: {'Checked (Attivo)' if checked else 'Unchecked (Inattivo)'}")

        # Prevent toggling if busy
        if self.active_worker_thread and self.active_worker_thread.isRunning():
            if self.is_preview_playing: # Allow unchecking if preview is playing
                 if not checked:
                      logging.info("Richiesta stop anteprima da toggle bottone (durante altra operazione).")
                      self._stop_playback()
                      return
                 else: # Cannot start a new preview if already busy
                     logging.warning("Tentativo di attivare anteprima mentre un'altra operazione è in corso.")
                     QMessageBox.warning(self, "Operazione in Corso", "Impossibile generare l'anteprima mentre un'altra operazione è attiva.")
                     # Force button back to unchecked state visually
                     self.preview_button.blockSignals(True); self.preview_button.setChecked(False); self.preview_button.blockSignals(False)
                     return
            else: # Cannot start preview if busy and not playing preview
                 logging.warning("Tentativo di attivare anteprima mentre un'altra operazione è in corso.")
                 QMessageBox.warning(self, "Operazione in Corso", "Impossibile generare l'anteprima mentre un'altra operazione è attiva.")
                 self.preview_button.blockSignals(True); self.preview_button.setChecked(False); self.preview_button.blockSignals(False)
                 return


        if checked:
            # --- START PREVIEW ---
            selected_item, source_path, source_file_data = self._get_selected_item_data()

            if not selected_item or not source_path or not source_file_data:
                QMessageBox.warning(self, "Selezione Mancante", "Seleziona un file dalla lista per ascoltare l'anteprima normalizzata.")
                # Must manually uncheck the button if selection is invalid
                self.preview_button.blockSignals(True); self.preview_button.setChecked(False); self.preview_button.blockSignals(False)
                return

            if not self.lufs_meter:
                QMessageBox.critical(self, "Errore Normalizzazione", "Impossibile generare anteprima: librerie/meter LUFS non disponibili.")
                self.preview_button.blockSignals(True); self.preview_button.setChecked(False); self.preview_button.blockSignals(False)
                return

            logging.info(f"Richiesta generazione anteprima per: {source_file_data.filename}")

            # Stop any current playback first
            self._stop_playback()
            time.sleep(0.1) # Allow stop to process

            # Create a temporary file path for the normalized WAV preview
            try:
                # Using NamedTemporaryFile can be tricky with permissions/sharing on Windows
                # Create temp file in a known location instead? Or just use temp dir.
                temp_dir = tempfile.gettempdir()
                temp_filename = f"norm_preview_{os.path.splitext(source_file_data.filename)[0]}_{int(time.time())}.wav"
                temp_file_path = os.path.join(temp_dir, temp_filename)
                logging.debug(f"Percorso file anteprima temporaneo: {temp_file_path}")
            except Exception as e:
                 logging.error(f"Impossibile creare percorso file temporaneo: {e}", exc_info=True)
                 QMessageBox.critical(self, "Errore File Temporaneo", f"Impossibile creare il file temporaneo per l'anteprima:\n{e}")
                 self.preview_button.blockSignals(True); self.preview_button.setChecked(False); self.preview_button.blockSignals(False)
                 return

            # Store paths for cleanup/state management
            self.current_preview_temp_path = temp_file_path
            self.original_file_for_preview = source_path # Track original for state

            # Start the NormalizeWorker in preview mode
            norm_worker = NormalizeWorker(
                file_manager=self.file_manager,
                lufs_meter=self.lufs_meter,
                target_lufs=self.target_lufs,
                source_path=source_path,
                destination_path=temp_file_path, # Save to temp file
                is_preview=True,
                delete_original_on_success=False # Never delete original for preview
            )

            if not self.start_worker(norm_worker, norm_worker.run, f"Genero anteprima '{source_file_data.filename}'..."):
                # Failed to start worker (e.g., another worker running)
                logging.warning("Avvio worker anteprima fallito.")
                self.current_preview_temp_path = None # Reset path if worker didn't start
                self.original_file_for_preview = None
                self.preview_button.blockSignals(True); self.preview_button.setChecked(False); self.preview_button.blockSignals(False)

        else:
            # --- STOP PREVIEW (Button untoggled by user or code) ---
            if self.is_preview_playing:
                 logging.info("Richiesta stop anteprima da deselezione bottone.")
                 self._stop_playback() # This handles cleanup and resetting state
            else:
                 logging.debug("Bottone Preview deselezionato, ma nessuna anteprima era attiva.")
                 # If button was unchecked programmatically (e.g., on error), ensure state is clean
                 self._cleanup_preview_file()
                 self.is_preview_playing = False
                 self.original_file_for_preview = None
                 self._update_button_states() # Update UI

    def _on_preview_generated(self, result: NormalizeWorker.NormalizeResult):
         """Slot chiamato da NormalizeWorker quando l'anteprima è pronta."""
         if not result.success:
             logging.error(f"Generazione anteprima fallita: {result.message}")
             QMessageBox.critical(self, "Errore Generazione Anteprima", f"Impossibile generare l'anteprima per '{os.path.basename(result.original_source_path)}':\n{result.message}")
             self._cleanup_preview_file()
             self.preview_button.blockSignals(True); self.preview_button.setChecked(False); self.preview_button.blockSignals(False)
             # _on_thread_finished will handle unbusy state
             return

         if not result.output_path or not os.path.exists(result.output_path):
             logging.error(f"Generazione anteprima OK ma file output ('{result.output_path}') non trovato!")
             QMessageBox.critical(self, "Errore Interno", "Anteprima generata con successo ma file output non trovato.")
             self._cleanup_preview_file()
             self.preview_button.blockSignals(True); self.preview_button.setChecked(False); self.preview_button.blockSignals(False)
             return

         # Update measured LUFS in the source file data if available
         if result.measured_lufs is not None and np.isfinite(result.measured_lufs) and result.original_source_path:
             source_data = next((fd for fd in self.loaded_music_data if fd.full_path == result.original_source_path), None)
             if source_data:
                 source_data.measured_lufs = result.measured_lufs
                 logging.info(f"LUFS misurato per anteprima di '{source_data.filename}': {result.measured_lufs:.2f}")
                 # Update tooltip? Maybe too much detail.

         # Play the generated preview file
         logging.info(f"Anteprima generata con successo: {result.output_path}. Avvio riproduzione.")
         item = self.list_item_map.get(result.original_source_path) # Find original item in list
         if not item:
             logging.warning("Item originale non trovato nella lista dopo generazione anteprima. Annullamento riproduzione.")
             self._cleanup_preview_file(); self.preview_button.blockSignals(True); self.preview_button.setChecked(False); self.preview_button.blockSignals(False)
             return

         if self.music_player.play(result.output_path):
              # Playback started successfully, mark UI accordingly
              # self.is_preview_playing = True # set_playing_indicator handles this
              self._set_playing_indicator(item, result.output_path, is_preview=True)
              self.show_status_message(f"Riproduzione anteprima per {os.path.basename(result.original_source_path)}", persistent=True)
         else:
              # Playback failed even if file was generated
              QMessageBox.critical(self, "Errore Riproduzione Anteprima", f"Impossibile riprodurre il file di anteprima generato:\n{result.output_path}\nVerifica il player VLC e i log.")
              self._cleanup_preview_file()
              self._set_playing_indicator(None, None, False)
              self.preview_button.blockSignals(True); self.preview_button.setChecked(False); self.preview_button.blockSignals(False)


    def _cleanup_preview_file(self):
        """Elimina il file WAV temporaneo dell'anteprima, se esiste."""
        path_to_delete = self.current_preview_temp_path
        if path_to_delete and os.path.exists(path_to_delete):
            try:
                os.remove(path_to_delete)
                logging.info(f"File anteprima temporaneo eliminato: {path_to_delete}")
            except OSError as e:
                logging.warning(f"Impossibile eliminare il file anteprima '{path_to_delete}': {e}")
            except Exception as e:
                 logging.error(f"Errore imprevisto eliminazione file anteprima '{path_to_delete}': {e}", exc_info=True)
        elif path_to_delete:
             # If path variable exists but file doesn't, log as debug
             logging.debug(f"Pulizia anteprima: Percorso '{path_to_delete}' non trovato su disco.")

        # Always clear the state variables after attempting cleanup
        self.current_preview_temp_path = None


    def _toggle_pause(self):
        """Gestisce il click sul bottone Pausa/Riprendi."""
        if self.music_player and self.music_player.is_ready():
            state = self.music_player.get_state()
            if state in [vlc.State.Playing, vlc.State.Paused]:
                 logging.debug("Comando Pausa/Riprendi inviato al player.")
                 self.music_player.pause()
                 # Update UI slightly delayed to reflect state change
                 QTimer.singleShot(100, self._update_ui_for_player_state)
            else:
                 logging.debug("Toggle Pausa ignorato: player non in stato Playing/Paused.")
        else:
             logging.warning("Toggle Pausa ignorato: Player non pronto.")

    def _stop_playback(self):
        """Ferma qualsiasi riproduzione (originale o preview) e pulisce lo stato."""
        if not self.music_player or not self.music_player.is_ready():
             # logging.debug("Stop richiesto ma player non pronto o già fermo.")
             # Ensure cleanup even if player is gone
             was_preview = self.is_preview_playing
             self._set_playing_indicator(None, None, False) # Reset internal state/UI indicators
             self._cleanup_preview_file()
             if was_preview and self.preview_button.isChecked():
                  self.preview_button.blockSignals(True); self.preview_button.setChecked(False); self.preview_button.blockSignals(False)
             self._update_button_states()
             return

        current_state = self.music_player.get_state()
        was_playing = current_state != vlc.State.Stopped and current_state != vlc.State.Ended and current_state != vlc.State.Error
        was_preview = self.is_preview_playing # Capture state before changing it

        logging.info(f"Richiesta Stop. Era in riproduzione: {was_playing}. Era Anteprima: {was_preview}")

        # Send stop command to VLC if it was playing/paused
        if was_playing:
            self.music_player.stop()

        # --- Always perform cleanup after stop command (or if already stopped) ---
        self._set_playing_indicator(None, None, False) # Resets internal state and UI font/statusbar
        self._cleanup_preview_file()                  # Delete temp file if it was a preview

        # Update status bar message if we actually stopped something
        if was_playing:
            self.show_status_message("Riproduzione fermata.", timeout=STATUS_BAR_TIMEOUT)

        # Ensure the preview button is unchecked if we stopped a preview
        if was_preview and self.preview_button.isChecked():
            logging.debug("Deseleziono il bottone Preview dopo stop.")
            self.preview_button.blockSignals(True) # Prevent toggled signal loop
            self.preview_button.setChecked(False)
            self.preview_button.blockSignals(False)

        # Update overall UI state
        self._update_button_states()


    def _update_ui_for_player_state(self):
        """Aggiorna il testo/icona del bottone Pausa e la status bar in base allo stato del player."""
        if not self.music_player or not self.music_player.is_ready(): return

        state = self.music_player.get_state()
        # Get display name for status bar
        status_display_name = "Brano sconosciuto"
        original_path_for_status = self.original_file_for_preview if self.is_preview_playing else self.current_playing_file_path
        if original_path_for_status:
            file_data = next((fd for fd in self.loaded_music_data if fd.full_path == original_path_for_status), None)
            status_display_name = file_data.display_name if file_data else os.path.basename(original_path_for_status)

        status_msg = self.status_message_label.text() # Get current message

        if state == vlc.State.Playing:
            self.pause_button.setText("❚❚ Pausa")
            self.pause_button.setToolTip("Metti in pausa la riproduzione (P)")
            self.pause_button.setIcon(self.style().standardIcon(QStyle.SP_MediaPause))
            # Update status bar if needed
            prefix = "ANTEPRIMA: " if self.is_preview_playing else "Play Orig: "
            expected_msg = f"{prefix}{status_display_name}"
            if status_msg != expected_msg: self.show_status_message(expected_msg, persistent=True)
            # Ensure timer is running
            if not self.progress_timer.isActive(): self.progress_timer.start()

        elif state == vlc.State.Paused:
            self.pause_button.setText("▶ Riprendi")
            self.pause_button.setToolTip("Riprendi la riproduzione (P)")
            self.pause_button.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
             # Update status bar if needed
            prefix = "Pausa Anteprima: " if self.is_preview_playing else "Pausa Orig: "
            expected_msg = f"{prefix}{status_display_name}"
            if status_msg != expected_msg: self.show_status_message(expected_msg, persistent=True)
            # Stop timer when paused
            if self.progress_timer.isActive(): self.progress_timer.stop()

        else: # Stopped, Ended, Error, etc.
            self.pause_button.setText("❚❚ Pausa")
            self.pause_button.setToolTip("Metti in pausa / Riprendi la riproduzione (P)")
            self.pause_button.setIcon(self.style().standardIcon(QStyle.SP_MediaPause))
            # If playback implicitly stopped (e.g. finished), update status
            if "Play Orig:" in status_msg or "ANTEPRIMA:" in status_msg or "Pausa" in status_msg:
                # Check if an operation is running in background before setting "Pronto"
                if not (self.active_worker_thread and self.active_worker_thread.isRunning()):
                    self.show_status_message("Pronto.", timeout=STATUS_BAR_TIMEOUT)
            # Ensure timer is stopped
            if self.progress_timer.isActive(): self.progress_timer.stop()


    # --- Playback Progress/Seek/Volume --- (Largely unchanged logic)
    def _update_progress(self):
        """Aggiorna slider e label tempo durante la riproduzione."""
        if not self.music_player or not self.music_player.is_ready() or self.is_progress_slider_dragging:
             # logging.debug("Update progress skipped (player not ready or slider dragging).")
             return

        state = self.music_player.get_state()
        # logging.debug(f"Update progress tick. State: {state}") # Too verbose

        if state == vlc.State.Playing:
             current_pos = self.music_player.get_position() # Float 0.0 to 1.0
             current_length_ms = self.current_media_duration_ms

             if current_length_ms > 0:
                 # Update time labels
                 current_time_ms = int(current_pos * current_length_ms)
                 self.current_time_label.setText(format_time(current_time_ms))

                 # Update slider (map 0.0-1.0 to 0-1000)
                 slider_max = self.progress_slider.maximum()
                 slider_pos = int(current_pos * slider_max)

                 # Update slider only if position changed significantly to avoid jitter
                 # or blocking updates during seeking. Maybe increase threshold?
                 current_slider_val = self.progress_slider.value()
                 if abs(slider_pos - current_slider_val) > (slider_max * 0.002): # Threshold ~2ms for 1sec range?
                    self.progress_slider.setValue(slider_pos)
             else:
                  # Still playing but length unknown, maybe show percentage?
                  self.current_time_label.setText(f"{int(current_pos * 100)}%")
                  # Update slider anyway
                  self.progress_slider.setValue(int(current_pos * self.progress_slider.maximum()))


        elif state == vlc.State.Ended:
             logging.info("Playback terminato (stato VLC: Ended). Fermo e pulisco.")
             self._stop_playback() # Call standard stop procedure
             # Optional: auto-play next? -> Needs different logic

        elif state == vlc.State.Error:
             logging.error("Errore Player VLC rilevato durante playback.")
             self._stop_playback() # Stop and cleanup
             QMessageBox.warning(self, "Errore Player", "Si è verificato un errore nel player VLC durante la riproduzione.")

        elif state == vlc.State.Stopped:
             # Can happen if stop was called but timer fired again before being stopped
             logging.debug("Player in stato Stopped durante update progress, fermo timer.")
             if self.progress_timer.isActive(): self.progress_timer.stop()
             # Might need to ensure UI reflects stopped state if _stop_playback wasn't called explicitly
             if self.currently_playing_item or self.is_preview_playing:
                   logging.warning("Stato VLC = Stopped, ma UI indica ancora riproduzione. Forzo stop UI.")
                   self._stop_playback()


    def _progress_slider_pressed(self):
        """Chiamato quando l'utente inizia a trascinare lo slider."""
        state = self.music_player.get_state()
        if state in [vlc.State.Playing, vlc.State.Paused]:
            self.is_progress_slider_dragging = True
            logging.debug("Slider Pressed.")
            # Temporarily stop the progress timer updates to avoid conflicts
            if self.progress_timer.isActive(): self.progress_timer.stop()
        else:
             self.is_progress_slider_dragging = False # Ensure flag is reset if not playable

    def _progress_slider_released(self):
        """Chiamato quando l'utente rilascia lo slider (o clicca)."""
        if self.is_progress_slider_dragging:
            self.is_progress_slider_dragging = False
            new_value = self.progress_slider.value()
            new_position = float(new_value) / self.progress_slider.maximum()
            logging.info(f"Slider Released at value {new_value} -> seek to position {new_position:.3f}")
            self.music_player.set_position(new_position)
            # Update time label immediately based on seek position
            if self.current_media_duration_ms > 0:
                self.current_time_label.setText(format_time(int(new_position * self.current_media_duration_ms)))
            # Restart timer only if it was active before and player is still playing
            if self.music_player.get_state() == vlc.State.Playing:
                 if not self.progress_timer.isActive(): self.progress_timer.start()
        else:
             # Handle click seek (slider value changed without dragging)
             state = self.music_player.get_state()
             if state in [vlc.State.Playing, vlc.State.Paused]:
                 new_value = self.progress_slider.value()
                 new_position = float(new_value) / self.progress_slider.maximum()
                 logging.info(f"Slider Click -> seek to position {new_position:.3f}")
                 self.music_player.set_position(new_position)
                 if self.current_media_duration_ms > 0:
                     self.current_time_label.setText(format_time(int(new_position * self.current_media_duration_ms)))
                 # Timer restart handled by normal update loop? Or restart here if playing?
                 # if state == vlc.State.Playing and not self.progress_timer.isActive(): self.progress_timer.start()


    def _progress_slider_moved(self, value):
        """Chiamato MENTRE l'utente trascina lo slider."""
        if self.is_progress_slider_dragging and self.current_media_duration_ms > 0:
             # Update the time label in real-time as the user drags
             current_pos = float(value) / self.progress_slider.maximum()
             self.current_time_label.setText(format_time(int(current_pos * self.current_media_duration_ms)))
             # DO NOT call set_position here - wait for sliderReleased to avoid flooding VLC

    def _set_volume(self, value):
        """Imposta il volume del player VLC quando lo slider cambia."""
        if self.music_player and self.music_player.is_ready():
            self.music_player.set_volume(value)
            # Volume label text is updated automatically via lambda connection


    # --- File Move Operation ---

    def _move_selected_to_subfolder(self):
        """Avvia la normalizzazione e lo spostamento (async)."""
        if self.active_worker_thread and self.active_worker_thread.isRunning():
             QMessageBox.warning(self, "Operazione in Corso", "Attendere il completamento dell'operazione corrente prima di spostare un altro file.")
             return

        selected_item, source_path, source_file_data = self._get_selected_item_data()

        # --- Validations ---
        if not selected_item or not source_path or not source_file_data:
             QMessageBox.warning(self, "Selezione Mancante", "Seleziona un file dalla lista da normalizzare e spostare.")
             return

        if not self.current_base_output_dir or not os.path.isdir(self.current_base_output_dir):
             QMessageBox.warning(self, "Cartella Output Mancante", "Seleziona una Cartella Base Output valida prima di spostare i file.")
             return

        if not self.lufs_meter:
            QMessageBox.critical(self, "Errore Normalizzazione", "Impossibile normalizzare e spostare: librerie/meter LUFS non disponibili.")
            return

        relative_subfolder = self.subfolder_edit.text().strip()
        if not relative_subfolder:
             QMessageBox.warning(self, "Sottocartella Mancante", "Specifica una sottocartella di destinazione (relativa alla base output).")
             self.subfolder_edit.setFocus()
             return

        # Clean and validate relative path
        try:
             # Replace backslashes, normalize, remove leading/trailing slashes
             cleaned_relative = os.path.normpath(relative_subfolder.replace("\\", "/")).strip(os.sep)
             # Basic sanity checks
             if not cleaned_relative or os.path.isabs(cleaned_relative) or ".." in cleaned_relative.split(os.sep):
                  raise ValueError("Percorso relativo non valido o non sicuro.")
             # Check for invalid characters (basic check, OS specific might be needed)
             # invalid_chars = '<>:"/\\|?*' # Example, might vary by OS
             # if any(c in invalid_chars for c in cleaned_relative):
             #      raise ValueError("Il nome della sottocartella contiene caratteri non validi.")

             destination_folder = os.path.join(self.current_base_output_dir, cleaned_relative)

        except ValueError as path_err:
            QMessageBox.critical(self, "Errore Percorso Sottocartella", f"Il percorso sottocartella specificato non è valido:\n'{relative_subfolder}'\n\n({path_err})\n\nNon usare percorsi assoluti, '..' o caratteri speciali.")
            self.subfolder_edit.selectAll(); self.subfolder_edit.setFocus()
            return
        except Exception as e: # Catch other unexpected errors during path join/validation
             QMessageBox.critical(self, "Errore Percorso", f"Errore imprevisto nella gestione del percorso di destinazione:\n{e}")
             return

        # Define destination WAV filename
        source_basename = os.path.basename(source_path)
        destination_filename_wav = f"{os.path.splitext(source_basename)[0]}.wav"
        destination_file_path_wav = os.path.join(destination_folder, destination_filename_wav)

        logging.info(f"Richiesta Normalizza/Sposta per: '{source_basename}'")
        logging.info(f"  -> Sorgente: {source_path}")
        logging.info(f"  -> Destinazione WAV: {destination_file_path_wav}")
        logging.info(f"  -> MP3 Originale verrà ELIMINATO dopo successo.")

        # --- Confirmation ---
        # Check if destination WAV exists
        if os.path.exists(destination_file_path_wav):
             overwrite_reply = QMessageBox.question(self, 'File Esistente',
                                          f"Il file WAV di destinazione esiste già:\n'{destination_filename_wav}'\n\nin: ...{os.sep}{cleaned_relative}\n\nSovrascriverlo?",
                                          QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
             if overwrite_reply == QMessageBox.No:
                 logging.warning("Operazione annullata dall'utente (file esistente).")
                 self.show_status_message("Spostamento annullato.", timeout=STATUS_BAR_TIMEOUT)
                 return

        # Build confirmation message
        original_lufs_str = ""
        # Try getting LUFS from file data if previously measured (e.g., by preview)
        if source_file_data.measured_lufs is not None and np.isfinite(source_file_data.measured_lufs):
            original_lufs_str = f"\n(LUFS Originale Misurato: {source_file_data.measured_lufs:.1f} LUFS)"
        # Add target LUFS info
        confirm_msg = (
             f"<b>Confermi l'operazione?</b><br><br>"
             f"<b>File:</b> '{source_file_data.display_name}'<br>"
             f"<b>Azione:</b> Normalizza a <b>{self.target_lufs:.1f} LUFS</b> e Salva come WAV<br>"
             f"<b>Destinazione:</b> ...{os.sep}{os.path.basename(self.current_base_output_dir)}{os.sep}<b>{cleaned_relative}</b><br>"
             f"<b>Nuovo Nome File:</b> '{destination_filename_wav}'<br>"
             f"{original_lufs_str}<br><br>"
             f"<font color='orange'><b>ATTENZIONE:</b> Il file MP3 originale ('{source_basename}') sarà <b>eliminato definitivamente</b> se l'operazione riesce.</font>"
        )

        # Show confirmation dialog
        confirm_reply = QMessageBox.question(self, 'Conferma Normalizzazione e Spostamento', confirm_msg,
                                            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)

        if confirm_reply != QMessageBox.Yes:
            logging.info("Operazione Normalizza/Sposta annullata dall'utente.")
            self.show_status_message("Spostamento annullato.", timeout=STATUS_BAR_TIMEOUT)
            return

        # --- Stop Playback if Target File is Playing ---
        is_playing_this = False
        if self.currently_playing_item == selected_item:
            # Check if playing original or preview OF THE SAME FILE
            if (not self.is_preview_playing and self.current_playing_file_path == source_path) or \
               (self.is_preview_playing and self.original_file_for_preview == source_path):
               is_playing_this = True

        if is_playing_this:
             logging.info(f"Il file da spostare ('{source_basename}') è attualmente in riproduzione/anteprima. Fermo la riproduzione...")
             self._stop_playback()
             time.sleep(0.1) # Allow stop to process


        # --- Start Worker ---
        logging.info("Avvio worker per normalizzazione e spostamento...")
        norm_worker = NormalizeWorker(
            file_manager=self.file_manager,
            lufs_meter=self.lufs_meter,
            target_lufs=self.target_lufs,
            source_path=source_path,
            destination_path=destination_file_path_wav, # Dest is WAV
            is_preview=False, # This is the final move operation
            delete_original_on_success=True # Request deletion of original
        )

        if not self.start_worker(norm_worker, norm_worker.run, f"Normalizzo/Sposto '{source_basename}'..."):
            logging.error("Avvio worker normalizzazione/spostamento fallito.")
            # UI should already show message from start_worker if another worker was active


    def _on_normalize_move_finished(self, result: NormalizeWorker.NormalizeResult):
        """Slot chiamato quando NormalizeWorker (in modalità spostamento) finisce."""
        logging.info(f"Worker Normalizza/Sposta terminato per '{os.path.basename(result.original_source_path)}'. Norm OK: {result.success}, Delete OK: {result.delete_success}")

        # Find the original item in the list
        original_item = self.list_item_map.get(result.original_source_path)

        if result.success:
             # --- Normalization Successful ---
             success_message_parts = [
                 f"'{os.path.basename(result.original_source_path)}' normalizzato e salvato con successo.",
                 f"Messaggio: {result.message}.",
             ]
             final_lufs = result.measured_lufs
             if final_lufs is not None and np.isfinite(final_lufs):
                 success_message_parts.append(f"LUFS Originale Misurato: {final_lufs:.1f} LUFS.")
             else:
                 # Try getting LUFS from original data if measurement failed/skipped but data existed
                 if original_item:
                      source_data = next((fd for fd in self.loaded_music_data if fd.full_path == result.original_source_path), None)
                      if source_data and source_data.measured_lufs is not None and np.isfinite(source_data.measured_lufs):
                           success_message_parts.append(f"LUFS Originale (pre-misurato): {source_data.measured_lufs:.1f} LUFS.")

             # Now check deletion status
             if result.delete_success is None: # Should not happen if norm succeeded and delete was requested
                 logging.error("Stato eliminazione inatteso (None) dopo normalizzazione OK.")
                 success_message_parts.append("\n\n<font color='red'><b>ERRORE INTERNO:</b> Stato eliminazione originale sconosciuto!</font>")
                 QMessageBox.critical(self, "Completato con Errore Interno", "\n".join(success_message_parts))
             elif result.delete_success:
                  # --- Deletion Successful ---
                  success_message_parts.append("\nMP3 Originale eliminato con successo.")
                  logging.info("Normalizzazione e eliminazione completate con successo.")
                  self.show_status_message(f"Spostato: {os.path.basename(result.original_source_path)}", STATUS_BAR_TIMEOUT * 2)

                  # Update UI: Remove item, add recent folder, clear input
                  if original_item:
                      self._remove_item_from_list(original_item)
                      dest_folder = os.path.dirname(result.output_path) if result.output_path else None
                      if dest_folder and self.current_base_output_dir:
                          try:
                             relative_dest = os.path.relpath(dest_folder, self.current_base_output_dir)
                             relative_dest = relative_dest.replace("\\", "/") # Use forward slashes for consistency
                             if relative_dest and relative_dest != '.':
                                 self._add_to_recent_folders(relative_dest)
                          except ValueError:
                             logging.warning("Impossibile calcolare path relativo per cartella recente.")

                  self.subfolder_edit.clear()
                  if self.recent_folder_combo.count() > 1: # If recents exist
                       self.recent_folder_combo.setCurrentIndex(0) # Reset combo selection

                  QMessageBox.information(self, "Operazione Completata", "\n".join(success_message_parts))

             else:
                  # --- Deletion Failed ---
                  logging.error(f"Normalizzazione OK, ma eliminazione originale fallita: {result.delete_message}")
                  success_message_parts.append(f"\n\n<font color='orange'><b>ATTENZIONE: Eliminazione file MP3 originale ('{os.path.basename(result.original_source_path)}') fallita!</b></font>")
                  if result.delete_message:
                      success_message_parts.append(f"Motivo: {result.delete_message}")
                  success_message_parts.append("\nIl file WAV normalizzato è stato creato.")
                  # Do NOT remove item from list as original still exists
                  QMessageBox.warning(self, "Completato con Avviso", "\n".join(success_message_parts))
                  self.show_status_message(f"Norm. OK, Elim. Fallita: {os.path.basename(result.original_source_path)}", STATUS_BAR_TIMEOUT * 3)

        else:
             # --- Normalization Failed ---
             logging.error(f"Normalizzazione fallita per '{os.path.basename(result.original_source_path)}': {result.message}")
             error_msg = (
                  f"Errore durante la normalizzazione/salvataggio di:\n'{os.path.basename(result.original_source_path)}'\n\n"
                  f"Motivo: {result.message}\n\n"
                  "Il file originale NON è stato modificato o eliminato."
             )
             QMessageBox.critical(self, "Errore Operazione", error_msg)
             self.show_status_message(f"Errore Normalizzazione: {os.path.basename(result.original_source_path)}", STATUS_BAR_TIMEOUT * 3)
             # Do not remove item from list

        # Update button states regardless of outcome (thread completion handles busy state)
        # self._update_button_states() # Handled by _on_thread_finished -> _set_busy(False)


    # --- Recent Folders & List Management ---

    def _add_to_recent_folders(self, relative_path: str):
        """Aggiunge una sottocartella relativa all'elenco dei recenti."""
        if not relative_path: return
        # Normalize path separator to '/' for consistency in storage and display
        norm_path = relative_path.strip().replace("\\", "/")
        if not norm_path or norm_path == '.': return

        logging.debug(f"Aggiungo cartella recente: '{norm_path}'")
        # Remove if already exists to move it to the top
        if norm_path in self.recent_folders:
            self.recent_folders.remove(norm_path)
        # Insert at the beginning
        self.recent_folders.insert(0, norm_path)
        # Trim list to max size
        self.recent_folders = self.recent_folders[:MAX_RECENT_FOLDERS]

        # Update ComboBox
        self.recent_folder_combo.blockSignals(True) # Avoid triggering currentIndexChanged
        self.recent_folder_combo.clear()
        self.recent_folder_combo.addItem("--- Seleziona Recente ---") # Placeholder
        self.recent_folder_combo.addItems(self.recent_folders)
        self.recent_folder_combo.setCurrentIndex(0) # Reset selection
        self.recent_folder_combo.blockSignals(False)

        # Save updated list to settings
        self.settings.setValue(SETTINGS_RECENT_FOLDERS, self.recent_folders)
        logging.debug(f"Cartelle recenti aggiornate: {self.recent_folders}")
        self._update_button_states() # Update UI state (e.g., enable combo if now has items)

    def _recent_folder_selected(self, index: int):
        """Popola il campo subfolder_edit quando un item recente è selezionato."""
        if index > 0: # Index 0 is the placeholder
             folder = self.recent_folder_combo.itemText(index)
             logging.debug(f"Cartella recente selezionata: '{folder}'")
             # Set text, which will trigger _update_button_states via textChanged signal
             self.subfolder_edit.setText(folder)
        elif index == 0:
             # If placeholder selected, clear the edit field
             self.subfolder_edit.clear()


    def _remove_item_from_list(self, item_to_remove: QListWidgetItem):
        """Rimuove un item dalla QListWidget, dalla mappa e dalla lista dati."""
        path = item_to_remove.data(FULL_PATH_ROLE)
        row = self.music_list_widget.row(item_to_remove)

        if row >= 0:
             logging.info(f"Rimozione item '{item_to_remove.text()}' (path: {path}) dalla lista.")
             # 1. Remove from QListWidget
             taken_item = self.music_list_widget.takeItem(row)
             # takeItem returns the item, delete it properly later if needed? Usually not.
             # del taken_item

             # 2. Remove from path -> item map
             if path in self.list_item_map:
                 del self.list_item_map[path]
                 logging.debug(f"  - Rimosso dalla mappa.")
             else:
                 logging.warning(f"  - Path '{path}' non trovato nella mappa durante rimozione.")

             # 3. Remove from underlying data list
             initial_data_len = len(self.loaded_music_data)
             self.loaded_music_data = [fd for fd in self.loaded_music_data if fd.full_path != path]
             final_data_len = len(self.loaded_music_data)

             if final_data_len == initial_data_len - 1:
                 logging.debug(f"  - Rimosso dalla lista dati.")
             elif final_data_len == initial_data_len:
                 logging.warning(f"  - Path '{path}' non trovato nella lista dati durante rimozione.")
             else: # Should not happen with single selection/removal
                  logging.error(f"  - Discrepanza lunghezza lista dati dopo rimozione! ({initial_data_len} -> {final_data_len})")

             # Update filter counts / status bar might be needed if filter active?
             # For simplicity, just update button states for now.
             self._update_button_states()
             # Refresh status bar message if list becomes empty or based on filter
             self._filter_music_list()


        else:
             logging.warning(f"Tentativo di rimuovere un item ('{item_to_remove.text()}' / '{path}') non trovato nella QListWidget (row={row}).")


    # --- UI State Management ---
    def _update_button_states(self):
        """Aggiorna lo stato (enabled/disabled) dei bottoni e controlli UI."""
        # Ignore updates if busy, except for playback controls handled by _set_busy
        is_busy = self.active_worker_thread is not None and self.active_worker_thread.isRunning()
        if is_busy:
            # If busy, most controls are handled by _set_busy(True).
            # We only need to potentially manage playback buttons based on player state.
            is_playing_vlc = self.music_player.get_state() in [vlc.State.Playing, vlc.State.Paused]
            self.pause_button.setEnabled(is_playing_vlc)
            self.stop_button.setEnabled(is_playing_vlc)
            # Make sure preview button remains correctly synced if busy AND preview playing
            self.preview_button.blockSignals(True)
            self.preview_button.setChecked(self.is_preview_playing)
            self.preview_button.blockSignals(False)
            # Play button should remain disabled while busy
            self.play_button.setEnabled(False)
            return

        # --- State Evaluation (when not busy) ---
        selected_item, selected_path, selected_data = self._get_selected_item_data()
        is_selection_valid = selected_item is not None # Check only if an item is selected and visible

        can_normalize = _numpy_installed and _soundfile_installed and _pyloudnorm_installed and self.lufs_meter is not None
        is_output_dir_valid = bool(self.current_base_output_dir and os.path.isdir(self.current_base_output_dir))
        is_subfolder_specified = bool(self.subfolder_edit.text().strip())

        player_ready = self.music_player and self.music_player.is_ready()
        player_state = self.music_player.get_state() if player_ready else vlc.State.Error
        is_playing_or_paused = player_state in [vlc.State.Playing, vlc.State.Paused]
        is_actually_playing_orig = is_playing_or_paused and not self.is_preview_playing

        # --- Set Enabled States ---

        # Play Original Button
        self.play_button.setEnabled(player_ready and is_selection_valid and not self.is_preview_playing)
        self.play_button.setToolTip("Riproduci il file MP3 originale selezionato (Spazio)" if is_selection_valid else "Seleziona un brano per riprodurlo")

        # Preview Button
        can_start_preview = player_ready and is_selection_valid and can_normalize and not is_actually_playing_orig
        # Button should be enabled if we CAN start a preview OR if a preview IS currently playing (to allow stopping it)
        self.preview_button.setEnabled(can_start_preview or self.is_preview_playing)
        # Update tooltip based on why it's enabled/disabled
        preview_tooltip = "Genera e ascolta un'anteprima normalizzata (Ctrl+P)"
        if not can_normalize: preview_tooltip += "\n(Disabilitato: Librerie audio mancanti)"
        elif not is_selection_valid: preview_tooltip += "\n(Disabilitato: Seleziona un brano)"
        elif is_actually_playing_orig: preview_tooltip += "\n(Disabilitato durante riproduzione originale)"
        elif self.is_preview_playing: preview_tooltip = "Ferma l'anteprima in corso (Ctrl+P)"
        self.preview_button.setToolTip(preview_tooltip)
        # Ensure check state matches internal state
        self.preview_button.blockSignals(True); self.preview_button.setChecked(self.is_preview_playing); self.preview_button.blockSignals(False)


        # Pause/Stop Buttons
        self.pause_button.setEnabled(player_ready and is_playing_or_paused)
        self.stop_button.setEnabled(player_ready and is_playing_or_paused)

        # Move Button
        can_move = is_selection_valid and is_output_dir_valid and is_subfolder_specified and can_normalize and not self.is_preview_playing
        self.move_to_subfolder_button.setEnabled(can_move)
        # Update move button tooltip
        move_tooltip = "Normalizza, salva WAV in sottocartella, elimina MP3 originale."
        if not can_normalize: move_tooltip = "Spostamento disabilitato: Librerie normalizzazione mancanti o errore init."
        elif not is_selection_valid: move_tooltip = "Spostamento disabilitato: Seleziona un file."
        elif not is_output_dir_valid: move_tooltip = "Spostamento disabilitato: Seleziona una Cartella Base Output valida."
        elif not is_subfolder_specified: move_tooltip = "Spostamento disabilitato: Specifica una Sottocartella di destinazione."
        elif self.is_preview_playing: move_tooltip = "Spostamento disabilitato durante l'anteprima."
        self.move_to_subfolder_button.setToolTip(move_tooltip)


        # Other Controls
        self.recent_folder_combo.setEnabled(is_output_dir_valid and len(self.recent_folders) > 0)
        self.subfolder_edit.setEnabled(is_output_dir_valid)
        # Only allow changing recursive scan if input dir is set and not busy
        self.recursive_scan_checkbox.setEnabled(bool(self.current_input_dir))
        self.clear_filter_button.setEnabled(bool(self.filter_edit.text()))

        # Volume slider should always be enabled if player is ready
        self.volume_slider.setEnabled(player_ready)


    # --- Settings Load/Save ---
    def _load_settings(self):
        """Carica le impostazioni dell'applicazione (percorsi, opzioni, audio)."""
        logging.info("Caricamento impostazioni...")
        try:
            # Paths (provide default empty strings)
            saved_input = self.settings.value(SETTINGS_INPUT_PATH, "", type=str)
            saved_output = self.settings.value(SETTINGS_OUTPUT_PATH, "", type=str)

            # Options
            # Provide explicit type hint for bool to avoid Qt interpreting 'false' string etc.
            saved_recursive = self.settings.value(SETTINGS_RECURSIVE_SCAN, False, type=bool)
            # Provide default empty list and explicit type for list
            saved_recents = self.settings.value(SETTINGS_RECENT_FOLDERS, [], type=list)

            # Audio Settings
            saved_volume = self.settings.value(SETTINGS_LAST_VOLUME, 70, type=int)
            # Use float for LUFS target, provide default
            saved_target_lufs_str = self.settings.value(SETTINGS_TARGET_LUFS, str(TARGET_LUFS_DEFAULT), type=str)


            # --- Apply Settings ---

            # Input Path: Validate if it exists and is a directory
            valid_input_loaded = False
            if saved_input and os.path.isdir(saved_input):
                self.current_input_dir = os.path.normpath(saved_input)
                self.folder_input_edit.setText(self.current_input_dir)
                valid_input_loaded = True
                logging.info(f"Caricata cartella Input salvata: {self.current_input_dir}")
            elif saved_input: # If path was saved but is no longer valid
                 logging.warning(f"Cartella Input salvata '{saved_input}' non trovata o non valida. Sarà ignorata.")
                 self.folder_input_edit.clear()
                 self.current_input_dir = None
                 self.settings.remove(SETTINGS_INPUT_PATH) # Remove invalid setting

            # Output Path: Validate similarly
            if saved_output and os.path.isdir(saved_output):
                self.current_base_output_dir = os.path.normpath(saved_output)
                self.folder_output_edit.setText(self.current_base_output_dir)
                logging.info(f"Caricata cartella Base Output salvata: {self.current_base_output_dir}")
            elif saved_output:
                 logging.warning(f"Cartella Base Output salvata '{saved_output}' non trovata o non valida. Sarà ignorata.")
                 self.folder_output_edit.clear()
                 self.current_base_output_dir = None
                 self.settings.remove(SETTINGS_OUTPUT_PATH)

            # Apply Options
            # Block signals briefly while setting initial state if it triggers actions
            self.recursive_scan_checkbox.blockSignals(True)
            self.recursive_scan_checkbox.setChecked(saved_recursive)
            self.recursive_scan_checkbox.blockSignals(False)

            # Load recent folders (validate items are strings)
            self.recent_folders = [f for f in saved_recents if isinstance(f, str) and f.strip()][:MAX_RECENT_FOLDERS]
            self.recent_folder_combo.blockSignals(True)
            self.recent_folder_combo.clear()
            self.recent_folder_combo.addItem("--- Seleziona Recente ---")
            self.recent_folder_combo.addItems(self.recent_folders)
            self.recent_folder_combo.setCurrentIndex(0)
            self.recent_folder_combo.blockSignals(False)


            # Apply Audio Settings
            # Clamp volume just in case saved value is out of range
            clamped_volume = max(0, min(100, saved_volume))
            self.volume_slider.setValue(clamped_volume)
            # Set initial text for volume label
            self.volume_value_label.setText(f"{clamped_volume}%")
            # Apply volume to VLC player if ready
            if self.music_player and self.music_player.is_ready():
                self.music_player.set_volume(clamped_volume)

            # Apply LUFS Target (validate format and range)
            try:
                lufs_val = float(saved_target_lufs_str)
                # Define reasonable LUFS range (e.g., for music/streaming)
                if -24.0 <= lufs_val <= -5.0:
                     self.target_lufs = lufs_val
                     logging.info(f"Caricato Target LUFS valido: {self.target_lufs:.1f}")
                else:
                    self.target_lufs = TARGET_LUFS_DEFAULT
                    logging.warning(f"Target LUFS salvato ({lufs_val}) fuori range ragionevole. Uso default {self.target_lufs:.1f}.")
                    # Optionally, save the default back to settings immediately? Or just use it.
            except (ValueError, TypeError):
                self.target_lufs = TARGET_LUFS_DEFAULT
                logging.warning(f"Valore Target LUFS salvato ('{saved_target_lufs_str}') non valido. Uso default {self.target_lufs:.1f}.")

            # Update LUFS meter target and status label
            # self.file_manager.set_target_lufs(self.target_lufs) # Target passed directly to worker now
            self.lufs_status_label.setText(f"Target: {self.target_lufs:.1f} LUFS")

            logging.info(f"Impostazioni caricate: Input Valido={valid_input_loaded}, Output Valido={bool(self.current_base_output_dir)}, "
                         f"Ricorsiva={saved_recursive}, Recenti={len(self.recent_folders)}, Volume={clamped_volume}, Target LUFS={self.target_lufs:.1f}")

            # Trigger initial file list load IF a valid input path was loaded
            if valid_input_loaded:
                # Use QTimer to allow UI to fully initialize before starting scan
                QTimer.singleShot(100, self._load_music_list)
            else:
                 # If no valid input, just update UI state
                 self._update_button_states()

            logging.info("Caricamento impostazioni completato.")

        except Exception as e:
            logging.error(f"Errore critico durante il caricamento delle impostazioni: {e}", exc_info=True)
            QMessageBox.warning(self, "Errore Caricamento Impostazioni",
                                 "Impossibile caricare correttamente le impostazioni precedenti.\n"
                                f"Verranno usati i valori di default.\n\nDettagli: {e}")
            # Reset to defaults might be needed here if loading fails partially


    def _save_settings(self):
        """Salva le impostazioni correnti dell'applicazione."""
        logging.info("Salvataggio impostazioni...")
        try:
            # Save Paths (only if they seem valid)
            if self.current_input_dir and os.path.isdir(self.current_input_dir):
                self.settings.setValue(SETTINGS_INPUT_PATH, self.current_input_dir)
            else:
                 self.settings.remove(SETTINGS_INPUT_PATH) # Remove if invalid/not set

            if self.current_base_output_dir and os.path.isdir(self.current_base_output_dir):
                self.settings.setValue(SETTINGS_OUTPUT_PATH, self.current_base_output_dir)
            else:
                self.settings.remove(SETTINGS_OUTPUT_PATH)

            # Save Options
            self.settings.setValue(SETTINGS_RECURSIVE_SCAN, self.recursive_scan_checkbox.isChecked())
            # Ensure recent folders list doesn't contain duplicates or invalid entries? (already filtered on add)
            self.settings.setValue(SETTINGS_RECENT_FOLDERS, self.recent_folders)

            # Save Audio Settings
            current_volume = self.volume_slider.value()
            self.settings.setValue(SETTINGS_LAST_VOLUME, current_volume)
            # Save LUFS target as string for robustness
            self.settings.setValue(SETTINGS_TARGET_LUFS, f"{self.target_lufs:.1f}")

            # Force writing to disk (or registry on Windows)
            self.settings.sync()
            logging.info(f"Impostazioni salvate. Volume={current_volume}, Target LUFS={self.target_lufs:.1f}")

        except Exception as e:
             logging.error(f"Errore durante il salvataggio delle impostazioni: {e}", exc_info=True)
             # Show non-critical warning to user
             # QMessageBox.warning(self, "Errore Salvataggio Impostazioni", f"Impossibile salvare le impostazioni correnti:\n{e}")


    # --- Window Close Event ---
    def closeEvent(self, event: QtGui.QCloseEvent):
        """Gestisce la chiusura della finestra principale."""
        logging.info("Evento closeEvent ricevuto.")

        # 1. Stop any active worker thread gracefully
        if self.active_worker_thread and self.active_worker_thread.isRunning():
             reply = QMessageBox.question(self, "Operazione in Corso",
                                         "Un'operazione in background (scansione/normalizzazione) è ancora attiva.\n"
                                         "Vuoi interromperla e chiudere l'applicazione?",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
             if reply == QMessageBox.Yes:
                  logging.info("Interruzione worker richiesta da chiusura finestra.")
                  self.request_worker_stop()
                  # Need to wait briefly? Or just proceed? Best to let it try to cancel.
                  # Maybe disable closing for a moment? Hard to manage correctly.
                  # Let's proceed with other cleanup for now. The thread should eventually finish.
                  # event.ignore() # Prevent closing immediately?
                  # return
             else:
                  logging.info("Chiusura annullata dall'utente per operazione in corso.")
                  event.ignore() # Prevent the window from closing
                  return

        # 2. Stop Playback Timers
        logging.debug("Stop timer riproduzione e status bar...")
        if self.progress_timer.isActive(): self.progress_timer.stop()
        if self.status_clear_timer.isActive(): self.status_clear_timer.stop()

        # 3. Stop Playback & Release Player Resources
        logging.debug("Stop riproduzione e pulizia anteprima...")
        self._stop_playback() # Stops player and cleans preview file

        # Give VLC a moment to fully stop before releasing (important!)
        # This might require waiting in the event loop briefly? Or rely on player release logic.
        # QtCore.QCoreApplication.processEvents()
        # time.sleep(0.1)

        logging.debug("Rilascio risorse MusicPlayer (VLC)...")
        if self.music_player:
            self.music_player.release() # This handles stopping and releasing VLC instance/player
            self.music_player = None

        # 4. Final Cleanup of Temp File (just in case _stop_playback missed it)
        self._cleanup_preview_file()

        # 5. Save Settings
        logging.debug("Salvataggio impostazioni...")
        self._save_settings()

        logging.info(f"--- Chiusura {APP_NAME} ---")
        event.accept() # Allow the window to close


# --- Punto Ingresso Applicazione ---
if __name__ == "__main__":
    # --- Pre-GUI Checks & Setup ---
    if not _pyqt5_installed:
         print("ERRORE CRITICO: PyQt5 non trovato. Impossibile avviare l'applicazione.")
         # Show graphical message if possible, fallback to console
         try: app = QApplication(sys.argv); MainWindow._show_critical_error("Errore Critico", "PyQt5 non trovato. Installalo con 'pip install PyQt5'");
         except: pass
         sys.exit(1)

    # Setup App ID for Windows Taskbar Icon/Grouping (best effort)
    if sys.platform == 'win32':
        try:
            import ctypes
            myappid = f'{ORG_NAME}.{APP_NAME}.{APP_NAME}.1.3' # Needs to be unique-ish string
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
            logging.info(f"AppUserModelID impostato (Win): {myappid}")
        except Exception as e:
            logging.warning(f"Impossibile impostare AppUserModelID (Win): {e}")

    # Qt Application Setup
    # Enable High DPI support
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    # Set Org/App Name for QSettings
    QApplication.setOrganizationName(ORG_NAME)
    QApplication.setApplicationName(APP_NAME)

    app = QApplication(sys.argv)

    # Apply a modern style (Fusion is good cross-platform)
    try:
        app.setStyle(QStyleFactory.create("Fusion"))
    except Exception as style_e:
        logging.warning(f"Impossibile applicare lo stile Fusion: {style_e}. Verrà usato lo stile di default.")

    # Set Application Icon (optional, requires an icon file)
    icon_path = "app_icon.ico" # Example: place app_icon.ico near the script
    if os.path.exists(icon_path):
        app.setWindowIcon(QtGui.QIcon(icon_path))
        logging.info(f"Icona applicazione caricata da: {icon_path}")
    else:
         logging.debug(f"Icona applicazione ('{icon_path}') non trovata.")

    # --- Create and Show Main Window ---
    window = None # Initialize variable
    try:
        window = MainWindow()
        window.show()
        logging.info("Finestra principale creata e mostrata.")
    except SystemExit as exit_e:
        # Handle sys.exit called during MainWindow init (e.g., VLC error)
        logging.critical(f"Uscita durante l'inizializzazione di MainWindow: {exit_e}")
        sys.exit(getattr(exit_e, 'code', 1)) # Use exit code if available, default to 1
    except Exception as main_win_e:
        logging.critical(f"Errore critico imprevisto durante la creazione di MainWindow: {main_win_e}", exc_info=True)
        # Try to show graphical error message before exiting
        try: MainWindow._show_critical_error("Errore Avvio Applicazione", f"Si è verificato un errore critico:\n\n{main_win_e}\n\nL'applicazione sarà chiusa.");
        except: print(f"ERRORE CRITICO AVVIO: {main_win_e}") # Fallback print
        sys.exit(1)


    # --- Run Event Loop ---
    if window: # Only run app if window was successfully created
         exit_code = app.exec_()
         logging.info(f"Applicazione terminata con codice di uscita: {exit_code}")
         sys.exit(exit_code)
    else:
         # Should not happen if exceptions are caught, but as a safeguard
         logging.critical("MainWindow non è stata creata. Uscita.")
         sys.exit(1)
