from PyQt5 import QtWidgets
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QLabel, QListWidget, QFileDialog,
                             QMessageBox, QListWidgetItem, QSlider, QProgressBar)
from PyQt5.QtCore import pyqtSlot, Qt, QSettings, QTimer, QDir
from PyQt5.QtGui import QFont
from file_manager import FileManager, Track
from music_handler import MusicPlayer
from settings_dialog import SettingsDialog

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Music Organizer")
        self.setGeometry(100, 100, 1000, 800)
        self.settings = QSettings("MusicOrganizer", "MusicOrganizer")
        self.file_manager = FileManager()
        self.music_folder = ""
        self.dest_folder = ""
        self._init_ui()
        self._init_player()
        self._load_settings()
        QTimer.singleShot(0, self._check_initial_folders)

    def _init_ui(self):
        # UI components initialization
        self._create_widgets()
        self._create_layout()
        self._create_menu()
        self._connect_signals()
        self._setup_styles()

    def _create_widgets(self):
        # Widgets creation
        self.music_folder_button = QPushButton("Seleziona Cartella Musicale")
        self.music_folder_label = QLabel("Cartella Musicale: Non selezionata")
        self.dest_folder_button = QPushButton("Seleziona Cartella Destinazione")
        self.dest_folder_label = QLabel("Cartella Destinazione: Non selezionata")
        self.music_list = QListWidget()
        self.play_button = QPushButton("Play")
        self.stop_button = QPushButton("Stop")
        self.next_button = QPushButton("Successivo")
        self.prev_button = QPushButton("Precedente")
        self.pause_button = QPushButton("Pause")
        self.title_label = QLabel("Nessun brano in riproduzione")
        self.progress_bar = QProgressBar()
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(50)

    def _setup_styles(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #f0f0f0; }
            QPushButton { 
                background-color: #4CAF50; 
                color: white; 
                padding: 8px;
                border-radius: 4px;
            }
            QListWidget { background-color: white; }
        """)

    def _init_player(self):
        self.music_player = MusicPlayer(
            self.settings.value("audio_device", "Predefinito")
        )
        self.music_player.positionChanged.connect(self._update_progress)
        self.music_player.stateChanged.connect(self._update_player_state)

    def _update_progress(self, position):
        self.progress_bar.setValue(int(position * 100))

    def _update_player_state(self, state):
        states = {
            "playing": "▶️ Riproduzione in corso",
            "paused": "⏸ In pausa",
            "stopped": "⏹ Fermato",
            "error": "❌ Errore riproduzione"
        }
        self.statusBar().showMessage(states.get(state, ""))

    def _load_settings(self):
        # Load saved folders
        if self.settings.contains("music_folder"):
            self.music_folder = self.settings.value("music_folder")
            self.music_folder_label.setText(f"Cartella Musicale: {self.music_folder}")
            self.dest_folder = self.settings.value("dest_folder", "")
            self.dest_folder_label.setText(f"Cartella Destinazione: {self.dest_folder}")
            self.file_manager.set_folders(
                self.music_folder,
                self.dest_folder
            )
            self.load_music_files()

    def _check_initial_folders(self):
        if not self.settings.contains("music_folder"):
            QMessageBox.information(
                self, 
                "Benvenuto",
                "Seleziona una cartella musicale per iniziare"
            )

    def _create_layout(self):
        hbox1 = QHBoxLayout()
        hbox1.addWidget(self.music_folder_button)
        hbox1.addWidget(self.music_folder_label)

        hbox2 = QHBoxLayout()
        hbox2.addWidget(self.dest_folder_button)
        hbox2.addWidget(self.dest_folder_label)

        hbox3 = QHBoxLayout()
        hbox3.addWidget(self.prev_button)
        hbox3.addWidget(self.play_button)
        hbox3.addWidget(self.pause_button)
        hbox3.addWidget(self.stop_button)
        hbox3.addWidget(self.next_button)

        vbox = QVBoxLayout()
        vbox.addLayout(hbox1)
        vbox.addLayout(hbox2)
        vbox.addWidget(self.music_list)
        vbox.addLayout(hbox3)
        vbox.addWidget(self.title_label)
        vbox.addWidget(self.progress_bar)
        vbox.addWidget(self.volume_slider)

        central_widget = QWidget()
        central_widget.setLayout(vbox)
        self.setCentralWidget(central_widget)

    def _create_menu(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")
        settings_action = QtWidgets.QAction("Impostazioni", self)
        settings_action.triggered.connect(self.open_settings_dialog)
        file_menu.addAction(settings_action)

    def _connect_signals(self):
        self.music_folder_button.clicked.connect(self.select_music_folder)
        self.dest_folder_button.clicked.connect(self.select_dest_folder)
        self.play_button.clicked.connect(self.play_music)
        self.stop_button.clicked.connect(self.stop_music)
        self.next_button.clicked.connect(self.next_music)
        self.prev_button.clicked.connect(self.prev_music)
        self.pause_button.clicked.connect(self.pause_music)
        self.music_list.itemDoubleClicked.connect(self.play_selected_music)
        self.volume_slider.valueChanged.connect(self.set_volume)
        self.file_manager.progress_updated.connect(self.update_progress_bar)
        self.file_manager.files_loaded.connect(self.display_music_files)

    def closeEvent(self, event):
        self.music_player.stop()
        self.settings.setValue("music_folder", self.file_manager.music_folder)
        self.settings.setValue("dest_folder", self.file_manager.dest_folder)
        super().closeEvent(event)

    @pyqtSlot()
    def select_music_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleziona Cartella Musicale", QDir.homePath())
        if folder:
            self.music_folder = folder
            self.music_folder_label.setText(f"Cartella Musicale: {self.music_folder}")
            self.file_manager.set_folders(self.music_folder, self.dest_folder)
            self.load_music_files()

    @pyqtSlot()
    def select_dest_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleziona Cartella Destinazione", QDir.homePath())
        if folder:
            self.dest_folder = folder
            self.dest_folder_label.setText(f"Cartella Destinazione: {self.dest_folder}")
            self.file_manager.set_folders(self.music_folder, self.dest_folder)

    def load_music_files(self):
        self.music_list.clear()
        self.file_manager.load_music_files()

    @pyqtSlot()
    def play_music(self):
        if self.music_list.currentItem():
            file_path = self.music_list.currentItem().data(Qt.UserRole)
            self.music_player.play(file_path)
            self.update_title()

    @pyqtSlot(QtWidgets.QListWidgetItem)
    def play_selected_music(self, item):
        file_path = item.data(Qt.UserRole)
        self.music_player.play(file_path)
        self.update_title()

    @pyqtSlot()
    def stop_music(self):
        self.music_player.stop()
        self.update_title()

    @pyqtSlot()
    def pause_music(self):
        """Mette in pausa la riproduzione."""
        self.music_player.pause()

    @pyqtSlot()
    def next_music(self):
        self.music_player.stop()
        self.file_manager.next_track()
        self.update_ui()
        self.play_music()

    @pyqtSlot()
    def prev_music(self):
        self.music_player.stop()
        self.file_manager.prev_track()
        self.update_ui()
        self.play_music()

    def update_ui(self):
        if self.file_manager.get_current_track():
            current_track = self.file_manager.get_current_track()
            self.title_label.setText(f"Riproduzione: {current_track.title} - {current_track.artist}")

    def update_title(self):
        if self.music_list.currentItem():
            title = self.music_list.currentItem().text()
            self.title_label.setText(f"Riproduzione: {title}")
        else:
            self.title_label.setText("Nessun brano in riproduzione")

    @pyqtSlot()
    def open_settings_dialog(self):
        """Apre la finestra di dialogo delle impostazioni."""
        print("Apertura finestra di dialogo impostazioni")
        dialog = SettingsDialog(self.settings, self)
        result = dialog.exec_()

        if result == QtWidgets.QDialog.Accepted:
            selected_device = dialog.get_selected_device()
            self.preferred_device = selected_device
            self.settings.setValue("audio_device", selected_device)
            print(f"Dispositivo audio selezionato: {selected_device}")

            # Ricrea l'istanza del MusicPlayer con il nuovo dispositivo
            self.music_player = MusicPlayer(device=self.preferred_device)

    @pyqtSlot(int)
    def set_volume(self, volume):
        self.music_player.set_volume(volume)

    @pyqtSlot(list)
    def display_music_files(self, music_files):
        self.music_list.clear()
        for track in music_files:
            item = QListWidgetItem(track.title)
            item.setData(Qt.UserRole, track.path)
            self.music_list.addItem(item)
        self.update_ui()

    @pyqtSlot(int)
    def update_progress_bar(self, progress):
        self.progress_bar.setValue(progress)