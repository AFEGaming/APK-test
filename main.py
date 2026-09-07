import os
import requests
from PIL import Image
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed

# Sunucu ve Dünya Bilgileri
SERVER_URL = "http://wafflesonne.com:8080"
WORLD_NAME = "minecraft_yeni"  # İndirmek istediğin dünya adı[cite: 1]
ZOOM_LEVEL = 5        # İstediğin yakınlaşma / detay seviyesi[cite: 1]
TILE_SIZE = 512       # Squaremap için 512x512 piksel[cite: 1]

def download_single_tile(args):
    x, z, world, zoom = args
    tile_url = f"{SERVER_URL}/tiles/{world}/{zoom}/{x}_{z}.png"
    try:
        res = requests.get(tile_url, timeout=3)
        if res.status_code == 200 and res.content:
            tile_img = Image.open(BytesIO(res.content)).convert('RGB')
            return x, z, tile_img
    except Exception:
        pass
    return x, z, None

def download_full_map():
    print("🌍 Sunucu ayarları alınıyor...")
    try:
        settings_res = requests.get(f"{SERVER_URL}/tiles/settings.json")
        if settings_res.status_code != 200:
            print("❌ Ayarlar dosyasına ulaşılamadı!")
            return
        settings = settings_res.json()
    except Exception as e:
        print(f"❌ Bağlantı hatası: {e}")
        return

    print(f"📥 '{WORLD_NAME}' dünyası için tile'lar taranıyor (Zoom: {ZOOM_LEVEL})...")

    # Tarama aralığı (Zoom 5 için matris sınırları)
    min_x, max_x = -50, 50  
    min_z, max_z = -50, 50  

    # Boyutları hesapla
    width_tiles = (max_x - min_x) + 1
    height_tiles = (max_z - min_z) + 1
    
    final_image = Image.new('RGB', (width_tiles * TILE_SIZE, height_tiles * TILE_SIZE))

    # İstek listesini hazırla
    tile_coords = []
    for x in range(min_x, max_x + 1):
        for z in range(min_z, max_z + 1):
            tile_coords.append((x, z, WORLD_NAME, ZOOM_LEVEL))

    print(f"🚀 Hızlı indirme başlatılıyor (Toplam {len(tile_coords)} parça)...")

    # Çoklu iş parçacığı ile hızlı ve güvenli indirme (Çökme yapmaz)
    with ThreadPoolExecutor(max_workers=16) as executor:
        futures = {executor.submit(download_single_tile, coord): coord for coord in tile_coords}
        
        for future in as_completed(futures):
            x, z, tile_img = future.result()
            if tile_img:
                # Konum hesaplama
                paste_x = (x - min_x) * TILE_SIZE
                paste_z = (z - min_z) * TILE_SIZE
                
                final_image.paste(tile_img, (paste_x, paste_z))
                print(f"İndiriliyor: {x}, {z}")

    # Sonucu orijinal formatta kaydet
    output_filename = f"minecraft_full_map_{WORLD_NAME}_z{ZOOM_LEVEL}.png"
    final_image.save(output_filename, "PNG")
    print(f"✅ İşlem tamamlandı! Harita '{output_filename}' olarak kaydedildi.")

if __name__ == "__main__":
    download_full_map()