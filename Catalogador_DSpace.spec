# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('core', 'core'), ('prompt_sistema.txt', '.')]
binaries = []
hiddenimports = ['pandas', 'PIL', 'openai', 'requests', 'dotenv', 'customtkinter', 're', 'shutil', 'datetime']
tmp_ret = collect_all('customtkinter')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


excludes = [
    'torch', 'torchvision', 'torchaudio',
    'cv2', 'opencv_python',
    'scipy', 'scipy.libs',
    'pyarrow', 'pyarrow.libs',
    'faiss', 'faiss_cpu', 'faiss_cpu.libs',
    'duckdb', '_duckdb',
    'transformers',
    'onnxruntime',
    'matplotlib',
    'pytest', 'IPython', 'ipykernel', 'jupyter', 'notebook',
    'tensorboard', 'tensorflow', 'keras',
    'sympy', 'llvmlite', 'numba', 'h5py'
]

a = Analysis(
    ['app_gui.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Catalogador_DSpace',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Catalogador_DSpace',
)
