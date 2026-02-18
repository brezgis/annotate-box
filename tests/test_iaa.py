"""Tests for iaa.py — inter-annotator agreement metrics."""
import pytest
from iaa import (
    cohens_kappa, percent_agreement, span_exact_match,
    extract_classification_annotations, extract_span_annotations,
    detect_task_type, generate_report,
)


# ─── Cohen's Kappa ───────────────────────────────────────────────────────────

class TestCohensKappa:
    def test_perfect_agreement(self):
        a = {1: 'A', 2: 'B', 3: 'A'}
        b = {1: 'A', 2: 'B', 3: 'A'}
        assert cohens_kappa(a, b) == pytest.approx(1.0)

    def test_no_agreement(self):
        # Systematic disagreement — kappa should be <= 0
        a = {1: 'A', 2: 'A', 3: 'A', 4: 'A'}
        b = {1: 'B', 2: 'B', 3: 'B', 4: 'B'}
        k = cohens_kappa(a, b)
        assert k is not None
        assert k <= 0.0

    def test_chance_agreement(self):
        # 50/50 split, random-ish
        a = {1: 'A', 2: 'B', 3: 'A', 4: 'B'}
        b = {1: 'B', 2: 'A', 3: 'A', 4: 'B'}
        k = cohens_kappa(a, b)
        assert k is not None
        assert -1.0 <= k <= 1.0

    def test_empty_returns_none(self):
        assert cohens_kappa({}, {}) is None

    def test_single_item_returns_none(self):
        assert cohens_kappa({1: 'A'}, {1: 'A'}) is None

    def test_no_shared_items_returns_none(self):
        assert cohens_kappa({1: 'A'}, {2: 'B'}) is None


# ─── Percent Agreement ──────────────────────────────────────────────────────

class TestPercentAgreement:
    def test_perfect(self):
        a = {1: 'X', 2: 'Y'}
        b = {1: 'X', 2: 'Y'}
        assert percent_agreement(a, b) == pytest.approx(1.0)

    def test_half(self):
        a = {1: 'X', 2: 'Y'}
        b = {1: 'X', 2: 'Z'}
        assert percent_agreement(a, b) == pytest.approx(0.5)

    def test_empty(self):
        assert percent_agreement({}, {}) is None


# ─── Span Exact Match ───────────────────────────────────────────────────────

class TestSpanExactMatch:
    def test_identical(self):
        spans = [(0, 5, 'PER'), (10, 15, 'ORG')]
        p, r, f1 = span_exact_match(spans, spans)
        assert f1 == pytest.approx(1.0)

    def test_no_overlap(self):
        a = [(0, 5, 'PER')]
        b = [(10, 15, 'ORG')]
        p, r, f1 = span_exact_match(a, b)
        assert f1 == pytest.approx(0.0)

    def test_both_empty(self):
        p, r, f1 = span_exact_match([], [])
        assert f1 == pytest.approx(1.0)

    def test_one_empty(self):
        p, r, f1 = span_exact_match([(0, 5, 'X')], [])
        assert f1 == pytest.approx(0.0)

    def test_partial_overlap(self):
        a = [(0, 5, 'X'), (10, 15, 'Y')]
        b = [(0, 5, 'X'), (10, 15, 'Z')]
        p, r, f1 = span_exact_match(a, b)
        assert 0 < f1 < 1.0


# ─── Extraction ──────────────────────────────────────────────────────────────

class TestExtraction:
    def test_classification_extraction(self):
        data = [{
            'id': 1,
            'annotations': [{
                'completed_by': 'alice',
                'result': [{'type': 'choices', 'value': {'choices': ['POS']}}]
            }, {
                'completed_by': 'bob',
                'result': [{'type': 'choices', 'value': {'choices': ['NEG']}}]
            }]
        }]
        tasks, annotators = extract_classification_annotations(data)
        assert tasks[1]['alice'] == 'POS'
        assert tasks[1]['bob'] == 'NEG'
        assert annotators == {'alice', 'bob'}

    def test_span_extraction(self):
        data = [{
            'id': 1,
            'annotations': [{
                'completed_by': 'alice',
                'result': [{'type': 'labels', 'value': {'start': 0, 'end': 5, 'labels': ['PER']}}]
            }]
        }]
        tasks, annotators = extract_span_annotations(data)
        assert (0, 5, 'PER') in tasks[1]['alice']


# ─── Detection ───────────────────────────────────────────────────────────────

class TestDetection:
    def test_detect_classification(self):
        data = [{'annotations': [{'result': [{'type': 'choices'}]}]}]
        assert detect_task_type(data) == 'classification'

    def test_detect_span(self):
        data = [{'annotations': [{'result': [{'type': 'labels'}]}]}]
        assert detect_task_type(data) == 'span'

    def test_detect_paragraph(self):
        data = [{'annotations': [{'result': [{'type': 'paragraphlabels'}]}]}]
        assert detect_task_type(data) == 'paragraph'

    def test_detect_unknown(self):
        assert detect_task_type([{'annotations': [{'result': []}]}]) == 'unknown'
        assert detect_task_type([]) == 'unknown'


# ─── Report generation ──────────────────────────────────────────────────────

class TestReport:
    def test_empty_data(self):
        report = generate_report([], task_type='classification')
        assert 'Tasks: 0' in report

    def test_classification_report(self):
        data = [{
            'id': i,
            'annotations': [
                {'completed_by': 'a', 'result': [{'type': 'choices', 'value': {'choices': ['X']}}]},
                {'completed_by': 'b', 'result': [{'type': 'choices', 'value': {'choices': ['X']}}]},
            ]
        } for i in range(5)]
        report = generate_report(data, task_type='classification')
        assert 'kappa' in report.lower() or 'agreement' in report.lower()

    def test_markdown_format(self):
        data = [{'id': 1, 'annotations': []}]
        report = generate_report(data, task_type='classification', fmt='markdown')
        assert '##' in report
