import sys
import json
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QFileDialog, QTabWidget, QLabel, QSplitter, 
    QListWidget, QDoubleSpinBox, QFormLayout, QGroupBox
)
from PyQt5.QtCore import Qt, QPointF

from data_models import Animation, Keyframe
from graphics_items import JointItem
from editor_widget import SkeletonEditor
from timeline_widget import TimelineWidget

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Skeletal Shader Animator Pro")
        self.setGeometry(100, 100, 1200, 800)
        
        self.current_animation = Animation("Default")
        
        self.init_ui()
        self.apply_styles()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout(central_widget)

        # Сначала инициализируем редактор и таймлайн, чтобы вкладки могли к ним обращаться
        self.editor = SkeletonEditor()
        self.editor.jointSelected.connect(self.on_joint_selected)
        
        self.timeline = TimelineWidget()
        self.timeline.timeChanged.connect(self.on_time_scrubbed)
        self.timeline.keyframeAdded.connect(self.on_keyframe_added)
        
        # ЛЕВАЯ ПАНЕЛЬ (Инструменты и свойства)
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_panel.setMaximumWidth(300)
        
        # Вкладки Setup / Animate
        self.tabs = QTabWidget()
        self.tab_setup = QWidget()
        self.tab_animate = QWidget()
        self.tabs.addTab(self.tab_setup, "1. Skeleton Setup")
        self.tabs.addTab(self.tab_animate, "2. Animation")
        self.tabs.currentChanged.connect(self.on_tab_changed)
        
        self.setup_tab_setup(self.tab_setup)
        self.setup_tab_animate(self.tab_animate)
        
        left_layout.addWidget(self.tabs)
        
        # Свойства выбранной кости
        group_props = QGroupBox("Bone Properties")
        form_layout = QFormLayout(group_props)
        
        self.lbl_bone_name = QLabel("-")
        self.spin_weight = QDoubleSpinBox()
        self.spin_weight.setRange(0.0, 1.0)
        self.spin_weight.setSingleStep(0.1)
        self.spin_weight.setValue(1.0)
        
        form_layout.addRow("Name:", self.lbl_bone_name)
        form_layout.addRow("Weight:", self.spin_weight)
        
        left_layout.addWidget(group_props)
        left_layout.addStretch()
        
        # Кнопки сохранения/загрузки
        self.btn_load_sprite = QPushButton("Load Sprite")
        self.btn_save_json = QPushButton("Export Animation (JSON)")
        self.btn_load_sprite.clicked.connect(self.load_sprite_dialog)
        self.btn_save_json.clicked.connect(self.export_json)
        
        left_layout.addWidget(self.btn_load_sprite)
        left_layout.addWidget(self.btn_save_json)
        
        # ПРАВАЯ ПАНЕЛЬ (Редактор и Таймлайн) 
        right_panel = QSplitter(Qt.Vertical)
        
        right_panel.addWidget(self.editor)
        right_panel.addWidget(self.timeline)
        right_panel.setSizes([600, 200]) # Пропорции сплиттера
        
        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel)

    def setup_tab_setup(self, tab):
        layout = QVBoxLayout(tab)
        
        self.btn_add_root = QPushButton("Add Root Bone")
        self.btn_add_child = QPushButton("Add Child Bone")
        
        self.btn_add_root.clicked.connect(self.editor.add_root_bone)
        self.btn_add_child.clicked.connect(self.add_child_bone_dialog)
        
        self.list_bones = QListWidget()
        
        self.btn_bind = QPushButton("Bind Mesh to Bones")
        self.btn_bind.clicked.connect(self.editor.bind_mesh)
        
        layout.addWidget(self.btn_add_root)
        layout.addWidget(self.btn_add_child)
        layout.addWidget(self.btn_bind) # Новая кнопка
        layout.addWidget(QLabel("Bones Hierarchy:"))
        layout.addWidget(self.list_bones)

    def setup_tab_animate(self, tab):
        layout = QVBoxLayout(tab)
        layout.addWidget(QLabel("Select a bone in the editor,\nmove it, and click 'Add Keyframe'\non the timeline."))
        layout.addStretch()

    def on_tab_changed(self, index):
        if index == 0:
            self.editor.set_mode("SETUP")
            self.timeline.setEnabled(False)
        else:
            self.editor.set_mode("ANIMATE")
            self.timeline.setEnabled(True)

    def load_sprite_dialog(self):
        options = QFileDialog.Options()
        file_name, _ = QFileDialog.getOpenFileName(self, "Load Sprite Image", "", "Images (*.png *.jpg *.jpeg *.bmp)", options=options)
        if file_name:
            self.editor.load_sprite(file_name)

    def add_child_bone_dialog(self):
        # В реальном приложении здесь был бы диалог. Для примера берем выбранную или Root
        selected_items = self.editor.scene.selectedItems()
        parent_name = "Root"
        
        for item in selected_items:
            if isinstance(item, JointItem):
                parent_name = item.bone_data.name
                break
                
        new_name = f"Bone_{len(self.editor.joints)}"
        self.editor.add_child_bone(parent_name, new_name)
        self.update_bone_list()

    def update_bone_list(self):
        self.list_bones.clear()
        for name in self.editor.joints.keys():
            self.list_bones.addItem(name)

    def on_joint_selected(self, bone_data):
        self.lbl_bone_name.setText(bone_data.name)
        self.spin_weight.setValue(bone_data.weight)
        
        # Обновляем вес при изменении спинбокса
        try:
            self.spin_weight.valueChanged.disconnect()
        except: pass
        self.spin_weight.valueChanged.connect(lambda val: setattr(bone_data, 'weight', val))

    def on_keyframe_added(self, time_sec):
        kf = Keyframe(time_sec)
        # Сохраняем текущее состояние всех костей
        for name, joint in self.editor.joints.items():
            pos = joint.pos()
            # Берем позицию сустава как его состояние
            kf.set_bone_state(name, QPointF(pos.x(), pos.y()), joint.bone_data.rotation)
            
        self.current_animation.add_keyframe(kf)
        print(f"Keyframe added at {time_sec}s")

    def on_time_scrubbed(self, time_sec):
        if self.editor.current_mode != "ANIMATE":
            return
            
        # Получаем интерполированное состояние
        state = self.current_animation.get_interpolated_state(time_sec)
        
        # Применяем к костям в редакторе
        for bone_name, data in state.items():
            if bone_name in self.editor.joints:
                joint = self.editor.joints[bone_name]
                joint.setPos(data['pos'])
                # joint.bone_data.rotation = data['rot']
                
        # Обновляем линии
        for line in self.editor.bone_lines:
            line.updatePosition()

    def export_json(self):
        options = QFileDialog.Options()
        file_name, _ = QFileDialog.getSaveFileName(self, "Export Animation Data", "animation.json", "JSON Files (*.json)", options=options)
        
        if file_name:
            # Собираем данные
            data = {
                'skeleton': self.editor.root_bone.to_dict() if self.editor.root_bone else {},
                'animation': self.current_animation.to_dict()
            }
            
            with open(file_name, 'w') as f:
                json.dump(data, f, indent=4)
            print(f"Exported successfully to {file_name}")

    def apply_styles(self):
        dark_stylesheet = """
        QMainWindow, QWidget {
            background-color: #1E1E1E;
            color: #D4D4D4;
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 14px;
        }
        
        QTabWidget::pane {
            border: 1px solid #333333;
            background: #252526;
            border-radius: 4px;
        }
        
        QTabBar::tab {
            background: #2D2D30;
            color: #969696;
            padding: 8px 16px;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
            margin-right: 2px;
        }
        
        QTabBar::tab:selected {
            background: #1E1E1E;
            color: #FFFFFF;
            border-bottom: 2px solid #007ACC;
        }
        
        QPushButton {
            background-color: #0E639C;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            font-weight: bold;
        }
        
        QPushButton:hover {
            background-color: #1177BB;
        }
        
        QPushButton:pressed {
            background-color: #094771;
        }
        
        QPushButton:disabled {
            background-color: #333333;
            color: #666666;
        }
        
        QGroupBox {
            border: 1px solid #3E3E42;
            border-radius: 4px;
            margin-top: 1ex;
            padding-top: 10px;
        }
        
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top center;
            padding: 0 5px;
            color: #007ACC;
        }
        
        QListWidget {
            background-color: #252526;
            border: 1px solid #3E3E42;
            border-radius: 4px;
        }
        
        QListWidget::item:selected {
            background-color: #094771;
        }
        
        QSlider::groove:horizontal {
            border: 1px solid #3E3E42;
            height: 8px;
            background: #252526;
            margin: 2px 0;
            border-radius: 4px;
        }

        QSlider::handle:horizontal {
            background: #007ACC;
            border: 1px solid #007ACC;
            width: 14px;
            margin: -4px 0;
            border-radius: 7px;
        }
        
        QDoubleSpinBox {
            background-color: #3C3C3C;
            border: 1px solid #3E3E42;
            padding: 4px;
            border-radius: 2px;
        }
        """
        self.setStyleSheet(dark_stylesheet)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    # Для лучшего вида на экранах высокого разрешения
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        app.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
        
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())