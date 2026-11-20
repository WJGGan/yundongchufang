"""每周计划 Excel 导出。"""
from io import BytesIO
from itertools import groupby

from fastapi import APIRouter
from fastapi.responses import Response
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1")


class ExportItem(BaseModel):
    name: str = ""
    exercise_id: str = ""
    dosage: str = ""
    notes: str = ""
    points: str = ""
    errors: str = ""
    kind: str = ""


class ExportDay(BaseModel):
    day: str = ""
    theme: str = ""
    total_minutes: int | None = None
    actions: list[ExportItem] = Field(default_factory=list)


class ExportRequest(BaseModel):
    days: list[ExportDay] = Field(default_factory=list, max_length=7)
    include_details: bool = False
    name: str = ""


@router.post('/export/weekly-plan.xlsx')
def export_weekly_plan(request: ExportRequest) -> Response:
    wb = Workbook()
    ws = wb.active
    ws.title = '每周运动计划'
    columns = ['日期与计划', '运动类别', '动作', '剂量'] + (['动作要点与注意事项'] if request.include_details else [])
    last_col = len(columns)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last_col)
    ws.cell(1, 1, '每周运动计划')
    ws.cell(1, 1).font = Font(name='微软雅黑', size=18, bold=True, color='FFFFFF')
    ws.cell(1, 1).fill = PatternFill('solid', fgColor='2468BD')
    ws.cell(1, 1).alignment = Alignment(horizontal='left', vertical='center', indent=1)
    ws.row_dimensions[1].height = 36
    header_row = 2
    if request.name:
        ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=last_col)
        ws.cell(2, 1, '姓名：' + request.name)
        header_row = 3
    for col, title in enumerate(columns, 1):
        c = ws.cell(header_row, col, title)
        c.fill = PatternFill('solid', fgColor='EAF1FA')
        c.font = Font(name='微软雅黑', size=11, bold=True, color='29486D')
        c.alignment = Alignment(horizontal='center', vertical='center')
    ws.row_dimensions[header_row].height = 26
    colors = {'warm': ('热身', 'FFF5E8'), 'cardio': ('有氧', 'EDF5FF'), 'strength': ('力量／核心', 'F4EFFC'), 'cool': ('拉伸／放松', 'EDF8F2'), 'rest': ('休息', 'F7F9FC')}
    row = header_row + 1
    for day in request.days:
        start = row
        items = day.actions or [ExportItem(name=day.theme or '休息', kind='rest')]
        for kind, group in groupby(items, key=lambda item: item.kind if item.kind in colors else 'cardio'):
            group_start = row
            for item in group:
                values = [None, None, item.name or item.exercise_id, item.dosage]
                if request.include_details:
                    values.append('；'.join(filter(None, [item.notes, '动作要点：' + item.points if item.points else '', '注意避免：' + item.errors if item.errors else ''])))
                for col, value in enumerate(values, 1):
                    if value is not None:
                        cell = ws.cell(row, col, str(value))
                        cell.data_type = 's'
                ws.row_dimensions[row].height = 32 if not request.include_details else 48
                row += 1
            if row - group_start > 1:
                ws.merge_cells(start_row=group_start, start_column=2, end_row=row-1, end_column=2)
            c = ws.cell(group_start, 2, colors[kind][0])
            c.fill = PatternFill('solid', fgColor=colors[kind][1])
            c.font = Font(name='微软雅黑', bold=True, color='345474')
            c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        if row - start > 1:
            ws.merge_cells(start_row=start, start_column=1, end_row=row-1, end_column=1)
        parts = [day.day, day.theme or ('训练' if day.actions else '休息')]
        if day.total_minutes is not None:
            parts.append(f'{day.total_minutes} 分钟')
        c = ws.cell(start, 1, '\n'.join(parts))
        c.font = Font(name='微软雅黑', bold=True, color='29486D')
        c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        c.fill = PatternFill('solid', fgColor='F5F8FC')
    line = Side(style='thin', color='DFE7F1')
    for row_cells in ws.iter_rows(min_row=header_row, max_row=max(header_row, row-1), max_col=last_col):
        for c in row_cells:
            c.border = Border(left=line, right=line, top=line, bottom=line)
            if c.row > header_row and c.column >= 3:
                c.alignment = Alignment(vertical='center', wrap_text=True)
                c.font = Font(name='微软雅黑', size=11, color='263B57')
    for i, width in enumerate([25, 17, 26, 27, 48][:last_col], 1):
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.freeze_panes = f'C{header_row+1}'
    ws.sheet_view.showGridLines = False
    ws.print_options.horizontalCentered = True
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.print_title_rows = f'1:{header_row}'
    output = BytesIO()
    wb.save(output)
    return Response(output.getvalue(), media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers={'Content-Disposition': 'attachment; filename="weekly-plan.xlsx"'})
