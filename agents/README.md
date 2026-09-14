# C4 · agents

Six independent plug-ins, each its own installable package in the `agents` namespace, discovered by the worker through the `gp.agents` entry point group.

| Agent | Family | Input → output | External dependency (via port) | Status |
|---|---|---|---|---|
| researcher | create | topic, num_sources → notes, sources | `SearchPort` (Tavily / SerpAPI) | skeleton works on fakes · real search W3 |
| writer | create | notes, length, style, format → title, summary, article_md | `LLMPort` (OpenAI) | skeleton + reformat retry · prompts W3 |
| image | create | prompt/title → image paths | `ImagePort` (provider TBD, R1) | skeleton · provider W5 |
| video | create | script, voice, resolution → mp4 path, duration | `TTSPort` + `exporters.video` (FFmpeg) | renders a real MP4 · slides W5 |
| publisher | distribute · approval | file, platform, metadata → remote_url | `PublishPort` (YouTube / Drive) | skeleton · real uploads W6 |
| email | distribute · approval | recipients, subject, body, links → message_id | `EmailPort` (Gmail / SMTP) | skeleton · Gmail W7 |

Adding one: [docs/ADDING_AN_AGENT.md](../docs/ADDING_AN_AGENT.md).
