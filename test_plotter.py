import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

from plotter import SVG, make_svg, read_glyphs, wrap_text

NS = {"svg": SVG}


class PlotterTests(unittest.TestCase):
    def test_all_russian_letters_both_cases(self):
        alphabet = "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ"
        for char in alphabet + alphabet.lower():
            with self.subTest(char=char):
                root = ET.fromstring(make_svg(char))
                self.assertIsNotNone(root.find(".//svg:path", NS))

    def test_strokes_are_separate_open_paths(self):
        root = ET.fromstring(make_svg("А"))
        paths = root.findall(".//svg:path", NS)
        self.assertEqual(len(paths), 2)
        self.assertTrue(all("Z" not in p.attrib["d"] and p.attrib["d"].startswith("M ") for p in paths))
        self.assertEqual(root.attrib["width"], "210mm")
        self.assertEqual(root.find("svg:g", NS).attrib["fill"], "none")

    def test_missing_char_and_overflow_are_reported(self):
        with self.assertRaisesRegex(ValueError, "Нет штрихов"):
            make_svg("Привет @")
        with self.assertRaisesRegex(ValueError, "не помещается"):
            make_svg("А\nА", height=31)

    def test_wrap_and_cyrillic_normalization(self):
        self.assertEqual(list(wrap_text("АБВГ ДЕ\n\nЖ", 2)), ["АБ", "ВГ", "ДЕ", "", "Ж"])
        self.assertEqual(make_svg("ё"), make_svg("е\u0308"))

    def test_editable_glyph_overrides_exact_character(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "glyphs.json"
            path.write_text(json.dumps({"version": 1, "glyphs": {"ё": [[[0, 0], [10, 10]]]}}),
                            encoding="utf-8")
            svg = make_svg("ёЁ", read_glyphs(path))
            root = ET.fromstring(svg)
            self.assertEqual(len(root.findall(".//svg:path", NS)), 5)
            self.assertEqual(root.find(".//svg:path", NS).attrib["d"], "M 12.0000,12.0000 L 18.0000,18.0000")
            for bad in (float("nan"), 11, True):
                path.write_text(json.dumps({"version": 1, "glyphs": {"ё": [[[0, 0], [bad, 10]]]}}),
                                encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "координаты"):
                    read_glyphs(path)

    def test_cli_offline_demo_and_bad_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "demo.svg"
            app = Path(__file__).with_name("plotter.py")
            command = [sys.executable, str(app), "render", "-o", str(out)]
            subprocess.run(command + ["--demo"], check=True, capture_output=True)
            root = ET.parse(out)
            self.assertGreater(len(root.findall(".//svg:path", NS)), 40)
            before = out.read_bytes()
            r = subprocess.run(command + ["--text", "@"], capture_output=True)
            self.assertEqual(r.returncode, 2)
            self.assertEqual(out.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
