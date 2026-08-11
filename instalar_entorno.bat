@echo off
echo ==============================================
echo Instalando entorno para Catalogador DSPACE...
echo ==============================================

echo.
echo Instalando dependencias de Python...
pip install -r requirements.txt

echo.
echo ==============================================
echo Entorno listo! Recuerda configurar tu .env
echo Ya puedes ejecutar: python catalogador_openai.py
echo ==============================================
pause
