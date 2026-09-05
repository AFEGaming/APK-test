[app]
# Uygulamanızın adı ve paket bilgileri
title = MyPythonApp
package.name = mypythonapp
package.domain = org.test

# Ana kod dosyasının konumu (bulunduğu dizin)
source.dir = .

# Dahil edilecek dosya uzantıları
source.include_exts = py,png,jpg,kv,atlas

# Uygulamanın versiyonu
version = 0.1

# GEREKLİ KÜTÜPHANELER: Kivy kullanıyorsanız burası aynen kalmalı.
# Başka kütüphane varsa virgül koyup eklemelisiniz (örn: kivy,requests)
requirements = python3,kivy

# Ekran yönü (landscape, portrait veya all)
orientation = portrait

# Android izinleri ve SDK Ayarları (Docker çökmesini önleyen kritik ayarlar)
android.accept_sdk_license = True
android.archs = armeabi-v7a, arm64-v8a
android.allow_backup = True

[buildozer]
# Log seviyesi (Hata ayıklama için)
log_level = 2
warn_on_root = 1
