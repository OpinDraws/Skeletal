from PyQt5.QtWidgets import QGraphicsLineItem, QGraphicsEllipseItem, QGraphicsItem
from PyQt5.QtCore import Qt, QPointF, QRectF
from PyQt5.QtGui import QColor, QPen, QBrush, QPainter, QTransform, QPolygonF, QPainterPath, QPixmap

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

        # Рисуем сетку поверх для отладки
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
