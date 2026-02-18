"""Tests for schema_builder.py"""
import pytest
from schema_builder import build_schema, build_label_xml, BUILDERS


# ─── Fixtures ────────────────────────────────────────────────────────────────

def make_labels(*names):
    return [{'name': n, 'color': '#FF0000', 'hotkey': str(i+1)} for i, n in enumerate(names)]


BASIC_LABELS = make_labels('POS', 'NEG', 'NEU')


# ─── build_schema basics ────────────────────────────────────────────────────

class TestBuildSchema:
    def test_span_sentence(self):
        xml = build_schema({'type': 'span', 'granularity': 'sentence', 'labels': BASIC_LABELS})
        assert '<ParagraphLabels' in xml
        assert '<Paragraphs' in xml
        assert 'value="POS"' in xml

    def test_span_character(self):
        xml = build_schema({'type': 'span', 'granularity': 'character', 'labels': BASIC_LABELS})
        assert '<Labels' in xml
        assert '<Text' in xml

    def test_classification_single(self):
        xml = build_schema({'type': 'classification', 'labels': BASIC_LABELS})
        assert '<Choices' in xml
        assert 'choice="single"' in xml

    def test_classification_multi(self):
        xml = build_schema({'type': 'classification', 'multi_label': True, 'labels': BASIC_LABELS})
        assert 'choice="multiple"' in xml

    def test_ner(self):
        xml = build_schema({'type': 'ner', 'labels': BASIC_LABELS})
        assert '<Labels' in xml

    def test_pairwise(self):
        xml = build_schema({'type': 'pairwise', 'labels': make_labels('A_BETTER', 'B_BETTER', 'TIE')})
        assert 'text_a' in xml
        assert 'text_b' in xml

    def test_unsupported_type_raises(self):
        with pytest.raises(ValueError, match="Unsupported schema type"):
            build_schema({'type': 'nonexistent', 'labels': BASIC_LABELS})

    def test_case_insensitive_type(self):
        xml = build_schema({'type': 'SPAN', 'granularity': 'SENTENCE', 'labels': BASIC_LABELS})
        assert '<ParagraphLabels' in xml

    def test_span_without_granularity_raises(self):
        """Span type requires granularity (sentence or character)."""
        with pytest.raises(ValueError):
            build_schema({'type': 'span', 'labels': BASIC_LABELS})


# ─── Edge cases ──────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_labels_raises(self):
        with pytest.raises(ValueError, match="at least one label"):
            build_schema({'type': 'classification', 'labels': []})

    def test_single_label(self):
        xml = build_schema({'type': 'classification', 'labels': make_labels('ONLY')})
        assert 'value="ONLY"' in xml

    def test_many_labels(self):
        labels = make_labels(*[f'LABEL_{i}' for i in range(100)])
        xml = build_schema({'type': 'classification', 'labels': labels})
        assert 'LABEL_99' in xml

    def test_unicode_label_names(self):
        labels = [{'name': '감정', 'color': '#FF0000'}, {'name': 'Ärger', 'color': '#00FF00'}]
        xml = build_schema({'type': 'classification', 'labels': labels})
        assert '감정' in xml
        assert 'Ärger' in xml

    def test_special_chars_escaped(self):
        labels = [{'name': 'A & B', 'color': '#FF0000'}, {'name': '"quoted"', 'color': '#00FF00'}]
        xml = build_schema({'type': 'classification', 'labels': labels})
        assert '&amp;' in xml

    def test_label_without_hotkey(self):
        labels = [{'name': 'TEST', 'color': '#FF0000'}]
        xml = build_schema({'type': 'classification', 'labels': labels})
        assert 'hotkey' not in xml

    def test_label_without_color_uses_default(self):
        labels = [{'name': 'TEST'}]
        xml = build_schema({'type': 'span', 'granularity': 'sentence', 'labels': labels})
        assert 'background=' in xml


# ─── build_label_xml ─────────────────────────────────────────────────────────

class TestBuildLabelXml:
    def test_basic(self):
        xml = build_label_xml(BASIC_LABELS)
        assert xml.count('<Label') == 3

    def test_custom_tag_name(self):
        xml = build_label_xml(BASIC_LABELS, tag_name="Choice")
        assert '<Choice' in xml
        assert '<Label' not in xml
