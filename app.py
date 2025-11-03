import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import fitz  # PyMuPDF
from flask import Flask, flash, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'pdf'}
app.config['SECRET_KEY'] = 'supersecretkey'


def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


def extract_text_and_blocks(filepath: Path) -> Tuple[str, List[Dict[str, Any]]]:
    text_chunks: List[str] = []
    blocks: List[Dict[str, Any]] = []

    with fitz.open(filepath) as doc:
        for page_index, page in enumerate(doc):
            text_chunks.append(page.get_text())
            page_dict = page.get_text('dict')
            for block in page_dict.get('blocks', []):
                if block.get('type', 0) != 0:
                    continue
                lines = block.get('lines')
                if not lines:
                    continue
                block_text = ''.join(
                    span.get('text', '')
                    for line in lines
                    for span in line.get('spans', [])
                )
                if block_text.strip():
                    blocks.append({
                        'page_index': page_index,
                        'bbox': block.get('bbox'),
                        'text': block_text
                    })

    return '\n'.join(text_chunks), blocks


def split_passage_questions(full_text: str) -> Tuple[str, str]:
    passage = full_text
    questions = ''

    passage_start = re.search(r'below\.', full_text, re.IGNORECASE)
    if passage_start:
        passage_start_index = passage_start.end()
        question_keywords = [
            'Choose the correct letter',
            'Complete the sentences',
            'Complete the summary',
            'Do the following statements agree',
            'Matching',
            'List of Headings',
            r'Questions?\s+\d+'
        ]
        question_start_index = -1
        for keyword in question_keywords:
            search_result = re.search(keyword, full_text[passage_start_index:], re.IGNORECASE)
            if search_result:
                absolute_index = passage_start_index + search_result.start()
                if question_start_index == -1 or absolute_index < question_start_index:
                    question_start_index = absolute_index
        if question_start_index != -1:
            passage = full_text[passage_start_index:question_start_index]
            questions = full_text[question_start_index:]
        else:
            passage = full_text[passage_start_index:]
            questions = full_text[passage_start_index:]
    else:
        passage = full_text
        questions = full_text

    return passage.strip(), questions.strip()


def normalize_whitespace(value: str) -> str:
    return re.sub(r'\s+', ' ', value or '').strip()


def collect_passage_blocks(passage: str, blocks: Optional[List[Dict[str, Any]]]) -> List[str]:
    if not passage or not blocks:
        return []

    normalized_passage = normalize_whitespace(passage)
    if not normalized_passage:
        return []

    cursor = 0
    passage_blocks: List[str] = []

    question_prefixes = (
        'questions ',
        'choose the correct letter',
        'complete the summary',
        'complete the sentences',
        'do the following statements',
        'list of headings',
        'match the',
        'writing no more than'
    )

    for block in blocks:
        raw_text = block.get('text', '')
        normalized_block = normalize_whitespace(raw_text)
        if not normalized_block:
            continue

        lowered = normalized_block.lower()
        if lowered.startswith(question_prefixes):
            continue

        index = normalized_passage.find(normalized_block, cursor)
        if index == -1:
            continue

        passage_blocks.append(raw_text.strip())
        cursor = index + len(normalized_block)
        if cursor >= len(normalized_passage):
            break

    return passage_blocks


def collect_question_blocks(question_text: str, blocks: Optional[List[Dict[str, Any]]]) -> List[str]:
    if not question_text or not blocks:
        return []

    normalized_questions = normalize_whitespace(question_text)
    if not normalized_questions:
        return []

    cursor = 0
    question_blocks: List[str] = []

    for block in blocks:
        raw_text = block.get('text', '')
        normalized_block = normalize_whitespace(raw_text)
        if not normalized_block:
            continue

        idx = normalized_questions.find(normalized_block, cursor)
        if idx == -1:
            continue

        question_blocks.append(raw_text.strip())
        cursor = idx + len(normalized_block)
        if cursor >= len(normalized_questions):
            break

    return question_blocks


def structure_passage(raw_passage: str, passage_blocks: Optional[List[str]] = None) -> Dict[str, Any]:
    """Derive title and paragraph lettering from the reading passage."""

    def index_to_label(idx: int) -> str:
        label = ''
        current = idx
        while current >= 0:
            current, remainder = divmod(current, 26)
            label = chr(65 + remainder) + label
            current -= 1
        return label

    non_empty_lines = [line.strip() for line in raw_passage.splitlines() if line.strip()]
    title = non_empty_lines[0] if non_empty_lines else ''

    normalized_title = normalize_whitespace(title).lower()
    paragraphs: List[Dict[str, str]] = []
    intro_text = ''

    source_blocks = passage_blocks[:] if passage_blocks else []
    source_blocks = [normalize_whitespace(block) for block in source_blocks if normalize_whitespace(block)]

    def extract_letter_sections() -> Tuple[List[str], List[Tuple[str, str]]]:
        raw_lines = [line.rstrip('\r') for line in raw_passage.splitlines()]
        pre_letter_lines: List[str] = []
        sections: List[Tuple[str, List[str]]] = []
        current_letter: Optional[str] = None
        buffer: List[str] = []
        encountered_letter = False

        letter_only_pattern = re.compile(r'^[A-Z]$')
        inline_letter_pattern = re.compile(r'^(?P<letter>[A-Z])(?:[\.\)]\s*|\s+)(?P<body>.+)$')

        def first_alpha_is_upper(text_value: str) -> bool:
            for char in text_value:
                if char.isalpha():
                    return char.isupper()
            return False

        def flush() -> None:
            nonlocal current_letter, buffer
            if current_letter and buffer:
                sections.append((current_letter, buffer[:]))
            current_letter = None
            buffer = []

        total_lines = len(raw_lines)
        for idx, raw_line in enumerate(raw_lines):
            stripped = raw_line.strip()
            if not stripped:
                if current_letter and buffer:
                    buffer.append('')
                continue

            inline_match = inline_letter_pattern.match(stripped)
            if inline_match:
                letter = inline_match.group('letter')
                body = inline_match.group('body').strip()

                if current_letter and letter == current_letter and not first_alpha_is_upper(body):
                    buffer.append(stripped)
                    continue

                if first_alpha_is_upper(body):
                    flush()
                    current_letter = letter
                    encountered_letter = True
                    if body:
                        buffer.append(body)
                    continue

                if current_letter:
                    buffer.append(stripped)
                else:
                    pre_letter_lines.append(stripped)
                continue

            if letter_only_pattern.match(stripped):
                next_line_text = ''
                for look_ahead in range(idx + 1, total_lines):
                    candidate = raw_lines[look_ahead].strip()
                    if not candidate:
                        continue
                    next_line_text = candidate
                    break

                if next_line_text and first_alpha_is_upper(next_line_text):
                    flush()
                    current_letter = stripped
                    encountered_letter = True
                    continue
                else:
                    if current_letter:
                        buffer.append(stripped)
                    else:
                        pre_letter_lines.append(stripped)
                    continue

            if current_letter:
                buffer.append(stripped)
            else:
                pre_letter_lines.append(stripped)

        flush()

        normalized_sections = [
            (letter, normalize_whitespace(' '.join(lines)))
            for letter, lines in sections
            if normalize_whitespace(' '.join(lines))
        ]

        return pre_letter_lines, normalized_sections if encountered_letter else []

    pre_letter, letter_sections = extract_letter_sections()

    if letter_sections:
        if not intro_text and pre_letter:
            intro_text = normalize_whitespace(' '.join(pre_letter))
        paragraphs.extend({'letter': letter, 'text': text} for letter, text in letter_sections)
    elif source_blocks:
        source_blocks = [block for block in source_blocks if block.lower() != normalized_title]
        if source_blocks and len(source_blocks[0]) <= 120 and '.' not in source_blocks[0]:
            intro_text = source_blocks.pop(0)

        for block in source_blocks:
            paragraphs.append({'letter': '', 'text': block})
    else:
        blocks = re.split(r'(?:\r?\n){2,}', raw_passage)
        for block in blocks:
            cleaned = normalize_whitespace(block)
            if not cleaned or cleaned.lower() == normalized_title:
                continue
            if not intro_text and len(cleaned) <= 120 and '.' not in cleaned:
                intro_text = cleaned
                continue
            paragraphs.append({'letter': '', 'text': cleaned})

    return {
        'title': title,
        'intro': intro_text,
        'paragraphs': paragraphs,
        'raw': raw_passage
    }


def parse_single_choice(questions_text: str) -> List[Dict[str, Any]]:
    if not questions_text:
        return []

    pattern = re.compile(
        r'(\d+)\s+(.*?)\s+A\s+(.*?)\s+B\s+(.*?)\s+C\s+(.*?)\s+D\s+(.*?)(?=\s+\d+\s|\Z)',
        re.DOTALL
    )

    questions: List[Dict[str, Any]] = []
    for match in pattern.finditer(questions_text):
        number = match.group(1)
        prompt = re.sub(r'\s+', ' ', match.group(2).strip())
        # Find the last sentence of the prompt
        sentences = re.split(r'(?<=[.?!])\s+', prompt)
        actual_prompt = sentences[-1] if sentences else ''
        
        options = [re.sub(r'\s+', ' ', match.group(i).strip()) for i in range(3, 7) if match.group(i)]
        if options:
            questions.append({
                'type': 'single_choice',
                'number': number,
                'text': actual_prompt,
                'options': options,
                'match_start': match.start(),
                'match_end': match.end()
            })

    return questions


def parse_summary_completion(questions_text: str, blocks: Optional[List[Dict[str, Any]]]) -> Optional[Dict[str, Any]]:
    if not blocks:
        return None

    if 'complete the summary' not in (questions_text or '').lower():
        return None

    def normalize(text_value: str) -> str:
        cleaned = re.sub(r'\s+', ' ', text_value)
        replacements = (
            ('\u2019', "'"),
            ('\u2018', "'"),
            ('\u2013', '-'),
            ('\u2014', '-'),
            ('\uFFFD', '-')
        )
        for before, after in replacements:
            cleaned = cleaned.replace(before, after)
        return cleaned.strip()

    def is_option_line(text_value: str) -> bool:
        tokens = [token.strip('.,()') for token in text_value.split() if token]
        letter_tokens = [token for token in tokens if len(token) == 1 and token.isupper()]
        return len(letter_tokens) >= 2

    blank_pattern = re.compile(r'(?P<num>\d{1,2})\s*[_]{2,}')

    summary_anchor_idx: Optional[int] = None
    for idx, block in enumerate(blocks):
        plain_text = normalize(block.get('text', ''))
        if not plain_text:
            continue
        if blank_pattern.search(plain_text):
            summary_anchor_idx = idx
            break

    if summary_anchor_idx is None:
        return None

    summary_page = blocks[summary_anchor_idx].get('page_index')
    if summary_page is None:
        return None

    option_lines: List[str] = []
    option_range_start = max(0, summary_anchor_idx - 12)
    for block in blocks[option_range_start:summary_anchor_idx]:
        if block.get('page_index') != summary_page:
            continue
        plain = normalize(block.get('text', ''))
        if plain and is_option_line(plain):
            option_lines.append(plain)

    seen_option_lines = set(option_lines)

    start_idx = summary_anchor_idx
    while start_idx > 0:
        prev_block = blocks[start_idx - 1]
        if prev_block.get('page_index') != summary_page:
            break
        prev_plain = normalize(prev_block.get('text', ''))
        if not prev_plain:
            start_idx -= 1
            continue
        lowered_prev = prev_plain.lower()
        if lowered_prev.startswith('questions ') or is_option_line(prev_plain):
            break
        start_idx -= 1

    summary_lines: List[str] = []
    option_lines_after: List[str] = []
    idx = start_idx
    while idx < len(blocks):
        block = blocks[idx]
        if block.get('page_index') != summary_page:
            break
        plain = normalize(block.get('text', ''))
        if not plain:
            idx += 1
            continue
        lowered_plain = plain.lower()
        if is_option_line(plain) and idx >= summary_anchor_idx:
            if plain not in seen_option_lines:
                option_lines_after.append(plain)
                seen_option_lines.add(plain)
            idx += 1
            continue
        if idx > summary_anchor_idx and (
            lowered_plain.startswith('questions ')
            or lowered_plain.startswith('choose the correct letter')
            or lowered_plain.startswith('write the correct letter')
        ):
            break
        summary_lines.append(plain)
        idx += 1

    option_lines = list(set(option_lines + option_lines_after))

    if not summary_lines:
        return None

    first_blank_idx: Optional[int] = None
    for idx, line in enumerate(summary_lines):
        if blank_pattern.search(line):
            first_blank_idx = idx
            break

    if first_blank_idx is not None and first_blank_idx > 0:
        start_from = max(0, first_blank_idx - 1)
        summary_lines = summary_lines[start_from:]

    summary_text = '\n'.join(summary_lines).strip()
    if not summary_text:
        return None

    blank_numbers: List[str] = []

    def blank_replacer(match: re.Match) -> str:
        number = match.group('num')
        blank_numbers.append(number)
        return f'[{number}]'

    display_summary = blank_pattern.sub(blank_replacer, summary_text)
    blank_numbers = list(dict.fromkeys(blank_numbers))

    option_entries: List[Dict[str, str]] = []
    if option_lines:
        raw_options = ' '.join(option_lines).replace('.', ' ')
        tokens = [token for token in re.split(r'\s+', raw_options) if token]
        idx = 0
        seen_letters: set[str] = set()
        while idx < len(tokens):
            token = tokens[idx].strip('.,()')
            if len(token) == 1 and token.isupper() and token not in seen_letters:
                letter = token
                idx += 1
                value_parts: List[str] = []
                while idx < len(tokens):
                    lookahead = tokens[idx].strip('.,()')
                    if len(lookahead) == 1 and lookahead.isupper():
                        break
                    value_parts.append(tokens[idx])
                    idx += 1
                option_text = ' '.join(value_parts).strip()
                if option_text:
                    option_entries.append({'key': letter, 'text': option_text})
                    seen_letters.add(letter)
            else:
                idx += 1

    if not blank_numbers or not option_entries:
        return None

    option_entries.sort(key=lambda option: option['key'])

    return {
        'type': 'summary_completion',
        'text': display_summary,
        'blanks': blank_numbers,
        'options': option_entries
    }

def parse_paragraph_matching(questions_text: str) -> List[Dict[str, Any]]:
    if not questions_text:
        return []

    heading_pattern = re.compile(r'Questions?\s+(\d+)(?:\s*[-\u2013]\s*(\d+))?', re.IGNORECASE)
    matches = list(heading_pattern.finditer(questions_text))
    if not matches:
        return []

    def extract_paragraph_options(text_value: str) -> List[str]:
        if not text_value:
            return []

        normalized_text = text_value.replace('\u2013', '-').replace('\u2014', '-').replace('\u2012', '-')

        letters: List[str] = []

        for start_letter, end_letter in re.findall(r'([A-Z])\s*-[\s]*([A-Z])', normalized_text):
            start_ord = ord(start_letter)
            end_ord = ord(end_letter)
            if start_ord <= end_ord:
                letter_range = range(start_ord, end_ord + 1)
            else:
                letter_range = range(start_ord, end_ord - 1, -1)
            for code in letter_range:
                candidate = chr(code)
                if candidate not in letters:
                    letters.append(candidate)

        for token in re.findall(r'\b([A-Z])\b', normalized_text):
            if token not in letters:
                letters.append(token)

        if letters:
            return letters

        for match in re.finditer(r'(?:paragraphs?|sections?)\s+([A-Z][^.;]*)', text_value, re.IGNORECASE):
            segment = re.split(r'[.;]', match.group(1))[0]
            for token in re.split(r'[;,\s]+', segment):
                cleaned = token.strip().upper()
                if len(cleaned) == 1 and cleaned.isalpha() and cleaned not in letters:
                    letters.append(cleaned)

        return letters

    sections: List[Dict[str, Any]] = []

    for idx, heading in enumerate(matches):
        start_idx = heading.start()
        end_idx = matches[idx + 1].start() if idx + 1 < len(matches) else len(questions_text)
        section_text = questions_text[start_idx:end_idx].strip()
        if not section_text:
            continue

        lowered_section = section_text.lower()
        if not any(keyword in lowered_section for keyword in ('which paragraph', 'which section')):
            continue

        lines = section_text.splitlines()
        title = ''
        instruction_lines: List[str] = []
        statement_lines: List[str] = []
        statement_started = False

        for line in lines:
            raw_line = line.rstrip()
            stripped = raw_line.strip()
            if not stripped:
                continue
            if not title:
                title = normalize_whitespace(stripped)
                continue
            if re.match(r'\d{1,2}\s+', stripped):
                statement_started = True
            if statement_started:
                statement_lines.append(raw_line)
            else:
                instruction_lines.append(stripped)

        if not title or not statement_lines:
            continue

        statements_block = '\n'.join(statement_lines).strip()
        statement_pattern = re.compile(r'(\d{1,2})\s+(.*?)(?=(?:\n\d{1,2}\s)|\Z)', re.DOTALL)
        statements: List[Dict[str, str]] = []
        for stmt_match in statement_pattern.finditer(statements_block):
            number = stmt_match.group(1)
            text_value = normalize_whitespace(stmt_match.group(2))
            if text_value:
                statements.append({'number': number, 'text': text_value})

        if not statements:
            continue

        instructions_clean = [normalize_whitespace(line) for line in instruction_lines if normalize_whitespace(line)]
        options = extract_paragraph_options(' '.join(instructions_clean))

        sections.append({
            'type': 'paragraph_matching',
            'title': title,
            'instructions': instructions_clean,
            'statements': statements,
            'options': options,
            'match_start': start_idx,
            'match_end': end_idx
        })

    return sections


def parse_yes_no_not_given(questions_text: str) -> List[Dict[str, Any]]:
    if not questions_text:
        return []

    lines = questions_text.splitlines()

    def clean(value: str) -> str:
        text_value = value.strip()
        if not text_value:
            return ''
        replacements = (
            ('\u2013', '-'),
            ('\u2014', '-'),
            ('\u2019', "'"),
            ('\u2018', "'"),
        )
        for before, after in replacements:
            text_value = text_value.replace(before, after)
        return re.sub(r'\s+', ' ', text_value)

    sections: List[Dict[str, Any]] = []
    i = 0
    total_lines = len(lines)

    while i < total_lines:
        stripped = lines[i].strip()
        heading_match = re.match(r'Questions?\s+(\d+)(?:\s*[-\u2013]\s*(\d+))?', stripped, re.IGNORECASE)
        if not heading_match:
            i += 1
            continue

        j = i + 1
        section_lines = [lines[i]]
        while j < total_lines and not re.match(r'Questions?\s+\d+', lines[j].strip(), re.IGNORECASE):
            section_lines.append(lines[j])
            j += 1

        section_upper = ' '.join(section_lines).upper()
        if ('YES' in section_upper and 'NOT GIVEN' in section_upper) or (
            'TRUE' in section_upper and 'NOT GIVEN' in section_upper
        ):
            statement_start_idx: Optional[int] = None
            for idx, line in enumerate(section_lines):
                if re.match(r'\s*\d+\s+', line):
                    statement_start_idx = idx
                    break

            if statement_start_idx is not None:
                instruction_lines = section_lines[:statement_start_idx]
                cleaned_instructions = [clean(line) for line in instruction_lines if clean(line)]

                title = cleaned_instructions[0] if cleaned_instructions else clean(section_lines[0])
                additional_instructions = cleaned_instructions[1:] if len(cleaned_instructions) > 1 else []

                statements_block = '\n'.join(section_lines[statement_start_idx:])
                statement_pattern = re.compile(r'(\d+)\s+(.*?)(?=(?:\n\d+\s)|\Z)', re.DOTALL)
                statements: List[Dict[str, str]] = []
                for match in statement_pattern.finditer(statements_block.strip()):
                    number = match.group(1)
                    text_value = clean(match.group(2))
                    if text_value:
                        statements.append({'number': number, 'text': text_value})

                if statements:
                    options = ['YES', 'NO', 'NOT GIVEN'] if 'YES' in section_upper else ['TRUE', 'FALSE', 'NOT GIVEN']
                    sections.append({
                        'type': 'yes_no_not_given',
                        'title': title,
                        'instructions': additional_instructions,
                        'statements': statements,
                        'options': options
                    })

        i = j

    return sections


def parse_questions(questions_text: str, blocks: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    questions: List[Dict[str, Any]] = []
    consumed_numbers: set[str] = set()
    consumed_ranges: List[Tuple[int, int]] = []
    question_blocks = collect_question_blocks(questions_text, blocks)

    def is_consumed(start: int, end: int) -> bool:
        if start < 0 or end < 0:
            return False
        for r_start, r_end in consumed_ranges:
            if max(start, r_start) < min(end, r_end):
                return True
        return False

    summary = parse_summary_completion(questions_text, blocks)
    if summary:
        questions.append(summary)
        consumed_numbers.update(summary['blanks'])

    paragraph_sections = parse_paragraph_matching(questions_text)
    for section in paragraph_sections:
        start = section.get('match_start', -1)
        end = section.get('match_end', -1)
        if is_consumed(start, end):
            continue
        section_numbers = {statement['number'] for statement in section['statements']}
        if section_numbers & consumed_numbers:
            continue
        questions.append(section)
        consumed_numbers.update(section_numbers)
        if start >= 0 and end >= 0:
            consumed_ranges.append((start, end))

    # Parse fill-in-the-blank (Complete the sentences / Complete the summary style)
    def parse_fill_in_blanks(text: str, block_texts: List[str]) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        if not text:
            return results

        candidate_blocks: List[str] = []
        lowered_phrases = ('complete the summary', 'complete the sentences')

        if block_texts:
            found_header = False
            for block_text in block_texts:
                normalized_block = normalize_whitespace(block_text)
                if not normalized_block:
                    continue
                lowered = normalized_block.lower()
                if not found_header and any(phrase in lowered for phrase in lowered_phrases):
                    found_header = True

                if not found_header:
                    continue

                candidate_blocks.append(block_text)

                if re.search(r'questions?\s+\d+', lowered, re.IGNORECASE):
                    break

        segment_text = '\n'.join(candidate_blocks) if candidate_blocks else text
        segment_text = re.split(r'Questions?\s+\d+', segment_text, maxsplit=1, flags=re.IGNORECASE)[0]

        pattern = re.compile(
            r'(?P<num>\d{1,2})\s*(?:[).:-])?\s*(?P<blank>_{2,})(?P<after>[^0-9_]{0,200})',
            re.DOTALL
        )

        instruction_markers = (
            'complete the summary',
            'complete the sentences',
            'write your answers'
        )

        def strip_instruction_text(value: str) -> str:
            lowered = value.lower()
            for marker in instruction_markers:
                idx = lowered.rfind(marker)
                if idx != -1:
                    value = value[idx + len(marker):]
                    lowered = value.lower()
            return value.strip()

        seen_numbers: set[str] = set()

        for match in pattern.finditer(segment_text):
            num = match.group('num')
            if num in seen_numbers:
                continue
            start_idx = match.start('num')

            prefix_chunk = segment_text[max(0, start_idx - 200):start_idx]
            prefix_clean = re.sub(r'_+', ' ', prefix_chunk)
            prefix_clean = normalize_whitespace(prefix_clean)
            prefix_clean = strip_instruction_text(prefix_clean)
            prefix_words = prefix_clean.split()
            prefix = ' '.join(prefix_words[-8:])
            if prefix:
                prefix = re.sub(r'\b\d{1,2}\b', '', prefix)
                prefix = re.split(r'[.;!?]', prefix)[-1].strip()
                prefix = normalize_whitespace(prefix)

            suffix_raw = match.group('after') or ''
            suffix_raw_stripped = suffix_raw.lstrip()
            post_blank_punct = ''
            if suffix_raw_stripped and suffix_raw_stripped[0] in '.;,!?':
                post_blank_punct = suffix_raw_stripped[0]
                suffix_raw_stripped = suffix_raw_stripped[1:]

            suffix_clean = re.sub(r'_+', ' ', suffix_raw_stripped)
            suffix_clean = normalize_whitespace(suffix_clean)
            suffix_clean = strip_instruction_text(suffix_clean)
            suffix_words = suffix_clean.split()
            suffix = ' '.join(suffix_words[:8])
            if suffix:
                suffix = re.sub(r'\b\d{1,2}\b', '', suffix)
                suffix = re.split(r'[.;!?]', suffix)[0].strip()
                suffix = normalize_whitespace(suffix)

            snippet_parts: List[str] = []
            if prefix:
                snippet_parts.append(prefix)

            blank_repr = '____'
            if post_blank_punct:
                blank_repr = f'____{post_blank_punct}'
            snippet_parts.append(blank_repr)

            append_suffix = bool(suffix)
            if append_suffix and post_blank_punct and suffix and suffix[0].isalpha() and suffix[0].isupper():
                append_suffix = False

            if append_suffix:
                snippet_parts.append(suffix)

            snippet = ' '.join(snippet_parts).strip()
            snippet = snippet.strip('-:;,')

            lowered_snippet = snippet.lower()
            if not snippet or 'write your answers' in lowered_snippet or 'complete the summary' in lowered_snippet:
                continue

            results.append({'type': 'fill_blank', 'number': num, 'text': snippet, 'match_start': match.start(), 'match_end': match.end()})
            seen_numbers.add(num)

        if results:
            return results

        # Fallback: basic chunking if underscore matching fails
        number_matches = list(re.finditer(r'\b(\d{1,2})\b', segment_text))
        for idx, nm in enumerate(number_matches):
            num = nm.group(1)
            if num in seen_numbers:
                continue

            start = nm.end()
            end = number_matches[idx + 1].start() if idx + 1 < len(number_matches) else len(segment_text)
            chunk = segment_text[start:end]
            if '_' not in chunk:
                continue

            cleaned = normalize_whitespace(chunk)
            if not cleaned:
                continue

            results.append({'type': 'fill_blank', 'number': num, 'text': cleaned, 'match_start': nm.start(), 'match_end': end})
            seen_numbers.add(num)

        return results

    fills = parse_fill_in_blanks(questions_text, question_blocks)
    for f in fills:
        start = f.get('match_start', -1)
        end = f.get('match_end', -1)
        if f['number'] in consumed_numbers or is_consumed(start, end):
            continue
        questions.append(f)
        consumed_numbers.add(f['number'])
        if start >= 0 and end >= 0:
            consumed_ranges.append((start, end))

    yes_no_sections = parse_yes_no_not_given(questions_text)
    for section in yes_no_sections:
        # This parser is section-based, so we assume it doesn't overlap badly
        questions.append(section)
        consumed_numbers.update(statement['number'] for statement in section['statements'])

    for single in parse_single_choice(questions_text):
        start = single.get('match_start', -1)
        end = single.get('match_end', -1)
        if single['number'] in consumed_numbers or is_consumed(start, end):
            continue
        questions.append(single)
        if start >= 0 and end >= 0:
            consumed_ranges.append((start, end))

    # Clean up temporary keys from question dicts
    for q in questions:
        q.pop('match_start', None)
        q.pop('match_end', None)

    return questions


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        flash('No file part')
        return redirect(url_for('index'))

    file = request.files['file']
    if file.filename == '':
        flash('No selected file')
        return redirect(url_for('index'))

    if not allowed_file(file.filename):
        flash('Allowed file types are pdf')
        return redirect(url_for('index'))

    upload_folder = Path(app.config['UPLOAD_FOLDER'])
    upload_folder.mkdir(parents=True, exist_ok=True)

    filename = secure_filename(file.filename)
    filepath = upload_folder / filename
    file.save(filepath)

    full_text, blocks = extract_text_and_blocks(filepath)
    passage, question_text = split_passage_questions(full_text)
    passage_blocks = collect_passage_blocks(passage, blocks)
    structured_passage = structure_passage(passage, passage_blocks)
    parsed_questions = parse_questions(question_text, blocks)

    flash('File successfully uploaded')
    return render_template('passage.html', passage=structured_passage, questions=parsed_questions)


if __name__ == '__main__':
    app.run(debug=True)
