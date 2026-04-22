Tạo UI đăng nhập khi truy cập vào trang chủ:
Tham khảo login html sau:
<!DOCTYPE html>
<html lang="vi">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Đăng nhập - {{ app_name }}</title>
    <link
      href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css"
      rel="stylesheet"
    />
    <link
      href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css"
      rel="stylesheet"
    />
  </head>
  <body class="bg-light">
    <div class="container min-vh-100 d-flex align-items-center justify-content-center">
      <div class="card shadow" style="max-width: 440px; width: 100%">
        <div class="text-center p-4">
          <img
            src="/static/Marex.jpg"
            alt="Marex"
            class="img-fluid rounded"
            style="max-height: 120px; width: 100%; object-fit: cover"
          />
        </div>
        <div class="card-body p-4">
          {% if error %}
          <div class="alert alert-danger" role="alert">{{ error }}</div>
          {% endif %}

          <div class="mb-3">
            <label class="form-label fw-semibold">Mã nhân viên</label>
            <input
              type="text"
              class="form-control"
              id="loginEmployeeCode"
              placeholder="Nhập mã nhân viên (ví dụ: A1234)"
              autocomplete="username"
              autofocus
            />
          </div>

          <button class="btn btn-primary w-100" onclick="doLogin()">
            <i class="fas fa-sign-in-alt me-2"></i>Đăng nhập
          </button>
          <div class="text-center mt-3">
            <small class="text-muted">Sử dụng mã nhân viên đã được cấp quyền truy cập.</small>
          </div>
        </div>
      </div>
    </div>

    <script>
      async function doLogin() {
        const code = document.getElementById("loginEmployeeCode").value.trim().toUpperCase();
        if (!code) {
          alert("Vui lòng nhập mã nhân viên");
          return;
        }
        try {
          const formData = new FormData();
          formData.append("ma_nv", code);
          const endpoint = "/rcp/login?next=" + encodeURIComponent("{{ next_url }}");
          const res = await fetch(endpoint, { method: "POST", body: formData });
          if (res.redirected) {
            window.location.href = res.url;
            return;
          }
          if (res.ok) {
            window.location.href = "{{ next_url }}";
            return;
          }
          alert("Đăng nhập thất bại");
        } catch (e) {
          alert("Đăng nhập thất bại");
        }
      }
    </script>
  </body>
</html>


2. Yêu cầu: tạo bảng users với cấu trúc giống: "public.general_employees" ở RCP
ma_nv | ho_ten | chuc_vu | don_vi | bo_phan | station
add trước 2 row:
admin | admin | admin | P.TH | KSHT | []
H9253 | Nguyễn Thị Thu Hà | Nhân viên kho | XNDT | Kho nguyên liệu | []

3. Duy trì session đăng nhập xuyên suốt, tránh bị log out, dùng mã nhân viên ma_nv trong table được tạo để đăng nhập