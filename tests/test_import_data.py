"""Tests for import_data.py"""
import json
import os
import pytest
import tempfile
from pathlib import Path

from import_data import (
    load_text_files, load_csv, load_json, load_jsonl,
    format_for_label_studio, LOADERS,
)


@pytest.fixture
def tmp_data(tmp_path):
    """Create a temp directory with sample data files."""
    # Text files
    (tmp_path / "doc1.txt").write_text("Hello world.", encoding='utf-8')
    (tmp_path / "doc2.txt").write_text("Second document.\nWith two lines.", encoding='utf-8')
    (tmp_path / "empty.txt").write_text("", encoding='utf-8')

    # CSV
    (tmp_path / "data.csv").write_text("text,label\nfoo,A\nbar,B\n", encoding='utf-8')

    # TSV
    (tmp_path / "data.tsv").write_text("text\tlabel\nbaz\tC\n", encoding='utf-8')

    # JSON
    (tmp_path / "data.json").write_text(json.dumps([
        {"text": "json item 1", "id": 1},
        {"text": "json item 2", "id": 2},
        {"text": "", "id": 3},  # empty text
    ]), encoding='utf-8')

    # JSONL
    (tmp_path / "data.jsonl").write_text(
        '{"text": "line 1"}\n{"text": "line 2"}\n{"text": ""}\n\n',
        encoding='utf-8'
    )

    return tmp_path


# ─── Loaders ─────────────────────────────────────────────────────────────────

class TestLoadTextFiles:
    def test_loads_txt_files(self, tmp_data):
        items = load_text_files(str(tmp_data))
        # empty.txt should be skipped
        assert len(items) == 2
        assert all('text' in i for i in items)

    def test_empty_directory(self, tmp_path):
        items = load_text_files(str(tmp_path))
        assert items == []

    def test_metadata_has_filename(self, tmp_data):
        items = load_text_files(str(tmp_data))
        assert all('filename' in i['meta'] for i in items)

    def test_unicode_content(self, tmp_path):
        (tmp_path / "uni.txt").write_text("日本語テスト", encoding='utf-8')
        items = load_text_files(str(tmp_path))
        assert items[0]['text'] == "日本語テスト"


class TestLoadCsv:
    def test_loads_csv(self, tmp_data):
        items = load_csv(str(tmp_data))
        texts = [i['text'] for i in items]
        assert 'foo' in texts
        assert 'bar' in texts

    def test_loads_tsv(self, tmp_data):
        items = load_csv(str(tmp_data))
        texts = [i['text'] for i in items]
        assert 'baz' in texts

    def test_custom_text_column(self, tmp_path):
        (tmp_path / "c.csv").write_text("content,id\nhello,1\n", encoding='utf-8')
        items = load_csv(str(tmp_path), text_column='content')
        assert items[0]['text'] == 'hello'

    def test_empty_csv(self, tmp_path):
        (tmp_path / "e.csv").write_text("text\n", encoding='utf-8')
        items = load_csv(str(tmp_path))
        assert items == []


class TestLoadJson:
    def test_loads_json_array(self, tmp_data):
        items = load_json(str(tmp_data))
        # empty text item should be skipped
        assert len(items) == 2

    def test_single_object_json(self, tmp_path):
        (tmp_path / "single.json").write_text('{"text": "solo"}', encoding='utf-8')
        items = load_json(str(tmp_path))
        assert len(items) == 1

    def test_empty_directory(self, tmp_path):
        items = load_json(str(tmp_path))
        assert items == []


class TestLoadJsonl:
    def test_loads_jsonl(self, tmp_data):
        items = load_jsonl(str(tmp_data))
        assert len(items) == 2  # empty text skipped, blank line skipped

    def test_malformed_line(self, tmp_path):
        (tmp_path / "bad.jsonl").write_text('{"text": "ok"}\nNOT JSON\n', encoding='utf-8')
        with pytest.raises(json.JSONDecodeError):
            load_jsonl(str(tmp_path))


# ─── Sentence splitting ─────────────────────────────────────────────────────

class TestSentenceSplit:
    def test_split(self, tmp_data):
        """Only run if nltk is available."""
        try:
            from import_data import sentence_split
        except ImportError:
            pytest.skip("NLTK not available")
        items = [{'text': 'Hello world. This is a test. Third sentence.', 'meta': {}}]
        result = sentence_split(items)
        assert len(result) == 1
        assert isinstance(result[0]['text'], list)
        assert len(result[0]['text']) == 3


# ─── Format for Label Studio ────────────────────────────────────────────────

class TestFormatForLabelStudio:
    def test_wraps_in_data(self):
        items = [{'text': 'hello', 'meta': {'f': 'x'}}]
        result = format_for_label_studio(items, 'classification')
        assert len(result) == 1
        assert result[0]['data']['text'] == 'hello'

    def test_empty_list(self):
        assert format_for_label_studio([], 'span') == []
