from datetime import datetime
from io import BytesIO

import openpyxl
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Sum, Count
from django.http import JsonResponse, HttpResponse
from openpyxl.styles import Border, Side, PatternFill, Font
from openpyxl.utils import get_column_letter

from backend.models import Floor, Room, Building, Student


# Create your views here.
def get_floors(request):
    building_id = request.GET.get("building_id")
    floors = Floor.objects.filter(building_id=building_id).values("id", "floor_number")  # Return filtered floors
    return JsonResponse({"floors": list(floors)})


@staff_member_required  # Restrict access to admin users
def export_rooms_buildings(request):
    """Export Buildings and Rooms into an Excel file with separate sheets"""
    wb = openpyxl.Workbook()

    #  Add Buildings Sheet
    add_buildings_sheet(wb)

    #  Add Rooms Sheet
    add_rooms_sheet(wb)

    #  Save workbook to BytesIO
    output = BytesIO()
    wb.save(output)
    output.seek(0)

    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"Báo cáo-{date_str}.xlsx"

    #  Create HTTP Response
    response = HttpResponse(
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def add_buildings_sheet(wb):
    """Add Buildings data to an Excel sheet with correct room capacity calculations"""
    ws_buildings = wb.active
    ws_buildings.title = "Tòa nhà"

    #  Add Header Row with Formatting
    header_row = ["Tòa nhà", "Số phòng ở", "Tổng số chỗ ở", "Số chỗ ở đã bố trí", "Số chỗ ở chưa bố trí"]
    ws_buildings.append(header_row)
    format_header(ws_buildings, len(header_row))  # Format the header

    #  Initialize Totals
    total_rooms = total_capacity = total_allocated = total_unallocated = 0

    #  Process Buildings Data
    for building in Building.objects.all():
        # Count the total rooms (excluding locked rooms)
        num_rooms = Room.objects.filter(is_lock=False, building=building).count()

        # Sum up actual capacity from all rooms in this building (excluding locked rooms)
        total_slots = Room.objects.filter(is_lock=False, building=building).aggregate(
            total_capacity=Sum('capacity')
        )['total_capacity'] or 0  # Default to 0 if no rooms

        # Get total number of students assigned in this building
        student_count = get_reserved_count(building)

        # Calculate available slots
        available_capacity = total_slots - student_count

        # Append building data to the sheet
        ws_buildings.append([
            building.name, num_rooms, total_slots, student_count, available_capacity
        ])

        #  Accumulate Totals
        total_rooms += num_rooms
        total_capacity += total_slots
        total_allocated += student_count
        total_unallocated += available_capacity

    #  Append Final Summary Row at the Bottom
    summary_row = ["Tổng cộng", total_rooms, total_capacity, total_allocated, total_unallocated]
    ws_buildings.append(summary_row)

    #  Apply Border to All Rows
    apply_table_borders(ws_buildings)

    #  Auto-adjust Column Widths
    adjust_column_width(ws_buildings)


#  Function to Format Header
def format_header(ws, column_count):
    """Apply gray background, bold text, and center alignment to header"""
    header_fill = PatternFill(start_color="D3D3D3", end_color="D3D3D3", fill_type="solid")  # Gray background
    bold_font = Font(bold=True)

    for col in range(1, column_count + 1):
        cell = ws.cell(row=1, column=col)
        cell.fill = header_fill
        cell.font = bold_font


#  Function to Apply Borders to All Rows
def apply_table_borders(ws):
    """Apply thin borders to all cells in the worksheet"""
    thin_border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )

    for row in ws.iter_rows():
        for cell in row:
            cell.border = thin_border


#  Function to Auto-Fit Column Widths
def adjust_column_width(ws):
    """Adjust column width based on content length"""
    for col in ws.columns:
        max_length = 0
        col_letter = get_column_letter(col[0].column)  # Get column letter (A, B, C, etc.)
        for cell in col:
            if cell.value:
                max_length = max(max_length, len(str(cell.value)))
        ws.column_dimensions[col_letter].width = max_length + 2  # Adjust width with padding


def add_rooms_sheet(wb):
    """Add Rooms data to an Excel sheet (split by room + platoon)"""
    ws_rooms = wb.create_sheet(title="Phòng")

    header_row = ["Tòa Nhà", "Phòng", "Trung đội", "Số lượng học viên", "Giới tính"]
    ws_rooms.append(header_row)
    format_header(ws_rooms, len(header_row))

    # Group students by room and platoon, and count
    grouped = (
        Student.objects
        .select_related("room", "room__building")
        .values("room", "room__room_code", "room__building__name", "platoon__name", "gender")
        .annotate(student_count=Count("id"))
    )

    for entry in grouped:
        building_name = entry["room__building__name"] or "N/A"
        room_code = entry["room__room_code"]
        platoon = entry["platoon__name"]
        student_count = entry["student_count"]
        gender = entry["gender"]

        ws_rooms.append([
            building_name,
            room_code,
            platoon,
            student_count,
            gender
        ])

    apply_table_borders(ws_rooms)
    adjust_column_width(ws_rooms)


def get_reserved_count(building):
    """Get the count of allocated and available capacity for a given building"""
    total_capacity = 0

    rooms = Room.objects.filter(building=building)  # Optimize by fetching once
    room_ids = rooms.values_list("id", flat=True)  # Get only room IDs

    student_count = Student.objects.filter(room_id__in=room_ids).count()  # Count students efficiently

    for room in rooms:
        if not room.is_lock and not room.is_temporary_lock:
            total_capacity += room.capacity

    return student_count
