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

from io import BytesIO

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont


# «Андроид версия» нарисована в картинках главного меню (её нет в
# скриптах). Стираем её и рисуем «Switch версия» шрифтом из игры.
OLD_TEXT = "Андроид версия"
NEW_TEXT = "Switch версия"
FONT = "fonts/PTSerif-400.ttf"

# Во сколько раз крупнее рисуем текст, чтобы после уменьшения края были
# гладкими.
SS = 4


def warn(msg):
    print("patch/assets.py: предупреждение: " + msg + " — пропускаю")


def load(game, path, mode):
    if not game.exists(path):
        warn("нет файла " + path)
        return None
    return Image.open(BytesIO(game.read(path))).convert(mode)


def save(game, path, im):
    out = BytesIO()
    if path.endswith(".webp"):
        im.save(out, "WEBP", quality=95, method=6)
    else:
        im.save(out, "PNG", optimize=True)
    game.write(path, out.getvalue())
    print("patch/assets.py: " + path + ": «" + OLD_TEXT + "» -> «" + NEW_TEXT + "»")


# --- надпись ---------------------------------------------------------------

def text_masks(font_data, size, text, bold, outline):
    """
    Маски надписи (заливка и обводка) в масштабе SS. bold — на сколько
    пикселей (в итоговом масштабе) утолщить буквы: в картинках шрифт жирнее,
    чем PT Serif Regular. Возвращает (fill, outline, baseline_y).
    """

    font = ImageFont.truetype(BytesIO(font_data), int(size * SS))
    pad = int((bold + outline + 4) * SS)
    l, t, r, b = font.getbbox(text)
    w, h = r - l + 2 * pad, b - t + 2 * pad
    origin = (pad - l, pad - t)

    def mask(stroke):
        m = Image.new("L", (w, h), 0)
        ImageDraw.Draw(m).text(origin, text, font=font, fill=255,
                               stroke_width=int(round(stroke * SS)), stroke_fill=255)
        return m

    ascent = font.getmetrics()[0]
    return mask(bold), mask(bold + outline), origin[1] + ascent


def ink_height(font_data, size, bold, outline):
    """Высота старой надписи (с обводкой), если нарисовать её этим шрифтом."""
    _, o, _ = text_masks(font_data, size, OLD_TEXT, bold, outline)
    l, t, r, b = o.getbbox()
    return (b - t) / SS


def render_label(font_data, height, style):
    """
    «Switch версия» в стиле style. Размер шрифта подбирается так, чтобы
    старая надпись этим шрифтом была высотой height (вместе с обводкой).
    Возвращает картинку RGBA и смещение от левого верхнего угла её «чернил»
    (без тени) до левого верхнего угла картинки.
    """

    bold, outline = style["bold"], style["outline"]

    size = height
    for _ in range(4):
        size *= height / ink_height(font_data, size, bold, outline)

    fill, edge, _ = text_masks(font_data, size, NEW_TEXT, bold, outline)
    w, h = fill.size

    layers = Image.new("RGBA", (w, h), (0, 0, 0, 0))

    if style.get("shadow"):
        color, alpha, radius, dx, dy = style["shadow"]
        a = edge.filter(ImageFilter.GaussianBlur(radius * SS)).point(lambda v: v * alpha // 255)
        moved = Image.new("L", (w, h), 0)
        moved.paste(a, (int(dx * SS), int(dy * SS)))
        shadow = Image.new("RGBA", (w, h), color)
        shadow.putalpha(moved)
        layers.alpha_composite(shadow)

    outline_layer = Image.new("RGBA", (w, h), style["outline_color"])
    outline_layer.putalpha(edge)
    layers.alpha_composite(outline_layer)

    top, bottom = style["fill"]
    grad = Image.linear_gradient("L").resize((w, h))
    fill_layer = Image.composite(Image.new("RGBA", (w, h), bottom),
                                 Image.new("RGBA", (w, h), top), grad)
    fill_layer.putalpha(fill)
    layers.alpha_composite(fill_layer)

    l, t, r, b = edge.getbbox()
    layers = layers.resize((w // SS, h // SS), Image.LANCZOS)
    return layers, (l / SS, t / SS, r / SS, b / SS)


def draw_label(im, font_data, box, style):
    """Рисует новую надпись по центру места старой (box — её «чернила»)."""

    x0, y0, x1, y1 = box
    label, (l, t, r, b) = render_label(font_data, y1 - y0, style)
    cx = (x0 + x1) / 2.0
    pos = (int(round(cx - (l + r) / 2.0)), int(round(y0 - t)))
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    layer.alpha_composite(label, (max(pos[0], 0), max(pos[1], 0)),
                          (max(-pos[0], 0), max(-pos[1], 0)))
    return Image.alpha_composite(im.convert("RGBA"), layer)


# --- стирание --------------------------------------------------------------

def text_mask(im, box, grow):
    """Маска старой надписи: светлые буквы в box, расширенные на grow."""
    r, g, b = im.convert("RGB").split()
    light = ImageChops.darker(ImageChops.darker(r, g), b).point(lambda v: 255 if v > 200 else 0)
    mask = Image.new("L", im.size, 0)
    mask.paste(light.crop(box), box[:2])
    return mask.filter(ImageFilter.MaxFilter(2 * grow + 1))


def pyramid_fill(rgba):
    """
    Заполняет прозрачные пиксели по соседним: Pillow уменьшает RGBA с
    учётом прозрачности, так что на каждом уровне пирамиды дыра меньше, а
    её цвет — среднее известных пикселей вокруг.
    """

    w, h = rgba.size
    if w <= 2 or h <= 2:
        out = rgba.resize((1, 1), Image.BOX).resize((w, h))
        out.putalpha(255)
        return out
    small = pyramid_fill(rgba.resize(((w + 1) // 2, (h + 1) // 2), Image.BOX))
    out = small.resize((w, h), Image.BICUBIC)
    out.alpha_composite(rgba)
    return out


def blur_fill(im, mask, margin=48):
    """Закрашивает дыру (mask = 255) по соседним пикселям."""

    im = im.convert("RGB")
    l, t, r, b = mask.getbbox()
    area = (max(l - margin, 0), max(t - margin, 0),
            min(r + margin, im.width), min(b + margin, im.height))
    piece = im.crop(area).convert("RGBA")
    piece.putalpha(ImageChops.invert(mask.crop(area)))
    filled = im.copy()
    filled.paste(pyramid_fill(piece).convert("RGB"), area[:2])
    return Image.composite(filled, im, mask.filter(ImageFilter.GaussianBlur(1)))


def matched_patch(src, ref, box, mask):
    """
    Кусок src (та же картинка с другой цветокоррекцией), подогнанный по
    цвету к ref: линейная подгонка каждого канала по кольцу вокруг дыры.
    """

    ring = mask.filter(ImageFilter.MaxFilter(15))
    ring = ImageChops.subtract(ring, mask)
    x0, y0, x1, y1 = box
    out = []
    for s, r in zip(src.convert("RGB").split(), ref.convert("RGB").split()):
        xs, ys = [], []
        for y in range(y0, y1):
            for x in range(x0, x1):
                if ring.getpixel((x, y)):
                    xs.append(s.getpixel((x, y)))
                    ys.append(r.getpixel((x, y)))
        n = float(len(xs))
        mx, my = sum(xs) / n, sum(ys) / n
        var = sum((v - mx) ** 2 for v in xs)
        k = sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / var if var else 1.0
        c = my - k * mx
        out.append(s.point(lambda v: max(0, min(255, int(k * v + c)))))
    return Image.merge("RGB", out)


# --- картинки --------------------------------------------------------------

# Дневной титульный экран: тёмная обводка, белые буквы.
TITLE_STYLE = dict(bold=0.5, outline=2.0, fill=("#ffffff", "#e9e9ee"),
                   outline_color="#36363c", shadow=("#000000", 70, 2.5, 1, 1.5))
# Ночной логотип (на прозрачном фоне, рисуется поверх неба).
LOGO_STYLE = dict(bold=1.2, outline=4.0, fill=("#ffffff", "#e6e6ec"),
                  outline_color="#26262c", shadow=("#000000", 110, 5, 2, 4))
# Титульный экран 1.5 (пианино): белые буквы, тонкая тёмная обводка.
TITLE15_STYLE = dict(bold=0.3, outline=1.2, fill=("#ffffff", "#ececf0"),
                     outline_color="#1e1e26", shadow=("#000000", 120, 2, 1, 1.5))


def fix_title(game, font_data):
    """gui/subahibi/title_android.png: фон без надписи есть в title.png."""

    path, clean_path = "gui/subahibi/title_android.png", "gui/subahibi/title.png"
    im = load(game, path, "RGB")
    clean = load(game, clean_path, "RGB")
    if im is None or clean is None:
        return
    if im.size != clean.size:
        warn(clean_path + " другого размера")
        return

    diff = ImageChops.difference(im, clean).convert("L").point(lambda v: 255 if v > 24 else 0)
    box = diff.getbbox()
    if box is None:
        warn("в " + path + " нет надписи")
        return

    hole = Image.new("L", im.size, 0)
    hole.paste(255, (box[0] - 6, box[1] - 6, box[2] + 6, box[3] + 6))
    im = Image.composite(clean, im, hole.filter(ImageFilter.GaussianBlur(2)))

    save(game, path, draw_label(im, font_data, box, TITLE_STYLE).convert("RGB"))


def fix_logo(game, font_data):
    """
    gui/subahibi/logo_android.png: логотип на прозрачном фоне, надпись —
    отдельная строка под ним.
    """

    path = "gui/subahibi/logo_android.png"
    im = load(game, path, "RGBA")
    if im is None:
        return

    # Ищем строку надписи: первую непрозрачную полосу после пустых строк
    # под логотипом.
    alpha = im.split()[3].point(lambda v: 255 if v > 60 else 0)
    rows = [alpha.crop((0, y, im.width, y + 1)).getbbox() is not None for y in range(im.height)]
    bands, start = [], None
    for y, filled in enumerate(rows + [False]):
        if filled and start is None:
            start = y
        elif not filled and start is not None:
            bands.append((start, y))
            start = None
    if len(bands) < 2:
        warn("в " + path + " не нашлась строка надписи")
        return

    y0, y1 = bands[-1]
    x0, _, x1, _ = alpha.crop((0, y0, im.width, y1)).getbbox()
    box = (x0, y0, x1, y1)

    # Стираем всё ниже логотипа (там только надпись и её тень).
    gap = (bands[-2][1] + y0) // 2
    cleared = im.copy()
    cleared.paste((0, 0, 0, 0), (0, gap, im.width, im.height))

    save(game, path, draw_label(cleared, font_data, box, LOGO_STYLE))


def find_title15_box(im):
    """Надпись в title15: светлые буквы под логотипом справа."""
    w, h = im.size
    search = (int(w * .62), int(h * .415), int(w * .92), int(h * .475))
    mask = text_mask(im, search, 0)
    return mask.getbbox()


def fix_title15(game, font_data):
    """
    gui/subahibi/title15_0.webp и title15_1.webp. Для вечерней картинки
    фон без надписи есть в about_bg.webp (с другой цветокоррекцией),
    ночную закрашиваем по соседним пикселям — новая надпись почти целиком
    закрывает это место.
    """

    about = None
    if game.exists("gui/subahibi/about_bg.webp"):
        about = load(game, "gui/subahibi/about_bg.webp", "RGB")

    for i in (0, 1):
        path = "gui/subahibi/title15_%d.webp" % i
        im = load(game, path, "RGB")
        if im is None:
            continue

        box = find_title15_box(im)
        if box is None:
            warn("в " + path + " не нашлась надпись")
            continue

        pad = (box[0] - 4, box[1] - 4, box[2] + 4, box[3] + 4)
        hole = text_mask(im, pad, 3)

        if i == 0 and about is not None and about.size == im.size:
            area = (pad[0] - 12, pad[1] - 12, pad[2] + 12, pad[3] + 12)
            patch = matched_patch(about, im, area, hole)
            filled = Image.composite(patch, im, hole.filter(ImageFilter.GaussianBlur(1.5)))
        else:
            filled = blur_fill(im, hole)

        save(game, path, draw_label(filled, font_data, box, TITLE15_STYLE).convert("RGB"))


def apply(game):
    if not game.exists(FONT):
        warn("нет шрифта " + FONT + ", надпись «" + OLD_TEXT + "» не заменена")
        return
    font_data = game.read(FONT)

    fix_title(game, font_data)
    fix_logo(game, font_data)
    fix_title15(game, font_data)
