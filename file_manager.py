import os
import shutil
import logging
from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3
from mutagen.flac import FLAC
from mutagen.oggvorbis import OggVorbis
from mutagen.wave import WAVE
from PyQt5.QtCore import QObject, pyqtSignal, QRunnable, QThreadPool
from typing import List, Dict, Optional
from dataclasses import dataclass

@dataclass
class Track:
    """Rappresenta un brano musicale."""
    name: str
    path: str
    title: str = "Sconosciuto"
    artist: str = "Sconosciuto"
    duration: float = 0.0

class FileManager(QObject):
    music_folder_changed = pyqtSignal()
    progress_updated = pyqtSignal(int)
    files_loaded = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.thread_pool = QThreadPool()
        self.music_folder = ""
        self.dest_folder = ""
        self.music_files: List[Track] = []
        self.current_index = 0

    def set_folders(self, music_folder: str, dest_folder: str):
        """Imposta i percorsi delle cartelle."""
        self.music_folder = os.path.normpath(music_folder)
        self.dest_folder = os.path.normpath(dest_folder)
        logging.info(f"Cartelle impostate: Musica={self.music_folder}, Destinazione={self.dest_folder}")
        self.music_folder_changed.emit()

    def load_music_files(self) -> list:
        """Carica i file in modo asincrono."""
        class LoadTask(QRunnable):
            def __init__(self, manager):
                super().__init__()
                self.manager = manager

            def run(self):
                try:
                    files = os.listdir(self.manager.music_folder)
                    total = len(files)
                    loaded_tracks = []
                    for i, f in enumerate(files):
                        if f.lower().endswith((".mp3", ".flac", ".ogg", ".wav")):
                            file_path = os.path.join(self.manager.music_folder, f)
                            track = Track(name=f, path=file_path)
                            self.manager.load_track_metadata(track)
                            loaded_tracks.append(track)
                        progress = int((i + 1) / total * 100)
                        self.manager.progress_updated.emit(progress)
                    self.manager.music_files = loaded_tracks
                    self.manager.files_loaded.emit(loaded_tracks)
                    self.manager.progress_updated.emit(0)  # Reset progress
                except Exception as e:
                    logging.error(f"Errore caricamento: {e}")
                    self.manager.progress_updated.emit(0)

        self.thread_pool.start(LoadTask(self))
        return self.music_files

    def load_track_metadata(self, track: Track):
        """Carica i metadati del brano."""
        try:
            ext = os.path.splitext(track.path.lower())[1]
            if ext == ".mp3":
                audio = EasyID3(track.path)
                track.title = audio.get("title", [track.name.split('.')[0]])[0]
                track.artist = audio.get("artist", ["Artista sconosciuto"])[0]
            elif ext == ".flac":
                audio = FLAC(track.path)
                track.title = audio.get("title", [track.name.split('.')[0]])[0]
                track.artist = audio.get("artist", ["Artista sconosciuto"])[0]
            elif ext == ".ogg":
                audio = OggVorbis(track.path)
                track.title = audio.get("title", [track.name.split('.')[0]])[0]
                track.artist = audio.get("artist", ["Artista sconosciuto"])[0]
            elif ext == ".wav":
                # WAV non supporta metadati standard
                track.title = track.name.split('.')[0]
                track.artist = "Artista sconosciuto"
        except Exception as e:
            logging.warning(f"Errore durante la lettura dei metadati per {track.name}: {e}")
            track.title = track.name.split('.')[0]
            track.artist = "Artista sconosciuto"

    def move_file(self, filename, destination):
        """Sposta il file nella cartella specificata."""
        source = os.path.join(self.music_folder, filename)
        dest = os.path.join(self.dest_folder, destination, filename)
        try:
            shutil.move(source, dest)
            return True
        except Exception as e:
            logging.error(f"Errore durante lo spostamento del file: {e}")
            return False