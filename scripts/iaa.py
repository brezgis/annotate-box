#!/usr/bin/env python3
"""Inter-annotator agreement from Label Studio exports.

Reads Label Studio JSON exports and computes agreement metrics:
- Classification tasks: Cohen's kappa (2 annotators), Fleiss' kappa (3+), Krippendorff's alpha
- Span tasks: exact match, token-level overlap, Krippendorff's alpha on spans

Usage:
    python3 iaa.py export.json
    python3 iaa.py export.json --format markdown
    python3 iaa.py export.json --task-type span
"""
import argparse
import json
import sys
from collections import defaultdict
from itertools import combinations

try:
    import krippendorff
    HAS_KRIPPENDORFF = True
except ImportError:
    HAS_KRIPPENDORFF = False

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


# ─── Data extraction ─────────────────────────────────────────────────────────

def extract_classification_annotations(data):
    """Extract classification labels per (task_id, annotator) pair.
    
    Returns:
        tasks: dict of task_id -> {annotator_id: label}
        annotators: set of annotator IDs
    """
    tasks = defaultdict(dict)
    annotators = set()

    for task in data:
        task_id = task['id']
        for ann in task.get('annotations', []):
            annotator = ann.get('completed_by', ann.get('id', 'unknown'))
            annotators.add(annotator)

            for result in ann.get('result', []):
                if result.get('type') in ('choices', 'taxonomy'):
                    values = result.get('value', {}).get('choices', [])
                    if values:
                        # For single-label: take first choice
                        tasks[task_id][annotator] = values[0]

    return dict(tasks), annotators


def extract_span_annotations(data):
    """Extract span annotations per (task_id, annotator) pair.
    
    Returns:
        tasks: dict of task_id -> {annotator_id: [(start, end, label), ...]}
        annotators: set of annotator IDs
    """
    tasks = defaultdict(lambda: defaultdict(list))
    annotators = set()

    for task in data:
        task_id = task['id']
        for ann in task.get('annotations', []):
            annotator = ann.get('completed_by', ann.get('id', 'unknown'))
            annotators.add(annotator)

            for result in ann.get('result', []):
                if result.get('type') in ('labels', 'paragraphlabels'):
                    value = result.get('value', {})
                    start = value.get('start', value.get('startOffset', 0))
                    end = value.get('end', value.get('endOffset', 0))
                    labels = value.get('labels', value.get('paragraphlabels', []))
                    for label in labels:
                        tasks[task_id][annotator].append((start, end, label))

    # Convert to regular dicts
    return {k: dict(v) for k, v in tasks.items()}, annotators


def extract_paragraph_annotations(data):
    """Extract paragraph-level (sentence) annotations per (task_id, annotator).
    
    For ParagraphLabels + Paragraphs configs (sentence-level annotation).
    
    Returns:
        tasks: dict of task_id -> {annotator_id: {paragraph_idx: label}}
        annotators: set of annotator IDs
        paragraph_counts: dict of task_id -> number of paragraphs
    """
    tasks = defaultdict(lambda: defaultdict(dict))
    annotators = set()
    paragraph_counts = {}

    for task in data:
        task_id = task['id']
        # Count paragraphs in data
        text_data = task.get('data', {}).get('text', '')
        if isinstance(text_data, list):
            paragraph_counts[task_id] = len(text_data)

        for ann in task.get('annotations', []):
            annotator = ann.get('completed_by', ann.get('id', 'unknown'))
            annotators.add(annotator)

            for result in ann.get('result', []):
                if result.get('type') == 'paragraphlabels':
                    value = result.get('value', {})
                    start = value.get('start', value.get('startOffset', 0))
                    end = value.get('end', value.get('endOffset', start + 1))
                    labels = value.get('paragraphlabels', [])
                    if labels:
                        # Map each paragraph index in the span to the label
                        for idx in range(start, end):
                            tasks[task_id][annotator][idx] = labels[0]

    return {k: dict(v) for k, v in tasks.items()}, annotators, paragraph_counts


# ─── Agreement metrics ───────────────────────────────────────────────────────

def cohens_kappa(labels_a, labels_b):
    """Compute Cohen's kappa for two annotators on shared items."""
    if not labels_a or not labels_b:
        return None

    # Get shared items
    shared = set(labels_a.keys()) & set(labels_b.keys())
    if len(shared) < 2:
        return None

    a_vals = [labels_a[k] for k in shared]
    b_vals = [labels_b[k] for k in shared]

    # Observed agreement
    agree = sum(1 for a, b in zip(a_vals, b_vals) if a == b)
    po = agree / len(shared)

    # Expected agreement
    all_labels = set(a_vals) | set(b_vals)
    pe = 0
    for label in all_labels:
        pa = sum(1 for v in a_vals if v == label) / len(shared)
        pb = sum(1 for v in b_vals if v == label) / len(shared)
        pe += pa * pb

    if pe == 1.0:
        return 1.0

    kappa = (po - pe) / (1 - pe)
    return kappa


def percent_agreement(labels_a, labels_b):
    """Simple percent agreement between two annotators."""
    shared = set(labels_a.keys()) & set(labels_b.keys())
    if not shared:
        return None
    agree = sum(1 for k in shared if labels_a[k] == labels_b[k])
    return agree / len(shared)


def krippendorff_alpha(tasks, annotators, label_set=None):
    """Compute Krippendorff's alpha for multiple annotators.
    
    tasks: dict of item_id -> {annotator_id: label}
    """
    if not HAS_KRIPPENDORFF or not HAS_NUMPY:
        return None

    annotator_list = sorted(annotators)
    items = sorted(tasks.keys())

    if not items or len(annotator_list) < 2:
        return None

    # Build label-to-int mapping
    if label_set is None:
        label_set = set()
        for item_labels in tasks.values():
            for label in item_labels.values():
                label_set.add(label)
    label_map = {label: i for i, label in enumerate(sorted(label_set))}

    # Build reliability matrix (annotators × items)
    # Use np.nan for missing values
    matrix = np.full((len(annotator_list), len(items)), np.nan)
    for j, item in enumerate(items):
        for i, annotator in enumerate(annotator_list):
            label = tasks[item].get(annotator)
            if label is not None and label in label_map:
                matrix[i, j] = label_map[label]

    try:
        alpha = krippendorff.alpha(reliability_data=matrix, level_of_measurement='nominal')
        return alpha
    except Exception:
        return None


def span_exact_match(spans_a, spans_b):
    """Compute exact match F1 between two sets of spans.
    
    spans: list of (start, end, label) tuples
    """
    set_a = set(spans_a)
    set_b = set(spans_b)

    if not set_a and not set_b:
        return 1.0, 1.0, 1.0  # perfect agreement on empty

    tp = len(set_a & set_b)
    precision = tp / len(set_b) if set_b else 0
    recall = tp / len(set_a) if set_a else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    return precision, recall, f1


# ─── Auto-detect task type ───────────────────────────────────────────────────

def detect_task_type(data):
    """Auto-detect whether annotations are classification, spans, or paragraphs."""
    for task in data:
        for ann in task.get('annotations', []):
            for result in ann.get('result', []):
                rtype = result.get('type', '')
                if rtype in ('choices', 'taxonomy'):
                    return 'classification'
                elif rtype == 'paragraphlabels':
                    return 'paragraph'
                elif rtype == 'labels':
                    return 'span'
    return 'unknown'


# ─── Report generation ───────────────────────────────────────────────────────

def generate_report(data, task_type=None, fmt='text'):
    """Generate an IAA report from Label Studio export data."""
    if task_type is None:
        task_type = detect_task_type(data)

    lines = []

    def heading(text):
        if fmt == 'markdown':
            lines.append(f"\n## {text}\n")
        else:
            lines.append(f"\n{'─' * 50}")
            lines.append(f"  {text}")
            lines.append(f"{'─' * 50}")

    def line(text):
        lines.append(f"  {text}" if fmt == 'text' else text)

    def metric(name, value, interpretation=""):
        if value is None:
            line(f"{name}: N/A (insufficient data)")
        else:
            interp = f" ({interpretation})" if interpretation else ""
            line(f"{name}: {value:.3f}{interp}")

    def interpret_kappa(k):
        if k is None: return ""
        if k < 0: return "poor"
        if k < 0.20: return "slight"
        if k < 0.40: return "fair"
        if k < 0.60: return "moderate"
        if k < 0.80: return "substantial"
        return "almost perfect"

    # Header
    if fmt == 'markdown':
        lines.append("# Inter-Annotator Agreement Report\n")
    else:
        lines.append("\n  📊 Inter-Annotator Agreement Report")

    # Summary stats
    total_tasks = len(data)
    annotated = sum(1 for t in data if t.get('annotations'))
    total_annotations = sum(len(t.get('annotations', [])) for t in data)
    heading("Summary")
    line(f"Tasks: {total_tasks} ({annotated} annotated)")
    line(f"Total annotations: {total_annotations}")
    line(f"Detected task type: {task_type}")

    if task_type == 'classification':
        tasks, annotators = extract_classification_annotations(data)
        annotator_list = sorted(annotators)

        heading("Annotators")
        for a in annotator_list:
            count = sum(1 for t in tasks.values() if a in t)
            line(f"Annotator {a}: {count} items annotated")

        # Pairwise Cohen's kappa
        if len(annotator_list) >= 2:
            heading("Pairwise Agreement")
            for a1, a2 in combinations(annotator_list, 2):
                labels_a = {k: v[a1] for k, v in tasks.items() if a1 in v}
                labels_b = {k: v[a2] for k, v in tasks.items() if a2 in v}
                k = cohens_kappa(labels_a, labels_b)
                p = percent_agreement(labels_a, labels_b)
                shared = len(set(labels_a.keys()) & set(labels_b.keys()))
                line(f"\nAnnotators {a1} vs {a2} ({shared} shared items):")
                metric("  Percent agreement", p)
                metric("  Cohen's kappa", k, interpret_kappa(k))

        # Krippendorff's alpha (all annotators)
        heading("Overall Agreement")
        alpha = krippendorff_alpha(tasks, annotators)
        metric("Krippendorff's alpha", alpha, interpret_kappa(alpha))

    elif task_type == 'paragraph':
        tasks, annotators, para_counts = extract_paragraph_annotations(data)
        annotator_list = sorted(annotators)

        heading("Annotators")
        for a in annotator_list:
            count = sum(1 for t in tasks.values() if a in t)
            line(f"Annotator {a}: {count} tasks annotated")

        # Convert paragraph annotations to flat classification for IAA
        # Each (task_id, paragraph_idx) is an item, label is the annotation
        flat_tasks = {}
        for task_id, ann_dict in tasks.items():
            n_paras = para_counts.get(task_id, 0)
            for para_idx in range(n_paras):
                item_key = (task_id, para_idx)
                flat_tasks[item_key] = {}
                for annotator, para_labels in ann_dict.items():
                    if para_idx in para_labels:
                        flat_tasks[item_key][annotator] = para_labels[para_idx]

        # Only keep items with 2+ annotations
        multi = {k: v for k, v in flat_tasks.items() if len(v) >= 2}
        line(f"\nSentences with 2+ annotations: {len(multi)}")

        if len(annotator_list) >= 2 and multi:
            heading("Pairwise Agreement (sentence-level)")
            for a1, a2 in combinations(annotator_list, 2):
                labels_a = {k: v[a1] for k, v in multi.items() if a1 in v}
                labels_b = {k: v[a2] for k, v in multi.items() if a2 in v}
                k = cohens_kappa(labels_a, labels_b)
                p = percent_agreement(labels_a, labels_b)
                shared = len(set(labels_a.keys()) & set(labels_b.keys()))
                line(f"\nAnnotators {a1} vs {a2} ({shared} shared sentences):")
                metric("  Percent agreement", p)
                metric("  Cohen's kappa", k, interpret_kappa(k))

            heading("Overall Agreement (sentence-level)")
            alpha = krippendorff_alpha(multi, annotators)
            metric("Krippendorff's alpha", alpha, interpret_kappa(alpha))

            # Per-label breakdown
            heading("Per-Label Agreement")
            all_labels = set()
            for v in multi.values():
                all_labels.update(v.values())

            for label in sorted(all_labels):
                # Binary: did annotators agree this sentence is/isn't this label?
                binary_tasks = {}
                for item_key, ann_dict in multi.items():
                    binary_tasks[item_key] = {
                        a: (1 if ann_dict.get(a) == label else 0)
                        for a in annotator_list if a in ann_dict
                    }
                binary_multi = {k: v for k, v in binary_tasks.items() if len(v) >= 2}
                if binary_multi:
                    alpha = krippendorff_alpha(binary_multi, annotators)
                    count = sum(1 for v in multi.values() for lbl in v.values() if lbl == label)
                    line(f"  {label} (n={count}): alpha={alpha:.3f}" if alpha is not None else f"  {label}: N/A")

    elif task_type == 'span':
        tasks, annotators = extract_span_annotations(data)
        annotator_list = sorted(annotators)

        heading("Annotators")
        for a in annotator_list:
            count = sum(1 for t in tasks.values() if a in t)
            total_spans = sum(len(tasks[t].get(a, [])) for t in tasks)
            line(f"Annotator {a}: {count} tasks, {total_spans} spans")

        if len(annotator_list) >= 2:
            heading("Pairwise Span Agreement (Exact Match)")
            for a1, a2 in combinations(annotator_list, 2):
                shared_tasks = [t for t in tasks if a1 in tasks[t] and a2 in tasks[t]]
                if not shared_tasks:
                    continue

                precisions, recalls, f1s = [], [], []
                for t in shared_tasks:
                    p, r, f1 = span_exact_match(tasks[t][a1], tasks[t][a2])
                    precisions.append(p)
                    recalls.append(r)
                    f1s.append(f1)

                avg_p = sum(precisions) / len(precisions)
                avg_r = sum(recalls) / len(recalls)
                avg_f1 = sum(f1s) / len(f1s)

                line(f"\nAnnotators {a1} vs {a2} ({len(shared_tasks)} shared tasks):")
                metric("  Avg precision", avg_p)
                metric("  Avg recall", avg_r)
                metric("  Avg F1 (exact match)", avg_f1)

    else:
        line(f"\nCould not detect task type from annotations.")
        line("Make sure the export contains completed annotations.")

    # Interpretation guide
    heading("Interpretation Guide")
    line("Kappa / Alpha scale (Landis & Koch 1977):")
    line("  < 0.00  Poor")
    line("  0.00–0.20  Slight")
    line("  0.21–0.40  Fair")
    line("  0.41–0.60  Moderate")
    line("  0.61–0.80  Substantial")
    line("  0.81–1.00  Almost perfect")
    line("")

    return '\n'.join(lines)


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Compute inter-annotator agreement from Label Studio exports')
    parser.add_argument('export_file', help='Label Studio JSON export file')
    parser.add_argument('--format', choices=['text', 'markdown'], default='text',
                        help='Output format (default: text)')
    parser.add_argument('--task-type', choices=['classification', 'span', 'paragraph'],
                        help='Override auto-detected task type')
    parser.add_argument('--output', '-o', help='Write report to file instead of stdout')
    args = parser.parse_args()

    with open(args.export_file, encoding='utf-8') as f:
        data = json.load(f)

    if not data:
        print("Empty export file.")
        sys.exit(1)

    report = generate_report(data, task_type=args.task_type, fmt=args.format)

    if args.output:
        with open(args.output, 'w') as f:
            f.write(report)
        print(f"Report written to {args.output}")
    else:
        print(report)


if __name__ == '__main__':
    main()
