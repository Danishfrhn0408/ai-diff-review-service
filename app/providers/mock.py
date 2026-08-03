import re
from typing import Any

from app.services.diff_parser import (
    parse_added_lines,
)


CREDENTIAL_PATTERN = re.compile(
    r"""(api[_-]?key|secret|token)"""
    r"""\s*[:=]\s*"""
    r"""['"][A-Za-z0-9_\-]{16,}['"]""",
    re.IGNORECASE,
)

SQL_STRING_PATTERN = re.compile(
    r"""
    (['"`])
    (?:
        (?!\1).
    )*
    \b(?:SELECT|INSERT|UPDATE|DELETE)\b
    (?:
        (?!\1).
    )*
    \1
    """,
    re.IGNORECASE | re.VERBOSE,
)

LOOSE_NULL_PATTERN = re.compile(
    r"""
    (?:
        (?<![=])==(?!=)
        |
        (?<![!])!=(?!=)
    )
    \s*null
    """,
    re.VERBOSE,
)


def create_finding(
    rule_id: str,
    path: str,
    line_number: int,
    severity: str,
    category: str,
    title: str,
    evidence: str,
) -> dict[str, Any]:
    return {
        "id": (
            f"{rule_id}:"
            f"{path}:"
            f"{line_number}"
        ),
        "ruleId": rule_id,
        "path": path,
        "line": line_number,
        "severity": severity,
        "category": category,
        "title": title,
        "evidence": evidence,
    }


def contains_sql_concatenation(
    text: str,
) -> bool:
    for match in SQL_STRING_PATTERN.finditer(
        text
    ):
        left_side = text[
            :match.start()
        ].rstrip()

        right_side = text[
            match.end():
        ].lstrip()

        if (
            left_side.endswith("+")
            or right_side.startswith("+")
        ):
            return True

    return False


def is_empty_catch_block(
    added_line: dict[str, Any],
) -> bool:
    text = added_line["text"]

    catch_match = re.search(
        r"""
        \bcatch
        \s*
        (?:\([^)]*\))?
        \s*
        \{
        """,
        text,
        re.VERBOSE,
    )

    if catch_match is None:
        return False

    body_parts: list[str] = []

    remaining_text = text[
        catch_match.end():
    ]

    if "}" in remaining_text:
        catch_body = remaining_text.split(
            "}",
            maxsplit=1,
        )[0]

        return not catch_body.strip()

    body_parts.append(remaining_text)

    all_lines = added_line["allLines"]
    start_index = added_line["index"]

    for raw_line in all_lines[
        start_index + 1:
        start_index + 30
    ]:
        if raw_line.startswith(
            "diff --git "
        ):
            break

        if raw_line.startswith("@@ "):
            break

        if (
            raw_line.startswith("-")
            and not raw_line.startswith("---")
        ):
            continue

        if (
            raw_line.startswith("+")
            and not raw_line.startswith("+++")
        ):
            content = raw_line[1:]

        elif raw_line.startswith(" "):
            content = raw_line[1:]

        else:
            content = raw_line

        if "}" in content:
            before_closing = content.split(
                "}",
                maxsplit=1,
            )[0]

            body_parts.append(
                before_closing
            )

            full_body = "\n".join(
                body_parts
            )

            return not full_body.strip()

        body_parts.append(content)

    return False


def scan_mock_chunk(
    diff: str,
) -> list[dict[str, Any]]:
    results: list[
        dict[str, Any]
    ] = []

    added_lines = parse_added_lines(
        diff
    )

    for added_line in added_lines:
        path = added_line["path"]
        line_number = added_line["line"]
        text = added_line["text"]
        lowercase_text = text.lower()

        if "eval(" in text:
            results.append(
                create_finding(
                    "MOCK-001",
                    path,
                    line_number,
                    "critical",
                    "security",
                    "eval usage",
                    text,
                )
            )

        if CREDENTIAL_PATTERN.search(text):
            results.append(
                create_finding(
                    "MOCK-002",
                    path,
                    line_number,
                    "critical",
                    "security",
                    "hardcoded credential",
                    text,
                )
            )

        if contains_sql_concatenation(
            text
        ):
            results.append(
                create_finding(
                    "MOCK-003",
                    path,
                    line_number,
                    "high",
                    "security",
                    "SQL string concatenation",
                    text,
                )
            )

        if is_empty_catch_block(
            added_line
        ):
            results.append(
                create_finding(
                    "MOCK-004",
                    path,
                    line_number,
                    "high",
                    "correctness",
                    "swallowed exception",
                    text,
                )
            )

        if LOOSE_NULL_PATTERN.search(text):
            results.append(
                create_finding(
                    "MOCK-005",
                    path,
                    line_number,
                    "medium",
                    "correctness",
                    "loose null comparison",
                    text,
                )
            )

        if (
            "JSON.parse(JSON.stringify("
            in text
        ):
            results.append(
                create_finding(
                    "MOCK-006",
                    path,
                    line_number,
                    "medium",
                    "performance",
                    "deep-clone via JSON",
                    text,
                )
            )

        if "console.log(" in text:
            results.append(
                create_finding(
                    "MOCK-007",
                    path,
                    line_number,
                    "low",
                    "style",
                    "console.log left in",
                    text,
                )
            )

        if (
            "TODO" in text
            or "FIXME" in text
        ):
            results.append(
                create_finding(
                    "MOCK-008",
                    path,
                    line_number,
                    "low",
                    "style",
                    "unresolved marker",
                    text,
                )
            )

        injection_found = (
            "ignore previous instructions"
            in lowercase_text
            or "disregard all prior"
            in lowercase_text
            or "you are now"
            in lowercase_text
        )

        if injection_found:
            results.append(
                create_finding(
                    "MOCK-INJ",
                    path,
                    line_number,
                    "critical",
                    "security",
                    "prompt-injection content",
                    text,
                )
            )

    return results


def sort_and_deduplicate(
    findings: list[
        dict[str, Any]
    ],
) -> list[dict[str, Any]]:
    unique_findings = {
        finding["id"]: finding
        for finding in findings
    }

    return sorted(
        unique_findings.values(),
        key=lambda finding: (
            finding["path"],
            finding["line"],
            finding["ruleId"],
        ),
    )