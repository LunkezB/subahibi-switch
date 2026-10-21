#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Проверка сборки без настоящей игры (запускается в CI):

  python tests/smoke.py [--engine ПАПКА]

Делает поддельный APK с мини-игрой и собирает его копией репозитория:
.nro и .nsp (одноразовые ключи), наложение patch/, пересборку с откатом
прошлых изменений (удалённые из patch/ файлы исчезают, заменённые
оригиналы возвращаются).
"""

import argparse
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def fail(msg):
    print("FAIL: " + msg)
    sys.exit(1)


def make_apk(path):
    from PIL import Image
    png = io.BytesIO()
    Image.new("RGB", (64, 48), (30, 60, 200)).save(png, "PNG")
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("assets/x-game/x-script.rpy", 'label start:\n    "Тест."\n    return\n')
        z.writestr("assets/x-game/x-images/x-bg.png", png.getvalue())
        z.writestr("assets/x-game/x-gui/x-window_icon.png", png.getvalue())
        z.writestr("assets/x-script_version.txt", "(8, 5, 3)")
        z.writestr("assets/android-presplash.jpg", b"\xff\xd8\xff\xd9")


def build(work, *extra):
    cmd = [sys.executable, os.path.join(work, "build.py"), "--apk", os.path.join(work, "test.apk")] + list(extra)
    print("+ " + " ".join(cmd))
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    print(r.stdout[-3000:])
    if r.returncode != 0:
        fail("build.py exited with {}".format(r.returncode))
    return r.stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", help="local engine files instead of the release in engine.txt")
    args = ap.parse_args()

    work = tempfile.mkdtemp(prefix="subahibi-smoke-")
    for n in ("build.py", "engine.txt"):
        shutil.copy(os.path.join(REPO, n), work)
    shutil.copytree(os.path.join(REPO, "patch"), os.path.join(work, "patch"))
    if not args.engine and os.path.isdir(os.path.join(REPO, "engine")):
        shutil.copytree(os.path.join(REPO, "engine"), os.path.join(work, "engine"))
    make_apk(os.path.join(work, "test.apk"))
    with open(os.path.join(work, "test.keys"), "w") as f:
        f.write("header_key = {}\n".format(hashlib.sha256(b"h").hexdigest()))
        f.write("key_area_key_application_00 = {}\n".format(hashlib.md5(b"k").hexdigest()))

    extra = ["--keys", os.path.join(work, "test.keys")]
    if args.engine:
        extra += ["--engine", os.path.abspath(args.engine)]

    pgame = os.path.join(work, "patch", "game")
    os.makedirs(pgame, exist_ok=True)
    with open(os.path.join(pgame, "zz_smoke_added.rpy"), "w") as f:
        f.write("# smoke\n")
    with open(os.path.join(pgame, "script.rpy"), "w") as f:
        f.write('label start:\n    "Заменено."\n    return\n')

    build(work, "--nsp", *extra)

    out = os.path.join(work, "out")
    game = os.path.join(out, "switch", "subahibi", "game")
    for p in (os.path.join(out, "switch", "subahibi", "subahibi.nro"), os.path.join(out, "subahibi.nsp"),
              os.path.join(game, "switch00.rpa"), os.path.join(game, "zz_smoke_added.rpy"),
              os.path.join(game, "zz_switch_controls.rpy")):
        if not os.path.isfile(p):
            fail("missing " + p)
    with open(os.path.join(game, "script.rpy"), encoding="utf-8") as f:
        if "Заменено" not in f.read():
            fail("patch/game/script.rpy was not applied")

    # Пересборка без этих файлов: добавленный удаляется, оригинал возвращается.
    os.remove(os.path.join(pgame, "zz_smoke_added.rpy"))
    os.remove(os.path.join(pgame, "script.rpy"))
    log = build(work, *extra)
    if "уже распакована" not in log:
        fail("the game was unpacked again instead of reused")
    if os.path.exists(os.path.join(game, "zz_smoke_added.rpy")):
        fail("removed patch file is still in the game")
    with open(os.path.join(game, "script.rpy"), encoding="utf-8") as f:
        if "Тест." not in f.read():
            fail("original script.rpy was not restored")

    # Сборка из папки (--game) в другую папку результата.
    src = os.path.join(work, "copy", "game")
    shutil.copytree(game, src)
    cmd = [sys.executable, os.path.join(work, "build.py"), "--game", src, "--out", os.path.join(work, "out2")] + extra
    print("+ " + " ".join(cmd))
    if subprocess.call(cmd) != 0:
        fail("build.py --game failed")
    if not os.path.isfile(os.path.join(work, "out2", "switch", "subahibi", "subahibi.nro")):
        fail("--game: no .nro")

    shutil.rmtree(work, ignore_errors=True)
    print("OK: smoke test passed")


if __name__ == "__main__":
    main()
