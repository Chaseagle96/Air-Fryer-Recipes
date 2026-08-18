from __future__ import annotations

from pathlib import Path

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .dashboard import write_dashboard

CATEGORY_SHEETS = ["Chicken", "Potatoes", "Vegetables", "Desserts", "Beef", "Pork", "Seafood", "Breakfast", "Snacks"]


def _df(rows) -> pd.DataFrame:
    if isinstance(rows, pd.DataFrame):
        return rows.copy()
    return pd.DataFrame(list(rows or []))


def _style_workbook(path: str) -> None:
    wb = load_workbook(path)
    for ws in wb.worksheets:
        if ws.max_row >= 1:
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
            for cell in ws[1]:
                cell.font = Font(bold=True)
                cell.fill = PatternFill("solid", fgColor="D9EAF7")
                cell.alignment = Alignment(vertical="center", wrap_text=True)
        for col_idx, col in enumerate(ws.columns, 1):
            values = [str(c.value) if c.value is not None else "" for c in col[:100]]
            width = min(48, max(10, max((len(v) for v in values), default=10) + 2))
            ws.column_dimensions[get_column_letter(col_idx)].width = width
        for row in ws.iter_rows():
            for cell in row:
                cell.alignment = Alignment(vertical="top", wrap_text=True)
    wb.save(path)


def write_csv_outputs(output_dir: str | Path, ranked: list[dict], coverage: list[dict], reliability: list[dict], anomalies: list[dict]) -> None:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    df = _df(ranked)
    if df.empty:
        (output / "leaderboard.csv").write_text("")
        (output / "top50.csv").write_text("")
    else:
        df.to_csv(output / "leaderboard.csv", index=False)
        df.head(50).to_csv(output / "top50.csv", index=False)
    _df(coverage).to_csv(output / "source_coverage.csv", index=False)
    _df(reliability).to_csv(output / "source_reliability.csv", index=False)
    _df(anomalies).to_csv(output / "anomalies.csv", index=False)


def write_workbook(
    path: str | Path,
    ranked: list[dict],
    coverage: list[dict],
    reliability: list[dict],
    recent_observations: list[dict],
    anomalies: list[dict],
    duplicate_groups: list[dict],
    methodology: dict,
) -> None:
    path = str(path)
    df = _df(ranked)
    cov = _df(coverage)
    rel = _df(reliability)
    obs = _df(recent_observations)
    anom = _df(anomalies)
    dup = _df(duplicate_groups)

    movers = pd.DataFrame()
    entrants = pd.DataFrame()
    if not df.empty:
        if "movement" in df:
            movers = df[df["movement"].notna()].copy()
            if not movers.empty:
                movers["abs_movement"] = movers["movement"].abs()
                movers = movers.sort_values(["abs_movement", "rating_count"], ascending=[False, False]).drop(columns=["abs_movement"])
        if "previous_rank" in df:
            entrants = df[df["previous_rank"].isna()].head(100).copy()

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.head(50).to_excel(writer, index=False, sheet_name="Top 50")
        df.to_excel(writer, index=False, sheet_name="All Rankings")
        cov.to_excel(writer, index=False, sheet_name="Source Coverage")
        rel.to_excel(writer, index=False, sheet_name="Source Reliability")
        obs.to_excel(writer, index=False, sheet_name="Rating History")
        entrants.to_excel(writer, index=False, sheet_name="New Entrants")
        movers.head(200).to_excel(writer, index=False, sheet_name="Biggest Movers")
        anom.to_excel(writer, index=False, sheet_name="QA Anomalies")
        dup.to_excel(writer, index=False, sheet_name="Duplicate Groups")
        pd.DataFrame([methodology]).to_excel(writer, index=False, sheet_name="Methodology")
        for category in CATEGORY_SHEETS:
            if df.empty or "categories" not in df:
                subset = pd.DataFrame()
            else:
                subset = df[df["categories"].fillna("").str.contains(category, regex=False)].head(100)
            subset.to_excel(writer, index=False, sheet_name=category)
    _style_workbook(path)
