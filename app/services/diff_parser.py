import re
from typing import Any, Optional

from app.config import CHUNK_BYTES


def is_valid_unified_diff(
    diff: str,
) -> bool:
    if not diff or not diff.strip():
        return False

    lines = diff.splitlines()

    has_diff_header = any(
        line.startswith("diff --git ")
        for line in lines
    )

    has_old_file = any(
        line.startswith("--- ")
        for line in lines
    )

    has_new_file = any(
        line.startswith("+++ ")
        for line in lines
    )

    has_hunk = any(
        line.startswith("@@ ")
        for line in lines
    )

    has_file_information = (
        has_diff_header
        or (
            has_old_file
            and has_new_file
        )
    )

    return (
        has_file_information
        and has_hunk
    )


def split_diff_by_files(
    diff: str,
) -> list[str]:
    lines = diff.splitlines(
        keepends=True
    )

    sections: list[str] = []
    current_section: list[str] = []

    for line in lines:
        if (
            line.startswith("diff --git ")
            and current_section
        ):
            sections.append(
                "".join(current_section)
            )

            current_section = [line]
        else:
            current_section.append(line)

    if current_section:
        sections.append(
            "".join(current_section)
        )

    return sections or [diff]


def chunk_diff(
    diff: str,
) -> list[str]:
    file_sections = split_diff_by_files(
        diff
    )

    chunks: list[str] = []
    current_chunk = ""

    for section in file_sections:
        section_size = len(
            section.encode("utf-8")
        )

        if section_size > CHUNK_BYTES:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = ""

            chunks.append(section)
            continue

        proposed_chunk = (
            current_chunk + section
        )

        proposed_size = len(
            proposed_chunk.encode("utf-8")
        )

        if (
            current_chunk
            and proposed_size > CHUNK_BYTES
        ):
            chunks.append(current_chunk)
            current_chunk = section
        else:
            current_chunk = proposed_chunk

    if current_chunk:
        chunks.append(current_chunk)

    return chunks or [diff]


def clean_file_path(
    raw_path: str,
) -> str:
    path = raw_path.split(
        "\t",
        maxsplit=1,
    )[0].strip()

    if path.startswith("b/"):
        path = path[2:]

    return path


def parse_added_lines(
    diff: str,
) -> list[dict[str, Any]]:
    lines = diff.splitlines()

    added_lines: list[
        dict[str, Any]
    ] = []

    current_path = "unknown"
    current_new_line: Optional[int] = None

    for index, line in enumerate(lines):
        if line.startswith("+++ "):
            current_path = clean_file_path(
                line[4:]
            )
            continue

        if line.startswith("@@ "):
            match = re.search(
                r"\+(\d+)(?:,(\d+))?",
                line,
            )

            if match:
                current_new_line = int(
                    match.group(1)
                )

            continue

        if current_new_line is None:
            continue

        if line.startswith(
            "\\ No newline at end of file"
        ):
            continue

        if (
            line.startswith("+")
            and not line.startswith("+++")
        ):
            added_lines.append(
                {
                    "path": current_path,
                    "line": current_new_line,
                    "text": line[1:],
                    "index": index,
                    "allLines": lines,
                }
            )

            current_new_line += 1

        elif (
            line.startswith("-")
            and not line.startswith("---")
        ):
            # Removed lines do not exist
            # in the new file.
            continue

        else:
            # Context line.
            current_new_line += 1

    return added_lines