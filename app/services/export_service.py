from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from app.models.models import TestCase


def compile_how_to_test(tc: TestCase, visited_ids: set = None) -> str:
    """
    Merakit teks 'How to test' secara rekursif.
    Jika menemukan INCLUDE_SCENARIO, langkah dari sub-skenario ditarik dan diuraikan.
    """
    if visited_ids is None:
        visited_ids = set()

    if tc.id in visited_ids:
        return f"[WARN: Circular include detected for Scenario ID {tc.id}]"

    current_visited = set(visited_ids)
    current_visited.add(tc.id)

    if tc.ut_how_to_test and tc.ut_how_to_test.strip():
        return tc.ut_how_to_test.strip()

    if not tc.steps:
        return "Belum ada langkah pengujian disetting."

    sorted_steps = sorted(tc.steps, key=lambda s: s.step_order)
    step_lines = []

    for s in sorted_steps:
        if s.command == "INCLUDE_SCENARIO" and s.input_value and s.input_value.strip().isdigit():
            # Jika sub-skenario diload via ORM
            sub_id = int(s.input_value.strip())
            step_lines.append(f"{s.step_order}. [SUB-SCENARIO #{sub_id}]")
        else:
            line = f"{s.step_order}. {s.command}"
            if s.target_selector:
                line += f" [{s.target_selector}]"
            if s.input_value:
                line += f" (Value: '{s.input_value}')"
            step_lines.append(line)

    return "\n".join(step_lines)


def generate_ut_matrix_excel(test_cases: list[TestCase], project_name: str = "All Projects") -> BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.title = "UT Document Matrix"
    
    header_fill = PatternFill(start_color="D9D9D9", end_color="D9D9D9", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="000000")
    data_font = Font(name="Calibri", size=10, color="000000")
    
    status_pass_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
    status_pass_font = Font(name="Calibri", size=10, bold=True, color="375623")
    
    status_fail_fill = PatternFill(start_color="FCE4D6", end_color="FCE4D6", fill_type="solid")
    status_fail_font = Font(name="Calibri", size=10, bold=True, color="C65911")

    thin_border = Border(
        left=Side(style="thin", color="BFBFBF"),
        right=Side(style="thin", color="BFBFBF"),
        top=Side(style="thin", color="BFBFBF"),
        bottom=Side(style="thin", color="BFBFBF")
    )

    headers = [
        "Case ID",
        "Theme",
        "Action",
        "Condition 1",
        "Condition 2",
        "Case classification",
        "Function name",
        "How to test",
        "Expected results",
        "Last Status",
        "Error / Log"
    ]
    
    ws.append(headers)
    
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = thin_border
    
    ws.row_dimensions[1].height = 28

    for idx, tc in enumerate(test_cases, start=1):
        case_id = str(idx)
        theme = tc.ut_theme if (tc.ut_theme and tc.ut_theme.strip()) else (tc.project.name if tc.project else "-")

        if tc.ut_action and tc.ut_action.strip():
            action = tc.ut_action
        elif tc.steps:
            sorted_steps = sorted(tc.steps, key=lambda s: s.step_order)
            first_step = sorted_steps[0]
            action = f"Jalankan perintah {first_step.command}"
            if first_step.target_selector:
                action += f" pada target {first_step.target_selector}"
        else:
            action = f"Eksekusi skenario {tc.name}"

        condition_1 = tc.ut_condition_1 if (tc.ut_condition_1 and tc.ut_condition_1.strip()) else f"Base URL: {tc.base_url}"
        condition_2 = tc.ut_condition_2 if (tc.ut_condition_2 and tc.ut_condition_2.strip()) else "-"
        classification = tc.ut_classification if (tc.ut_classification and tc.ut_classification.strip()) else "Normal"
        function_name = tc.ut_function_name if (tc.ut_function_name and tc.ut_function_name.strip()) else tc.name

        # Menggunakan kompilasi rekursif
        how_to_test = compile_how_to_test(tc)

        if tc.ut_expected_results and tc.ut_expected_results.strip():
            expected_results = tc.ut_expected_results
        elif tc.steps:
            verify_steps = [s for s in tc.steps if "VERIFY" in s.command.upper()]
            if verify_steps:
                verify_lines = [f"- {s.command}: Memastikan {s.target_selector or ''} bernilai '{s.input_value or ''}'".strip() for s in verify_steps]
                expected_results = "\n".join(verify_lines)
            else:
                expected_results = "Skenario berhasil dieksekusi tanpa error hingga langkah terakhir."
        else:
            expected_results = "-"

        last_run = sorted(tc.runs, key=lambda r: r.executed_at, reverse=True)[0] if tc.runs else None
        last_status = last_run.status if last_run else "UNTESTED"
        error_log = last_run.error_log if (last_run and last_run.error_log) else "-"

        row_values = [
            case_id, theme, action, condition_1, condition_2,
            classification, function_name, how_to_test, expected_results,
            last_status, error_log
        ]

        ws.append(row_values)
        current_row = idx + 1

        for col_num in range(1, len(row_values) + 1):
            cell = ws.cell(row=current_row, column=col_num)
            cell.font = data_font
            cell.border = thin_border
            cell.alignment = Alignment(vertical="top", wrap_text=True)

        ws.cell(row=current_row, column=1).alignment = Alignment(horizontal="center", vertical="top")
        ws.cell(row=current_row, column=6).alignment = Alignment(horizontal="center", vertical="top")
        
        status_cell = ws.cell(row=current_row, column=10)
        status_cell.alignment = Alignment(horizontal="center", vertical="top")
        
        if last_status == "SUCCESS":
            status_cell.fill = status_pass_fill
            status_cell.font = status_pass_font
        elif last_status == "FAILED":
            status_cell.fill = status_fail_fill
            status_cell.font = status_fail_font

    col_widths = {
        "A": 10, "B": 18, "C": 25, "D": 22, "E": 18,
        "F": 18, "G": 22, "H": 35, "I": 30, "J": 14, "K": 25
    }
    for col_letter, width in col_widths.items():
        ws.column_dimensions[col_letter].width = width

    stream = BytesIO()
    wb.save(stream)
    stream.seek(0)
    return stream