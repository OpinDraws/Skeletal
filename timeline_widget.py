from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSlider
from PyQt5.QtCore import Qt, pyqtSignal, QTimer

class TimelineWidget(QWidget):
    timeChanged = pyqtSignal(float)
    keyframeAdded = pyqtSignal(float)

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Панель управления
        control_layout = QHBoxLayout()
        self.btn_play = QPushButton("▶ Play")
        self.btn_stop = QPushButton("■ Stop")
        self.btn_add_key = QPushButton("➕ Add Keyframe")
        
        self.lbl_time = QLabel("Time: 0.0s")
        
        control_layout.addWidget(self.btn_play)
        control_layout.addWidget(self.btn_stop)
        control_layout.addWidget(self.btn_add_key)
        control_layout.addStretch()
        control_layout.addWidget(self.lbl_time)
        
        # Слайдер времени
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 500) # 0.0s - 5.0s (с шагом 0.01)
        self.slider.valueChanged.connect(self.on_slider_changed)
        
        layout.addLayout(control_layout)
        layout.addWidget(self.slider)
        
        # Таймер для проигрывания
        self.timer = QTimer()
        self.timer.timeout.connect(self.on_tick)
        self.is_playing = False
        
        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_stop.clicked.connect(self.stop_play)
        self.btn_add_key.clicked.connect(self.add_keyframe)

    def on_slider_changed(self, value):
        time_sec = value / 100.0
        self.lbl_time.setText(f"Time: {time_sec:.2f}s")
        self.timeChanged.emit(time_sec)

    def toggle_play(self):
        if self.is_playing:
            self.timer.stop()
            self.btn_play.setText("▶ Play")
        else:
            self.timer.start(33) # ~30 fps
            self.btn_play.setText("⏸ Pause")
        self.is_playing = not self.is_playing

    def stop_play(self):
        self.timer.stop()
        self.is_playing = False
        self.btn_play.setText("▶ Play")
        self.slider.setValue(0)

    def on_tick(self):
        val = self.slider.value() + 3
        if val > self.slider.maximum():
            val = 0
        self.slider.setValue(val)

    def add_keyframe(self):
        time_sec = self.slider.value() / 100.0
        self.keyframeAdded.emit(time_sec)
