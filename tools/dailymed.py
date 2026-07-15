"""DailyMed wrapper — retrieve structured product label information for a drug.

The wrapper finds the first matching SPL, downloads its full XML label, and
extracts important sections including boxed warnings, indications, dosage,
contraindications, and warnings and precautions.
"""
import requests
import xml.etree.ElementTree as ET

BASE = "https://dailymed.nlm.nih.gov/dailymed/services/v2"


def get_label(drug_name):
    """Return {'drug', 'setid', 'title', 'url'}; fields are None if not found."""
    out = {"drug": drug_name, "setid": None, "title": None, "url": None}
    r = requests.get(f"{BASE}/spls.json",
                     params={"drug_name": drug_name, "pagesize": 1}, timeout=30)
    if r.status_code == 404:
        return out

    r.raise_for_status()
    data = r.json().get("data", [])
    if data:
        out["setid"] = data[0].get("setid")
        out["title"] = data[0].get("title")
        out["url"] = (f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm"
                      f"?setid={out['setid']}")
    return out


def get_full_label_xml(setid):
    """Return the full DailyMed SPL XML for a set ID."""
    response = requests.get(
        f"{BASE}/spls/{setid}.xml",
        timeout=30
    )
    response.raise_for_status()
    return response.text


def _clean_text(element):
    """Combine all text inside an XML element into one clean string."""
    if element is None:
        return None

    text = " ".join(element.itertext())
    return " ".join(text.split())


def extract_label_sections(xml_text):
    """Extract important prescribing sections from DailyMed SPL XML."""
    root = ET.fromstring(xml_text)

    namespace = {
        "hl7": "urn:hl7-org:v3"
    }

    wanted_codes = {
        "34066-1": "warning",
        "34067-9": "indications",
        "34068-7": "dosage",
        "34070-3": "contraindications",
        "43685-7": "warnings_and_precautions",
    }

    results = {
        "warning": None,
        "indications": None,
        "dosage": None,
        "contraindications": None,
        "warnings_and_precautions": None,
    }

    sections = root.findall(
        ".//hl7:structuredBody/hl7:component/hl7:section",
        namespace
    )

    for section in sections:
        code_element = section.find("hl7:code", namespace)

        if code_element is None:
            continue

        section_code = code_element.get("code")

        if section_code not in wanted_codes:
            continue

        field_name = wanted_codes[section_code]
        results[field_name] = _get_section_text(section, namespace)

    return results


def _get_section_text(section, namespace):
    """Return the best available text for a DailyMed section."""

    # First choice: full text directly inside the section.
    direct_text = section.find("hl7:text", namespace)

    if direct_text is not None:
        return _clean_text(direct_text)

    # Second choice: concise highlights summary.
    excerpt_text = section.find(
        "hl7:excerpt/hl7:highlight/hl7:text",
        namespace
    )

    if excerpt_text is not None:
        return _clean_text(excerpt_text)

    # Final fallback: combine text from nested subsections.
    pieces = []

    for nested_section in section.findall(
        ".//hl7:component/hl7:section",
        namespace
    ):
        nested_text = nested_section.find("hl7:text", namespace)

        if nested_text is not None:
            cleaned = _clean_text(nested_text)

            if cleaned:
                pieces.append(cleaned)

    if pieces:
        return " ".join(pieces)

    return None

def get_dailymed_label(drug_name):
    """Return DailyMed metadata and important prescribing sections."""
    label = get_label(drug_name)

    if not label["setid"]:
        return {
            **label,
            "warning": None,
            "indications": None,
            "dosage": None,
            "contraindications": None,
            "warnings_and_precautions": None,
        }

    xml_text = get_full_label_xml(label["setid"])
    sections = extract_label_sections(xml_text)

    return {
        **label,
        **sections,
    }

