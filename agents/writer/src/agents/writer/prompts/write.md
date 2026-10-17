Write a {format} in a {style} style of about {length_words} words.

Facts come only from the research notes below. Do not add numbers, dates, names, places,
programmes or claims that the notes do not contain. If the notes are thin, write a shorter piece
rather than invent anything. Reach the length by explaining what each note means, why it matters
and how the notes relate to each other — never by adding facts.

Structure it as an introduction, {sections} sections with "##" headings, and a short conclusion.
Cite sources inline as [n], where n is the source number, and only for what that source's note says.

Return a JSON object with exactly these keys:
- "title": a headline of at most 100 characters
- "summary": two sentences
- "article_md": the full text in Markdown, starting with a level-1 heading

Research notes:
{notes}

Sources:
{sources}
