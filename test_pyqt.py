import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget, QLabel

class TestApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyQt6 Test")
        self.setGeometry(100, 100, 300, 200)
        
        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Create label
        label = QLabel("PyQt6 is working!")
        layout.addWidget(label)
        
        # Create button
        button = QPushButton("Click Me")
        button.clicked.connect(lambda: label.setText("Button clicked!"))
        layout.addWidget(button)

if __name__ == '__main__':
    print("Starting PyQt6 test application...")
    app = QApplication(sys.argv)
    window = TestApp()
    window.show()
    print("Test application started. Window should be visible.")
    sys.exit(app.exec()) 