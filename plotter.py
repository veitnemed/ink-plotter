"""Offline Cyrillic single-line SVG plotter and optional Tk glyph editor."""

import argparse
import json
import math
from pathlib import Path
import unicodedata
import xml.etree.ElementTree as ET

from glyphs_data import demo_glyphs

DEMO_TEXT = "Привет, мир!\nСъешь ещё этих мягких французских булок, да выпей чаю."
SVG = "http://www.w3.org/2000/svg"
MAX_POINTS = 20_000


def read_glyphs(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("glyphs"), dict):
        raise ValueError("Ожидается JSON с version: 1 и объектом glyphs.")
    glyphs = {}
    for char, strokes in data["glyphs"].items():
        if len(char) != 1 or not char.isprintable() or char.isspace() or not isinstance(strokes, list) or not strokes:
            raise ValueError(f"Неверная буква или список штрихов: {char!r}.")
        count = 0
        for stroke in strokes:
            if not isinstance(stroke, list) or len(stroke) < 2:
                raise ValueError(f"{char!r}: штрих должен содержать хотя бы две точки.")
            count += len(stroke)
            if count > MAX_POINTS:
                raise ValueError(f"{char!r}: слишком много точек.")
            for point in stroke:
                if (not isinstance(point, list) or len(point) != 2
                        or any(type(v) not in (int, float) or not 0 <= v <= 10 for v in point)):
                    raise ValueError(f"{char!r}: точка должна содержать две координаты от 0 до 10.")
            if all(point == stroke[0] for point in stroke):
                raise ValueError(f"{char!r}: штрих не должен быть нулевой длины.")
        glyphs[char] = strokes
    return glyphs


def wrap_text(text, cols):
    for paragraph in text.split("\n"):
        words = paragraph.split()
        line = ""
        for word in words:
            if line and len(line) + 1 + len(word) > cols:
                yield line
                line = ""
            while len(word) > cols:
                yield word[:cols]
                word = word[cols:]
            if word:
                line = f"{line} {word}" if line else word
        yield line


def make_svg(text, personal=None, width=210, height=297, margin=12, size=6):
    """Render text into physical millimetres; reject overflow rather than crop."""
    if not all(math.isfinite(x) and x > 0 for x in (width, height, margin, size)):
        raise ValueError("Размеры и поля должны быть положительными конечными числами.")
    usable = width - 2 * margin
    step = size * 1.25
    if usable < size or height - 2 * margin < size:
        raise ValueError("Рабочая область слишком мала для одной буквы.")
    cols = math.floor((usable - size) / step + 1e-9) + 1
    text = unicodedata.normalize("NFC", text)
    lines = list(wrap_text(text, cols))
    if not any(lines):
        raise ValueError("Нечего рисовать: текст пуст.")
    if size + (len(lines) - 1) * size * 1.65 > height - 2 * margin + 1e-9:
        raise ValueError("Текст не помещается. Уменьшите размер букв или сократите текст.")
    personal = personal or {}
    demo = demo_glyphs()
    unsupported = set()
    paths = []
    for row, line in enumerate(lines):
        for col, char in enumerate(line):
            if char == " ":
                continue
            strokes = personal.get(char) or demo.get(char.upper())
            if strokes is None:
                unsupported.add(char)
                continue
            for stroke in strokes:
                pts = [(margin + col * step + x * size / 10,
                        margin + row * size * 1.65 + y * size / 10) for x, y in stroke]
                paths.append("M " + " L ".join(f"{x:.4f},{y:.4f}" for x, y in pts))
    if unsupported:
        raise ValueError("Нет штрихов для символов: " + ", ".join(map(repr, sorted(unsupported))))
    root = ET.Element("svg", xmlns=SVG, width=f"{width:g}mm", height=f"{height:g}mm",
                      viewBox=f"0 0 {width:g} {height:g}")
    ET.SubElement(root, "title").text = "Штриховой текст"
    group = ET.SubElement(root, "g", fill="none", stroke="#172a46", attrib={
        "stroke-width": "0.28", "stroke-linecap": "round", "stroke-linejoin": "round"})
    for path in paths:
        ET.SubElement(group, "path", d=path)
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode", xml_declaration=True) + "\n"


def edit(path):
    import tkinter as tk
    from tkinter import messagebox, ttk

    personal = read_glyphs(path) if path.exists() else {}
    root = tk.Tk()
    root.title("Штриховой текст · редактор букв")
    frame = ttk.Frame(root, padding=15)
    frame.grid()
    char = tk.StringVar(value="А")
    loaded = "А"
    strokes = []
    active = None
    dirty = False
    status = tk.StringVar()
    ttk.Label(frame, text="Введите одну букву (регистр важен) и нажмите «Открыть».").grid(row=0, columnspan=5)
    ttk.Entry(frame, textvariable=char, width=6).grid(row=1, column=0)
    canvas = tk.Canvas(frame, width=382, height=382, background="#fffdf8", highlightthickness=0)
    canvas.grid(row=2, columnspan=5, pady=8)
    ttk.Label(frame, text="Один штрих — от нажатия до отпускания мыши или пера.").grid(row=3, columnspan=5)
    ttk.Label(frame, textvariable=status, wraplength=385).grid(row=4, columnspan=5)

    def repaint():
        canvas.delete("all")
        for i in range(11):
            p = 16 + 35 * i
            canvas.create_line(p, 16, p, 366, fill="#dcdfe4")
            canvas.create_line(16, p, 366, p, fill="#dcdfe4")
        for stroke in strokes:
            draw(stroke, "#172a46")
        status.set(f"Буква: {loaded!r} · штрихов: {len(strokes)}" + (" · не сохранено" if dirty else ""))

    def draw(stroke, color):
        if len(stroke) > 1:
            canvas.create_line(*(16 + 35 * z for point in stroke for z in point),
                               fill=color, width=2.6, capstyle=tk.ROUND, joinstyle=tk.ROUND)

    def point(event):
        return [round(min(10, max(0, (j - 16) / 35)), 3) for j in (event.x, event.y)]

    def start(event):
        nonlocal active
        if 16 <= event.x <= 366 and 16 <= event.y <= 366:
            active = [point(event)]

    def move(event):
        if active is None:
            return
        p = point(event)
        if sum(len(stroke) for stroke in strokes) + len(active) < MAX_POINTS and math.dist(p, active[-1]) >= .05:
            draw([active[-1], p], "#172a46")
            active.append(p)

    def finish(event):
        nonlocal active, dirty
        move(event)
        if active is not None and len(active) > 1:
            strokes.append(active)
            dirty = True
        active = None
        repaint()

    def open_char():
        nonlocal loaded, strokes, dirty
        selected = unicodedata.normalize("NFC", char.get())
        if len(selected) != 1 or not selected.isprintable() or selected.isspace():
            messagebox.showerror("Буква", "Укажите один печатный символ, не пробел.")
            return
        if dirty and not messagebox.askyesno("Не сохранено", "Отбросить изменения этой буквы?"):
            return
        loaded = selected
        strokes = [list(s) for s in personal.get(loaded, [])]
        dirty = False
        repaint()

    def undo():
        nonlocal dirty
        if strokes:
            strokes.pop()
            dirty = True
            repaint()

    def clear():
        nonlocal dirty
        strokes.clear()
        dirty = True
        repaint()

    def save():
        nonlocal dirty
        updated = dict(personal)
        if strokes:
            updated[loaded] = strokes
        else:
            updated.pop(loaded, None)
        temp = path.with_name(path.name + ".tmp")
        try:
            temp.write_text(json.dumps({"version": 1, "glyphs": updated},
                                       ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            temp.replace(path)
        except OSError as error:
            messagebox.showerror("Файл не сохранён", str(error))
            return
        personal.clear()
        personal.update(updated)
        dirty = False
        repaint()

    def quit_editor():
        if not dirty or messagebox.askyesno("Не сохранено", "Выйти без сохранения?"):
            root.destroy()

    for i, (label, callback) in enumerate((("Открыть", open_char), ("Отменить", undo),
                                          ("Очистить", clear), ("Сохранить", save)), start=1):
        ttk.Button(frame, text=label, command=callback).grid(row=1, column=i)
    canvas.bind("<Button-1>", start)
    canvas.bind("<B1-Motion>", move)
    canvas.bind("<ButtonRelease-1>", finish)
    root.protocol("WM_DELETE_WINDOW", quit_editor)
    open_char()
    root.mainloop()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Штриховой текст: локальный экспорт SVG.")
    commands = parser.add_subparsers(dest="command", required=True)
    render = commands.add_parser("render", help="Создать SVG")
    source = render.add_mutually_exclusive_group(required=True)
    source.add_argument("--demo", action="store_true", help="Встроенный русский пример")
    source.add_argument("--text", help="Строка текста")
    source.add_argument("--input", type=Path, help="Текстовый файл UTF-8")
    render.add_argument("--glyphs", type=Path, help="JSON личных букв")
    render.add_argument("-o", "--output", type=Path, required=True, help="Выходной SVG")
    for name, default in (("width", 210), ("height", 297), ("margin", 12), ("size", 6)):
        render.add_argument(f"--{name}", default=default, type=float)
    editor = commands.add_parser("edit", help="Нарисовать свой набор букв")
    editor.add_argument("--glyphs", required=True, type=Path, help="JSON личных букв")
    args = parser.parse_args(argv)
    try:
        if args.command == "edit":
            try:
                edit(args.glyphs)
            except ImportError as error:
                raise ValueError("Редактору нужен Tkinter из стандартной библиотеки Python.") from error
            except Exception as error:
                if type(error).__name__ != "TclError":
                    raise
                raise ValueError(f"Не удалось открыть окно Tk: {error}") from error
        else:
            text = DEMO_TEXT if args.demo else args.input.read_text(encoding="utf-8-sig") if args.input else args.text
            svg = make_svg(text, read_glyphs(args.glyphs) if args.glyphs else None,
                           args.width, args.height, args.margin, args.size)
            if args.output.suffix.lower() != ".svg":
                raise ValueError("Имя выходного файла должно заканчиваться на .svg.")
            if (args.input and args.input.resolve() == args.output.resolve()) or (args.glyphs and args.glyphs.resolve() == args.output.resolve()):
                raise ValueError("Выходной файл совпадает с входным.")
            args.output.write_text(svg, encoding="utf-8")
            print(f"SVG сохранён: {args.output}")
    except (OSError, UnicodeError, ValueError) as error:
        parser.exit(2, f"Ошибка: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
