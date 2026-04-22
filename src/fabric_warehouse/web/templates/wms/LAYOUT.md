Thiết kế tab Layout Pallet nằm trên "Dashboard" index.html
- Là 1 nhánh nhỏ của Dashboard
- Trực quan các dãy Pallet dưới dạng html layout
Logic trực quan tham khảo:
UI mẫu: "D:\Data Analyst\Tools\fabric-warehouse\src\fabric_warehouse\web\templates\stitch_fabric_warehouse_manager\s_kho_layout\code.html"

Code app cũ: "D:\Data Analyst\Python\Visual Code Studio\Hello\pallet_layout.py"

Hiển thị theo vị trí: Tầng - Line - Pallet
Trực quan theo màu sắc sức chứa:
- Đỏ: Sức chứa > 90%
- Vàng: Sức chứa 70-90%
- Xanh: Sức chứa < 70%

Tại mỗi pallet có nút "View" - icon => khi click vào thì tạo bảng data các cây đang được lưu:
Mã Cây | Nhu cầu | Lot | Số Yds | Ngày nhập kho | Thời gian lưu kho (ngày)