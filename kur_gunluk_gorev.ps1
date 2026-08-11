<#
.SYNOPSIS
    Gün sonu portföy kaydını Windows Görev Zamanlayıcı'ya kurar.

.DESCRIPTION
    `otomatik_takip.py` her gün belirlenen saatte çalışıp portföyünün o günkü
    değerini `portfoy_gecmisi.xlsx` dosyasına yazar. Bu betik o işi Windows'a
    kaydeder; bilgisayarın o saatte kapalıysa, açıldığında ilk fırsatta
    çalışır (StartWhenAvailable).

    Betiğin kendisi yönetici hakkı istemez: görev yalnızca senin kullanıcı
    hesabın altında tanımlanır.

.PARAMETER Saat
    Çalışma saati, SS:DD biçiminde. Varsayılan 23:30.

.PARAMETER Kaldir
    Görevi siler.

.PARAMETER Dene
    Görevi kurmadan, kaydı bir kez şimdi çalıştırır.

.EXAMPLE
    .\kur_gunluk_gorev.ps1
    .\kur_gunluk_gorev.ps1 -Saat 18:00
    .\kur_gunluk_gorev.ps1 -Dene
    .\kur_gunluk_gorev.ps1 -Kaldir
#>

# NOT: Bu dosya UTF-8 BOM ile kaydedilmelidir. Windows PowerShell 5.1, BOM
# yoksa .ps1 dosyalarını sistemin ANSI kod sayfasıyla okur ve Türkçe harfler
# bozuk görünür ("Başarılı" → "BaÅŸarÄ±lÄ±"). Düzenleyip kaydederken
# kodlamayı "UTF-8 with BOM" olarak koru.

[CmdletBinding()]
param(
    [string]$Saat = "23:30",
    [switch]$Kaldir,
    [switch]$Dene
)

$ErrorActionPreference = "Stop"
$GorevAdi = "BorsaPortfoy-GunSonuKaydi"
$ProjeYolu = $PSScriptRoot
$Betik = Join-Path $ProjeYolu "otomatik_takip.py"
$LogDosya = "otomatik_takip.log"

function Yaz-Baslik($metin) { Write-Host "`n$metin" -ForegroundColor Cyan }

# --- Kaldırma ---------------------------------------------------------------
if ($Kaldir) {
    $mevcut = Get-ScheduledTask -TaskName $GorevAdi -ErrorAction SilentlyContinue
    if ($mevcut) {
        Unregister-ScheduledTask -TaskName $GorevAdi -Confirm:$false
        Write-Host "Görev silindi: $GorevAdi" -ForegroundColor Green
    } else {
        Write-Host "Kayıtlı böyle bir görev yok; yapacak bir şey kalmadı." -ForegroundColor Yellow
    }
    return
}

# --- Ön kontroller ----------------------------------------------------------
Yaz-Baslik "Ön kontroller"

if (-not (Test-Path $Betik)) {
    throw "otomatik_takip.py bulunamadı: $Betik`nBu betiği proje klasöründen çalıştır."
}
Write-Host "  proje klasörü : $ProjeYolu"

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { $python = Get-Command python3 -ErrorAction SilentlyContinue }
if (-not $python) {
    throw "Python bulunamadı. PATH üzerinde 'python' komutu çalışmıyor."
}
$PythonYolu = $python.Source
Write-Host "  python        : $PythonYolu"

if ($Saat -notmatch '^([01]?\d|2[0-3]):[0-5]\d$') {
    throw "Saat biçimi SS:DD olmalı (örn. 23:30). Verilen: $Saat"
}
Write-Host "  çalışma saati : $Saat"

# --- Deneme çalıştırması ----------------------------------------------------
if ($Dene) {
    Yaz-Baslik "Deneme çalıştırması (görev kurulmuyor)"
    Push-Location $ProjeYolu
    try {
        & $PythonYolu "otomatik_takip.py" "--log" $LogDosya
        $kod = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    switch ($kod) {
        0 { Write-Host "`nBaşarılı: kayıt yazıldı." -ForegroundColor Green }
        2 { Write-Host "`nDefterler boş; kaydedilecek pozisyon yok." -ForegroundColor Yellow }
        default { Write-Host "`nKaydedilemedi (çıkış kodu $kod). $LogDosya dosyasına bak." -ForegroundColor Red }
    }
    return
}

# --- Görevi kur -------------------------------------------------------------
Yaz-Baslik "Görev kuruluyor"

# Konsol penceresi her gün ekrana düşmesin diye powershell sarmalayıcısı
# kullanılır; çıktı zaten log dosyasına yazılıyor.
$icKomut = "& '$PythonYolu' otomatik_takip.py --log $LogDosya"
$argumanlar = "-NoProfile -WindowStyle Hidden -Command `"$icKomut`""

$eylem = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument $argumanlar -WorkingDirectory $ProjeYolu

$tetik = New-ScheduledTaskTrigger -Daily -At $Saat

# StartWhenAvailable: ev bilgisayarı o saatte kapalı olabilir; kaçırılan
# çalıştırma, makine açıldığında telafi edilir. Bu ayar olmadan kapalı
# geçen her gün geçmişte boşluk bırakır.
$ayarlar = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 15)

if (Get-ScheduledTask -TaskName $GorevAdi -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $GorevAdi -Confirm:$false
    Write-Host "  (eski görev değiştirildi)"
}

Register-ScheduledTask -TaskName $GorevAdi -Action $eylem -Trigger $tetik `
    -Settings $ayarlar -Description "Portföyün gün sonu değerini portfoy_gecmisi.xlsx dosyasına kaydeder." | Out-Null

Write-Host "`nKuruldu: $GorevAdi" -ForegroundColor Green
Write-Host @"

  Her gün $Saat'da çalışır. Bilgisayar kapalıysa açılınca telafi eder.
  Kayıtlar : portfoy_gecmisi.xlsx
  Günlük   : $LogDosya

  Kontrol  : Get-ScheduledTask -TaskName $GorevAdi
  Hemen çalıştır : Start-ScheduledTask -TaskName $GorevAdi
  Kaldır   : .\kur_gunluk_gorev.ps1 -Kaldir
"@
