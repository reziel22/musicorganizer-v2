import sys
import logging
from PyQt5.QtWidgets import QApplication
from gui import MainWindow

# Configura il logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    filename='music_organizer.log')

def main():
    """Funzione principale per avviare l'applicazione."""
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()