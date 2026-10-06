import unittest

from voice2dir import dsl


class ParseTests(unittest.TestCase):
    def test_simple_file(self):
        tree = dsl.parse("файл привет\nпривет мир\nконец файла\n")
        self.assertEqual(tree, {"привет": "привет мир\n"})

    def test_empty_file(self):
        tree = dsl.parse("файл пусто\nконец файла\n")
        self.assertEqual(tree, {"пусто": ""})

    def test_multiline_content_keeps_lines(self):
        tree = dsl.parse("файл список\nпервый\n\nтретий\nконец файла\n")
        self.assertEqual(tree, {"список": "первый\n\nтретий\n"})

    def test_nested_dirs_and_up(self):
        tree = dsl.parse(
            "каталог а\nкаталог б\nфайл в\nтекст\nконец файла\nвверх\nвверх\nфайл г\nок\nконец файла\n"
        )
        self.assertEqual(tree, {"а": {"б": {"в": "текст\n"}}, "г": "ок\n"})

    def test_end_dir_keyword(self):
        tree = dsl.parse("каталог а\nфайл б\nx\nконец файла\nконец каталога\nфайл в\ny\nконец файла\n")
        self.assertEqual(tree, {"а": {"б": "x\n"}, "в": "y\n"})

    def test_script(self):
        tree = dsl.parse("скрипт привет\nэхо привет\nконец файла\n")
        self.assertEqual(tree, {"привет": ["script", "эхо привет\n"]})

    def test_link(self):
        tree = dsl.parse("ссылка алиас на цель\n")
        self.assertEqual(tree, {"алиас": ["link", "цель"]})

    def test_link_with_spaces_in_target(self):
        tree = dsl.parse("ссылка я на мой файл\n")
        self.assertEqual(tree, {"я": ["link", "мой файл"]})

    def test_end_tree_stops_parsing(self):
        tree = dsl.parse("файл а\nx\nконец файла\nконец дерева\nчто угодно дальше\n")
        self.assertEqual(tree, {"а": "x\n"})

    def test_case_insensitive_keywords_but_verbatim_content(self):
        tree = dsl.parse("ФАЙЛ имя\nКаталог слово\nконец файла\n")
        self.assertEqual(tree, {"имя": "Каталог слово\n"})

    def test_unclosed_file_errors(self):
        with self.assertRaises(dsl.DslError) as ctx:
            dsl.parse("файл а\nсодержимое без конца\n")
        self.assertIn("не закрыт", str(ctx.exception))

    def test_up_on_top_level_errors(self):
        with self.assertRaises(dsl.DslError):
            dsl.parse("вверх\n")

    def test_slash_in_name_errors(self):
        with self.assertRaises(dsl.DslError):
            dsl.parse("каталог а/б\n")

    def test_dotdot_name_errors(self):
        with self.assertRaises(dsl.DslError):
            dsl.parse("файл ..\nконец файла\n")

    def test_link_without_target_errors(self):
        with self.assertRaises(dsl.DslError):
            dsl.parse("ссылка алиас\n")

    def test_unknown_line_errors(self):
        with self.assertRaises(dsl.DslError):
            dsl.parse("привет как дела\n")

    def test_unknown_line_lenient_skips(self):
        tree = dsl.parse("привет как дела\nфайл а\nx\nконец файла\n", lenient=True)
        self.assertEqual(tree, {"а": "x\n"})

    def test_content_may_contain_keywords(self):
        tree = dsl.parse("файл заметка\nкаталог это просто слово\nвверх тоже\nконец файла\n")
        self.assertEqual(tree, {"заметка": "каталог это просто слово\nвверх тоже\n"})


if __name__ == "__main__":
    unittest.main()
