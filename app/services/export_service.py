import os
from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.drawing.image import Image as OpenPyxlImage
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


def generate_ut_matrix_excel(test_cases: list[TestCase], project_name: str = "All Projects") -> tuple[BytesIO, list[str]]:
    """
    Menghasilkan berkas Excel berisi:
    1. Sheet 'UT Document Matrix' (Menggunakan logika bawaan Anda)
    2. Sheet untuk tiap urutan Skenario ("1", "2", "3", dst) yang berisi baris langkah (Kuning) 
       serta Evidence Screenshot (57 cm x 32 cm).
    
    Mengembalikan tuple: (stream_excel_buffer, daftar_file_screenshot_untuk_dihapus)
    """
    wb = Workbook()
    
    # ---------------------------------------------------------
    # 1. SHEET UT UTAMA: "UT Document Matrix"
    # ---------------------------------------------------------
    ws = wb.active
    ws.title = "UT Document Matrix"
    
    header_fill = PatternFill(start_color="D9D9D9", end_color="D9D9D9", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="000000")
    data_font = Font(name="Calibri", size=10, color="000000")
    
    status_pass_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
    status_pass_font = Font(name="Calibri", size=10, bold=True, color="375623")
    
    status_fail_fill = PatternFill(start_color="FCE4D6", end_color="FCE4D6", fill_type="solid")
    status_fail_font = Font(name="Calibri", size=10, bold=True, color="C65911")

    # Style Tambahan untuk Sheet Evidence
    step_yellow_fill = PatternFill(start_color="FFFF00", end_color="FFFF00", fill_type="solid")
    step_header_font = Font(name="Calibri", size=11, bold=True, color="000000")

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

    screenshots_to_cleanup: list[str] = []

    # ---------------------------------------------------------
    # 2. POPULASI DATA MATRIX & PENAMBAHAN SHEET EVIDENCE
    # ---------------------------------------------------------
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

        # Ambil TestRun terakhir
        runs_sorted = sorted(tc.runs, key=lambda r: getattr(r, 'executed_at', getattr(r, 'created_at', None)), reverse=True) if tc.runs else []
        last_run = runs_sorted[0] if runs_sorted else None
        
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

        # ---------------------------------------------------------
        # 3. SHEET EVIDENCE (CAPTION DARI INPUT_VALUE / STRING KOSONG)
        # ---------------------------------------------------------
        ws_scen = wb.create_sheet(title=str(idx))
        ws_scen.column_dimensions['A'].width = 120

        scen_row = 1

        # Title Skenario
        ws_scen.cell(row=scen_row, column=1, value=f"SKENARIO #{idx}: {tc.name}").font = Font(name="Calibri", size=14, bold=True)
        scen_row += 1
        ws_scen.cell(row=scen_row, column=1, value=f"Base URL: {tc.base_url} | Status Terakhir: {last_status}").font = Font(name="Calibri", size=10, italic=True, color="595959")
        scen_row += 2

        evidence_count = 0

        if tc.steps:
            sorted_tc_steps = sorted(tc.steps, key=lambda s: s.step_order)
            for step in sorted_tc_steps:
                # 1. Cek ketersediaan file screenshot
                img_path = None
                if last_run:
                    possible_path = os.path.join("static", "screenshots", f"case_{tc.id}_step_{step.step_order}.png")
                    if os.path.exists(possible_path):
                        img_path = possible_path

                # 2. Skip jika langkah ini tidak menghasilkan screenshot
                if not img_path or not os.path.exists(img_path):
                    continue

                evidence_count += 1

                # 3. LOGIKA BARU: Baca input_value, jika kosong isi dengan string kosong ""
                caption_text = step.input_value.strip() if (step.input_value and step.input_value.strip()) else ""

                # Warnai seluruh cell A s/d K (Kolom 1-11) dengan warna kuning
                for col_idx in range(1, 12):
                    cell = ws_scen.cell(row=scen_row, column=col_idx)
                    cell.fill = step_yellow_fill
                    cell.border = thin_border
                    if col_idx == 1:
                        cell.value = caption_text
                        cell.font = step_header_font

                # Merge cell A s/d K
                ws_scen.merge_cells(start_row=scen_row, start_column=1, end_row=scen_row, end_column=11)
                ws_scen.row_dimensions[scen_row].height = 25
                scen_row += 1

                # 4. Sisipkan gambar screenshot (57 cm x 32 cm)
                try:
                    img = OpenPyxlImage(img_path)
                    img.width = int(57 * 37.795)   # ~2154 px
                    img.height = int(32 * 37.795)  # ~1209 px

                    ws_scen.add_image(img, f"A{scen_row}")
                    screenshots_to_cleanup.append(img_path)

                    scen_row += 62
                except Exception as e:
                    print(f"[Excel Export Image Error]: {e}")
                    scen_row += 2

        # Catatan jika tidak ada evidence sama sekali di skenario ini
        if evidence_count == 0:
            ws_scen.cell(row=scen_row, column=1, value="Tidak ada bukti screenshot yang diambil pada skenario ini.").font = Font(name="Calibri", size=11, italic=True, color="808080")

    # =========================================================================
    # 4. BAGIAN YANG SEBELUMNYA HILANG: ATUR LEBAR KOLOM, SIMPAN BUFFER & RETURN
    # =========================================================================
    col_widths = {
        "A": 10, "B": 18, "C": 25, "D": 22, "E": 18,
        "F": 18, "G": 22, "H": 35, "I": 30, "J": 14, "K": 25
    }
    for col_letter, width in col_widths.items():
        ws.column_dimensions[col_letter].width = width

    stream = BytesIO()
    wb.save(stream)
    stream.seek(0)
    return stream, screenshots_to_cleanup