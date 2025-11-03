# Quick Start Guide

## Setup (5 minutes)

1. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Start the application:**
   ```bash
   python app.py
   ```

3. **Open your browser:**
   - Navigate to: http://localhost:5000

## Using the Application

### Step 1: Upload PDF
- Click "Choose File" and select your IELTS reading PDF
- Click "Upload" to process the file

### Step 2: View Results
- The passage will appear on the left panel with:
  - Title
  - Introduction (if present)
  - Paragraphs labeled A, B, C, etc.

- Questions will appear on the right panel with:
  - Appropriate input controls for each question type
  - Options displayed clearly

### Supported Question Types

1. **Single/Multiple Choice** - Radio buttons with A, B, C, D options
2. **Summary Completion** - Dropdown menus with word bank
3. **Paragraph Matching** - "Which paragraph contains..." statements
4. **True/False/Not Given** - Three-option radio buttons
5. **Yes/No/Not Given** - Three-option radio buttons  
6. **Fill-in-the-Blank** - Text input fields

## Testing the Installation

Run the test script to verify everything is working:
```bash
python test_functionality.py
```

You should see:
```
✓ All imports successful
✓ Passage extracted: ...
✓ Questions extracted: ...
✓ All core functionality tests passed!
```

## Troubleshooting

### "Module not found" error
```bash
pip install -r requirements.txt
```

### Port 5000 already in use
Edit `app.py` and change the last line to:
```python
app.run(debug=True, port=8080)
```

### PDF not processing correctly
- Ensure the PDF is text-based (not a scanned image)
- Check that the PDF follows standard IELTS format
- Verify the PDF contains clear section markers

## Example Files

Check the `example/` directory for sample output HTML files showing how processed tests look.

## Need Help?

- Check the main README.md for detailed documentation
- Open an issue on GitHub
- Review the example HTML files in the `example/` directory
