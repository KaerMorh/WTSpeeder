# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('icon.ico', '.'),
        ('sounds/beep_fast.wav', 'sounds'),
        ('sounds/beep_force_critical.wav', 'sounds'),
        ('FM/fm_data_db.csv', 'FM'),
        ('FM/fm_names_db.csv', 'FM'),
        ('FM/index.json', 'FM'),
        ('FM/versions/fm-20260918-054634-manual/fm_data_db.csv', 'FM/versions/fm-20260918-054634-manual'),
        ('FM/versions/fm-20260918-054634-manual/fm_names_db.csv', 'FM/versions/fm-20260918-054634-manual'),
        ('FM/versions/fm-20260918-054634-manual/manifest.json', 'FM/versions/fm-20260918-054634-manual'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['test_features'],  # !!! 关键：排除敏感模块 !!!
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='WTOverlay_Public',  # 输出文件名：WTOverlay_Public.exe
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico',
)
