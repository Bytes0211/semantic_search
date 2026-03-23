#!/usr/bin/env python3
"""Split README.md at \\newpage markers and generate dark-mode PDFs using pandoc.

Usage:
    python scripts/readme_to_pdf.py [--max-pages N]

Requires: pandoc, xelatex (texlive), DejaVu fonts
"""

import argparse
import os
import subprocess
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
README_PATH = os.path.join(REPO_ROOT, "README.md")
DOCS_DIR = os.path.join(REPO_ROOT, "docs")

DARK_MODE_HEADER = r"""
\usepackage{xcolor}
\usepackage{pagecolor}
\definecolor{darkbg}{HTML}{1E1E2E}
\definecolor{lighttext}{HTML}{CDD6F4}
\definecolor{accentblue}{HTML}{89B4FA}
\definecolor{codeblockbg}{HTML}{313244}
\pagecolor{darkbg}
\color{lighttext}
\usepackage{hyperref}
\hypersetup{colorlinks=true, linkcolor=accentblue, urlcolor=accentblue}
\usepackage{fancyvrb}
\usepackage{fvextra}
\DefineVerbatimEnvironment{Highlighting}{Verbatim}{
  commandchars=\\\{\},
  breaklines,
  fontsize=\small
}
\RecustomVerbatimEnvironment{verbatim}{Verbatim}{}
\let\oldtexttt\texttt
\renewcommand{\texttt}[1]{{\colorbox{codeblockbg}{\textcolor{accentblue}{\oldtexttt{#1}}}}}
"""


def split_readme(path: str) -> list[str]:
    """Split README content on \\newpage markers.

    Args:
        path: Path to the README.md file.

    Returns:
        List of markdown strings, one per page section.
    """
    with open(path) as f:
        content = f.read()
    return content.split("\\newpage")


def clean_page(page_content: str) -> str:
    """Remove badge/image lines that won't render in PDF.

    Args:
        page_content: Raw markdown content for a single page.

    Returns:
        Cleaned markdown string.
    """
    lines = page_content.strip().split("\n")
    cleaned = [
        line
        for line in lines
        if not line.startswith("[![")
    ]
    return "\n".join(cleaned)


def generate_pdf(markdown_text: str, output_path: str, header_path: str) -> None:
    """Convert markdown text to a dark-mode PDF via pandoc + xelatex.

    Args:
        markdown_text: Markdown content to render.
        output_path: Destination PDF file path.
        header_path: Path to the LaTeX header file for dark-mode styling.

    Raises:
        subprocess.CalledProcessError: If pandoc conversion fails.
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as md_file:
        md_file.write(markdown_text)
        md_path = md_file.name

    try:
        cmd = [
            "pandoc",
            md_path,
            "-o",
            output_path,
            "--pdf-engine=xelatex",
            "-H",
            header_path,
            "--resource-path",
            REPO_ROOT,
            "-V",
            "geometry:margin=1in",
            "-V",
            "mainfont=DejaVu Sans",
            "-V",
            "monofont=DejaVu Sans Mono",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            print(f"ERROR generating {output_path}: {result.stderr}")
        else:
            print(f"Created: {output_path}")
    finally:
        os.unlink(md_path)


def main() -> None:
    """Split README.md at \\newpage markers and generate dark-mode PDFs."""
    parser = argparse.ArgumentParser(description="Generate dark-mode PDFs from README.md pages")
    parser.add_argument(
        "--max-pages",
        type=int,
        default=3,
        help="Maximum number of pages to generate (default: 3)",
    )
    args = parser.parse_args()

    pages = split_readme(README_PATH)
    num_pages = min(args.max_pages, len(pages))
    print(f"Found {len(pages)} sections, generating {num_pages} PDF(s)")

    os.makedirs(DOCS_DIR, exist_ok=True)

    # Write dark-mode LaTeX header to a temp file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".tex", delete=False) as hf:
        hf.write(DARK_MODE_HEADER)
        header_path = hf.name

    try:
        for i in range(num_pages):
            cleaned = clean_page(pages[i])
            out_pdf = os.path.join(DOCS_DIR, f"readme_page_{i + 1}.pdf")
            generate_pdf(cleaned, out_pdf, header_path)
    finally:
        os.unlink(header_path)


if __name__ == "__main__":
    main()
