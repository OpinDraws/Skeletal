import math
from PyQt5.QtCore import QPointF
from PyQt5.QtGui import QTransform

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
        # Рассчитываем веса для каждой вершины на основе расстояния до суставов
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
        # Обновляем позиции вершин на основе текущего положения суставов (Упрощенный LBS)
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
