"""Parse course descriptions and credit exclusions from kurser.dtu.dk course pages.

The description sections ("General course objectives", "Learning objectives",
"Content") are rendered as `div.bar` headings followed by sibling text. The
"Not applicable together with" field is a row of the `.box.information` table.
Both English and Danish labels are recognised so either page language works.
"""

import re

from bs4 import BeautifulSoup, NavigableString, Tag

SECTION_LABELS = {
    "general_objectives": {"general course objectives", "overordnede kursusmål"},
    "learning_objectives": {"learning objectives", "læringsmål"},
    "content": {"content", "course content", "indhold", "kursusindhold"},
}

NOT_APPLICABLE_LABELS = {"not applicable together with", "pointspærring"}

# Course numbers are five characters with at least one digit (01001, 42S01, KU002)
COURSE_CODE_PATTERN = re.compile(r"(?<![0-9A-Z])(?=[0-9A-Z]{0,4}[0-9])[0-9A-Z]{5}(?![0-9A-Z])")

MAX_SECTION_CHARS = 6000
HEADING_TAGS = {"h2", "h3", "h4"}


def clean_text(text: str) -> str:
    """Drop soft hyphens and collapse whitespace."""
    return " ".join(text.replace("\xad", "").split())


def normalize_label(text: str) -> str:
    return clean_text(text).rstrip(":").strip().lower()


def extract_course_codes(text: str) -> list[str]:
    """Return every course number in a field such as '(01911.01922)/01003/'.

    DTU writes combinations with '.' (all of) and alternatives with '/'. Any
    course named in the field counts as overlapping, so the structure is ignored.
    """
    return list(dict.fromkeys(COURSE_CODE_PATTERN.findall(clean_text(text))))


def _is_heading(node) -> bool:
    return isinstance(node, Tag) and (node.name in HEADING_TAGS or "bar" in (node.get("class") or []))


def _contains_heading(node) -> bool:
    return isinstance(node, Tag) and (_is_heading(node) or node.find(_is_heading) is not None)


def _section_text(heading: Tag) -> str:
    parts = []
    for sibling in heading.next_siblings:
        if _contains_heading(sibling):
            break
        if isinstance(sibling, NavigableString):
            parts.append(str(sibling))
        elif isinstance(sibling, Tag) and sibling.name not in {"script", "style"}:
            parts.append(sibling.get_text(" "))
    return clean_text(" ".join(parts))[:MAX_SECTION_CHARS]


def parse_course_page(html: str) -> dict:
    """Extract description sections and 'Not applicable together with' courses.

    Missing sections are omitted from the result rather than set to empty text.
    """
    soup = BeautifulSoup(html, "lxml")
    details = {}

    for heading in soup.find_all(_is_heading):
        label = normalize_label(heading.get_text(" "))
        for field, labels in SECTION_LABELS.items():
            if label in labels and field not in details:
                text = _section_text(heading)
                if text:
                    details[field] = text

    for row in soup.find_all("tr"):
        cells = row.find_all(["td", "th"], recursive=False)
        if len(cells) < 2 or normalize_label(cells[0].get_text(" ")) not in NOT_APPLICABLE_LABELS:
            continue
        raw = clean_text(" ".join(cell.get_text(" ") for cell in cells[1:]))
        details["not_applicable_raw"] = raw
        details["not_applicable_with"] = extract_course_codes(raw)
        break

    return details
