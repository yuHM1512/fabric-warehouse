Dựa vào UI mẫu để cải thiện /trace

1. Chọn Lot => CHọn mã cây
2. Hiển thị bảng data ghi nhận sự kiện
3. Hiện flow timeline trực quan
4. Mốc thời gian hiển thị đúng logic:
- Event gồm: "Nhập kho" - "Ngày" (lấy đầu thì lấy ngày đầu gán vị trí) 
"Xuất kho" - ngày làm thao tác xuất để cấp phát
"Tái nhập kho"
"Điều chuyển": đổi vị trí khác
...
Theo trình tự thời gian nhé
<!DOCTYPE html>

<html class="light" lang="en"><head>
<meta charset="utf-8"/>
<meta content="width=device-width, initial-scale=1.0" name="viewport"/>
<title>Traceability Intelligence | The Digital Curator</title>
<script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@200;400;600;700;800&amp;family=Inter:wght@300;400;500;600;700&amp;display=swap" rel="stylesheet"/>
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&amp;display=swap" rel="stylesheet"/>
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&amp;display=swap" rel="stylesheet"/>
<script id="tailwind-config">
        tailwind.config = {
            darkMode: "class",
            theme: {
                extend: {
                    "colors": {
                        "on-primary-fixed": "#001848",
                        "outline-variant": "#c3c6d4",
                        "on-tertiary-container": "#ff9c7a",
                        "surface": "#f8f9fa",
                        "tertiary-fixed-dim": "#ffb59d",
                        "surface-dim": "#d9dadb",
                        "on-secondary-container": "#62646a",
                        "inverse-on-surface": "#f0f1f2",
                        "inverse-primary": "#b2c5ff",
                        "surface-container-highest": "#e1e3e4",
                        "surface-container-lowest": "#ffffff",
                        "surface-tint": "#2c59ba",
                        "background": "#f8f9fa",
                        "secondary-fixed": "#e1e2e9",
                        "outline": "#747784",
                        "tertiary": "#5d1900",
                        "primary-fixed": "#dae2ff",
                        "on-tertiary-fixed-variant": "#822803",
                        "on-secondary-fixed-variant": "#44474c",
                        "surface-container-low": "#f3f4f5",
                        "on-secondary": "#ffffff",
                        "on-primary-fixed-variant": "#0040a1",
                        "on-tertiary": "#ffffff",
                        "surface-variant": "#e1e3e4",
                        "secondary": "#5c5e64",
                        "on-primary-container": "#98b3ff",
                        "on-error-container": "#93000a",
                        "primary-fixed-dim": "#b2c5ff",
                        "on-surface-variant": "#434652",
                        "on-background": "#191c1d",
                        "on-primary": "#ffffff",
                        "tertiary-container": "#822803",
                        "on-surface": "#191c1d",
                        "error": "#ba1a1a",
                        "error-container": "#ffdad6",
                        "secondary-fixed-dim": "#c5c6cd",
                        "surface-bright": "#f8f9fa",
                        "surface-container": "#edeeef",
                        "primary": "#002b73",
                        "secondary-container": "#e1e2e9",
                        "inverse-surface": "#2e3132",
                        "tertiary-fixed": "#ffdbd0",
                        "surface-container-high": "#e7e8e9",
                        "primary-container": "#0040a1",
                        "on-secondary-fixed": "#191c21",
                        "on-tertiary-fixed": "#390c00",
                        "on-error": "#ffffff"
                    },
                    "borderRadius": {
                        "DEFAULT": "0.25rem",
                        "lg": "0.5rem",
                        "xl": "0.75rem",
                        "full": "9999px"
                    },
                    "fontFamily": {
                        "headline": ["Manrope"],
                        "body": ["Inter"],
                        "label": ["Inter"]
                    }
                }
            }
        }
    </script>
<style>
        body { font-family: 'Inter', sans-serif; }
        h1, h2, h3, .brand-logo { font-family: 'Manrope', sans-serif; }
        .material-symbols-outlined { font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24; }
        .signature-gradient { background: linear-gradient(135deg, #0040a1 0%, #0056d2 100%); }
        .cloud-shadow { box-shadow: 0px 20px 40px rgba(25, 28, 29, 0.05); }
        .hide-scrollbar::-webkit-scrollbar { display: none; }
    </style>
</head>
<body class="bg-surface text-on-surface">
<!-- SideNavBar Shell -->
<aside class="h-screen w-72 fixed left-0 top-0 z-40 bg-slate-100 dark:bg-slate-900 flex flex-col p-6 border-r-0">
<div class="mb-10 px-4">
<span class="text-lg font-black text-blue-800 dark:text-blue-400 tracking-tighter">Warehouse Alpha</span>
<p class="text-[10px] uppercase tracking-[0.2em] text-slate-500 font-bold mt-1">Main Textile Depot</p>
</div>
<nav class="flex-1">
<div class="text-[11px] font-bold text-slate-400 mb-4 px-4 tracking-widest uppercase">Navigation</div>
<a class="text-slate-500 dark:text-slate-400 px-4 py-3 mb-2 flex items-center gap-3 hover:bg-slate-200/50 dark:hover:bg-slate-800/50 rounded-lg transition-all duration-300 ease-in-out" href="#">
<span class="material-symbols-outlined" data-icon="dashboard">dashboard</span>
<span class="font-semibold text-sm tracking-wide">Dashboard</span>
</a>
<a class="text-slate-500 dark:text-slate-400 px-4 py-3 mb-2 flex items-center gap-3 hover:bg-slate-200/50 dark:hover:bg-slate-800/50 rounded-lg transition-all duration-300 ease-in-out" href="#">
<span class="material-symbols-outlined" data-icon="texture">texture</span>
<span class="font-semibold text-sm tracking-wide">Fabric Library</span>
</a>
<a class="bg-white dark:bg-slate-800 text-blue-800 dark:text-blue-400 rounded-lg shadow-sm px-4 py-3 mb-2 flex items-center gap-3 transition-all duration-300 ease-in-out" href="#">
<span class="material-symbols-outlined" data-icon="Timeline">timeline</span>
<span class="font-semibold text-sm tracking-wide">Traceability</span>
</a>
<a class="text-slate-500 dark:text-slate-400 px-4 py-3 mb-2 flex items-center gap-3 hover:bg-slate-200/50 dark:hover:bg-slate-800/50 rounded-lg transition-all duration-300 ease-in-out" href="#">
<span class="material-symbols-outlined" data-icon="layers">layers</span>
<span class="font-semibold text-sm tracking-wide">Warehouse Map</span>
</a>
<a class="text-slate-500 dark:text-slate-400 px-4 py-3 mb-2 flex items-center gap-3 hover:bg-slate-200/50 dark:hover:bg-slate-800/50 rounded-lg transition-all duration-300 ease-in-out" href="#">
<span class="material-symbols-outlined" data-icon="local_shipping">local_shipping</span>
<span class="font-semibold text-sm tracking-wide">Logistics</span>
</a>
</nav>
<div class="mt-auto border-t border-slate-200/50 pt-6">
<button class="w-full signature-gradient text-white rounded-full py-3 font-bold text-sm mb-6 scale-95 active:scale-100 transition-transform">
                New Entry
            </button>
<a class="text-slate-500 dark:text-slate-400 px-4 py-3 flex items-center gap-3 hover:bg-slate-200/50 rounded-lg transition-all" href="#">
<span class="material-symbols-outlined" data-icon="help_outline">help_outline</span>
<span class="font-semibold text-sm tracking-wide">Support</span>
</a>
<a class="text-slate-500 dark:text-slate-400 px-4 py-3 flex items-center gap-3 hover:bg-slate-200/50 rounded-lg transition-all" href="#">
<span class="material-symbols-outlined" data-icon="logout">logout</span>
<span class="font-semibold text-sm tracking-wide">Sign Out</span>
</a>
</div>
</aside>
<!-- Main Content Wrapper -->
<main class="ml-72 min-h-screen">
<!-- TopAppBar Shell -->
<header class="fixed top-0 right-0 left-72 z-30 bg-slate-50/80 backdrop-blur-xl shadow-[0_20px_40px_rgba(25,28,29,0.05)]">
<div class="flex justify-between items-center px-12 py-4 w-full max-w-[1920px] mx-auto">
<div class="flex items-center gap-8">
<span class="text-xl font-bold tracking-tighter text-slate-900 dark:text-slate-100 font-['Manrope']">The Digital Curator</span>
<nav class="hidden md:flex items-center gap-6">
<a class="text-slate-500 font-medium hover:text-slate-900 transition-colors py-1" href="#">Inventory</a>
<a class="text-blue-800 font-bold border-b-2 border-blue-800 pb-1" href="#">Traceability</a>
<a class="text-slate-500 font-medium hover:text-slate-900 transition-colors py-1" href="#">Analytics</a>
<a class="text-slate-500 font-medium hover:text-slate-900 transition-colors py-1" href="#">Archive</a>
</nav>
</div>
<div class="flex items-center gap-4">
<div class="relative group">
<span class="material-symbols-outlined p-2 text-slate-500 hover:bg-slate-200/50 rounded-full transition-colors cursor-pointer" data-icon="notifications">notifications</span>
<div class="absolute top-2 right-2 w-2 h-2 bg-blue-600 rounded-full border-2 border-white"></div>
</div>
<span class="material-symbols-outlined p-2 text-slate-500 hover:bg-slate-200/50 rounded-full transition-colors cursor-pointer" data-icon="settings">settings</span>
<div class="h-8 w-8 rounded-full overflow-hidden ml-2 bg-slate-200">
<img alt="Warehouse Manager Profile" data-alt="professional warehouse manager portrait with neutral lighting and blurred industrial background" src="https://lh3.googleusercontent.com/aida-public/AB6AXuDdbDwLnuc7ql5U-V3wtmhi848mVd8hW3NTEeQK-sho6awn8G6urXb7cnw9iV0zepHT3MS8pog2VKr7Mv-iE2q9Pib3D9qt7_Q6I7RgYSzOvK6jwqbish2G5CYtSlvQMooQ2YL0wmnfP37dup0UDEiITVU2I7Am3nNCdLaFsLtsTdr0pBgLvUFssUoPHWs8JZZFxFngpb1h3P-mGtWhnUfIUtAuZpEQOlmc8um2RHgCL2_6FYYPyw_wluWZ1p7SxbHp9PDg54K2Xwg"/>
</div>
</div>
</div>
</header>
<!-- Canvas Area -->
<section class="pt-28 px-12 pb-12 max-w-[1920px] mx-auto">
<!-- Header Section -->
<div class="mb-10">
<nav class="flex items-center gap-2 text-xs font-bold text-slate-400 uppercase tracking-widest mb-4">
<span>Warehouse Alpha</span>
<span class="material-symbols-outlined text-[14px]" data-icon="chevron_right">chevron_right</span>
<span class="text-blue-600">Traceability Intelligence</span>
</nav>
<div class="flex flex-col md:flex-row justify-between items-start md:items-end gap-6">
<div>
<h1 class="text-[56px] font-extrabold leading-[1.1] tracking-tight text-on-surface mb-2">Traceability Intelligence</h1>
<p class="text-body-lg text-secondary max-w-2xl leading-[1.6]">Secure, end-to-end provenance mapping for premium textile assets. Real-time verification of movement and SKU integrity across the distribution network.</p>
</div>
<!-- Selection Area -->
<div class="flex gap-4 w-full md:w-auto">
<div class="flex-1 md:w-64">
<label class="block text-[10px] font-bold uppercase tracking-widest text-slate-400 mb-2 ml-1">Select Lot</label>
<div class="relative">
<select class="w-full appearance-none bg-surface-container-low border-none rounded-xl py-4 px-5 pr-12 text-sm font-semibold text-on-surface focus:ring-0 focus:bg-surface-container-lowest transition-all group">
<option>LOT-2023-F-8821</option>
<option>LOT-2023-G-1192</option>
<option>LOT-2024-A-0045</option>
</select>
<span class="material-symbols-outlined absolute right-4 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" data-icon="expand_more">expand_more</span>
</div>
</div>
<div class="flex-1 md:w-64">
<label class="block text-[10px] font-bold uppercase tracking-widest text-slate-400 mb-2 ml-1">Select Roll ID</label>
<div class="relative">
<select class="w-full appearance-none bg-surface-container-low border-none rounded-xl py-4 px-5 pr-12 text-sm font-semibold text-on-surface focus:ring-0 focus:bg-surface-container-lowest transition-all group">
<option>ROLL-VX-0992</option>
<option>ROLL-VX-0993</option>
<option>ROLL-VX-0994</option>
</select>
<span class="material-symbols-outlined absolute right-4 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" data-icon="expand_more">expand_more</span>
</div>
</div>
</div>
</div>
</div>
<!-- Main Split Layout -->
<div class="grid grid-cols-12 gap-8 items-start">
<!-- Left: Data Table Section -->
<div class="col-span-12 lg:col-span-8 bg-surface-container-lowest rounded-[1.5rem] cloud-shadow overflow-hidden">
<div class="p-8 pb-0 flex justify-between items-center">
<h2 class="text-2xl font-bold tracking-tight text-on-surface">Event Logs</h2>
<button class="flex items-center gap-2 text-blue-800 text-sm font-bold hover:bg-blue-50 px-4 py-2 rounded-full transition-colors">
<span class="material-symbols-outlined text-[18px]" data-icon="filter_list">filter_list</span>
                            Filter Logs
                        </button>
</div>
<div class="overflow-x-auto">
<table class="w-full mt-6">
<thead>
<tr class="text-left bg-surface-container-low">
<th class="py-4 px-8 text-[11px] font-bold uppercase tracking-widest text-slate-400">Event</th>
<th class="py-4 px-4 text-[11px] font-bold uppercase tracking-widest text-slate-400">Time</th>
<th class="py-4 px-4 text-[11px] font-bold uppercase tracking-widest text-slate-400">Plan Name</th>
<th class="py-4 px-4 text-[11px] font-bold uppercase tracking-widest text-slate-400">Qty</th>
<th class="py-4 px-4 text-[11px] font-bold uppercase tracking-widest text-slate-400">Location</th>
<th class="py-4 px-8 text-[11px] font-bold uppercase tracking-widest text-slate-400">Status</th>
</tr>
</thead>
<tbody>
<tr class="bg-surface group hover:bg-surface-container-low transition-colors h-[72px]">
<td class="px-8 font-semibold text-on-surface">Dispatch Delivery</td>
<td class="px-4 text-sm text-secondary font-medium">14:22 PM</td>
<td class="px-4">
<span class="bg-surface-container-high px-3 py-1 rounded text-[11px] font-bold text-slate-600">SILK-882-P</span>
</td>
<td class="px-4 font-bold text-error">- 140 yd</td>
<td class="px-4 text-sm text-secondary">Loading Bay 4</td>
<td class="px-8">
<div class="flex items-center gap-2">
<div class="w-2 h-2 rounded-full bg-blue-500"></div>
<span class="text-xs font-bold uppercase tracking-wider text-blue-700">In Transit</span>
</div>
</td>
</tr>
<tr class="bg-surface-container-low group hover:bg-surface-container-high transition-colors h-[72px]">
<td class="px-8 font-semibold text-on-surface">Quality Audit</td>
<td class="px-4 text-sm text-secondary font-medium">11:05 AM</td>
<td class="px-4">
<span class="bg-surface-container-lowest px-3 py-1 rounded text-[11px] font-bold text-slate-600">SILK-882-P</span>
</td>
<td class="px-4 font-bold text-blue-600">+ 0 yd</td>
<td class="px-4 text-sm text-secondary">QC Lab A</td>
<td class="px-8">
<div class="flex items-center gap-2">
<div class="w-2 h-2 rounded-full bg-green-500"></div>
<span class="text-xs font-bold uppercase tracking-wider text-green-700">Verified</span>
</div>
</td>
</tr>
<tr class="bg-surface group hover:bg-surface-container-low transition-colors h-[72px]">
<td class="px-8 font-semibold text-on-surface">Bulk Inbound</td>
<td class="px-4 text-sm text-secondary font-medium">08:30 AM</td>
<td class="px-4">
<span class="bg-surface-container-high px-3 py-1 rounded text-[11px] font-bold text-slate-600">SILK-882-P</span>
</td>
<td class="px-4 font-bold text-blue-600">+ 450 yd</td>
<td class="px-4 text-sm text-secondary">Receiving Docks</td>
<td class="px-8">
<div class="flex items-center gap-2">
<div class="w-2 h-2 rounded-full bg-green-500"></div>
<span class="text-xs font-bold uppercase tracking-wider text-green-700">Stocked</span>
</div>
</td>
</tr>
<tr class="bg-surface-container-low group hover:bg-surface-container-high transition-colors h-[72px]">
<td class="px-8 font-semibold text-on-surface">Internal Transfer</td>
<td class="px-4 text-sm text-secondary font-medium">Yesterday</td>
<td class="px-4">
<span class="bg-surface-container-lowest px-3 py-1 rounded text-[11px] font-bold text-slate-600">SILK-882-P</span>
</td>
<td class="px-4 font-bold text-on-secondary-container">0 yd</td>
<td class="px-4 text-sm text-secondary">Section C -&gt; F</td>
<td class="px-8">
<div class="flex items-center gap-2">
<div class="w-2 h-2 rounded-full bg-slate-400"></div>
<span class="text-xs font-bold uppercase tracking-wider text-slate-600">Archived</span>
</div>
</td>
</tr>
</tbody>
</table>
</div>
<div class="p-8 text-center">
<button class="text-sm font-bold text-slate-400 hover:text-blue-800 transition-colors uppercase tracking-widest">Load Historical Records</button>
</div>
</div>
<!-- Right: Life Cycle Sidebar -->
<div class="col-span-12 lg:col-span-4 flex flex-col gap-8">
<div class="bg-surface-container-lowest rounded-[1.5rem] cloud-shadow p-8">
<div class="flex justify-between items-start mb-8">
<div>
<h3 class="text-2xl font-bold tracking-tight text-on-surface">Life Cycle Journey</h3>
<p class="text-xs text-slate-500 mt-1 uppercase font-bold tracking-wider">Asset Provenance Tracking</p>
</div>
<div class="bg-blue-50 text-blue-800 p-2 rounded-xl">
<span class="material-symbols-outlined" data-icon="route">route</span>
</div>
</div>
<!-- Timeline Visual -->
<div class="relative pl-8">
<!-- Vertical Line -->
<div class="absolute left-[7px] top-0 bottom-0 w-1 bg-gradient-to-b from-blue-600 via-blue-200 to-slate-100 rounded-full"></div>
<!-- Timeline Nodes -->
<div class="space-y-12">
<!-- Node 1: Current -->
<div class="relative">
<div class="absolute -left-[31px] top-0 w-4 h-4 rounded-full border-4 border-white signature-gradient shadow-lg"></div>
<div>
<p class="text-[10px] font-bold text-blue-600 uppercase tracking-widest mb-1">Active Now</p>
<h4 class="font-bold text-on-surface mb-2">Transit to Distribution Hub</h4>
<p class="text-sm text-secondary leading-relaxed mb-4">Carrier: Global Logistics Express. ETA: Today, 18:00.</p>
<div class="bg-surface-container-low rounded-xl overflow-hidden mb-2">
<img alt="Logistics Context" class="w-full h-32 object-cover" data-alt="clean warehouse shipping area with packages on wooden pallets and forklift in soft focus background" src="https://lh3.googleusercontent.com/aida-public/AB6AXuDVmJrHQ8rUBLnFOHKHJ-bikWv-Nx4Kz_aTUQOtnxpyzAEZDlrXWRznyCqeLi7uOSp4LYrnRqdnM0w5COzkyVBx6GjfF1SZMqL_W48OX7pJUO1QmMHip8bSN6ebaMxqgZKQWbcsGizmaqZLnE6AkSEXFxBcvXscnSsQxlLAJKDNzySUiwkCAtT_iqKDEe09ujkjz8SnHvTyhejoWifOEnrKHrDk2U1gVqBVGvwvyxtKps0heykmRVBeG3_RzJ3IpQ3IUnBQwKSrQHQ"/>
</div>
</div>
</div>
<!-- Node 2 -->
<div class="relative opacity-60">
<div class="absolute -left-[31px] top-0 w-4 h-4 rounded-full border-4 border-white bg-blue-400"></div>
<div>
<p class="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">Oct 24, 11:05 AM</p>
<h4 class="font-bold text-on-surface mb-2">QC Validation Passed</h4>
<p class="text-sm text-secondary leading-relaxed">No defects found. Tensile strength and color fastness meet Premium Tier standards.</p>
</div>
</div>
<!-- Node 3 -->
<div class="relative opacity-40">
<div class="absolute -left-[31px] top-0 w-4 h-4 rounded-full border-4 border-white bg-slate-400"></div>
<div>
<p class="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">Oct 24, 08:30 AM</p>
<h4 class="font-bold text-on-surface mb-2">Arrived at Warehouse Alpha</h4>
<p class="text-sm text-secondary leading-relaxed">Inbound scan complete. Assigned to Zone Red-42.</p>
</div>
</div>
<!-- Node 4 -->
<div class="relative opacity-30">
<div class="absolute -left-[31px] top-0 w-4 h-4 rounded-full border-4 border-white bg-slate-300"></div>
<div>
<p class="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">Oct 20, 09:00 AM</p>
<h4 class="font-bold text-on-surface mb-2">Manufacturing Complete</h4>
<p class="text-sm text-secondary leading-relaxed">Finishing stage achieved at Milan Mill Plant 2.</p>
</div>
</div>
</div>
</div>
</div>
<!-- Asset Summary Card -->
<div class="bg-surface-container-low rounded-[1.5rem] p-8">
<h4 class="text-[10px] font-bold text-slate-500 uppercase tracking-[0.2em] mb-4">Roll Specification</h4>
<div class="space-y-4">
<div class="flex justify-between items-center">
<span class="text-sm text-secondary">Material</span>
<span class="text-sm font-bold text-on-surface">100% Mulberry Silk</span>
</div>
<div class="flex justify-between items-center">
<span class="text-sm text-secondary">Weight</span>
<span class="text-sm font-bold text-on-surface">19 Momme</span>
</div>
<div class="flex justify-between items-center">
<span class="text-sm text-secondary">Width</span>
<span class="text-sm font-bold text-on-surface">114 cm</span>
</div>
<div class="flex justify-between items-center">
<span class="text-sm text-secondary">Original Ydg</span>
<span class="text-sm font-bold text-on-surface">450 yd</span>
</div>
</div>
<div class="mt-8">
<div class="flex items-center gap-3 bg-white p-4 rounded-xl">
<div class="h-12 w-12 rounded-lg signature-gradient flex items-center justify-center text-white">
<span class="material-symbols-outlined" data-icon="qr_code_2">qr_code_2</span>
</div>
<div>
<p class="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Digital Twin ID</p>
<p class="font-mono text-xs text-on-surface">0x7782_SILK_ALPHA</p>
</div>
</div>
</div>
</div>
</div>
</div>
</section>
</main>
</body></html>