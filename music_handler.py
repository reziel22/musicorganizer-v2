import vlc
import os
import logging
from PyQt5.QtCore import QObject, pyqtSignal

class MusicPlayer(QObject):
    positionChanged = pyqtSignal(float)
    stateChanged = pyqtSignal(str)

    def __init__(self, device="Predefinito"):
        super().__init__()
        self.instance = None
        self.player = None
        self.current_file = None
        self.device = device
        self.volume = 50
        self._init_vlc()

    def _init_vlc(self):
        try:
            opts = ["--no-xlib", "--no-video"]
            if self.device != "Predefinito":
                opts.append(f"--mmdevice-audio-device={self.device}")
            
            self.instance = vlc.Instance(opts)
            if not self.instance:
                raise RuntimeError("Impossibile inizializzare VLC")
            
            self.player = self.instance.media_player_new()
            self.player.event_manager().event_attach(
                vlc.EventType.MediaPlayerPositionChanged, 
                self._update_position
            )
            self.player.audio_set_volume(self.volume)
        except Exception as e:
            logging.error(f"Errore inizializzazione VLC: {e}")

    def _update_position(self, event):
        self.positionChanged.emit(self.player.get_position())

    def play(self, file_path: str):
        if not self.player:
            return

        try:
            file_path = os.path.normpath(file_path)
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File non trovato: {file_path}")

            media = self.instance.media_new(file_path)
            self.player.set_media(media)
            self.player.play()
            self.current_file = file_path
            self.stateChanged.emit("playing")
            logging.info(f"Riproduzione avviata: {file_path}")
        except Exception as e:
            logging.error(f"Errore riproduzione: {e}")
            self.stateChanged.emit("error")

    def pause(self):
        if self.player:
            self.player.pause()
            self.stateChanged.emit("paused" if self.is_playing() else "playing")

    def stop(self):
        if self.player:
            self.player.stop()
            self.stateChanged.emit("stopped")
            self.current_file = None

    def set_volume(self, volume: int):
        if self.player:
            self.volume = max(0, min(100, volume))
            self.player.audio_set_volume(self.volume)

    def set_position(self, position: float):
        if self.player:
            self.player.set_position(position)

    def is_playing(self):
        return self.player and self.player.is_playing()

    def get_length(self):
        return self.player.get_length() if self.player else 0

    def get_position(self):
        return self.player.get_position() if self.player else 0