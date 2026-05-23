import sys
import json
import math
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QFileDialog, QTabWidget, QLabel, QSlider, QSpinBox, 
    QScrollArea, QSplitter, QListWidget, QDoubleSpinBox, QFormLayout,
    QGroupBox, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QGraphicsEllipseItem, QGraphicsLineItem, QGraphicsItem, QAction
)
from PyQt5.QtCore import Qt, QPointF, QRectF, pyqtSignal, QTimer
from PyQt5.QtGui import QPixmap, QImage, QColor, QPen, QBrush, QPainter, QTransform, QPolygonF, QPainterPath

# --- ЧАСТЬ 1: МОДЕЛИ ДАННЫХ (data_models.py) ---

class Bone:
    def __init__(self, name, parent=None):
        self.name = name
        self.parent = parent
        self.children = []
        self.position = QPointF(0, 0) # Позиция относительно родителя
        self.global_position = QPointF(0, 0)
        self.weight = 1.0 # Влияние на вершины (упрощенно)
        self.rotation = 0.0 # Угол поворота

    def add_child(self, child_bone):
        self.children.append(child_bone)
        child_bone.parent = self

    def update_global_position(self, parent_transform=QTransform()):
        # Вычисляем глобальную позицию на основе родителя
        t = QTransform()
        t.translate(self.position.x(), self.position.y())
        t.rotate(self.rotation)
        
        global_transform = t * parent_transform
        
        # Получаем координаты из матрицы трансформации
        self.global_position = QPointF(global_transform.dx(), global_transform.dy())
        
        for child in self.children:
            child.update_global_position(global_transform)

    def to_dict(self):
        return {
            'name': self.name,
            'pos_x': self.position.x(),
            'pos_y': self.position.y(),
            'weight': self.weight,
            'rotation': self.rotation,
            'children': [c.to_dict() for c in self.children]
        }

class Keyframe:
    def __init__(self, time):
        self.time = time # Время в секундах (или кадрах)
        self.bone_states = {} # Словарь {bone_name: {'pos': QPointF, 'rot': float}}

    def set_bone_state(self, bone_name, pos, rot):
        self.bone_states[bone_name] = {'pos': pos, 'rot': rot}

    def to_dict(self):
        state_dict = {}
        for name, state in self.bone_states.items():
             state_dict[name] = {
                 'pos_x': state['pos'].x(), 
                 'pos_y': state['pos'].y(), 
                 'rot': state['rot']
             }
        return {'time': self.time, 'states': state_dict}

class Animation:
    def __init__(self, name):
        self.name = name
        self.keyframes = [] # Отсортированный список ключевых кадров
        self.duration = 5.0 # Длительность по умолчанию

    def add_keyframe(self, keyframe):
        # Вставляем кадр, сохраняя сортировку по времени
        self.keyframes.append(keyframe)
        self.keyframes.sort(key=lambda k: k.time)

    def get_interpolated_state(self, time):
        if not self.keyframes:
            return {}
        
        # Находим кадры до и после текущего времени
        k1 = None
        k2 = None
        for k in self.keyframes:
            if k.time <= time:
                k1 = k
            elif k.time > time and k2 is None:
                k2 = k
                break
                
        if k1 is None: return self.keyframes[0].bone_states
        if k2 is None: return k1.bone_states
        
        # Линейная интерполяция
        t_factor = (time - k1.time) / (k2.time - k1.time)
        interpolated = {}
        
        all_bones = set(k1.bone_states.keys()).union(set(k2.bone_states.keys()))
        for bone_name in all_bones:
            s1 = k1.bone_states.get(bone_name)
            s2 = k2.bone_states.get(bone_name)
            
            if s1 and s2:
                # Интерполируем позицию
                p_x = s1['pos'].x() + (s2['pos'].x() - s1['pos'].x()) * t_factor
                p_y = s1['pos'].y() + (s2['pos'].y() - s1['pos'].y()) * t_factor
                # Интерполируем вращение
                rot = s1['rot'] + (s2['rot'] - s1['rot']) * t_factor
                interpolated[bone_name] = {'pos': QPointF(p_x, p_y), 'rot': rot}
            elif s1:
                interpolated[bone_name] = s1
            elif s2:
                interpolated[bone_name] = s2
                
        return interpolated

    def to_dict(self):
        return {
            'name': self.name,
            'duration': self.duration,
            'keyframes': [k.to_dict() for k in self.keyframes]
        }

# --- ЧАСТЬ 2: ГРАФИЧЕСКИЕ ЭЛЕМЕНТЫ (graphics_items.py) ---

class BoneItem(QGraphicsLineItem):
    def __init__(self, start_joint, end_joint, bone_data):
        super().__init__()
        self.start_joint = start_joint
        self.end_joint = end_joint
        self.bone_data = bone_data
        
        pen = QPen(QColor(0, 255, 255, 150), 4)
        pen.setCapStyle(Qt.RoundCap)
        self.setPen(pen)
        self.setZValue(1)
        self.updatePosition()

    def updatePosition(self):
        self.setLine(self.start_joint.pos().x(), self.start_joint.pos().y(),
                     self.end_joint.pos().x(), self.end_joint.pos().y())

class JointItem(QGraphicsEllipseItem):
    def __init__(self, bone_data, is_root=False):
        super().__init__(-6, -6, 12, 12)
        self.bone_data = bone_data
        self.is_root = is_root
        
        self.setBrush(QBrush(QColor(255, 100, 100) if is_root else QColor(100, 255, 100)))
        self.setPen(QPen(Qt.white, 2))
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable | QGraphicsItem.ItemSendsGeometryChanges)
        self.setZValue(2)
        
        self.bones_connected = [] # Список подключенных BoneItem
        
        # Обновляем позицию на основе данных
        if bone_data:
            self.setPos(bone_data.global_position)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            for bone_line in self.bones_connected:
                bone_line.updatePosition()
                
            # Обновляем меш, если он есть
            scene = self.scene()
            if scene and hasattr(scene.views()[0], 'mesh_data'):
                editor = scene.views()[0]
                if editor.mesh_data:
                    editor.mesh_data.update_deformation(editor.joints)
                    # Принудительно перерисовываем меш-айтем
                    if editor.mesh_item:
                        editor.mesh_item.update()
                        
        return super().itemChange(change, value)

# --- ЧАСТЬ 3: РЕДАКТОР (editor_widget.py) ---

class SkeletonEditor(QGraphicsView):
    jointSelected = pyqtSignal(object) # Сигнал при выборе сустава

    def __init__(self):
        super().__init__()
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setBackgroundBrush(QBrush(QColor(40, 40, 45)))

        # Устанавливаем якорь масштабирования под курсор мыши
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)

        self.mesh_data = None
        self.mesh_item = None
        
        self.sprite_item = None
        self.joints = {} # name -> JointItem
        self.bone_lines = []
        
        self.root_bone = None
        self.current_mode = "SETUP" # SETUP или ANIMATE
        
        # Настройка сетки
        self.draw_grid()

    def draw_grid(self):
        pen = QPen(QColor(60, 60, 65), 1, Qt.DotLine)
        for i in range(-1000, 1000, 50):
            self.scene.addLine(i, -1000, i, 1000, pen).setZValue(-1)
            self.scene.addLine(-1000, i, 1000, i, pen).setZValue(-1)

    def wheelEvent(self, event):
        # Коэффициент масштабирования (1.2 — это +20% или -20% за шаг)
        zoom_in_factor = 1.2
        zoom_out_factor = 1 / zoom_in_factor

        # Проверяем направление прокрутки колесика
        if event.angleDelta().y() > 0:
            zoom_factor = zoom_in_factor
        else:
            zoom_factor = zoom_out_factor

        # Применяем масштаб
        self.scale(zoom_factor, zoom_factor)

    def load_sprite(self, filepath):
        if self.mesh_item:
            self.scene.removeItem(self.mesh_item)
            
        pixmap = QPixmap(filepath)
        # Сохраняем меш-данные
        offset_x = -pixmap.width() / 2
        offset_y = -pixmap.height() / 2
        
        self.mesh_data = Mesh(pixmap.width(), pixmap.height(), offset_x, offset_y, rows=15, cols=15)
        # Передаем и данные меша, и саму картинку
        self.mesh_item = MeshItem(self.mesh_data, pixmap)
        self.scene.addItem(self.mesh_item)
        
        self.fitInView(self.mesh_item.boundingRect(), Qt.KeepAspectRatio)

    def add_root_bone(self):
        if self.root_bone is not None:
            return
            
        self.root_bone = Bone("Root")
        self.root_bone.global_position = QPointF(0, 0)
        
        joint = JointItem(self.root_bone, is_root=True)
        self.scene.addItem(joint)
        self.joints["Root"] = joint

    def add_child_bone(self, parent_name, new_name):
        if parent_name not in self.joints or new_name in self.joints:
            return
            
        parent_joint = self.joints[parent_name]
        parent_bone = parent_joint.bone_data
        
        new_bone = Bone(new_name, parent_bone)
        # Устанавливаем начальную позицию немного в стороне от родителя
        new_bone.position = QPointF(50, 50)
        parent_bone.add_child(new_bone)
        
        # Обновляем глобальные координаты
        self.root_bone.update_global_position()
        
        new_joint = JointItem(new_bone)
        new_joint.setPos(new_bone.global_position)
        self.scene.addItem(new_joint)
        self.joints[new_name] = new_joint
        
        # Создаем линию между ними
        bone_line = BoneItem(parent_joint, new_joint, new_bone)
        self.scene.addItem(bone_line)
        self.bone_lines.append(bone_line)
        
        parent_joint.bones_connected.append(bone_line)
        new_joint.bones_connected.append(bone_line)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        
        # Ищем выбранный сустав
        items = self.scene.selectedItems()
        for item in items:
            if isinstance(item, JointItem):
                self.jointSelected.emit(item.bone_data)
                break

    def set_mode(self, mode):
        self.current_mode = mode
        # В режиме анимации можно двигать кости, но не добавлять
        # (Упрощенная логика для примера)
    def bind_mesh(self):
        if self.mesh_data and self.joints:
            self.mesh_data.bind_to_joints(self.joints)
            print("Сетка привязана к костям!")

# --- ЧАСТЬ 4: ВИДЖЕТ ТАЙМЛАЙНА (timeline_widget.py) ---

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

# ГЛАВНОЕ ОКНО И ИНТЕРФЕЙС

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


class Mesh:
    def __init__(self, width, height, offset_x=0, offset_y=0, rows=10, cols=10):
        self.rows = rows
        self.cols = cols
        self.bind_vertices = []       # Исходные позиции при привязке (Bind Pose)
        self.current_vertices = []    # Текущие позиции для отрисовки
        self.weights = []             # [{joint_name: weight, ...}, ...]
        
        # Генерируем сетку с учетом смещения (offset) спрайта
        for y in range(rows + 1):
            for x in range(cols + 1):
                px = (x / cols) * width + offset_x
                py = (y / rows) * height + offset_y
                self.bind_vertices.append(QPointF(px, py))
                self.current_vertices.append(QPointF(px, py))
                self.weights.append({})

    def bind_to_joints(self, joints_dict):
        """Рассчитываем веса для каждой вершины на основе расстояния до суставов"""
        self.weights = []
        for v in self.bind_vertices:
            v_weights = {}
            total_weight = 0.0
            
            for name, joint in joints_dict.items():
                # Дистанция от вершины до сустава
                dist = math.hypot(v.x() - joint.x(), v.y() - joint.y())
                # Избегаем деления на ноль, используем обратное расстояние в квадрате
                weight = 1.0 / (dist * dist + 0.0001) 
                
                # Учитываем индивидуальный вес кости (заданный в UI)
                weight *= joint.bone_data.weight 
                
                v_weights[name] = weight
                total_weight += weight
                
            # Нормализуем веса, чтобы их сумма равнялась 1.0
            if total_weight > 0:
                for name in v_weights:
                    v_weights[name] /= total_weight 
            self.weights.append(v_weights)
            
        # Сохраняем позиции суставов в момент привязки (Bind Pose)
        self.bind_joint_positions = {name: QPointF(j.x(), j.y()) for name, j in joints_dict.items()}

    def update_deformation(self, joints_dict):
        """Обновляем позиции вершин на основе текущего положения суставов (Упрощенный LBS)"""
        if not hasattr(self, 'bind_joint_positions'):
            return # Сетка еще не привязана

        for i, bind_v in enumerate(self.bind_vertices):
            new_x, new_y = 0.0, 0.0
            v_weights = self.weights[i]
            
            for name, weight in v_weights.items():
                if name in joints_dict and weight > 0:
                    current_joint = joints_dict[name]
                    bind_joint = self.bind_joint_positions[name]
                    
                    # Вектор смещения сустава относительно Bind Pose
                    delta_x = current_joint.x() - bind_joint.x()
                    delta_y = current_joint.y() - bind_joint.y()
                    
                    # Смещаем вершину (здесь упрощенная трансляция без учета сложных вращений матриц)
                    new_x += (bind_v.x() + delta_x) * weight
                    new_y += (bind_v.y() + delta_y) * weight
                    
            self.current_vertices[i] = QPointF(new_x, new_y)

class MeshItem(QGraphicsItem):
    def __init__(self, mesh_data, pixmap):
        super().__init__()
        self.mesh_data = mesh_data
        self.pixmap = pixmap
        self.setZValue(0) # Теперь это наш основной визуальный слой
        
    def boundingRect(self):
        # Упрощенный bounding box для всей сцены
        return QRectF(-2000, -2000, 4000, 4000)

    def paint(self, painter, option, widget):
        if not self.mesh_data or not self.mesh_data.current_vertices:
            return
            
        # Настраиваем качественную отрисовку
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setPen(Qt.NoPen)

        cols = self.mesh_data.cols
        rows = self.mesh_data.rows
        curr_verts = self.mesh_data.current_vertices
        bind_verts = self.mesh_data.bind_vertices
        verts = self.mesh_data.current_vertices

        # Отрисовка текстуры треугольниками
        for y in range(rows):
            for x in range(cols):
                # Индексы вершин квадрата (quad)
                i1 = y * (cols + 1) + x
                i2 = i1 + 1
                i3 = (y + 1) * (cols + 1) + x
                i4 = i3 + 1

                # Отрисовываем два треугольника для каждого квадрата сетки
                self.draw_textured_triangle(painter, i1, i2, i3, curr_verts, bind_verts)
                self.draw_textured_triangle(painter, i2, i4, i3, curr_verts, bind_verts)

        # Опционально: рисуем сетку поверх для отладки (можешь потом закомментировать)
        painter.setPen(QPen(QColor(0, 255, 255, 50), 1))
        
        # Отрисовка линий сетки (квадратов)
        for y in range(rows):
            for x in range(cols):
                idx = y * (cols + 1) + x
                # Текущая вершина, сосед справа, сосед снизу
                v_curr = verts[idx]
                v_right = verts[idx + 1]
                v_bottom = verts[idx + cols + 1]
                
                # Горизонтальная линия
                painter.drawLine(v_curr, v_right)
                # Вертикальная линия
                painter.drawLine(v_curr, v_bottom)
                
        # Дорисовываем правый и нижний края
        for y in range(rows):
            idx = y * (cols + 1) + cols
            painter.drawLine(verts[idx], verts[idx + cols + 1])
        for x in range(cols):
            idx = rows * (cols + 1) + x
            painter.drawLine(verts[idx], verts[idx + 1])

    def draw_textured_triangle(self, painter, idx1, idx2, idx3, curr_v, bind_v):
        """Рисует один треугольник текстуры с учетом трансформации"""
        # Текущие экранные координаты (куда рисуем)
        p1, p2, p3 = curr_v[idx1], curr_v[idx2], curr_v[idx3]
        
        # Исходные координаты в текстуре (откуда берем)
        offset = QPointF(self.pixmap.width() / 2, self.pixmap.height() / 2)
        t1, t2, t3 = bind_v[idx1] + offset, bind_v[idx2] + offset, bind_v[idx3] + offset

        # QTransform.quadToQuad жестко требует 4 точки.
        # Математически достраиваем наши треугольники до параллелограммов:
        p4 = QPointF(p1.x() + p3.x() - p2.x(), p1.y() + p3.y() - p2.y())
        t4 = QPointF(t1.x() + t3.x() - t2.x(), t1.y() + t3.y() - t2.y())

        dest_quad = QPolygonF([p1, p2, p3, p4])
        src_quad = QPolygonF([t1, t2, t3, t4])

        trans = QTransform()
        if QTransform.quadToQuad(src_quad, dest_quad, trans):
            painter.save()
            
            # 1. СНАЧАЛА задаем маску обрезки в текущих (экранных) координатах.
            # Нам нужен только исходный треугольник, а не весь параллелограмм!
            path = QPainterPath()
            path.addPolygon(QPolygonF([p1, p2, p3]))
            painter.setClipPath(path)
            
            # 2. ПОТОМ применяем трансформацию (из текстурных координат в экранные)
            painter.setTransform(trans, True)
            
            # 3. Рисуем картинку с нулевых координат (трансформация сама поставит её куда надо)
            painter.drawPixmap(0, 0, self.pixmap)
            
            painter.restore()

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