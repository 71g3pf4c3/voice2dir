import unittest

from voice2dir import spoken_json


class NormalizeTests(unittest.TestCase):
    def test_quote_word_quote(self):
        self.assertEqual(spoken_json.normalize("кавычка а кавычка"), '"а"')

    def test_comma_and_dot_inside_string(self):
        text = "кавычка привет запятая мир точка кавычка"
        self.assertEqual(spoken_json.normalize(text), '"привет, мир."')

    def test_smart_bracket_inside_string_is_literal(self):
        text = "кавычка фигурная скобка кавычка"
        self.assertEqual(spoken_json.normalize(text), '"{"')

    def test_float_number(self):
        # "3 точка 14" -> 3.14: no space between a dot and digits
        self.assertEqual(spoken_json.normalize("3 точка 14"), "3.14")


class ParseTests(unittest.TestCase):
    def test_simple_object(self):
        text = ("фигурная скобка кавычка приветствие кавычка двоеточие "
                "кавычка привет мир кавычка закрывающая фигурная скобка")
        self.assertEqual(spoken_json.parse(text), {"приветствие": "привет мир"})

    def test_nested_smart_brackets(self):
        # bare "фигурная скобка" resolves by parser state: open where a
        # value is expected, close after a completed value
        text = ("фигурная скобка кавычка а кавычка двоеточие фигурная скобка "
                "кавычка бэ кавычка двоеточие кавычка це кавычка фигурная скобка "
                "фигурная скобка")
        self.assertEqual(spoken_json.parse(text), {"а": {"бэ": "це"}})

    def test_explicit_brackets_and_cyrillic_link_tag(self):
        text = ("открывающая фигурная скобка кавычка а кавычка двоеточие "
                "открывающая квадратная скобка кавычка ссылка кавычка запятая "
                "кавычка бэ кавычка закрывающая квадратная скобка "
                "закрывающая фигурная скобка")
        self.assertEqual(spoken_json.parse(text), {"а": ["link", "бэ"]})

    def test_cyrillic_script_tag_with_newline(self):
        text = ("фигурная скобка кавычка а кавычка двоеточие квадратная скобка "
                "кавычка скрипт кавычка запятая кавычка икс перевод строки "
                "кавычка закрывающая квадратная скобка закрывающая фигурная скобка")
        self.assertEqual(spoken_json.parse(text), {"а": ["script", "икс\n"]})

    def test_link_name_survives_tag_fixup(self):
        # "ссылка" as a plain file name is not a tag position
        text = ("фигурная скобка кавычка ссылка кавычка двоеточие кавычка цель "
                "кавычка закрывающая фигурная скобка")
        self.assertEqual(spoken_json.parse(text), {"ссылка": "цель"})

    def test_english_tag(self):
        text = ("фигурная скобка кавычка а кавычка двоеточие квадратная скобка "
                "кавычка link кавычка запятая кавычка бэ кавычка "
                "закрывающая квадратная скобка закрывающая фигурная скобка")
        self.assertEqual(spoken_json.parse(text), {"а": ["link", "бэ"]})

    def test_backslash_quote_escape(self):
        text = ("фигурная скобка кавычка а кавычка двоеточие кавычка "
                "бэкслэш кавычка кавычка закрывающая фигурная скобка")
        self.assertEqual(spoken_json.parse(text), {"а": '"'})

    def test_multiple_pairs(self):
        text = ("фигурная скобка кавычка дом кавычка двоеточие фигурная скобка "
                "кавычка ридми кавычка двоеточие кавычка привет запятая мир "
                "кавычка запятая кавычка бин кавычка двоеточие квадратная скобка "
                "кавычка ссылка кавычка запятая кавычка ридми кавычка "
                "закрывающая квадратная скобка фигурная скобка фигурная скобка")
        self.assertEqual(
            spoken_json.parse(text),
            {"дом": {"ридми": "привет, мир", "бин": ["link", "ридми"]}},
        )


class ParseErrorTests(unittest.TestCase):
    def test_root_not_object(self):
        with self.assertRaises(spoken_json.SpokenJsonError):
            spoken_json.parse("кавычка а кавычка")

    def test_bad_json(self):
        with self.assertRaises(spoken_json.SpokenJsonError):
            spoken_json.parse("фигурная скобка кавычка а кавычка")

    def test_scheme_violation(self):
        # valid JSON, invalid json2dir scheme: 1 is not a legal value
        text = ("фигурная скобка кавычка а кавычка двоеточие 1 "
                "закрывающая фигурная скобка")
        with self.assertRaises(spoken_json.SpokenJsonError):
            spoken_json.parse(text)


if __name__ == "__main__":
    unittest.main()
