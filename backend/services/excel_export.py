"""Build a downloadable assignment workbook from the uploaded Excel template."""

from io import BytesIO

from openpyxl import load_workbook


ASSIGNMENT_COLUMNS = (20, 21, 24, 25, 26, 27)
EXPECTED_HEADERS = {
    20: "Jv. kód",
    21: "Játékvezető",
    24: "Assz-1, F-2. Jv. Kód",
    25: "Asszisztens-1 (Futsal: 2. játékvezető)",
    26: "AR-2, F-idm. Kód",
    27: "Asszisztens-2 (Futsal: időmérő)",
}


def fill_assignment_workbook(source_file, matches):
    """Fill officials into the uploaded workbook and return it as a byte stream.

    The importer stores each match's original Excel row. Before writing, verify
    the template headers to avoid placing referee data in the wrong columns.
    """
    workbook = load_workbook(BytesIO(source_file))
    worksheet = workbook.worksheets[0]
    if any(
        str(worksheet.cell(row=8, column=column).value or "").strip() != header
        for column, header in EXPECTED_HEADERS.items()
    ):
        raise ValueError("Az Excel kiosztási oszlopai nem a várt formátumúak.")

    for match in matches:
        row = match.get("excel_row")
        if not isinstance(row, int) or row < 9:
            raise ValueError("A mérkőzés eredeti Excel-sora nem található.")

        for column in ASSIGNMENT_COLUMNS:
            worksheet.cell(row=row, column=column).value = None

        referee = match.get("referee")
        assistants = match.get("assistant") or []
        officials = [referee, *assistants[:2]]
        for person, code_column, name_column in zip(
            officials, (20, 24, 26), (21, 25, 27)
        ):
            if isinstance(person, dict):
                worksheet.cell(row=row, column=code_column).value = person.get("id")
                worksheet.cell(row=row, column=name_column).value = person.get("name")

    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return output
