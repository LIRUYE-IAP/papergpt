import pymupdf

from tests.conftest import ApiClient

TEST_PASSWORD = "correct-horse-battery-staple"
MINIMAL_PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF\n"


def register_user(client: ApiClient, email: str, name: str = "Test User") -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": TEST_PASSWORD, "name": name},
    )
    assert response.status_code == 201, response.text
    return response.json()


def login_user(client: ApiClient, email: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": TEST_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def upload_pdf(client: ApiClient, token: str, filename: str = "paper.pdf") -> dict:
    return upload_pdf_bytes(client, token, MINIMAL_PDF, filename)


def upload_pdf_bytes(
    client: ApiClient, token: str, content: bytes, filename: str = "paper.pdf"
) -> dict:
    response = client.post(
        "/api/v1/papers",
        headers=auth_headers(token),
        files={"file": (filename, content, "application/pdf")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def academic_pdf_bytes() -> bytes:
    document = pymupdf.open()
    page_width, page_height = 595.0, 842.0
    left = pymupdf.Rect(48, 0, 282, 0)
    right = pymupdf.Rect(313, 0, 547, 0)

    def add_text(
        page: pymupdf.Page,
        rect: pymupdf.Rect,
        text: str,
        *,
        size: float = 9,
        font: str = "helv",
        align: int = 0,
    ) -> None:
        result = page.insert_textbox(
            rect,
            text,
            fontsize=size,
            fontname=font,
            align=align,
            lineheight=1.2,
        )
        assert result >= 0, f"Text did not fit in fixture rectangle: {text}"

    def add_frame(page: pymupdf.Page, page_number: int) -> None:
        add_text(
            page,
            pymupdf.Rect(48, 18, 547, 34),
            "Journal of Synthetic Document Research | doi:10.0000/papergpt.test",
            size=7,
            align=1,
        )
        add_text(
            page,
            pymupdf.Rect(48, 812, 547, 826),
            "PaperGPT document-engine test fixture",
            size=7,
            align=1,
        )
        add_text(
            page,
            pymupdf.Rect(270, 826, 325, 839),
            str(page_number),
            size=7,
            align=1,
        )

    page = document.new_page(width=page_width, height=page_height)
    add_frame(page, 1)
    add_text(
        page,
        pymupdf.Rect(48, 52, 547, 88),
        "A Layout-Aware Engine for Academic Documents",
        size=18,
        font="hebo",
        align=1,
    )
    add_text(
        page,
        pymupdf.Rect(48, 92, 547, 110),
        "Ada Example, Grace Sample",
        size=10,
        align=1,
    )
    add_text(
        page,
        pymupdf.Rect(48, 112, 547, 130),
        "Department of Reproducible Systems, Example University",
        size=9,
        align=1,
    )
    add_text(page, pymupdf.Rect(48, 145, 547, 165), "Abstract", size=11, font="hebo")
    add_text(
        page,
        pymupdf.Rect(48, 168, 547, 205),
        "This generated paper evaluates layout-aware extraction for born-digital academic PDFs while preserving page coordinates and reading order.",
        size=9,
    )
    add_text(
        page,
        pymupdf.Rect(48, 207, 547, 225),
        "Keywords: document layout; reading order; reproducible tests",
        size=8,
    )
    add_text(page, pymupdf.Rect(48, 238, 547, 260), "1 Introduction", size=12, font="hebo")
    add_text(
        page,
        pymupdf.Rect(left.x0, 268, left.x1, 326),
        "LEFT ONE. Academic documents often use two columns. A reader must finish the left column before moving to the right column.",
    )
    add_text(
        page,
        pymupdf.Rect(left.x0, 330, left.x1, 350),
        "1.1 Motivation",
        size=10.5,
        font="hebo",
    )
    add_text(
        page,
        pymupdf.Rect(left.x0, 360, left.x1, 426),
        "LEFT TWO. Paragraph reconstruction joins wrapped lines and recovers fore-\ncasting when a word is split by line wrapping.",
    )
    add_text(
        page,
        pymupdf.Rect(right.x0, 268, right.x1, 326),
        "RIGHT ONE. Interleaving this text with the left column would produce an incorrect reading sequence for downstream use.",
    )
    add_text(
        page,
        pymupdf.Rect(right.x0, 336, right.x1, 402),
        "RIGHT TWO. Bounding boxes remain attached to every extracted block so interfaces can locate the source text later.",
    )
    add_text(
        page,
        pymupdf.Rect(right.x0, 416, right.x1, 448),
        "Figure 1. Conceptual flow of the document engine.",
        size=8,
    )

    page = document.new_page(width=page_width, height=page_height)
    add_frame(page, 2)
    add_text(page, pymupdf.Rect(48, 52, 547, 76), "2 Methods", size=12, font="hebo")
    add_text(page, pymupdf.Rect(48, 82, 547, 104), "2.1 Data", size=11, font="hebo")
    add_text(
        page,
        pymupdf.Rect(left.x0, 116, left.x1, 190),
        "The fixture is generated entirely for this repository. It contains no third-party paper text and stays intentionally small.",
    )
    add_text(
        page,
        pymupdf.Rect(left.x0, 202, left.x1, 270),
        "Font size, boldness, numbering patterns, and position provide deterministic signals for section detection.",
    )
    add_text(
        page,
        pymupdf.Rect(right.x0, 116, right.x1, 190),
        "Column membership is inferred around the page midpoint while full-width headings divide vertical reading regions.",
    )
    add_text(
        page,
        pymupdf.Rect(right.x0, 202, right.x1, 270),
        "Table 1. Expected block categories and layout metadata.",
        size=8,
    )
    add_text(page, pymupdf.Rect(48, 300, 547, 324), "3 Results", size=12, font="hebo")
    add_text(
        page,
        pymupdf.Rect(left.x0, 336, left.x1, 410),
        "The parser produces ordered blocks, nested sections, and debug artifacts while retaining the original text.",
    )
    add_text(
        page,
        pymupdf.Rect(right.x0, 336, right.x1, 410),
        "Repeated headers, footers, and page numbers remain visible but are marked as non-translatable metadata.",
    )

    page = document.new_page(width=page_width, height=page_height)
    add_frame(page, 3)
    add_text(page, pymupdf.Rect(48, 52, 547, 76), "4 Conclusion", size=12, font="hebo")
    add_text(
        page,
        pymupdf.Rect(48, 84, 547, 125),
        "A lightweight heuristic engine is sufficient for the Phase 2 born-digital baseline and remains inspectable through JSON.",
    )
    add_text(page, pymupdf.Rect(48, 150, 547, 176), "References", size=12, font="hebo")
    add_text(
        page,
        pymupdf.Rect(48, 184, 547, 220),
        "[1] A. Example. Reproducible document layout experiments. 2026.",
        size=9,
    )
    add_text(
        page,
        pymupdf.Rect(48, 224, 547, 260),
        "[2] G. Sample. Deterministic reading order for two-column papers. 2026.",
        size=9,
    )

    content = document.tobytes(garbage=4, deflate=True)
    document.close()
    return content
