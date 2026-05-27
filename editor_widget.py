from PyQt5.QtWidgets import QGraphicsView, QGraphicsScene
from PyQt5.QtCore import Qt, QPointF, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QPen, QPainter, QPixmap

from data_models import Bone, Mesh
from graphics_items import BoneItem, JointItem, MeshItem

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
