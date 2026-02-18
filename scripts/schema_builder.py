#!/usr/bin/env python3
"""Schema builder — converts YAML config to Label Studio XML.

Supports:
- span (sentence-level or character-level)
- classification (single or multi-label)
- ner (named entity recognition)
- pairwise (compare two texts)
"""
import sys
import yaml
from xml.sax.saxutils import escape

# Default color palette (Label Studio friendly)
DEFAULT_COLORS = [
    "#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4", "#FFEAA7",
    "#DDA0DD", "#98D8C8", "#F7DC6F", "#BB8FCE", "#85C1E9",
    "#F1948A", "#82E0AA", "#F8C471", "#AED6F1", "#D7BDE2",
    "#A3E4D7", "#FAD7A0", "#A9CCE3", "#D5F5E3", "#FADBD8",
]


def build_label_xml(labels, tag_name="Label"):
    """Build XML for a list of label definitions."""
    parts = []
    for i, label in enumerate(labels):
        name = label['name']
        color = label.get('color', DEFAULT_COLORS[i % len(DEFAULT_COLORS)])
        hotkey = label.get('hotkey', '')
        attrs = f'value="{escape(name)}" background="{color}"'
        if hotkey:
            attrs += f' hotkey="{escape(str(hotkey))}"'
        parts.append(f'    <{tag_name} {attrs}/>')
    return '\n'.join(parts)


def build_span_sentence(labels):
    """Span labeling on sentence-level paragraphs.
    
    Uses <ParagraphLabels> + <Paragraphs>.
    Data format: {"text": [{"author": "", "text": "sentence"}, ...]}
    """
    label_xml = build_label_xml(labels, "Label")
    return f"""<View>
  <ParagraphLabels name="labels" toName="text">
{label_xml}
  </ParagraphLabels>
  <Paragraphs name="text" value="$text" layout="dialogue" />
</View>"""


def build_span_character(labels):
    """Span labeling on character level (highlight arbitrary spans).
    
    Uses <Labels> + <Text>.
    Data format: {"text": "full text here"}
    """
    label_xml = build_label_xml(labels, "Label")
    return f"""<View>
  <Labels name="labels" toName="text">
{label_xml}
  </Labels>
  <Text name="text" value="$text" />
</View>"""


def build_classification_single(labels):
    """Single-label document classification.
    
    Uses <Choices> + <Text>.
    Data format: {"text": "document text"}
    """
    label_xml = build_label_xml(labels, "Choice").replace("background=", "html=")
    # Choices use different attributes
    parts = []
    for i, label in enumerate(labels):
        name = label['name']
        hotkey = label.get('hotkey', '')
        attrs = f'value="{escape(name)}"'
        if hotkey:
            attrs += f' hotkey="{escape(str(hotkey))}"'
        parts.append(f'    <Choice {attrs}/>')
    choices_xml = '\n'.join(parts)

    return f"""<View>
  <Choices name="label" toName="text" choice="single" showInline="true">
{choices_xml}
  </Choices>
  <Text name="text" value="$text" />
</View>"""


def build_classification_multi(labels):
    """Multi-label document classification.
    
    Same as single but with choice="multiple".
    """
    parts = []
    for i, label in enumerate(labels):
        name = label['name']
        hotkey = label.get('hotkey', '')
        attrs = f'value="{escape(name)}"'
        if hotkey:
            attrs += f' hotkey="{escape(str(hotkey))}"'
        parts.append(f'    <Choice {attrs}/>')
    choices_xml = '\n'.join(parts)

    return f"""<View>
  <Choices name="labels" toName="text" choice="multiple" showInline="true">
{choices_xml}
  </Choices>
  <Text name="text" value="$text" />
</View>"""


def build_ner(labels):
    """Named entity recognition (token-level spans).
    
    Uses <Labels> + <Text>. Same XML as character spans but semantically for entities.
    """
    return build_span_character(labels)


def build_pairwise(labels):
    """Pairwise comparison — annotator chooses which of two texts fits a criterion.
    
    Data format: {"text_a": "first text", "text_b": "second text"}
    """
    parts = []
    for label in labels:
        name = label['name']
        hotkey = label.get('hotkey', '')
        attrs = f'value="{escape(name)}"'
        if hotkey:
            attrs += f' hotkey="{escape(str(hotkey))}"'
        parts.append(f'    <Choice {attrs}/>')
    choices_xml = '\n'.join(parts)

    return f"""<View>
  <View style="display:flex;gap:20px">
    <View style="flex:1">
      <Header value="Text A" />
      <Text name="text_a" value="$text_a" />
    </View>
    <View style="flex:1">
      <Header value="Text B" />
      <Text name="text_b" value="$text_b" />
    </View>
  </View>
  <Choices name="label" toName="text_a" choice="single" showInline="true">
{choices_xml}
  </Choices>
</View>"""


# Map of (type, granularity) → builder function
BUILDERS = {
    ('span', 'sentence'): build_span_sentence,
    ('span', 'character'): build_span_character,
    ('classification', None): build_classification_single,
    ('classification_multi', None): build_classification_multi,
    ('ner', None): build_ner,
    ('pairwise', None): build_pairwise,
}


def build_schema(config):
    """Build Label Studio XML from a schema config dict.
    
    Args:
        config: dict with keys: type, granularity (optional), labels
        
    Returns:
        Label Studio XML string
    """
    schema_type = config['type'].lower()
    granularity = config.get('granularity', '').lower() or None
    labels = config['labels']

    # Handle classification subtypes
    if schema_type == 'classification':
        multi = config.get('multi_label', False)
        if multi:
            schema_type = 'classification_multi'

    key = (schema_type, granularity)

    # Try exact match first, then without granularity
    builder = BUILDERS.get(key) or BUILDERS.get((schema_type, None))

    if not builder:
        supported = ', '.join(f"{t}({g})" if g else t for t, g in BUILDERS.keys())
        raise ValueError(f"Unsupported schema type: {schema_type}/{granularity}. Supported: {supported}")

    return builder(labels)


def from_yaml_file(path):
    """Load config from YAML file and build schema."""
    with open(path) as f:
        config = yaml.safe_load(f)
    return build_schema(config['schema'])


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python schema_builder.py config.yaml")
        print("       Outputs Label Studio XML to stdout")
        sys.exit(1)

    xml = from_yaml_file(sys.argv[1])
    print(xml)
