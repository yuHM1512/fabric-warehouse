# Báo cáo hệ thống WMS cũ (Streamlit) — tính năng & công nghệ

Tài liệu này tóm tắt **module WMS kho vải** của hệ thống cũ (code dạng Streamlit) để tải lên NotebookLM phục vụ tư vấn tái xây dựng.

## 0) Phạm vi & nguồn tham chiếu

- App WMS cũ: `D:\Data Analyst\Python\Visual Code Studio\Hello\wms.py`
- Module liên quan:
  - `D:\Data Analyst\Python\Visual Code Studio\Hello\excel_uploader.py`
  - `D:\Data Analyst\Python\Visual Code Studio\Hello\database_utils.py`
  - `D:\Data Analyst\Python\Visual Code Studio\Hello\backup_manager.py`
  - `D:\Data Analyst\Python\Visual Code Studio\Hello\pallet_layout.py`
  - Hướng dẫn nghiệp vụ: `D:\Data Analyst\Python\Visual Code Studio\Hello\wms.md`
- Lưu ý: `D:\Data Analyst\Python\Visual Code Studio\Hello\app.py` + `guide.html` là **tool khác** (Merchandiser Self‑Check), không thuộc WMS kho vải.

---

## 1) App WMS có chức năng gì? Quy trình thực hiện

### 1.1. Điều hướng tổng thể (menu)

WMS cũ là 1 app Streamlit, điều hướng bằng sidebar theo cấu trúc **menu mẹ → menu con**:

1) **Trang chủ**
- “Tổng quan”: render HTML từ `demo_home.html`
- “Hướng dẫn”: render nội dung từ `wms.md`

2) **Cập nhật phiếu nhập kho**
- Tab: tải Excel, nhập tay, cập nhật lại phiếu tạm (chi tiết nằm trong `wms.py` + `excel_uploader.py`)

3) **Nhập kho** (menu con)
- (1) Tạo bảng treo
- (2) Nhập kho (kiểm kho từng cây)
- (3) Định danh vị trí (gán pallet)
- (4) Tái nhập kho (trả lại từ tổ cắt)

4) **Xuất kho**
- Xuất cây theo Nhu cầu/Lot, ghi lịch sử, cập nhật trạng thái vị trí

5) **Báo cáo**
- Xem tổng quan kho
- Pallet layout
- Báo cáo theo dõi nhập kho

6) **Tính năng khác**
- Truy xuất cây vải (timeline lịch sử)
- Điều chuyển nhu cầu
- Tra cứu định mức (đọc từ `fabric.db`)
- Điều chuyển vị trí
- Quản lý người dùng
- Backup & Recovery
- Reset Database

---

### 1.2. Quy trình nghiệp vụ chính (end‑to‑end)

#### A) Nhập liệu phiếu → tạo dữ liệu nền

**Mục tiêu:** đưa dữ liệu phiếu (Excel) vào hệ thống để tạo “bảng treo” và dữ liệu gốc phục vụ nhập kho/xuất kho/báo cáo.

**Luồng:**
1. Vào **Cập nhật phiếu nhập kho**
2. Upload Excel phiếu (xlsx) (đọc `header=6` theo code trong `excel_uploader.py`)
3. Hệ thống xử lý:
   - Điền “Phiếu xuất” (fill‑forward) để suy ra **Ngày nhập hàng** từ chuỗi phiếu
   - Chuẩn hoá “Ánh màu” (nếu trống gán “CHUNG”)
   - Tạo dữ liệu **bảng treo** (`table_data`) từ dữ liệu raw (`excel_data`)
4. Ghi vào SQLite (append) và có bước **loại trùng**:
   - `excel_data`: drop duplicate theo “Mã cây” giữ bản ghi đầu
   - `table_data`: drop duplicate theo “ID bảng treo”

**Output chính:**
- `excel_data`: dữ liệu phiếu (raw)
- `table_data`: bảng treo (tổng hợp theo nhu cầu/lot/ngày…)

#### B) Nhập kho / kiểm kho (ghi nhận thực tế)

**Mục tiêu:** xác nhận số lượng thực tế theo từng cây vải trong từng Nhu cầu/Lot.

**Luồng:**
1. Vào **Nhập kho → Nhập kho**
2. Chọn **Nhu cầu** → **Lot**
3. Hiển thị danh sách cây, nhập:
   - “đủ” hoặc số **thực tế** (thuc_te)
   - ghi chú
   - ngày cập nhật
4. Lưu vào bảng `kiemkho_data` (upsert theo khóa (nhu_cau, lot, ma_cay))

**Output chính:** `kiemkho_data`


#### D) Xuất kho

**Mục tiêu:** xuất cây vải khỏi kho theo Nhu cầu/Lot, phân loại mục đích xuất và cập nhật trạng thái vị trí.

**Luồng:**
1. Vào **Xuất kho**
2. Chọn **Nhu cầu → Lot → chọn nhiều Mã cây**
3. Nhấn “Xuất kho”:
   - Ghi `xuatkho_data` (nhu_cau, lot, ma_cay, so_luong_xuat, ngay_xuat, status)
   - `status` được suy luận:
     - mặc định “Cấp phát sản xuất”
     - nếu ghi chú/ trạng thái vị trí chứa “Trả Mẹ Nhu” thì status = “Trả Mẹ Nhu”
   - Update `vi_tri_data.trang_thai = 'Đã xuất'` cho cây tương ứng
4. Xem lịch sử xuất, lọc theo ngày

**Output chính:** `xuatkho_data` + cập nhật `vi_tri_data`

#### E) Tái nhập kho (trả lại từ tổ cắt)

**Mục tiêu:** quản lý cây đã xuất nhưng quay lại kho (dư/hoàn).

**Luồng (tóm tắt theo code):**
1. Vào **Nhập kho → Tái nhập kho**
2. Đọc lịch sử `xuatkho_data`, vị trí `vi_tri_data`, log `tai_nhap_kho_data`
3. Chọn cây chưa tái nhập, nhập:
   - số YDS dư
   - trạng thái (tái nhập kho / trả mẹ nhu / … theo UI)
   - gán nhu cầu mới + vị trí mới (thường có use-case “NC-TAM” rồi điều chuyển nhu cầu sau)
4. Ghi `tai_nhap_kho_data` + cập nhật liên quan

**Output chính:** `tai_nhap_kho_data`

---

### 1.3. Báo cáo, tra cứu, công cụ hỗ trợ

#### Báo cáo tổng quan kho
- Tổng hợp theo nhu cầu/lot/loại vải/màu…
- Loại các cây đã xuất dựa trên `xuatkho_data`
- Kết hợp vị trí hiện tại từ `vi_tri_data` (lọc trạng thái “Đang lưu”)

#### Pallet Layout
- Hiển thị layout theo Tầng/Line/Pallet, cảnh báo theo sức chứa/định mức (chi tiết trong `pallet_layout.py`)

#### Truy xuất cây vải (Trace)
- Lọc theo Lot + Mã cây, hiển thị “timeline” lịch sử từ nhiều bảng (nhập/định danh/xuất/tái nhập/điều chuyển…)

#### Điều chuyển nhu cầu
- Use-case điển hình: cây ở **NC‑TAM** được chuyển sang nhu cầu thực tế
- Ghi log `dieu_chuyen_nhu_cau_log` và update các bảng liên quan (ít nhất: `tai_nhap_kho_data`, `kiemkho_data`, `vi_tri_data`)

#### Điều chuyển vị trí
- Chọn vị trí hiện tại (tách `vi_tri` thành tầng/line/pallet), chọn cây, gán vị trí mới
- Có log riêng cho điều chuyển pallet: `dieu_chuyen_pallet_vai`

#### Tra cứu định mức
- Kết nối DB riêng `fabric.db`, query `fabric_table`
- Mục tiêu: tra “YRD/Pallet” theo “Mã Model/Mã Art” để tham chiếu sức chứa tối đa

#### Quản lý người dùng
- CRUD người dùng (admin)
- Phân quyền: `admin` / `user`

#### Backup & Recovery
- Backup file DB `wms.db` thành `.zip` kèm metadata `.json` vào thư mục `backups/`
- Restore từ backup, có tạo “pre_restore backup” trước khi restore

#### Reset Database
- Có menu reset DB trong “Tính năng khác” (chi tiết xử lý nằm trong `wms.py`)

---

## 2) Dùng công nghệ gì trong code?

### 2.1. Frontend/UI

- **Streamlit**: UI chính (forms, sidebar navigation, tabs, dataframe rendering)
- **HTML/CSS nhúng**:
  - Dùng `streamlit.components.v1.components.html` để render HTML (trang home, timeline, table HTML tuỳ biến)
- **streamlit‑aggrid** (`st_aggrid`): bảng dạng grid tương tác (đang import trong `wms.py`)

### 2.2. Xử lý dữ liệu

- **Pandas**: đọc/transform dữ liệu Excel, lọc/merge/summary, format hiển thị
- **Regex** (`re`): trích xuất ngày từ chuỗi “phiếu”, làm sạch chuỗi…
- **Datetime/Time**: timestamp, lọc theo ngày, format hiển thị

### 2.3. Backend/Data layer

- **SQLite**:
  - DB chính: `wms.db`
  - DB định mức: `fabric.db`
- **SQLAlchemy** (engine + `text()`): tạo engine/execute SQL trong nhiều đoạn
- Đồng thời **sqlite3** (builtin) cũng được dùng trực tiếp để query `fabric.db`

### 2.4. Xuất file/ấn phẩm

- **pdfkit**: xuất PDF (phụ thuộc wkhtmltopdf trong môi trường)
- **openpyxl**: xử lý/định dạng Excel (một số phần trong hệ thống cũ)

### 2.5. Auth & session

- Bảng `users` lưu:
  - `username`, `password_hash` (hash sha256), `role`
- Session “nhẹ”:
  - Lưu file JSON `session.json` để giữ đăng nhập (dạng 1–2 người dùng)

### 2.6. Backup/Recovery

- `shutil`, `zipfile`, `pathlib`, `json`, `logging`
- Cơ chế backup chủ yếu là **copy file DB** + metadata, không phải logical dump

### 2.7. Thư viện phụ thuộc (requirements)

Theo `requirements_wms.txt` của dự án cũ:
- `streamlit`, `pandas`
- `streamlit-aggrid`
- `sqlalchemy`
- `openpyxl`
- và một số libs plotting (ví dụ `plotly`, `matplotlib`), timezone (`pytz`)

---

## 3) Ghi chú kỹ thuật quan trọng (để tư vấn làm mới)

Các điểm nổi bật có thể ảnh hưởng thiết kế khi tái xây:

- App cũ **monolithic**: nhiều nghiệp vụ + UI + SQL trộn trong `wms.py`
- Schema có hiện tượng **ALTER TABLE lúc runtime** (try/except) → nên thay bằng migration (Alembic) khi chuyển qua Postgres
- Tên cột có dấu tiếng Việt (ví dụ `"Ánh màu"`) → trên Postgres nên chuẩn hoá snake_case (vd: `anh_mau`) và mapping label ở UI
- Trạng thái vị trí và logic “đã xuất / đang lưu / trả mẹ nhu…” đang được suy luận từ text/ghi chú ở một số đoạn → khi làm mới nên chuẩn hoá enum/trạng thái

