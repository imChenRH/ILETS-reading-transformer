# Batch PDF Testing

## Overview

This directory contains a comprehensive batch testing program for IELTS Reading PDFs. The program tests all PDFs to identify potential bugs in passage formatting, question recognition, and cross-contamination between question types.

## Files

- **`batch_test_pdfs.py`**: Main batch testing program
- **`PDF_BATCH_TEST_REPORT.md`**: Detailed report of testing results and bug fixes
- **`test_results*.json`**: Test results in JSON format (gitignored)

## Quick Start

### Run All Tests

```bash
python batch_test_pdfs.py
```

### Run Quick Test (First 20 PDFs)

```bash
python batch_test_pdfs.py --max 20
```

### Verbose Output

```bash
python batch_test_pdfs.py --verbose
```

### Save Results to JSON

```bash
python batch_test_pdfs.py --json results.json
```

## What It Tests

### 1. Left Side (Passage) Formatting
- ✅ Title recognition and formatting
- ✅ Paragraph structure and lettering
- ✅ Prevention of instruction text leaking into passage
- ✅ Detection and merging of standalone subheadings

### 2. Right Side (Questions) Formatting
- ✅ Question completeness (all questions detected)
- ✅ Question type recognition (10+ IELTS question types)
- ✅ Duplicate question number detection
- ✅ Prevention of cross-contamination between question types

### 3. Matching Headings (Special Attention)
- ✅ Roman numeral headings recognition (i, ii, iii, etc.)
- ✅ Paragraph letter matching (A, B, C, etc.)
- ✅ Instructions parsing

## Test Results

Current Status: **163/163 PDFs PASS (100%)**

### Question Types Detected

| Question Type | Count |
|--------------|-------|
| Single Choice (MCQ) | 209 |
| Summary Completion | 96 |
| Yes/No/Not Given | 95 |
| Short Answer | 78 |
| Matching Features | 50 |
| Paragraph Matching | 40 |
| Matching Headings | 25 |
| Fill in the Blank | 17 |
| Diagram Label Completion | 3 |

## Bug Fixes

Two bugs were identified and fixed during testing:

### Bug #1: TRUE/FALSE/NOT GIVEN Not Detected
**File**: `25. P1 - The Rise and Fall of Detective Stories`
**Fix**: Updated regex pattern to exclude period (.) from option separators
**Status**: ✅ Fixed

### Bug #2: Standalone Subheadings
**File**: `60. P3 - A closer examination of a study on verbal and non-verbal messages`
**Fix**: Added logic to merge subheadings with following paragraphs
**Status**: ✅ Fixed

See `PDF_BATCH_TEST_REPORT.md` for detailed information.

## Usage Examples

### Example 1: Quick Validation
Test first 20 PDFs to quickly validate changes:
```bash
python batch_test_pdfs.py --max 20
```

### Example 2: Full Test with Report
Run full test and save results:
```bash
python batch_test_pdfs.py --json full_test.json
```

### Example 3: Debug Specific Issue
Run in verbose mode to see all details:
```bash
python batch_test_pdfs.py --verbose --max 5
```

## Output Format

The program outputs:
1. Progress for each PDF tested
2. Errors and warnings for failed tests
3. Summary statistics
4. Issues categorized by type
5. Detailed failure information

Example output:
```
================================================================================
BATCH PDF TESTING - Testing 163 PDFs
================================================================================

[1/163] Testing: 1. P1 - A Brief History of Tea 茶叶简史【高】.pdf
    ✅ PASS
[2/163] Testing: 10. P1 - Maori Fish Hooks 毛利鱼钩【次】.pdf
    ✅ PASS
...

================================================================================
BATCH TEST SUMMARY
================================================================================

✅ Passed:  163/163 (100.0%)
❌ Failed:  0/163 (0.0%)
```

## Integration with CI/CD

This test program can be integrated into CI/CD pipelines:

```yaml
# Example GitHub Actions
- name: Run PDF Batch Tests
  run: |
    pip install -r requirements.txt
    python batch_test_pdfs.py --json test_results.json
```

## Troubleshooting

### Common Issues

1. **Module not found error**
   - Ensure you've installed dependencies: `pip install -r requirements.txt`

2. **PDF not found errors**
   - Ensure PDFs are in the `pdf/` directory
   - Check file paths are correct

3. **Timeout errors**
   - Some PDFs may take longer to process
   - This is normal for complex PDFs with many questions

## Contributing

When adding new features or fixing bugs:

1. Run the batch test before making changes
2. Make your changes
3. Run the batch test again
4. Ensure no new failures are introduced
5. Update this README if needed

## License

Part of the IELTS Reading Transformer project.
