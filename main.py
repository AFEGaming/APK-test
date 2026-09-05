import sys
import requests
import math
import csv
import os
import json
from datetime import datetime
from io import BytesIO
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QTableWidget, QTableWidgetItem, 
                             QTabWidget, QLabel, QLineEdit, QCheckBox, 
                             QHeaderView, QFrame, QComboBox, QPushButton)
from PyQt6.QtCore import Qt, QPoint, QTimer, QThread, pyqtSignal, QPointF
from PyQt6.QtGui import QColor, QFont, QPixmap, QPainter, QPen, QBrush, QPolygonF

SERVER_URL = "http://wafflesonne.com:8080"
PLAYERS_ENDPOINT = f"{SERVER_URL}/tiles/players.json"
SETTINGS_ENDPOINT = f"{SERVER_URL}/tiles/settings.json"
MARKERS_ENDPOINT = f"{SERVER_URL}/tiles/markers.json"
TILE_URL_TEMPLATE = f"{SERVER_URL}/tiles/{{world}}/{{zoom}}/{{x}}_{{z}}.png"
CONFIG_FILE = "config.json"

def get_compass_direction(yaw):
    yaw = (yaw + 360) % 360
    if 45 <= yaw < 135: return "Batı"
    elif 135 <= yaw < 225: return "Kuzey"
    elif 225 <= yaw < 315: return "Doğu"
    else: return "Güney"

class TileDownloadWorker(QThread):
    """Tile görsellerini güvenli ve hızlı indiren işçi sınıfı"""
    tile_loaded = pyqtSignal(tuple, object)

    def __init__(self, tile_requests):
        super().__init__()
        self.tile_requests = tile_requests

    def run(self):
        for key, url in self.tile_requests.items():
            try:
                res = requests.get(url, timeout=2)
                if res.status_code == 200 and res.content:
                    pixmap = QPixmap()
                    if pixmap.loadFromData(BytesIO(res.content).getvalue()) and not pixmap.isNull():
                        self.tile_loaded.emit(key, pixmap)
                    else:
                        self.tile_loaded.emit(key, None)
                else:
                    self.tile_loaded.emit(key, None)
            except Exception:
                self.tile_loaded.emit(key, None)

class MapCanvas(QWidget):
    """Null pixmap hatalarından arındırılmış, fareyle sürüklenebilir harita motoru"""
    def __init__(self):
        super().__init__()
        self.players = []
        self.markers = []
        self.center_x = 0
        self.center_z = 0
        self.zoom = 0
        self.world_name = "world"
        self.tile_cache = {}
        self.active_downloads = set()
        
        self.dragging = False
        self.last_mouse_pos = QPoint()
        
        self.setMinimumSize(600, 600)
        self.setStyleSheet("background-color: #11111b;")
        self.setMouseTracking(True)

    def update_map_data(self, players, markers, cx, cz, zoom, world):
        self.players = players
        self.markers = markers
        self.center_x = cx
        self.center_z = cz
        self.zoom = int(zoom)
        self.world_name = world
        self.update()

    def wheelEvent(self, event):
        angle = event.angleDelta().y()
        if angle > 0:
            if self.zoom < 4: self.zoom += 1
        else:
            if self.zoom > -3: self.zoom -= 1
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = True
            self.last_mouse_pos = event.pos()

    def mouseMoveEvent(self, event):
        if self.dragging:
            delta = event.pos() - self.last_mouse_pos
            self.last_mouse_pos = event.pos()
            scale = math.pow(2, self.zoom)
            self.center_x -= delta.x() * (1.0 / max(0.25, scale))
            self.center_z -= delta.y() * (1.0 / max(0.25, scale))
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = False

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        width = self.width()
        height = self.height()
        center_screen_x = width // 2
        center_screen_y = height // 2

        tile_size = 512
        scale_factor = math.pow(2, self.zoom)
        effective_tile_size = int(tile_size * max(0.25, scale_factor))

        center_tile_x = int(math.floor(self.center_x / tile_size))
        center_tile_z = int(math.floor(self.center_z / tile_size))

        requests_to_fetch = {}
        render_range = 2 if self.zoom >= 0 else 4

        for dx in range(-render_range, render_range + 1):
            for dz in range(-render_range, render_range + 1):
                tx = center_tile_x + dx
                tz = center_tile_z + dz
                tile_key = (self.world_name, self.zoom, tx, tz)

                if tile_key in self.tile_cache:
                    pixmap = self.tile_cache[tile_key]
                    # Null kontrolü ile QPixmap hatası kesin olarak engellendi
                    if pixmap and not pixmap.isNull():
                        draw_x = center_screen_x + int((tx * tile_size - self.center_x) * scale_factor)
                        draw_y = center_screen_y + int((tz * tile_size - self.center_z) * scale_factor)
                        
                        if self.zoom != 0:
                            scaled_pix = pixmap.scaled(effective_tile_size, effective_tile_size, 
                                                       Qt.AspectRatioMode.KeepAspectRatio, 
                                                       Qt.TransformationMode.SmoothTransformation)
                            if not scaled_pix.isNull():
                                painter.drawPixmap(draw_x, draw_y, scaled_pix)
                        else:
                            painter.drawPixmap(draw_x, draw_y, pixmap)
                else:
                    if tile_key not in self.active_downloads:
                        url = TILE_URL_TEMPLATE.format(world=self.world_name, zoom=self.zoom, x=tx, z=tz)
                        requests_to_fetch[tile_key] = url
                        self.active_downloads.add(tile_key)

        if requests_to_fetch:
            self.worker = TileDownloadWorker(requests_to_fetch)
            self.worker.tile_loaded.connect(self.on_tile_loaded)
            self.worker.start()

        # Claim / Sınır Çizimleri
        for m in self.markers:
            m_type = m.get("type", "")
            if "rectangle" in m_type or "polygon" in m_type:
                points = m.get("points", [])
                if points:
                    painter.setPen(QPen(QColor("#f38ba8"), 2, Qt.PenStyle.SolidLine))
                    painter.setBrush(QBrush(QColor(243, 139, 168, 40)))
                    polygon_points = []
                    for pt in points:
                        px = pt.get("x", 0)
                        pz = pt.get("z", 0)
                        sx = center_screen_x + int((px - self.center_x) * scale_factor)
                        sy = center_screen_y + int((pz - self.center_z) * scale_factor)
                        polygon_points.append(QPointF(sx, sy))
                    
                    if len(polygon_points) > 2:
                        painter.drawPolygon(QPolygonF(polygon_points))

        # Oyuncular
        for p in self.players:
            px = int(p.get("x", 0))
            pz = int(p.get("z", 0))
            name = p.get("name", "Bilinmeyen")

            screen_x = center_screen_x + int((px - self.center_x) * scale_factor)
            screen_y = center_screen_y + int((pz - self.center_z) * scale_factor)

            if -50 <= screen_x <= width + 50 and -50 <= screen_y <= height + 50:
                painter.setBrush(QBrush(QColor("#a6e3a1")))
                painter.setPen(QPen(QColor("#11111b"), 2))
                painter.drawEllipse(QPoint(screen_x, screen_y), 7, 7)

                painter.setPen(QPen(QColor("#cdd6f4"), 1))
                painter.setFont(QFont("Arial", 9, QFont.Weight.Bold))
                painter.drawText(screen_x + 10, screen_y + 4, f"{name} ({px}, {pz})")

        painter.setPen(QPen(QColor("#89b4fa")))
        painter.setFont(QFont("Arial", 9))
        painter.drawText(15, 25, f"Zoom: {self.zoom} | Merkez: ({int(self.center_x)}, {int(self.center_z)})")

    def on_tile_loaded(self, key, pixmap):
        self.tile_cache[key] = pixmap
        if key in self.active_downloads:
            self.active_downloads.remove(key)
        self.update()

class AdvancedMapClient(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Squaremap Komuta Merkezi v4.5")
        self.setGeometry(100, 100, 1250, 750)
        self.setStyleSheet("background-color: #1e1e2e; color: #cdd6f4;")

        self.config = self.load_config()
        self.mapped_worlds = []
        self.unmapped_worlds = []
        self.markers_data = []
        self.total_players_cache = 0

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabBar::tab { background: #313244; color: white; padding: 8px 15px; margin-right: 2px; }
            QTabBar::tab:selected { background: #89b4fa; color: #11111b; font-weight: bold; }
        """)
        self.layout.addWidget(self.tabs)

        self.setup_dashboard_tab()
        self.setup_radar_tab()
        self.setup_map_tab()

        self.status_bar = QLabel("Sistem başlatılıyor...")
        self.status_bar.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self.status_bar.setStyleSheet("color: #a6e3a1; padding: 5px;")
        self.layout.addWidget(self.status_bar)

        self.log_file = "advanced_player_logs.csv"
        if not os.path.exists(self.log_file):
            with open(self.log_file, mode='w', newline='', encoding='utf-8') as f:
                csv.writer(f).writerow(["Tarih", "Saat", "UUID", "İsim", "Dünya", "X", "Y", "Z", "Yön", "Can"])

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_data)
        self.timer.start(3000)

        self.update_settings()

    def load_config(self):
        default_config = {"x": "0", "z": "0", "range": "500", "zoom": "0", "world": "Tümü"}
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    return {**default_config, **json.load(f)}
            except Exception:
                pass
        return default_config

    def save_config(self):
        config_data = {
            "x": self.entry_x.text(),
            "z": self.entry_z.text(),
            "range": self.entry_range.text(),
            "zoom": self.config.get("zoom", "0"),
            "world": self.combo_world.currentText()
        }
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config_data, f, indent=4)
        except Exception:
            pass

    def closeEvent(self, event):
        self.save_config()
        event.accept()

    def setup_dashboard_tab(self):
        self.tab_dash = QWidget()
        layout = QVBoxLayout(self.tab_dash)
        self.server_info_label = QLabel("Sunucu Bilgileri Yükleniyor...")
        self.server_info_label.setFont(QFont("Arial", 11))
        self.server_info_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.server_info_label)
        self.tabs.addTab(self.tab_dash, "Genel Bakış")

    def setup_radar_tab(self):
        self.tab_radar = QWidget()
        layout = QVBoxLayout(self.tab_radar)

        control_frame = QFrame()
        control_layout = QHBoxLayout(control_frame)
        
        control_layout.addWidget(QLabel("Dünya Filtresi:"))
        self.combo_world = QComboBox()
        self.combo_world.addItem("Tümü")
        self.combo_world.setStyleSheet("background: #313244; color: white; padding: 3px;")
        control_layout.addWidget(self.combo_world)

        control_layout.addWidget(QLabel("Merkez X:"))
        self.entry_x = QLineEdit(self.config.get("x", "0"))
        self.entry_x.setMaximumWidth(70)
        control_layout.addWidget(self.entry_x)

        control_layout.addWidget(QLabel("Merkez Z:"))
        self.entry_z = QLineEdit(self.config.get("z", "0"))
        self.entry_z.setMaximumWidth(70)
        control_layout.addWidget(self.entry_z)

        control_layout.addWidget(QLabel("Menzil:"))
        self.entry_range = QLineEdit(self.config.get("range", "500"))
        self.entry_range.setMaximumWidth(70)
        control_layout.addWidget(self.entry_range)

        self.check_log = QCheckBox("CSV Log Aktif")
        self.check_log.setChecked(True)
        control_layout.addWidget(self.check_log)
        control_layout.addStretch()
        layout.addWidget(control_frame)

        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(["İsim", "Dünya", "Koordinat", "Yön", "Mesafe", "Can", "Zırh", "UUID"])
        
        header = self.table.horizontalHeader()
        for i in range(7):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)

        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)

        self.tabs.addTab(self.tab_radar, "Canlı Radar & Tablo")

    def setup_map_tab(self):
        self.tab_map = QWidget()
        layout = QVBoxLayout(self.tab_map)
        
        map_control_layout = QHBoxLayout()
        
        self.check_claims = QCheckBox("Claim / Sınırları Göster")
        self.check_claims.setChecked(True)
        map_control_layout.addWidget(self.check_claims)

        btn_reset_view = QPushButton("Merkeze Dön (0,0)")
        btn_reset_view.setStyleSheet("background: #313244; color: white; padding: 4px 10px;")
        btn_reset_view.clicked.connect(lambda: self.reset_map_center(0, 0))
        map_control_layout.addWidget(btn_reset_view)

        btn_world_view = QPushButton("Tüm Dünyayı Gör (Kuş Bakışı)")
        btn_world_view.setStyleSheet("background: #89b4fa; color: #11111b; font-weight: bold; padding: 4px 10px;")
        btn_world_view.clicked.connect(self.zoom_out_full)
        map_control_layout.addWidget(btn_world_view)

        map_control_layout.addStretch()
        layout.addLayout(map_control_layout)

        self.map_canvas = MapCanvas()
        layout.addWidget(self.map_canvas)

        self.tabs.addTab(self.tab_map, "Canlı Harita Görseli (Tiles)")

    def reset_map_center(self, x, z):
        self.map_canvas.center_x = x
        self.map_canvas.center_z = z
        self.map_canvas.update()

    def zoom_out_full(self):
        self.map_canvas.zoom = -3
        self.map_canvas.center_x = 0
        self.map_canvas.center_z = 0
        self.map_canvas.update()

    def update_settings(self):
        try:
            res = requests.get(SETTINGS_ENDPOINT, timeout=3)
            if res.status_code == 200:
                data = res.json()
                self.mapped_worlds = [w.get('name', 'Bilinmiyor') for w in data.get("worlds", [])]
            
            res_markers = requests.get(MARKERS_ENDPOINT, timeout=3)
            if res_markers.status_code == 200:
                self.markers_data = res_markers.json() if isinstance(res_markers.json(), list) else []
        except Exception:
            pass

    def update_dashboard_ui(self):
        mapped_str = ", ".join(self.mapped_worlds) if self.mapped_worlds else "Yok"
        unmapped_str = ", ".join(list(self.unmapped_worlds)) if self.unmapped_worlds else "Yok (Tüm aktif dünyalar haritalı)"
        
        info_html = f"""
        <h2>🌍 Sunucu Komuta Merkezi & Durum Paneli</h2>
        <hr style="border: 1px solid #313244;">
        <p><b>Sunucu Adresi:</b> {SERVER_URL}</p>
        <p><b>Toplam Çevrimiçi Oyuncu:</b> {self.total_players_cache}</p>
        <br>
        <h3>🗺️ Harita Desteği Olan Dünyalar (Tiles Aktif)</h3>
        <ul>
            <li><b>{mapped_str}</b></li>
        </ul>
        <br>
        <h3>⚠️ Harita Desteği Olmayan / Diğer Aktif Dünyalar (Sadece Koordinat/CSV)</h3>
        <ul>
            <li><b>{unmapped_str}</b></li>
        </ul>
        <br>
        <p style="color: #a6e3a1;"><i>İpucu: Harita sekmesinden farenizle sürükleyerek gezinebilir, tekerlekle yakınlaşıp uzaklaşabilirsiniz.</i></p>
        """
        self.server_info_label.setText(info_html)

    def update_data(self):
        try:
            res = requests.get(PLAYERS_ENDPOINT, timeout=3)
            if res.status_code != 200: return
            
            data = res.json()
            players = data.get("players", []) if isinstance(data, dict) else data
        except Exception:
            self.status_bar.setText("⚠️ Bağlantı hatası!")
            return

        self.total_players_cache = len(players)

        # Dünyaları sınıflandır (Haritalı vs Haritasız)
        all_player_worlds = set([p.get("world", "world") for p in players])
        self.unmapped_worlds = all_player_worlds - set(self.mapped_worlds)

        # Genel Bakış arayüzünü güncel verilerle tazele
        self.update_dashboard_ui()

        # ComboBox filtre listesini doldur (Haritalı + Haritasız tüm dünyalar)
        combined_worlds = sorted(list(set(self.mapped_worlds + list(all_player_worlds))))
        current_selection = self.combo_world.currentText()
        
        self.combo_world.clear()
        self.combo_world.addItem("Tümü")
        for w in combined_worlds:
            self.combo_world.addItem(w)
        
        index = self.combo_world.findText(current_selection)
        if index >= 0:
            self.combo_world.setCurrentIndex(index)
        else:
            saved_world = self.config.get("world", "Tümü")
            saved_index = self.combo_world.findText(saved_world)
            if saved_index >= 0:
                self.combo_world.setCurrentIndex(saved_index)

        try:
            base_x = float(self.entry_x.text())
            base_z = float(self.entry_z.text())
            radar_range = float(self.entry_range.text())
        except ValueError:
            base_x, base_z, radar_range = 0, 0, 500

        selected_world_filter = self.combo_world.currentText()

        filtered_players = []
        for p in players:
            p_world = p.get("world", "world")
            if selected_world_filter == "Tümü" or p_world == selected_world_filter:
                filtered_players.append(p)

        self.table.setRowCount(len(filtered_players))
        alert_count = 0
        now = datetime.now()

        active_world = selected_world_filter if selected_world_filter != "Tümü" else (filtered_players[0].get("world", "world") if filtered_players else "world")

        for row, p in enumerate(filtered_players):
            name = p.get("name", "-")
            world = p.get("world", "world")
            x, y, z = int(p.get("x", 0)), int(p.get("y", 0)), int(p.get("z", 0))
            hp = str(p.get("health", "-"))
            armor = str(p.get("armor", "-"))
            uuid = p.get("uuid", "-")
            yaw = p.get("yaw", 0)
            direction = get_compass_direction(yaw)

            distance = int(math.hypot(x - base_x, z - base_z))
            
            if self.check_log.isChecked():
                with open(self.log_file, mode='a', newline='', encoding='utf-8') as f:
                    csv.writer(f).writerow([now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), p.get("uuid", ""), name, world, x, y, z, direction, hp])

            items = [
                QTableWidgetItem(name), QTableWidgetItem(world), 
                QTableWidgetItem(f"{x}, {y}, {z}"), QTableWidgetItem(direction), 
                QTableWidgetItem(f"{distance}m"), QTableWidgetItem(hp), 
                QTableWidgetItem(armor), QTableWidgetItem(uuid)
            ]

            is_danger = distance <= radar_range
            if is_danger: alert_count += 1

            for col, item in enumerate(item
