# ECONOVA English-only rule (permanent)

Effective 2026-11-13. ECONOVA is an English-only economics learning platform.

## What must be in English
Everything a person can see in the application, for students and administrators alike:
- pages, navigation, buttons, form labels, placeholders, tooltips, `aria-*` labels, notifications, validation and error messages
- JavaScript-generated text and server-generated JSON messages
- course metadata, lesson materials (all levels), worked examples, SDG cases, sources metadata shown to users
- formative quizzes, final assessments, the diagnostic assessment, answer choices and explanations (including private answer-key explanations)
- simulation titles, input labels, result labels, units and interpretation notes
- AI system prompts and structured-response instructions; every prompt must include the shared English-only instruction
  (`econova/ai/language.py`) so model output is English even when a student writes in another language
- capstone prompts, rubrics and feedback labels, debate interfaces, recommendations, learning reports
- CLI output that administrators read (`check-content`, `review-package`, release commands)

Courses c04–c09 and every new feature must be written in English from the start. Do not draft in another language and translate later.

## What may stay in another language
- developer comments, docstrings and Jinja comments (`{# ... #}`)
- internal planning and review documents under `docs/`, and reports to the project owner
- regular expressions or keyword lists whose purpose is to detect non-English input; mark each such line with `# i18n-allow`
  (kept rare; a test caps the count)

## Style
Clear, academically appropriate American English for high-school students. Use second person for students, concise neutral wording for admins,
and the fixed economics terminology already used in c01–c03 (e.g. "quantity demanded", "deadweight loss", "Pigouvian tax").
Hypothetical numbers are labeled "Hypothetical example". Use US-dollar amounts and internationally understandable settings.
Do not change identifiers, routes, JSON keys or status values for translation.

## Enforcement
`tests/test_english_only.py` fails if Hangul appears in templates, JavaScript strings, CSS generated text, Python user-facing string constants,
any `content/` JSON string, simulation labels, AI prompts, or the rendered student, admin and preview pages. Run the full test suite before every commit.

## Assessments after text changes
Any change to a public question's wording changes its fingerprint. Regenerate the public file and the private answer key together
(`private_content.split`), raise the assessment `version` and each changed question's `version`, and confirm `flask --app app check-content`
reports that every assessment has a valid answer key. Private answers and explanations never enter the repository.
