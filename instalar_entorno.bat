@echo off
echo ==============================================
echo Instalando entorno para Catalogador DSPACE...
echo ==============================================

echo.
echo Instalando dependencias de Python...
pip install -r requirements.txt

if not exist "jdk" (
    echo.
    echo Descargando Java Portable para SAFBuilder...
    python -c "import urllib.request; import zipfile; import io; print('Descargando JDK... (~200MB)'); r = urllib.request.urlopen('https://aka.ms/download-jdk/microsoft-jdk-21.0.3-windows-x64.zip'); z = zipfile.ZipFile(io.BytesIO(r.read())); z.extractall('jdk'); print('JDK descargado y extraido!')"
) else (
    echo.
    echo Java Portable ya esta instalado.
)

echo.
echo ==============================================
echo Entorno listo! Recuerda configurar tu .env
echo Ya puedes ejecutar: python catalogador_openai.py
echo ==============================================
pause
