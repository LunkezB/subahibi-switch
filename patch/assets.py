# -*- coding: utf-8 -*-
"""
Файлы игры, изменённые для Switch, которые делаются при сборке из файлов
самой игры (например, картинка главного меню с другой надписью).

Так в репозитории нет ни одного файла игры: здесь только код, который
изменяет файлы из вашего APK.

build.py вызывает apply(game) после распаковки игры. game умеет:

  game.read(path) -> bytes     файл игры: обычный или из .rpa-архива
                               (пути как в Ren'Py: "gui/main_menu.png")
  game.exists(path) -> bool
  game.files() -> [path]       все файлы игры
  game.write(path, data)       записать файл в игру. Обычный файл важнее
                               файла с тем же именем в .rpa-архиве, так
                               что так заменяется любая картинка игры.
                               Заменённые оригиналы build.py сохраняет и
                               возвращает при следующей сборке.
  game.apk                     сведения об APK (или None при --game)

Картинки обрабатываются через Pillow:

  from io import BytesIO
  from PIL import Image
  im = Image.open(BytesIO(game.read("gui/logo.png"))).convert("RGBA")
  ...
  out = BytesIO(); im.save(out, "PNG"); game.write("gui/logo.png", out.getvalue())

Если нужного файла в игре нет (другая версия APK), лучше напечатать
предупреждение и пропустить этот шаг, чем падать.
"""


def apply(game):
    pass
