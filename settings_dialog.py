from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QComboBox, QPushButton, QDialogButtonBox
from PyQt5.QtCore import pyqtSlot
import vlc
import logging
import pyaudio

class SettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Impostazioni Audio")
        self.setGeometry(200, 200, 400, 200)

        self.device_label = QLabel("Dispositivo Audio:")
        self.device_combo = QComboBox()
        self.populate_device_combo()

        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addWidget(self.device_label)
        layout.addWidget(self.device_combo)
        layout.addWidget(self.button_box)
        self.setLayout(layout)

        saved_device = self.settings.value("audio_device", "Predefinito")
        index = self.device_combo.findText(saved_device)
        if index >= 0:
            self.device_combo.setCurrentIndex(index)

    def populate_device_combo(self):
        """Popola la ComboBox con i dispositivi audio usando PyAudio"""
        self.device_combo.addItem("Predefinito")
        try:
            audio = pyaudio.PyAudio()
            for i in range(audio.get_device_count()):
                try:
                    device_info = audio.get_device_info_by_index(i)
                    self.device_combo.addItem(device_info['name'])
                except OSError as e:
                    logging.error(f"Errore nel recupero dispositivo {i}: {e}")
            audio.terminate()
        except Exception as e:
            logging.error(f"Errore nell'inizializzazione PyAudio: {e}")

    def accept(self):
        selected_device = self.device_combo.currentText()
        self.settings.setValue("audio_device", selected_device)
        super().accept()

    def get_selected_device(self):
        return self.device_combo.currentText()