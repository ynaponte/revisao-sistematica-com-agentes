"""Spreadsheet I/O: read articles from .xls and write results to .xlsx."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from .models import Article

# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

_COL_ID = 0
_COL_TITLE = 1
_COL_ABSTRACT = 4
_DATA_START_ROW = 8


def parse_row_range(row_range_str: str, total_data_rows: int) -> tuple[int, int]:
    parts = row_range_str.strip().split("-")
    if len(parts) == 1:
        start = int(parts[0]) - 1
        return start, start
    start = int(parts[0]) - 1
    end = int(parts[1]) - 1
    end = min(end, total_data_rows - 1)
    return start, end


def load_articles(
    path: str | Path,
    sheet_name: str = "Papers",
    row_range: str | None = None,
) -> list[Article]:
    # O Pandas utiliza a dependência xlrd por debaixo dos panos se instalada
    df = pd.read_excel(str(path), sheet_name=sheet_name, header=None, engine="xlrd")

    # Calculamos as linhas físicas baseados na interface do array numpy retornado
    total_data_rows = len(df) - _DATA_START_ROW
    if total_data_rows <= 0:
        return []

    if row_range:
        range_start, range_end = parse_row_range(row_range, total_data_rows)
    else:
        range_start, range_end = 0, total_data_rows - 1

    articles: list[Article] = []
    
    # Iteração elegante baseada em iloc do Pandas
    for i in range(range_start, range_end + 1):
        row_idx = _DATA_START_ROW + i
        if row_idx >= len(df):
            break

        row_data = df.iloc[row_idx]
        raw_id = row_data[_COL_ID]

        if pd.isna(raw_id) or not isinstance(raw_id, (int, float)) or raw_id <= 0:
            continue
            
        title = str(row_data[_COL_TITLE]).strip()
        abstract = str(row_data[_COL_ABSTRACT]).strip()

        articles.append(
            Article(
                id=int(raw_id),
                title=title,
                abstract=abstract if (abstract and abstract != "nan") else "(no abstract available)",
                row_index=row_idx,
            )
        )

    return articles


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def write_results(
    articles: Sequence[Article],
    results: Sequence[dict], 
    inclusion_criteria: Sequence[str],
    exclusion_criteria: Sequence[str],
    output_path: str | Path,
    metadata: dict[str, str] | None = None,
) -> Path:
    """Export results to an Excel file using Pandas."""
    output_path = Path(output_path)
    
    # Prepare data for DataFrame
    data = []
    for article, result in zip(articles, results):
        data.append({
            "ID": article.id,
            "Title": article.title,
            "Abstract": article.abstract,
            "Decision": result.get("decision", "ERROR"),
            "Discriminants": ", ".join(result.get("rejection_reasons", [])),
            "Justification": result.get("justification", ""),
        })
        
    df = pd.DataFrame(data)
    
    # In Pandas, it's easier to write data first
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        # If there's metadata, we might want to slip it in, but usually 
        # it's cleaner to put metadata in a separate sheet or just above.
        # Given pandas writes df at row 0 or specified row:
        start_row = 0
        if metadata:
            meta_df = pd.DataFrame([metadata])
            meta_df.to_excel(writer, sheet_name="Screening Results", index=False, startrow=0)
            start_row = 3 # Leave space for metadata
            
        df.to_excel(writer, sheet_name="Screening Results", index=False, startrow=start_row)

        # Basic styling with openpyxl 
        ws = writer.sheets["Screening Results"]
        
        # Adjust column widths
        widths = {"A": 8, "B": 50, "C": 60, "D": 12, "E": 25, "F": 80}
        for col_letter, width in widths.items():
            ws.column_dimensions[col_letter].width = width

        # Apply basic text wrap to all cells
        wrap_alignment = Alignment(wrap_text=True, vertical="top")
        for row in ws.iter_rows():
            for cell in row:
                cell.alignment = wrap_alignment
                
        # Color specific decisions
        decision_col_idx = 4 # 1-based index for decision in the D column
        for row in ws.iter_rows(min_row=start_row + 2, max_row=ws.max_row):
            decision_cell = row[decision_col_idx - 1]
            if decision_cell.value == "ACCEPTED":
                decision_cell.fill = PatternFill("solid", fgColor="C8E6C9")
            elif decision_cell.value == "REJECTED":
                decision_cell.fill = PatternFill("solid", fgColor="FFCDD2")

    return output_path
