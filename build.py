#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сборка «Чудесных дней» (Subarashiki Hibi) для Nintendo Switch.

Берёт Android-порт игры (APK) или уже распакованную папку game, накладывает
изменения для Switch из папки patch/ и собирает:
  * .nro — для Homebrew Menu (папка switch/ на SD-карту);
  * .nsp — устанавливаемую игру для главного экрана (нужны prod.keys).

Движок (Ren'Py 8.5.3 для Switch) скачивается из релизов RenpySwitch,
версия записана в engine.txt.

Примеры:
  python build.py                  .nro из единственного APK рядом со скриптом
  python build.py --nsp            .nro и .nsp
  python build.py --apk игра.apk --nsp
  python build.py --game путь\\к\\switch\\subahibi\\game --nsp
"""

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import urllib.request

# --- Настройки порта --------------------------------------------------------

GAME_NAME = "subahibi"                  # папка на SD-карте; из неё же title id NSP
TITLE = "Чудесные дни"                  # название на главном экране / в Homebrew Menu
AUTHOR = "Innocence translations, VienDesu!"   # издатель в меню
PORT_REVISION = "2"                     # версия Switch-порта: «<версия APK>-sw<это>»
PREPARE_VERSION = 2                     # вид распаковки (см. prepare_game)
ENGINE_REPO = "LunkezB/RenpySwitch"

# ---------------------------------------------------------------------------

HERE = os.path.dirname(os.path.abspath(__file__))
PATCH_DIR = os.path.join(HERE, "patch")
EXE = ".exe" if os.name == "nt" else ""
ENGINE_FILES = ("renpy-switch.nro", "apk2switch.py", "hacbrewpack" + EXE)


def say(*args):
    print(*args)
    sys.stdout.flush()


def fail(msg):
    say("")
    say("ОШИБКА: " + msg)
    sys.exit(1)


# --- Движок -----------------------------------------------------------------

def engine_tag():
    with open(os.path.join(HERE, "engine.txt"), encoding="utf-8") as f:
        return f.read().strip()


def download(url, dst):
    tmp = dst + ".part"
    try:
        with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as out:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if total:
                    sys.stdout.write("\r  {} {:3d}%".format(os.path.basename(dst), done * 100 // total))
                    sys.stdout.flush()
        sys.stdout.write("\n")
    except Exception as e:
        if os.path.exists(tmp):
            os.remove(tmp)
        fail("не удалось скачать {}\n  {}\nСкачайте файлы релиза вручную и укажите папку: --engine ПАПКА".format(url, e))
    os.replace(tmp, dst)


def get_engine(args, need_hbp):
    """Папка с renpy-switch.nro, apk2switch.py и hacbrewpack."""
    if args.engine:
        d = os.path.abspath(args.engine)
    else:
        tag = engine_tag()
        d = os.path.join(HERE, "engine", tag)
        os.makedirs(d, exist_ok=True)
        missing = [n for n in ENGINE_FILES
                   if (need_hbp or not n.startswith("hacbrewpack")) and not os.path.isfile(os.path.join(d, n))]
        if missing:
            say("Скачиваю движок {} ...".format(tag))
        for name in missing:
            download("https://github.com/{}/releases/download/{}/{}".format(ENGINE_REPO, tag, name),
                     os.path.join(d, name))
            if name.startswith("hacbrewpack") and os.name != "nt":
                os.chmod(os.path.join(d, name), 0o755)
    for name in ENGINE_FILES:
        if name.startswith("hacbrewpack") and not need_hbp:
            continue
        if not os.path.isfile(os.path.join(d, name)):
            fail("в папке движка нет {}: {}".format(name, d))
    return d


def load_apk2switch(engine_dir):
    spec = importlib.util.spec_from_file_location("apk2switch", os.path.join(engine_dir, "apk2switch.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_apk2switch(engine_dir, *argv):
    cmd = [sys.executable, os.path.join(engine_dir, "apk2switch.py")] + list(argv)
    if subprocess.call(cmd) != 0:
        fail("apk2switch.py завершился с ошибкой (см. выше).")


# --- Игра: распаковка и изменения для Switch ----------------------------------

class Game(object):
    """
    Файлы игры для patch/assets.py: читает и обычные файлы, и файлы внутри
    .rpa-архивов; пишет обычные файлы (они важнее файлов из архивов, так что
    так можно заменить любую картинку игры).
    """

    def __init__(self, a2s, game_dir, apk, keep_original=None):
        self.a2s = a2s
        self.dir = game_dir
        self.apk = apk              # apk2switch.ApkInfo или None
        self.written = []
        self._index = None
        self._keep_original = keep_original

    def _archives(self):
        if self._index is None:
            self._index = {}
            for fn in sorted(os.listdir(self.dir)):
                if fn.lower().endswith(".rpa"):
                    path = os.path.join(self.dir, fn)
                    for name, entry in self.a2s.read_rpa_index(path).items():
                        self._index.setdefault(name, (path, entry[0]))
        return self._index

    def path(self, rel):
        return os.path.join(self.dir, *rel.split("/"))

    def exists(self, rel):
        return os.path.isfile(self.path(rel)) or rel in self._archives()

    def read(self, rel):
        if os.path.isfile(self.path(rel)):
            with open(self.path(rel), "rb") as f:
                return f.read()
        if rel in self._archives():
            path, entry = self._archives()[rel]
            return self.a2s.read_rpa_file(path, entry)
        raise KeyError("в игре нет файла " + rel)

    def files(self):
        """Все файлы игры (относительные пути через /)."""
        names = set(self._archives())
        for root, _dirs, files in os.walk(self.dir):
            for fn in files:
                names.add(os.path.relpath(os.path.join(root, fn), self.dir).replace(os.sep, "/"))
        return sorted(names)

    def write(self, rel, data):
        if self._keep_original:
            self._keep_original(rel)
        p = self.path(rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)
        self.written.append(rel)


def file_id(path):
    st = os.stat(path)
    return [os.path.abspath(path), st.st_size, int(st.st_mtime)]


def patch_files():
    """[(путь в игре, путь в patch/game)] — файлы, которые кладутся в игру как есть."""
    src = os.path.join(PATCH_DIR, "game")
    out = []
    for root, _dirs, files in os.walk(src):
        for fn in files:
            if fn.endswith((".rpyc", ".pyc")) or fn.startswith("."):
                continue
            full = os.path.join(root, fn)
            out.append((os.path.relpath(full, src).replace(os.sep, "/"), full))
    return sorted(out)


def prepare_game(args, a2s, engine_dir, out_dir, game_dir, apk_path):
    stamp_path = os.path.join(out_dir, "build-state.json")
    backup_dir = os.path.join(out_dir, "originals")
    try:
        with open(stamp_path, encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, ValueError):
        state = {}

    # Картинки игры — AVIF в файлах .webp: Switch их не декодирует, поэтому
    # при распаковке они переводятся в WebP (--convert-avif). "prepare" в
    # build-state.json: распаковки старого вида делаются заново.
    source = file_id(apk_path) if apk_path else [os.path.abspath(args.game)]
    if state.get("prepare") != PREPARE_VERSION:
        state["source"] = None
    if args.clean or state.get("source") != source or not os.path.isdir(game_dir):
        for d in (game_dir, backup_dir):
            if os.path.isdir(d):
                shutil.rmtree(d)
        state = {}
        if apk_path:
            say("Распаковываю игру из APK ...")
            run_apk2switch(engine_dir, apk_path, "-o", out_dir, "--name", GAME_NAME, "--pack", "--force",
                           "--convert-avif")
        else:
            say("Копирую игру из {} ...".format(args.game))
            shutil.copytree(args.game, game_dir)
            packed = any(f.startswith("switch") and f.endswith(".rpa") for f in os.listdir(game_dir))
            loose = [os.path.relpath(os.path.join(r, f), game_dir).replace(os.sep, "/")
                     for r, _d, fs in os.walk(game_dir) for f in fs]
            if not packed and any(not a2s.keep_loose(rel) for rel in loose):
                run_apk2switch(engine_dir, game_dir, "--pack", "--convert-avif")
        state["source"] = source
        state["prepare"] = PREPARE_VERSION
    else:
        say("Игра уже распакована, накладываю изменения заново.")

    # Откатываем прошлое наложение: убираем добавленные файлы (и их .rpyc)
    # и возвращаем оригиналы, которые были заменены.
    for rel in state.get("added", []):
        p = os.path.join(game_dir, *rel.split("/"))
        for q in (p, p + "c" if p.endswith(".rpy") else None):
            if q and os.path.isfile(q):
                os.remove(q)
    for rel in state.get("replaced", []):
        src = os.path.join(backup_dir, *rel.split("/"))
        if os.path.isfile(src):
            shutil.copyfile(src, os.path.join(game_dir, *rel.split("/")))

    def keep_original(rel):
        """Сохраняет оригинальный файл игры перед заменой."""
        dst = os.path.join(game_dir, *rel.split("/"))
        if os.path.isfile(dst) and rel not in replaced:
            b = os.path.join(backup_dir, *rel.split("/"))
            if not os.path.isfile(b):
                os.makedirs(os.path.dirname(b), exist_ok=True)
                shutil.copyfile(dst, b)
            replaced.append(rel)

    replaced = list(state.get("replaced", []))
    added = []
    for rel, src in patch_files():
        keep_original(rel)
        dst = os.path.join(game_dir, *rel.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)
        added.append(rel)
    if added:
        say("Изменения для Switch: {} файл(ов) из patch/game.".format(len(added)))

    apk = a2s.ApkInfo(apk_path) if apk_path else None
    assets = os.path.join(PATCH_DIR, "assets.py")
    if os.path.isfile(assets):
        spec = importlib.util.spec_from_file_location("subahibi_assets", assets)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if hasattr(mod, "apply"):
            game = Game(a2s, game_dir, apk, keep_original)
            mod.apply(game)
            added += game.written
            if game.written:
                say("patch/assets.py: создано файлов: {}.".format(len(game.written)))

    # Оригиналы, которые уже не заменяются, остаются на месте (их вернули выше).
    state["added"] = sorted(set(added) - set(replaced))
    state["replaced"] = sorted(r for r in set(replaced) if r in added)
    with open(stamp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    return apk


# --- Иконка и версия ---------------------------------------------------------

def make_icon(apk, out_dir):
    """PNG иконки: patch/icon.png, иначе иконка из APK. None — пусть решает apk2switch."""
    custom = os.path.join(PATCH_DIR, "icon.png")
    if os.path.isfile(custom):
        return custom
    if apk is None:
        return None
    try:
        im = apk.icon()
    except Exception:
        im = None
    if im is None:
        return None
    path = os.path.join(out_dir, "icon.png")
    im.save(path)
    return path


def find_keys(explicit):
    if explicit:
        if not os.path.isfile(explicit):
            fail("нет файла ключей: " + explicit)
        return os.path.abspath(explicit)
    for p in (os.path.join(HERE, "prod.keys"), os.path.join(os.getcwd(), "prod.keys"),
              os.path.join(os.path.expanduser("~"), ".switch", "prod.keys")):
        if os.path.isfile(p):
            return p
    fail("для NSP нужен prod.keys с вашей консоли (Lockpick_RCM).\n"
         "Положите его рядом с build.py или укажите: --keys ПУТЬ")


def find_apk(args):
    if args.apk:
        if not os.path.isfile(args.apk):
            fail("нет файла " + args.apk)
        return os.path.abspath(args.apk)
    found = []
    for d in (HERE, os.getcwd()):
        for fn in sorted(os.listdir(d)):
            p = os.path.abspath(os.path.join(d, fn))
            if fn.lower().endswith(".apk") and p not in found:
                found.append(p)
    if len(found) == 1:
        return found[0]
    if not found:
        fail("не найден APK игры. Положите его рядом с build.py или укажите --apk ФАЙЛ\n"
             "(или --game ПАПКА с уже распакованной игрой).")
    fail("несколько APK, укажите нужный: --apk ФАЙЛ\n  " + "\n  ".join(found))


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

    ap = argparse.ArgumentParser(description="Сборка «Чудесных дней» для Nintendo Switch (.nro / .nsp).")
    ap.add_argument("--nro", action="store_true", help="собрать .nro для Homebrew Menu (по умолчанию)")
    ap.add_argument("--nsp", action="store_true", help="собрать устанавливаемый .nsp (нужны prod.keys)")
    ap.add_argument("--apk", help="APK игры (по умолчанию — единственный .apk рядом с build.py)")
    ap.add_argument("--game", help="вместо APK: уже распакованная папка game")
    ap.add_argument("--out", default=os.path.join(HERE, "out"), help="папка результата (по умолчанию out/)")
    ap.add_argument("--keys", help="prod.keys для --nsp (по умолчанию рядом с build.py или в ~/.switch/)")
    ap.add_argument("--engine", help="папка с файлами движка вместо скачивания релиза из engine.txt")
    ap.add_argument("--clean", action="store_true", help="распаковать игру заново")
    args = ap.parse_args()

    if not (args.nro or args.nsp):
        args.nro = True
    if args.game and not os.path.isdir(args.game):
        fail("нет папки " + args.game)
    if args.game and os.path.isdir(os.path.join(args.game, "game")):
        args.game = os.path.join(args.game, "game")
    if args.game and os.path.abspath(args.game).startswith(os.path.abspath(args.out) + os.sep):
        fail("--game указывает внутрь папки результата ({}); укажите исходную папку игры.".format(args.out))

    try:
        from PIL import features
    except ImportError:
        fail("нужна библиотека Pillow (иконка, картинки): pip install --upgrade pillow")
    if not features.check("avif"):
        fail("нужна Pillow 11.2 или новее с поддержкой AVIF (картинки игры — AVIF):\n"
             "  pip install --upgrade pillow")

    apk_path = None if args.game else find_apk(args)
    keys = find_keys(args.keys) if args.nsp else None

    engine_dir = get_engine(args, need_hbp=args.nsp)
    a2s = load_apk2switch(engine_dir)

    out_dir = os.path.abspath(args.out)
    sd_dir = os.path.join(out_dir, "switch", GAME_NAME)
    game_dir = os.path.join(sd_dir, "game")
    os.makedirs(out_dir, exist_ok=True)

    apk = prepare_game(args, a2s, engine_dir, out_dir, game_dir, apk_path)

    version = (apk.version_name() if apk else None) or "1.0"
    version = "{}-sw{}".format(version, PORT_REVISION)[:15]
    icon = make_icon(apk, out_dir)

    cmd = [game_dir, "--nro", os.path.join(engine_dir, "renpy-switch.nro"), "--name", GAME_NAME,
           "--title", TITLE, "--author", AUTHOR, "--version", version]
    if icon:
        cmd += ["--icon", icon]
    if args.nsp:
        cmd += ["--nsp", "--keys", keys, "--hacbrewpack", os.path.join(engine_dir, "hacbrewpack" + EXE)]
    say("")
    say("Собираю {} ...".format(" и ".join(x for x, on in ((".nro", args.nro), (".nsp", args.nsp)) if on)))
    run_apk2switch(engine_dir, *cmd)

    if apk is not None:
        apk.zip.close()

    say("")
    say("=" * 70)
    say("Готово ({} {}).".format(TITLE, version))
    if args.nro:
        say("")
        say(".nro для Homebrew Menu: скопируйте папку")
        say("  " + os.path.join(out_dir, "switch"))
        say("в корень SD-карты (получится sdmc:/switch/{0}/{0}.nro и sdmc:/switch/{0}/game/).".format(GAME_NAME))
        say("Запуск: Homebrew Menu, открытый через игру с зажатой R.")
    if args.nsp:
        say("")
        say(".nsp: " + os.path.join(out_dir, GAME_NAME + ".nsp"))
        say("Установите через DBI / Tinfoil / Goldleaf (нужны sigpatches) и запускайте")
        say("с главного экрана. Папка game на карте для NSP не нужна.")
    say("")
    say("Сохранения в обоих случаях: sdmc:/switch/{}/save/".format(GAME_NAME))


if __name__ == "__main__":
    main()
