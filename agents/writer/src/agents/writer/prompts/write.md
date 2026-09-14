Write a {format} in a {style} style, about {length_words} words long.

Use only the research notes below. Cite sources inline as [n] where n is the source number.

Return a JSON object with exactly these keys:
- "title": a headline of at most 100 characters
- "summary": two sentences
- "article_md": the full text in Markdown, starting with a level-1 heading

Research notes:
{notes}

Sources:
{sources}
