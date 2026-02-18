#!/usr/bin/env python3
"""Data preprocessor and Label Studio importer.

Reads data from common formats, applies transforms (sentence splitting,
shuffling, filtering), and outputs Label Studio-compatible JSON.
"""
import argparse
import csv
import json
import os
import random
import sys
from pathlib import Path

import yaml

try:
    import nltk
    HAS_NLTK = True
except ImportError:
    HAS_NLTK = False


def load_text_files(source_dir, **kwargs):
    """Load plain text files from a directory. Each file becomes one item."""
    items = []
    source = Path(source_dir)
    for f in sorted(source.glob('**/*.txt')):
        text = f.read_text(encoding='utf-8').strip()
        if text:
            items.append({
                'text': text,
                'meta': {'filename': f.name, 'path': str(f.relative_to(source))},
            })
    return items


def load_csv(source_dir, text_column='text', **kwargs):
    """Load CSV/TSV files. Each row becomes one item."""
    items = []
    source = Path(source_dir)
    for f in sorted(source.glob('**/*.csv')) | sorted(source.glob('**/*.tsv')):
        delimiter = '\t' if f.suffix == '.tsv' else ','
        with open(f, encoding='utf-8') as fh:
            reader = csv.DictReader(fh, delimiter=delimiter)
            for row in reader:
                text = row.get(text_column, '')
                if text.strip():
                    meta = {k: v for k, v in row.items() if k != text_column}
                    meta['filename'] = f.name
                    items.append({'text': text.strip(), 'meta': meta})
    return items


def load_json(source_dir, text_field='text', **kwargs):
    """Load JSON files. Supports single objects, arrays, or one-object-per-file."""
    items = []
    source = Path(source_dir)
    for f in sorted(source.glob('**/*.json')):
        with open(f, encoding='utf-8') as fh:
            data = json.load(fh)
        if isinstance(data, list):
            for obj in data:
                text = obj.get(text_field, '') if isinstance(obj, dict) else str(obj)
                if text.strip():
                    meta = {k: v for k, v in obj.items() if k != text_field} if isinstance(obj, dict) else {}
                    meta['filename'] = f.name
                    items.append({'text': text.strip(), 'meta': meta})
        elif isinstance(data, dict):
            text = data.get(text_field, '')
            if text.strip():
                meta = {k: v for k, v in data.items() if k != text_field}
                meta['filename'] = f.name
                items.append({'text': text.strip(), 'meta': meta})
    return items


def load_jsonl(source_dir, text_field='text', **kwargs):
    """Load JSONL files (one JSON object per line)."""
    items = []
    source = Path(source_dir)
    for f in sorted(source.glob('**/*.jsonl')):
        with open(f, encoding='utf-8') as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                text = obj.get(text_field, '')
                if text.strip():
                    meta = {k: v for k, v in obj.items() if k != text_field}
                    meta['filename'] = f.name
                    items.append({'text': text.strip(), 'meta': meta})
    return items


LOADERS = {
    'text': load_text_files,
    'csv': load_csv,
    'json': load_json,
    'jsonl': load_jsonl,
}


def sentence_split(items):
    """Split each item's text into sentences using NLTK."""
    if not HAS_NLTK:
        print("ERROR: NLTK required for sentence splitting. Install: pip install nltk")
        sys.exit(1)

    nltk.download('punkt_tab', quiet=True)

    split_items = []
    for item in items:
        sentences = nltk.sent_tokenize(item['text'])
        paragraphs = [{"author": "", "text": s} for s in sentences]
        split_items.append({
            'text': paragraphs,
            'meta': {**item.get('meta', {}), 'sentence_count': len(sentences)},
        })
    return split_items


def format_for_label_studio(items, schema_type, granularity=None):
    """Convert items to Label Studio import format.
    
    For sentence-level spans: text field is array of {author, text} objects.
    For everything else: text field is a string.
    """
    ls_items = []
    for item in items:
        data = {'text': item['text']}
        # Add metadata fields
        if 'meta' in item:
            data['meta'] = item['meta']
        ls_items.append({'data': data})
    return ls_items


def main():
    parser = argparse.ArgumentParser(description='Import data into annotate-box format')
    parser.add_argument('--config', required=True, help='Path to config.yaml')
    parser.add_argument('--input', help='Override input directory from config')
    parser.add_argument('--output', default='import.json', help='Output JSON file (default: import.json)')
    parser.add_argument('--dry-run', action='store_true', help='Preview without writing')
    args = parser.parse_args()

    with open(args.config) as f:
        config = yaml.safe_load(f)

    data_config = config.get('data', {})
    schema_config = config.get('schema', {})

    # Determine source
    source = args.input or data_config.get('source', './data/')
    fmt = data_config.get('format', 'text')

    print(f"Loading {fmt} data from {source}...")
    loader = LOADERS.get(fmt)
    if not loader:
        print(f"ERROR: Unsupported format '{fmt}'. Supported: {', '.join(LOADERS.keys())}")
        sys.exit(1)

    items = loader(source, **data_config)
    print(f"  Loaded {len(items)} items")

    # Filtering
    min_len = data_config.get('min_length')
    max_len = data_config.get('max_length')
    if min_len:
        items = [i for i in items if len(i['text']) >= min_len]
        print(f"  After min_length filter: {len(items)}")
    if max_len:
        items = [i for i in items if len(i['text']) <= max_len]
        print(f"  After max_length filter: {len(items)}")

    max_items = data_config.get('max_items')
    if max_items and len(items) > max_items:
        # If shuffling, shuffle first then truncate; otherwise take first N
        if data_config.get('shuffle', False):
            seed = data_config.get('shuffle_seed', 42)
            random.seed(seed)
            random.shuffle(items)
        items = items[:max_items]
        print(f"  Truncated to {len(items)} items")

    # Sentence splitting (for sentence-level span tasks)
    if data_config.get('sentence_split', False):
        print("  Splitting into sentences...")
        items = sentence_split(items)
        total_sents = sum(len(i['text']) for i in items if isinstance(i['text'], list))
        print(f"  {total_sents} total sentences across {len(items)} items")

    # Shuffling (if not already done above)
    if data_config.get('shuffle', False) and not max_items:
        seed = data_config.get('shuffle_seed', 42)
        random.seed(seed)
        random.shuffle(items)
        print(f"  Shuffled (seed={seed})")

    # Format for Label Studio
    ls_data = format_for_label_studio(
        items,
        schema_type=schema_config.get('type', 'span'),
        granularity=schema_config.get('granularity'),
    )

    if args.dry_run:
        print(f"\n  Would write {len(ls_data)} tasks to {args.output}")
        if ls_data:
            print(f"  Sample item: {json.dumps(ls_data[0], indent=2)[:500]}")
        return

    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(ls_data, f, ensure_ascii=False, indent=2)

    print(f"\n  ✓ Wrote {len(ls_data)} tasks to {args.output}")
    print(f"  Import into Label Studio: curl -X POST 'https://your-server/api/projects/ID/import' ...")


if __name__ == '__main__':
    main()
