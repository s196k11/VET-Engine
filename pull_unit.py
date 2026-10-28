import json
import re

import requests
from bs4 import BeautifulSoup


UNIT_CODE = "SIRXOSM003"
UNIT_BUNDLE_URL = "https://training.gov.au/api/content/bundle/da5b666f-5b06-4fa4-8585-9f49ef9331d6"
ASSESSMENT_BUNDLE_URL = "https://training.gov.au/api/content/bundle/3320337b-0095-4f0e-9c8f-a019c0f3cf02"
HEADERS = {"Accept": "application/json", "User-Agent": "Mozilla/5.0"}


def get_json(url):
    response = requests.get(url, headers=HEADERS)
    response.raise_for_status()
    return response.json()


def parse_performance_criteria(html):
    elements = []
    current_element = None

    for row in BeautifulSoup(html, "html.parser").find_all("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["td", "th"])]
        if not cells:
            continue

        if len(cells) >= 4 and cells[0].isdigit():
            current_element = {
                "number": cells[0],
                "title": cells[1],
                "performance_criteria": []
            }
            elements.append(current_element)
            if "." in cells[2]:
                current_element["performance_criteria"].append({"number": cells[2], "text": cells[3]})
        elif current_element and len(cells) >= 2 and "." in cells[0]:
            current_element["performance_criteria"].append({"number": cells[0], "text": cells[1]})

    return elements


def parse_foundation_skills(html):
    skills = []
    for row in BeautifulSoup(html, "html.parser").find_all("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["td", "th"])]
        if len(cells) >= 2:
            skills.append({"skill": cells[0], "description": cells[1]})
    return skills


def parse_performance_evidence(html):
    evidence = []
    current = None
    pending_detail = None
    detail_depths = {}
    last_detail = None
    group_parent = None

    for row in BeautifulSoup(html, "html.parser").find_all("tr"):
        parts = []
        for cell_index, cell in enumerate(row.find_all(["td", "th"])):
            blocks = cell.find_all(["p", "li"])
            if blocks:
                parts.extend(
                    (cell_index, text)
                    for block in blocks
                    if not (block.name == "p" and block.find_parent("li"))
                    if (text := block.get_text(" ", strip=True))
                )
            elif (text := cell.get_text(" ", strip=True)):
                parts.append((cell_index, text))

        if not parts:
            continue

        root = re.match(r"^(\d+)\.\s*(.*)$", parts[0][1])
        if parts[0][0] == 0 and root:
            current = {
                "id": f"PE{len(evidence) + 1}",
                "number": root.group(1),
                "text": root.group(2),
                "details": []
            }
            evidence.append(current)
            pending_detail = last_detail = group_parent = None
            detail_depths = {}
            current["text"] = " ".join([current["text"], *(text for _, text in parts[1:])]).strip()
            continue

        if current is None:
            continue

        for cell_index, text in parts:
            marker = re.match(r"^([a-z]|[ivxlcdm]+)\.\s*(.*)$", text, re.I)
            if pending_detail and not marker:
                pending_detail["text"] = text
                pending_detail = None
                continue

            if marker:
                detail = {"number": marker.group(1), "text": marker.group(2), "children": []}
                parent = detail_depths.get(cell_index - 1) if cell_index >= 2 else None
                parent = parent or group_parent or (
                    last_detail if last_detail and last_detail["text"].endswith(":") else None
                )
                (parent["children"] if parent else current["details"]).append(detail)
                detail_depths[cell_index] = detail
                detail_depths = {depth: node for depth, node in detail_depths.items() if depth <= cell_index}
                last_detail = detail
                if not detail["text"]:
                    pending_detail = detail
            else:
                detail = {"text": text, "children": []}
                current["details"].append(detail)
                detail_depths = {}
                last_detail = detail
                group_parent = detail if text.endswith(":") else None

    return evidence


def parse_knowledge_evidence(html):
    evidence = []
    for item in BeautifulSoup(html, "html.parser").find_all("li"):
        if item.find_parent("li"):
            continue

        nested = item.find("ul")
        children = [
            {"text": child.get_text(" ", strip=True)}
            for child in nested.find_all("li", recursive=False)
        ] if nested else []
        if nested:
            nested.extract()

        evidence.append({
            "id": f"KE{len(evidence) + 1}",
            "text": item.get_text(" ", strip=True),
            "children": children
        })

    return evidence


unit_bundle = get_json(UNIT_BUNDLE_URL)
assessment_bundle = get_json(ASSESSMENT_BUNDLE_URL)
data = {
    "unit_code": UNIT_CODE,
    "elements": [],
    "foundation_skills": [],
    "performance_evidence": [],
    "knowledge_evidence": [],
    "assessment_conditions": ""
}

for item in unit_bundle.get("items", []):
    content = item.get("content", "")
    if item.get("contentType") == "PerformanceCriteria":
        data["elements"] = parse_performance_criteria(content)
    elif item.get("contentType") == "FoundationSkills":
        data["foundation_skills"] = parse_foundation_skills(content)

for item in assessment_bundle.get("items", []):
    content = item.get("content", "")
    content_type = item.get("contentType")
    if content_type == "PerformanceEvidence":
        data["performance_evidence"] = parse_performance_evidence(content)
    elif content_type == "KnowledgeEvidence":
        data["knowledge_evidence"] = parse_knowledge_evidence(content)
    elif content_type == "AssessmentConditions":
        data["assessment_conditions"] = BeautifulSoup(content, "html.parser").get_text(" ", strip=True)

file_name = f"{UNIT_CODE}.json"
with open(file_name, "w", encoding="utf-8") as file:
    json.dump(data, file, indent=4, ensure_ascii=False)

print(f"\nCreated {file_name}")