"use strict";
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
const money = (value) => new Intl.NumberFormat('ar-PS', { style: 'currency', currency: settings.currency || 'ILS', maximumFractionDigits: 2 }).format(Number(value || 0));
const dateLabel = (value, options = { day: 'numeric', month: 'short', year: 'numeric' }) => value ? new Intl.DateTimeFormat('ar-PS', options).format(new Date(value.length === 10 ? `${value}T12:00:00` : value)) : '—';
const timeLabel = (value) => value ? new Intl.DateTimeFormat('ar-PS', { hour: '2-digit', minute: '2-digit' }).format(new Date(value)) : '—';
const localISODate = (d = new Date()) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const localDateTime = (d = new Date()) => `${localISODate(d)}T${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
const statusLabel = (status) => ({ pending: 'بانتظار التأكيد', confirmed: 'مؤكد', completed: 'مكتمل', cancelled: 'ملغي' }[status] || status);
const statusClass = (status) => ({ pending: 'pending', confirmed: 'confirmed', completed: 'completed', cancelled: 'cancelled' }[status] || 'neutral');
const initialToken = localStorage.getItem('sd_access_token') || '';
let token = initialToken;
let user = null;
let view = 'dashboard';
let settings = { business_name: 'SALOON DREEM', currency: 'ILS', phone: '', address: '', open_time: '09:00', close_time: '22:00', theme: 'dark' };
let cachedServices = [];
let cachedBarbers = [];
let customerPrefillService = '';
let activeCustomerView = 'discover';
async function api(path, init = {}) {
    const headers = new Headers(init.headers || {});
    if (token)
        headers.set('Authorization', `Bearer ${token}`);
    if (init.body && !headers.has('Content-Type'))
        headers.set('Content-Type', 'application/json');
    const response = await fetch(`${apiBase()}${path}`, { ...init, headers });
    const type = response.headers.get('content-type') || '';
    const data = type.includes('application/json') ? await response.json().catch(() => ({})) : await response.text();
    if (!response.ok) {
        if (response.status === 401 && token) {
            token = '';
            user = null;
            localStorage.removeItem('sd_access_token');
        }
        throw new Error(data?.detail || data?.message || `تعذر إتمام الطلب (${response.status}).`);
    }
    return data;
}
function apiBase() { return (localStorage.getItem('sd_api_base') || window.SD_DEFAULT_API_BASE || '').trim().replace(/\/$/, ''); }
function toast(message, kind = 'success') {
    const region = $('#toast-region');
    if (!region)
        return;
    const item = document.createElement('div');
    item.className = `toast toast-${kind}`;
    item.textContent = message;
    region.append(item);
    window.setTimeout(() => item.classList.add('toast-out'), 3200);
    window.setTimeout(() => item.remove(), 3650);
}
function showAuth(setup) {
    $('#auth-screen')?.classList.remove('hidden');
    $('#customer-screen')?.classList.add('hidden');
    $('#app-shell')?.classList.add('hidden');
    $('#auth-title').textContent = setup ? 'لنبدأ بصالونك' : 'أهلًا بعودتك';
    $('#auth-eyebrow').textContent = setup ? 'الإعداد الأولي' : 'مساحة عملك';
    $('#auth-description').textContent = setup ? 'أنشئ حساب المدير لتأمين بيانات الصالون.' : 'سجّل الدخول لإدارة صالونك.';
    $('#business-name-wrap').classList.toggle('hidden', !setup);
    $('#confirm-password-wrap').classList.toggle('hidden', !setup);
    const password = $('#auth-password');
    password.autocomplete = setup ? 'new-password' : 'current-password';
    password.placeholder = setup ? '٨ أحرف على الأقل' : 'أدخل كلمة المرور';
    $('#auth-password-confirm')?.toggleAttribute('required', setup);
    $('#auth-submit').innerHTML = setup ? 'إنشاء حساب المدير <span>←</span>' : 'تسجيل الدخول <span>←</span>';
    $('#auth-footnote').textContent = setup ? 'اختر كلمة مرور قوية. لا توجد كلمة مرور افتراضية.' : 'بيانات الإدارة محفوظة في قاعدة بيانات الصالون على هذا الجهاز.';
}
function setToken(value) { token = value; localStorage.setItem('sd_access_token', value); }
async function init() {
    const baseInput = $('#api-base-input');
    baseInput.value = apiBase();
    try {
        const health = await api('/api/health');
        const setup = await api('/api/setup/status');
        if (token && !setup.setup_required) {
            try {
                const me = await api('/api/auth/me');
                user = me.user;
                await enterAdmin();
                return;
            }
            catch {
                token = '';
                localStorage.removeItem('sd_access_token');
            }
        }
        showAuth(setup.setup_required);
        const label = $('#today-label');
        if (label)
            label.textContent = dateLabel(localISODate());
    }
    catch (error) {
        showAuth(true);
        toast(`تعذر الاتصال بالخادم. ${error instanceof Error ? error.message : ''}`, 'error');
    }
}
async function enterAdmin() {
    $('#auth-screen')?.classList.add('hidden');
    $('#customer-screen')?.classList.add('hidden');
    $('#app-shell')?.classList.remove('hidden');
    $('#account-username').textContent = user?.username || 'المدير';
    $('#today-label').textContent = dateLabel(localISODate());
    try {
        settings = await api('/api/settings');
        applyTheme();
        $('#sidebar-salon-name').textContent = settings.business_name || 'SALOON DREEM';
    }
    catch (e) {
        toast(errorText(e), 'error');
    }
    try {
        cachedServices = await api('/api/services?include_inactive=true');
        cachedBarbers = await api('/api/barbers');
    }
    catch (e) {
        toast(errorText(e), 'error');
    }
    await renderView(view);
}
function errorText(error) { return error instanceof Error ? error.message : 'حدث خطأ غير متوقع.'; }
function applyTheme() {
    document.documentElement.dataset.theme = settings.theme === 'light' ? 'light' : 'dark';
    const theme = document.querySelector('meta[name="theme-color"]');
    if (theme)
        theme.setAttribute('content', settings.theme === 'light' ? '#f4f1e8' : '#101916');
}
function setView(next) { view = next; renderView(next); $$('.nav-item[data-view]').forEach(el => el.classList.toggle('active', el.getAttribute('data-view') === next)); closeSidebar(); }
function closeSidebar() { $('#sidebar')?.classList.remove('sidebar-open'); $('#sidebar-backdrop')?.classList.remove('visible'); }
function openSidebar() { $('#sidebar')?.classList.add('sidebar-open'); $('#sidebar-backdrop')?.classList.add('visible'); }
function pageHeader(kicker, title, description, action = '') { return `<div class="page-heading"><div><p class="eyebrow">${kicker}</p><h2>${title}</h2><p class="muted">${description}</p></div>${action}</div>`; }
function emptyState(icon, title, description, button = '') { return `<div class="empty-state"><div class="empty-icon">${icon}</div><h3>${title}</h3><p>${description}</p>${button}</div>`; }
function actionButton(action, label, icon = '', extra = '') { return `<button type="button" class="button button-secondary button-small" data-action="${action}" ${extra}>${icon ? `<span>${icon}</span> ` : ''}${label}</button>`; }
function appointmentsTable(rows, compact = false) {
    if (!rows.length)
        return emptyState('◷', 'لا توجد مواعيد هنا', 'ستظهر الحجوزات بمجرد إضافتها.');
    return `<div class="table-wrap"><table><thead><tr><th>العميل</th><th>الخدمة</th><th>الحلاق</th><th>التاريخ والوقت</th><th>الحالة</th><th>القيمة</th>${compact ? '' : '<th>إجراءات</th>'}</tr></thead><tbody>${rows.map(a => `<tr><td><div class="person-cell"><span class="person-avatar">${escapeHtml((a.customer_name || 'ع').trim().slice(0, 1))}</span><div><strong>${escapeHtml(a.customer_name)}</strong><small>${escapeHtml(a.customer_phone)}</small></div></div></td><td>${escapeHtml(a.service_name)}</td><td>${escapeHtml(a.barber_name || 'غير محدد')}</td><td><strong>${dateLabel(a.start_at, { day: 'numeric', month: 'short' })}</strong><small class="cell-sub">${timeLabel(a.start_at)}</small></td><td><span class="status-pill status-${statusClass(a.status)}">${statusLabel(a.status)}</span></td><td>${money(a.price)}<small class="cell-sub">${a.payment_status === 'paid' ? 'مدفوع' : 'غير مدفوع'}</small></td>${compact ? '' : `<td><div class="table-actions"><button class="icon-button" title="تحديث الحالة" aria-label="تحديث حالة الموعد" data-action="appointment-status" data-id="${a.id}" data-status="${a.status}">•••</button>${a.payment_status === 'paid' ? '' : `<button class="button button-small button-primary" data-action="pay" data-id="${a.id}">تحصيل</button>`}</div></td>`}</tr>`).join('')}</tbody></table></div>`;
}
async function renderView(next) {
    view = next;
    const titles = { dashboard: ['مساحة العمل', 'نظرة عامة', 'صورة واضحة عن الحجوزات وحركة الصالون.'], appointments: ['تنظيم اليوم', 'المواعيد والتقويم', 'تابع الحجوزات، أكّد المواعيد وأدر التحصيل.'], customers: ['علاقات تدوم', 'العملاء', 'ملف موحد لكل عميل وتاريخ زيارته.'], barbers: ['فريقك هو قوتك', 'فريق الحلاقين', 'نظّم الفريق وتوزيع المواعيد.'], services: ['تفاصيل الخدمة', 'الخدمات والأسعار', 'حدّث قائمة الخدمات ومددها وأسعارها.'], finance: ['الصندوق', 'المالية والصندوق', 'سجّل الدخل والمصروفات وراجع صافي الحركة.'], reports: ['قرارات أوضح', 'التقارير والتصدير', 'اطّلع على المؤشرات ونزّل بياناتك.'], settings: ['مساحة مخصصة لك', 'إعدادات الصالون', 'هوية المكان، أوقات العمل، والأمان.'] };
    const [kicker, title, description] = titles[next];
    $('#page-title').textContent = title;
    $('#topbar-kicker').textContent = kicker;
    const content = $('#page-content');
    content.innerHTML = `<div class="loading-state"><span class="spinner"></span><p>جارٍ تجهيز مساحة العمل…</p></div>`;
    try {
        if (next === 'dashboard')
            content.innerHTML = await dashboardPage();
        if (next === 'appointments')
            content.innerHTML = await appointmentsPage();
        if (next === 'customers')
            content.innerHTML = await customersPage();
        if (next === 'barbers')
            content.innerHTML = await barbersPage();
        if (next === 'services')
            content.innerHTML = await servicesPage();
        if (next === 'finance')
            content.innerHTML = await financePage();
        if (next === 'reports')
            content.innerHTML = await reportsPage();
        if (next === 'settings')
            content.innerHTML = await settingsPage();
    }
    catch (error) {
        content.innerHTML = emptyState('!', 'تعذّر تحميل هذه الصفحة', escapeHtml(errorText(error)), `<button class="button button-primary" data-action="refresh-view">إعادة المحاولة</button>`);
    }
    $$('.nav-item[data-view]').forEach(el => el.classList.toggle('active', el.getAttribute('data-view') === next));
}
async function dashboardPage() {
    const d = await api('/api/dashboard');
    const m = d.metrics;
    const upcoming = d.upcoming;
    const dateGreeting = new Intl.DateTimeFormat('ar-PS', { weekday: 'long', day: 'numeric', month: 'long' }).format(new Date());
    const cards = [['مواعيد اليوم', m.today_appointments, '◷', 'مواعيد غير ملغاة'], ['بانتظار التأكيد', m.pending_appointments, '✧', 'طلبات تحتاج مراجعتك'], ['قاعدة العملاء', m.customers, '♙', 'إجمالي العملاء المسجلين'], ['دخل هذا الشهر', money(m.monthly_income), '↗', 'عمليات تحصيل مسجلة']];
    return `${pageHeader('مرحبًا بعودتك', `صباح الأعمال الجميلة <span class="heading-spark">✦</span>`, `اليوم ${dateGreeting}. إليك أهم ما يحتاج انتباهك.`, actionButton('new-booking', 'حجز جديد', '＋', 'class="button button-primary"'))}
    <section class="metric-grid">${cards.map((c, i) => `<article class="metric-card metric-${i}"><div class="metric-top"><span>${c[0]}</span><span class="metric-icon">${c[2]}</span></div><strong class="metric-value">${c[1]}</strong><small>${c[3]}</small></article>`).join('')}</section>
    <section class="dashboard-grid"><article class="panel panel-main"><div class="panel-heading"><div><h3>المواعيد القادمة</h3><p>أقرب المواعيد التي تتطلب المتابعة</p></div><button class="text-link" data-view="appointments">عرض جميع المواعيد ←</button></div>${appointmentsTable(upcoming, true)}</article><article class="panel welcome-panel"><div class="welcome-art"><span class="art-scissors">✂</span><span class="art-star">✦</span><span class="art-circle"></span></div><p class="eyebrow">DREEM STANDARD</p><h3>التفاصيل الصغيرة<br>تصنع تجربة كبيرة.</h3><p>نظّم الحجز، اهتمّ بالعميل، واترك لصنعتك مساحة لتتألق.</p><div class="welcome-footer"><span class="status-dot"></span> ${cachedBarbers.filter(b => !!b.active).length} حلاق نشط في الفريق</div></article></section>
    <section class="panel"><div class="panel-heading"><div><h3>أحدث الحجوزات</h3><p>آخر الطلبات التي وصلت إلى الصالون</p></div><span class="muted small-text">آخر 5 حجوزات</span></div>${appointmentsTable(d.recent, true)}</section>`;
}
async function appointmentsPage() {
    const rows = await api('/api/appointments?limit=1000');
    const selected = $('#appointment-filter')?.value || 'all';
    const q = $('#appointment-search')?.value.trim().toLowerCase() || '';
    const filtered = rows.filter(a => (selected === 'all' || a.status === selected) && (!q || [a.customer_name, a.customer_phone, a.service_name, a.barber_name].some(v => String(v || '').toLowerCase().includes(q))));
    return `${pageHeader('كل شيء في وقته', 'المواعيد والتقويم', 'راقب جدولك اليومي وراجع الحالات والمدفوعات.', `<button class="button button-primary" data-action="new-booking">＋ إضافة موعد</button>`)}
  <section class="panel filter-panel"><div class="filter-row"><label class="search-box"><span>⌕</span><input id="appointment-search" placeholder="ابحث باسم العميل أو الهاتف أو الخدمة" value="${escapeHtml(q)}"></label><label class="select-field"><span>الحالة</span><select id="appointment-filter"><option value="all" ${selected === 'all' ? 'selected' : ''}>كل الحالات</option><option value="pending" ${selected === 'pending' ? 'selected' : ''}>بانتظار التأكيد</option><option value="confirmed" ${selected === 'confirmed' ? 'selected' : ''}>مؤكد</option><option value="completed" ${selected === 'completed' ? 'selected' : ''}>مكتمل</option><option value="cancelled" ${selected === 'cancelled' ? 'selected' : ''}>ملغي</option></select></label><span class="result-count">${filtered.length} موعد</span></div></section>
  <section class="panel">${appointmentsTable(filtered)}</section>`;
}
async function customersPage() {
    const q = $('#customer-search')?.value || '';
    const customers = await api(`/api/customers?limit=1000${q ? `&q=${encodeURIComponent(q)}` : ''}`);
    return `${pageHeader('الناس أولًا', 'العملاء', 'تعرّف على زبائنك واحتفظ بسجل الزيارات والإنفاق.', `<button class="button button-primary" data-action="new-customer">＋ عميل جديد</button>`)}
  <section class="panel"><div class="filter-row"><label class="search-box"><span>⌕</span><input id="customer-search" placeholder="ابحث بالاسم أو رقم الهاتف" value="${escapeHtml(q)}"></label><span class="result-count">${customers.length} عميل</span></div>
  ${customers.length ? `<div class="table-wrap"><table><thead><tr><th>العميل</th><th>رقم الهاتف</th><th>عدد الزيارات</th><th>إجمالي الإنفاق</th><th>آخر زيارة</th><th>تواصل</th></tr></thead><tbody>${customers.map(c => `<tr><td><div class="person-cell"><span class="person-avatar">${escapeHtml(c.name.trim().slice(0, 1))}</span><strong>${escapeHtml(c.name)}</strong></div></td><td dir="ltr" class="numeric-cell">${escapeHtml(c.phone)}</td><td>${c.appointments_count || 0}</td><td>${money(c.total_spend)}</td><td>${dateLabel(c.last_appointment)}</td><td><a class="button button-small button-secondary" href="tel:${escapeHtml(c.phone)}">اتصال</a></td></tr>`).join('')}</tbody></table></div>` : emptyState('♙', 'لا توجد نتائج', 'أضف أول عميل، أو غيّر كلمات البحث.')}</section>`;
}
async function barbersPage() {
    cachedBarbers = await api('/api/barbers');
    const active = cachedBarbers.filter(b => !!b.active).length;
    return `${pageHeader('صنّاع الإطلالة', 'فريق الحلاقين', `${active} حلاق نشط · أضف الفريق ووزّع الحجوزات باحتراف.`, `<button class="button button-primary" data-action="new-barber">＋ إضافة حلاق</button>`)}
  ${cachedBarbers.length ? `<section class="team-grid">${cachedBarbers.map(b => `<article class="team-card"><div class="team-card-top"><span class="team-avatar">${escapeHtml(b.name.trim().slice(0, 1))}</span><span class="status-pill ${b.active ? 'status-completed' : 'status-cancelled'}">${b.active ? 'نشط' : 'متوقف'}</span></div><h3>${escapeHtml(b.name)}</h3><p>${escapeHtml(b.specialty || 'حلاق · فريق الصالون')}</p><div class="team-stats"><div><strong>${b.appointments_count || 0}</strong><small>حجز</small></div><div><strong>${b.completed_count || 0}</strong><small>مكتمل</small></div></div><div class="team-actions"><button class="button button-secondary button-small" data-action="edit-barber" data-id="${b.id}">تعديل البيانات</button><button class="button button-quiet button-small" data-action="toggle-barber" data-id="${b.id}" data-active="${b.active ? 1 : 0}">${b.active ? 'إيقاف' : 'تفعيل'}</button></div></article>`).join('')}</section>` : emptyState('✂', 'ابدأ ببناء فريقك', 'لم تتم إضافة أي حلاق بعد. أضف حلاقًا لتفعيل استقبال الحجوزات.', `<button class="button button-primary" data-action="new-barber">＋ إضافة أول حلاق</button>`)}`;
}
async function servicesPage() {
    cachedServices = await api('/api/services?include_inactive=true');
    return `${pageHeader('قائمة خدماتك', 'الخدمات والأسعار', 'أسعار واضحة ومدد واقعية تجعل حجز العميل أسهل.', `<button class="button button-primary" data-action="new-service">＋ إضافة خدمة</button>`)}
  ${cachedServices.length ? `<section class="service-grid">${cachedServices.map(s => `<article class="service-admin-card ${s.active ? '' : 'service-disabled'}"><div class="service-glyph">✦</div><div class="service-admin-status"><span class="status-pill ${s.active ? 'status-completed' : 'status-cancelled'}">${s.active ? 'متاحة' : 'مخفية'}</span></div><h3>${escapeHtml(s.name)}</h3><p>${escapeHtml(s.description || 'خدمة من خدمات الصالون')}</p><div class="service-info"><strong>${money(s.price)}</strong><span>◷ ${s.duration_minutes} دقيقة</span></div><div class="service-card-footer"><small>${s.bookings_count || 0} حجز</small><div><button class="button button-small button-secondary" data-action="edit-service" data-id="${s.id}">تعديل</button> <button class="button button-small button-quiet" data-action="toggle-service" data-id="${s.id}" data-active="${s.active ? 1 : 0}">${s.active ? 'إخفاء' : 'إظهار'}</button></div></div></article>`).join('')}</section>` : emptyState('◇', 'أضف خدمات صالونك', 'مثل قص الشعر، تهذيب اللحية، والباقات الخاصة.', `<button class="button button-primary" data-action="new-service">＋ إضافة خدمة</button>`)}`;
}
async function financePage() {
    const f = await api('/api/finance/summary');
    const txs = f.transactions || [];
    return `${pageHeader('إدارة التدفق النقدي', 'المالية والصندوق', 'سجّل كل حركة مالية لتبقى الصورة دقيقة.', `<button class="button button-primary" data-action="new-transaction">＋ حركة مالية</button>`)}
  <section class="metric-grid metric-grid-finance"><article class="metric-card"><div class="metric-top">إجمالي الدخل <span class="metric-icon">↗</span></div><strong class="metric-value">${money(f.income)}</strong><small>عمليات التحصيل المسجلة</small></article><article class="metric-card"><div class="metric-top">المصروفات <span class="metric-icon">↘</span></div><strong class="metric-value">${money(f.expenses)}</strong><small>المصروفات المسجلة</small></article><article class="metric-card metric-net"><div class="metric-top">صافي الحركة <span class="metric-icon">＝</span></div><strong class="metric-value">${money(f.net)}</strong><small>الدخل ناقص المصروفات</small></article></section>
  <section class="panel"><div class="panel-heading"><div><h3>دفتر الحركات</h3><p>آخر الحركات المالية المسجلة</p></div><span class="result-count">${txs.length} حركة</span></div>${txs.length ? `<div class="table-wrap"><table><thead><tr><th>النوع</th><th>التصنيف</th><th>التاريخ</th><th>ملاحظة</th><th>القيمة</th></tr></thead><tbody>${txs.map((t) => `<tr><td><span class="status-pill ${t.kind === 'income' ? 'status-completed' : 'status-cancelled'}">${t.kind === 'income' ? 'دخل' : 'مصروف'}</span></td><td>${escapeHtml(t.category)}</td><td>${dateLabel(t.transaction_date)}</td><td>${escapeHtml(t.note || '—')}</td><td class="${t.kind === 'income' ? 'positive-value' : 'negative-value'}">${t.kind === 'income' ? '+' : '−'} ${money(t.amount)}</td></tr>`).join('')}</tbody></table></div>` : emptyState('↗', 'دفتر الصندوق فارغ', 'ستظهر الحركات هنا بمجرد تسجيلها.')}</section>`;
}
async function reportsPage() {
    const d = await api('/api/dashboard');
    const f = await api('/api/finance/summary');
    const a = await api('/api/appointments?limit=1000');
    const done = a.filter(x => x.status === 'completed').length;
    const cancelled = a.filter(x => x.status === 'cancelled').length;
    const pending = a.filter(x => x.status === 'pending').length;
    return `${pageHeader('الأرقام تحكي القصة', 'التقارير والتصدير', 'ملخص تشغيلي ومؤشرات قابلة للتنزيل والتدقيق.', `<button class="button button-primary" data-action="export-appointments">↓ تصدير الحجوزات CSV</button>`)}
  <section class="metric-grid"><article class="metric-card"><div class="metric-top">إجمالي الحجوزات <span class="metric-icon">▦</span></div><strong class="metric-value">${a.length}</strong><small>جميع الحالات</small></article><article class="metric-card"><div class="metric-top">مكتمل <span class="metric-icon">✓</span></div><strong class="metric-value">${done}</strong><small>مواعيد أُنجزت</small></article><article class="metric-card"><div class="metric-top">بانتظار التأكيد <span class="metric-icon">◷</span></div><strong class="metric-value">${pending}</strong><small>طلبات تحتاج متابعة</small></article><article class="metric-card"><div class="metric-top">ملغي <span class="metric-icon">×</span></div><strong class="metric-value">${cancelled}</strong><small>حجوزات ألغيت</small></article></section>
  <section class="report-grid"><article class="panel report-card"><span class="metric-icon">₪</span><p>صافي الحركات المالية المسجلة</p><strong>${money(f.net)}</strong><small>الدخل: ${money(f.income)} · المصروفات: ${money(f.expenses)}</small></article><article class="panel report-card"><span class="metric-icon">♙</span><p>قاعدة العملاء</p><strong>${d.metrics.customers}</strong><small>إجمالي العملاء المسجلين في قاعدة البيانات</small></article><article class="panel report-card"><span class="metric-icon">✂</span><p>فريق الحلاقين النشط</p><strong>${cachedBarbers.filter(b => !!b.active).length}</strong><small>بناءً على حالة أعضاء الفريق الحالية</small></article></section>
  <section class="panel note-panel"><span class="note-icon">i</span><p><strong>ملاحظة محاسبية:</strong> الأرقام المالية هنا مبنية على الحركات المسجلة داخل النظام، وليست متصلة ببنك أو بوابة دفع خارجية. راجعها مع مستنداتك الفعلية قبل اعتماد التقارير الرسمية.</p></section>`;
}
async function settingsPage() {
    settings = await api('/api/settings');
    return `${pageHeader('مصمّم حسب هويتك', 'إعدادات الصالون', 'عدّل معلومات النشاط ومظهر التطبيق وأمان الحساب.', `<button class="button button-secondary" data-action="change-password">تغيير كلمة المرور</button>`)}
  <form id="settings-form" class="settings-layout"><section class="panel settings-panel"><div class="panel-heading"><div><h3>بيانات النشاط</h3><p>تظهر هذه البيانات داخل مساحة العمل</p></div><span class="settings-symbol">✦</span></div><div class="form-grid"><label class="field full-field"><span>اسم الصالون</span><input name="business_name" required minlength="2" maxlength="100" value="${escapeHtml(settings.business_name)}"></label><label class="field"><span>رقم الهاتف</span><input name="phone" type="tel" value="${escapeHtml(settings.phone)}" placeholder="059…"></label><label class="field"><span>العملة</span><select name="currency"><option value="ILS" ${settings.currency === 'ILS' ? 'selected' : ''}>شيكل إسرائيلي (ILS)</option><option value="USD" ${settings.currency === 'USD' ? 'selected' : ''}>دولار أمريكي (USD)</option><option value="JOD" ${settings.currency === 'JOD' ? 'selected' : ''}>دينار أردني (JOD)</option><option value="SAR" ${settings.currency === 'SAR' ? 'selected' : ''}>ريال سعودي (SAR)</option><option value="AED" ${settings.currency === 'AED' ? 'selected' : ''}>درهم إماراتي (AED)</option><option value="EUR" ${settings.currency === 'EUR' ? 'selected' : ''}>يورو (EUR)</option></select></label><label class="field full-field"><span>العنوان</span><input name="address" value="${escapeHtml(settings.address)}" placeholder="المدينة، الشارع، والمعلم القريب"></label></div></section>
  <section class="panel settings-panel"><div class="panel-heading"><div><h3>أوقات العمل</h3><p>مرجع تنظيمي للفريق والعملاء</p></div><span class="settings-symbol">◷</span></div><div class="form-grid"><label class="field"><span>وقت الفتح</span><input type="time" name="open_time" value="${escapeHtml(settings.open_time || '09:00')}" required></label><label class="field"><span>وقت الإغلاق</span><input type="time" name="close_time" value="${escapeHtml(settings.close_time || '22:00')}" required></label></div><div class="theme-setting"><div><strong>مظهر مساحة العمل</strong><small>تغيير المظهر بين الداكن والفاتح</small></div><select name="theme"><option value="dark" ${settings.theme === 'dark' ? 'selected' : ''}>داكن أنيق</option><option value="light" ${settings.theme === 'light' ? 'selected' : ''}>فاتح هادئ</option></select></div><button class="button button-primary" type="submit">حفظ الإعدادات</button></section></form>
  <section class="panel security-panel"><div><span class="security-icon">⌑</span><div><h3>جلسة الإدارة</h3><p>مسجّل الدخول باسم <strong>${escapeHtml(user?.username || 'المدير')}</strong>. احتفظ بكلمة المرور ولا تشاركها.</p></div></div><button class="button button-secondary" data-action="logout">تسجيل الخروج</button></section>`;
}
function modal(title, body, submit = 'حفظ البيانات', formName = '') {
    const root = $('#modal-root');
    root.innerHTML = `<div class="modal-backdrop" data-action="close-modal"><section class="modal-card" role="dialog" aria-modal="true" aria-labelledby="modal-title"><div class="modal-heading"><div><p class="eyebrow">SALOON DREEM</p><h2 id="modal-title">${title}</h2></div><button type="button" class="icon-button" data-action="close-modal" aria-label="إغلاق">×</button></div><form id="modal-form" data-form="${formName}"><div class="modal-body">${body}</div><div class="modal-footer"><button type="button" class="button button-quiet" data-action="close-modal">إلغاء</button><button type="submit" class="button button-primary">${submit}</button></div></form></section></div>`;
    const first = $('input:not([type=hidden]),select,textarea', root);
    first?.focus();
}
function field(name, label, value = '', type = 'text', required = true, extra = '') { return `<label class="field"><span>${label}</span><input name="${name}" type="${type}" value="${escapeHtml(value)}" ${required ? 'required' : ''} ${extra}></label>`; }
function newBookingModal() {
    if (!cachedServices.length) {
        toast('أضف خدمة نشطة أولًا قبل إنشاء حجز.', 'error');
        setView('services');
        return;
    }
    if (!cachedBarbers.some(b => !!b.active)) {
        toast('أضف حلاقًا نشطًا أولًا حتى يمكن إسناد المواعيد.', 'error');
        setView('barbers');
        return;
    }
    const serviceOptions = cachedServices.filter(s => s.active).map(s => `<option value="${s.id}">${escapeHtml(s.name)} · ${money(s.price)} · ${s.duration_minutes} د</option>`).join('');
    const barberOptions = cachedBarbers.filter(b => !!b.active).map(b => `<option value="${b.id}">${escapeHtml(b.name)}</option>`).join('');
    modal('حجز موعد جديد', `<div class="form-grid">${field('customer_name', 'اسم العميل', '', 'text', true, 'minlength="2"')}${field('customer_phone', 'رقم الهاتف', '', 'tel', true, 'minlength="5"')}${field('customer_email', 'البريد الإلكتروني (اختياري)', '', 'email', false)}<label class="field"><span>الخدمة</span><select name="service_id" required>${serviceOptions}</select></label><label class="field"><span>الحلاق</span><select name="barber_id" required>${barberOptions}</select></label>${field('start_at', 'تاريخ ووقت الموعد', localDateTime(new Date(Date.now() + 3600000)), 'datetime-local', true, `min="${localDateTime()}"`)}<label class="field full-field"><span>ملاحظات (اختياري)</span><textarea name="notes" rows="3" maxlength="1000" placeholder="تفاصيل يهم الفريق معرفتها"></textarea></label></div>`, 'تأكيد الحجز', 'booking');
}
function customerModal() { modal('إضافة عميل', `<div class="form-grid">${field('name', 'اسم العميل')}${field('phone', 'رقم الهاتف', '', 'tel', true, 'minlength="5"')}${field('email', 'البريد الإلكتروني', '', 'email', false)}<label class="field full-field"><span>ملاحظات</span><textarea name="notes" rows="3" maxlength="1000"></textarea></label></div>`, 'إضافة العميل', 'customer'); }
function barberModal(barber) { modal(barber ? 'تعديل بيانات الحلاق' : 'إضافة حلاق', `${barber ? `<input type="hidden" name="id" value="${barber.id}">` : ''}<div class="form-grid">${field('name', 'الاسم', barber?.name || '')}${field('phone', 'رقم الهاتف', barber?.phone || '', 'tel', false)}${field('specialty', 'التخصص أو النبذة', barber?.specialty || '', 'text', false)}<label class="field full-field"><span>حالة الحساب</span><select name="active"><option value="1" ${!barber || barber.active ? 'selected' : ''}>نشط ويستقبل حجوزات</option><option value="0" ${barber && !barber.active ? 'selected' : ''}>متوقف مؤقتًا</option></select></label></div>`, 'حفظ بيانات الحلاق', 'barber'); }
function serviceModal(service) { modal(service ? 'تعديل الخدمة' : 'إضافة خدمة', `${service ? `<input type="hidden" name="id" value="${service.id}">` : ''}<div class="form-grid">${field('name', 'اسم الخدمة', service?.name || '')}${field('price', 'السعر', String(service?.price ?? ''), 'number', true, 'min="0" step="0.01"')}${field('duration_minutes', 'المدة بالدقائق', String(service?.duration_minutes ?? 30), 'number', true, 'min="5" max="480" step="5"')}<label class="field"><span>حالة الخدمة</span><select name="active"><option value="1" ${!service || service.active ? 'selected' : ''}>متاحة للحجز</option><option value="0" ${service && !service.active ? 'selected' : ''}>مخفية</option></select></label><label class="field full-field"><span>وصف الخدمة</span><textarea name="description" rows="3" maxlength="400">${escapeHtml(service?.description || '')}</textarea></label></div>`, 'حفظ الخدمة', 'service'); }
function transactionModal() { modal('إضافة حركة مالية', `<div class="form-grid"><label class="field"><span>نوع الحركة</span><select name="kind"><option value="income">دخل</option><option value="expense">مصروف</option></select></label>${field('category', 'التصنيف', 'خدمات الصالون')}${field('amount', 'المبلغ', '', 'number', true, 'min="0.01" step="0.01"')}${field('transaction_date', 'التاريخ', localISODate(), 'date')}<label class="field full-field"><span>ملاحظة</span><textarea name="note" rows="3" maxlength="1000" placeholder="مثال: شراء مستلزمات أو إيجار"></textarea></label></div>`, 'تسجيل الحركة', 'transaction'); }
function passwordModal() { modal('تغيير كلمة المرور', `<div class="form-grid">${field('current_password', 'كلمة المرور الحالية', '', 'password', true, 'autocomplete="current-password"')}${field('new_password', 'كلمة المرور الجديدة', '', 'password', true, 'minlength="8" autocomplete="new-password"')}${field('confirm_password', 'تأكيد كلمة المرور الجديدة', '', 'password', true, 'minlength="8" autocomplete="new-password"')}</div><p class="form-hint">استخدم ٨ أحرف على الأقل، وتجنب كلمات المرور المستخدمة في مواقع أخرى.</p>`, 'تحديث كلمة المرور', 'password'); }
function closeModal() { $('#modal-root').innerHTML = ''; }
function formValues(form) { const result = {}; new FormData(form).forEach((value, key) => result[key] = String(value).trim()); return result; }
async function handleModalSubmit(form) {
    const kind = form.dataset.form || '';
    const d = formValues(form);
    const button = $('button[type=submit]', form);
    if (button) {
        button.disabled = true;
        button.textContent = 'جارٍ الحفظ…';
    }
    try {
        if (kind === 'booking') {
            await api('/api/appointments', { method: 'POST', body: JSON.stringify({ ...d, service_id: Number(d.service_id), barber_id: Number(d.barber_id), status: 'confirmed' }) });
            toast('تم إنشاء الموعد بنجاح.');
            closeModal();
            await renderView('appointments');
        }
        else if (kind === 'customer') {
            await api('/api/customers', { method: 'POST', body: JSON.stringify(d) });
            toast('تمت إضافة العميل.');
            closeModal();
            await renderView('customers');
        }
        else if (kind === 'barber') {
            const payload = { name: d.name, phone: d.phone, specialty: d.specialty, active: d.active === '1' };
            if (d.id)
                await api(`/api/barbers/${d.id}`, { method: 'PATCH', body: JSON.stringify(payload) });
            else
                await api('/api/barbers', { method: 'POST', body: JSON.stringify(payload) });
            toast('تم حفظ بيانات الحلاق.');
            closeModal();
            cachedBarbers = await api('/api/barbers');
            await renderView('barbers');
        }
        else if (kind === 'service') {
            const payload = { name: d.name, description: d.description, duration_minutes: Number(d.duration_minutes), price: Number(d.price), active: d.active === '1' };
            if (d.id)
                await api(`/api/services/${d.id}`, { method: 'PUT', body: JSON.stringify(payload) });
            else
                await api('/api/services', { method: 'POST', body: JSON.stringify(payload) });
            toast('تم حفظ بيانات الخدمة.');
            closeModal();
            cachedServices = await api('/api/services?include_inactive=true');
            await renderView('services');
        }
        else if (kind === 'transaction') {
            await api('/api/finance/transactions', { method: 'POST', body: JSON.stringify({ ...d, amount: Number(d.amount) }) });
            toast('تم تسجيل الحركة المالية.');
            closeModal();
            await renderView('finance');
        }
        else if (kind === 'password') {
            if (d.new_password !== d.confirm_password)
                throw new Error('كلمتا المرور الجديدتان غير متطابقتين.');
            await api('/api/auth/change-password', { method: 'POST', body: JSON.stringify({ current_password: d.current_password, new_password: d.new_password }) });
            toast('تم تغيير كلمة المرور. سجّل الدخول مجددًا.');
            closeModal();
            logout();
        }
    }
    catch (error) {
        toast(errorText(error), 'error');
        if (button) {
            button.disabled = false;
            button.textContent = kind === 'booking' ? 'تأكيد الحجز' : 'حفظ البيانات';
        }
    }
}
async function handleAction(button) {
    const action = button.dataset.action || '';
    const id = Number(button.dataset.id || 0);
    try {
        if (action === 'new-booking')
            newBookingModal();
        if (action === 'new-customer')
            customerModal();
        if (action === 'new-barber')
            barberModal();
        if (action === 'new-service')
            serviceModal();
        if (action === 'new-transaction')
            transactionModal();
        if (action === 'change-password')
            passwordModal();
        if (action === 'logout')
            logout();
        if (action === 'close-modal')
            closeModal();
        if (action === 'refresh-view')
            await renderView(view);
        if (action === 'edit-barber') {
            const b = cachedBarbers.find(x => x.id === id);
            if (b)
                barberModal(b);
        }
        if (action === 'edit-service') {
            const s = cachedServices.find(x => x.id === id);
            if (s)
                serviceModal(s);
        }
        if (action === 'toggle-barber') {
            const b = cachedBarbers.find(x => x.id === id);
            if (b) {
                await api(`/api/barbers/${id}`, { method: 'PATCH', body: JSON.stringify({ ...b, active: !b.active }) });
                toast(b.active ? 'تم إيقاف الحلاق.' : 'تم تفعيل الحلاق.');
                await renderView('barbers');
            }
        }
        if (action === 'toggle-service') {
            const s = cachedServices.find(x => x.id === id);
            if (s) {
                await api(`/api/services/${id}`, { method: 'PUT', body: JSON.stringify({ ...s, active: !s.active }) });
                toast(s.active ? 'تم إخفاء الخدمة.' : 'تم إظهار الخدمة.');
                await renderView('services');
            }
        }
        if (action === 'pay') {
            if (confirm('تأكيد استلام المبلغ وتسجيله في دفتر الصندوق؟')) {
                await api(`/api/appointments/${id}/pay`, { method: 'POST' });
                toast('تم التحصيل وتحديث الدخل.');
                await renderView(view);
            }
        }
        if (action === 'appointment-status') {
            const current = button.dataset.status || 'pending';
            const options = [['confirmed', 'تأكيد الموعد'], ['completed', 'تحديد كمكتمل'], ['cancelled', 'إلغاء الموعد']];
            const choice = prompt(`الحالة الحالية: ${statusLabel(current)}\nاكتب رقم الخيار:\n1 - تأكيد الموعد\n2 - مكتمل\n3 - إلغاء الموعد`);
            const selected = choice === '1' ? 'confirmed' : choice === '2' ? 'completed' : choice === '3' ? 'cancelled' : null;
            if (selected) {
                await api(`/api/appointments/${id}`, { method: 'PATCH', body: JSON.stringify({ status: selected }) });
                toast('تم تحديث حالة الموعد.');
                await renderView('appointments');
            }
        }
        if (action === 'export-appointments') {
            const response = await fetch(`${apiBase()}/api/export/appointments.csv`, { headers: { Authorization: `Bearer ${token}` } });
            if (!response.ok)
                throw new Error('تعذر تنزيل التقرير.');
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'saloon-dreem-appointments.csv';
            a.click();
            URL.revokeObjectURL(url);
            toast('بدأ تنزيل ملف CSV.');
        }
        if (action === 'theme-quick') {
            settings.theme = settings.theme === 'light' ? 'dark' : 'light';
            await api('/api/settings', { method: 'PUT', body: JSON.stringify({ settings: { theme: settings.theme } }) });
            applyTheme();
            toast('تم تغيير المظهر.');
        }
    }
    catch (error) {
        toast(errorText(error), 'error');
    }
}
function logout() { token = ''; user = null; localStorage.removeItem('sd_access_token'); showAuth(false); toast('تم تسجيل الخروج.', 'info'); }
function customerProfile() { try {
    return JSON.parse(localStorage.getItem('sd_customer_profile') || '{}');
}
catch {
    return { name: '', phone: '' };
} }
function localBookings() { try {
    return JSON.parse(localStorage.getItem('sd_customer_bookings') || '[]');
}
catch {
    return [];
} }
async function enterCustomer(viewName = 'discover') {
    activeCustomerView = viewName;
    $('#auth-screen')?.classList.add('hidden');
    $('#app-shell')?.classList.add('hidden');
    $('#customer-screen')?.classList.remove('hidden');
    await renderCustomerView(viewName);
}
async function renderCustomerView(name) {
    activeCustomerView = name;
    $$('.customer-nav-item').forEach(el => el.classList.toggle('active', el.getAttribute('data-customer-view') === name));
    const host = $('#customer-content');
    try {
        const [publicSettings, services, barbers] = await Promise.all([api('/api/public/settings'), api('/api/public/services'), api('/api/public/barbers')]);
        settings = { ...settings, ...publicSettings };
        cachedServices = services;
        cachedBarbers = barbers;
        const profile = customerProfile();
        const bookings = localBookings();
        if (name === 'discover')
            host.innerHTML = `<section class="customer-hero"><span class="eyebrow">THE DREEM EXPERIENCE</span><h1>وقتك لك.<br><em>واطلالتك علينا.</em></h1><p>اختر خدمتك واحجز الموعد الذي يناسبك. تجربة بسيطة، عناية بالتفاصيل، ووقت محفوظ لك.</p><button class="button button-primary" data-customer-view="book">احجز موعدك الآن <span>←</span></button><span class="customer-hero-note">${services.length} خدمات متاحة · ${barbers.length} من الحلاقين في الفريق</span><div class="hero-decoration"><span>✦</span><b>D</b><i>✂</i></div></section><div class="section-title-row"><div><p class="eyebrow">MADE FOR YOUR STYLE</p><h2>خدماتنا</h2></div><button class="text-link" data-customer-view="book">احجز خدمة ←</button></div>${services.length ? `<div class="customer-service-grid">${services.map((s, i) => `<article class="customer-service-card"><div class="service-card-top"><span class="service-glyph">${['✦', '✂', '◇', '✧', '✥'][i % 5]}</span><span class="service-number">0${i + 1}</span></div><h3>${escapeHtml(s.name)}</h3><p>${escapeHtml(s.description || 'خدمة مصممة لتناسب تفاصيل إطلالتك.')}</p><div class="customer-service-meta"><strong>${money(s.price)}</strong><span>◷ ${s.duration_minutes} دقيقة</span></div><button class="button button-secondary button-wide" data-action="customer-book-service" data-id="${s.id}">احجز هذه الخدمة</button></article>`).join('')}</div>` : emptyState('◇', 'الخدمات ستُضاف قريبًا', 'تواصل مع الصالون لمعرفة الخدمات المتاحة.')}`;
        if (name === 'book')
            host.innerHTML = `<section class="customer-content-heading"><p class="eyebrow">YOUR NEXT APPOINTMENT</p><h1>احجز موعدك.</h1><p>املأ التفاصيل التالية وسيراجع فريق الصالون طلبك لتأكيد الموعد.</p></section><div class="booking-layout"><aside class="booking-aside"><div class="booking-aside-mark">D<span>✦</span></div><h3>وقت لنفسك،<br>بأسلوبك.</h3><p>اختر الخدمة والموعد المناسب، وسنتولى الباقي.</p><div class="booking-aside-detail"><span>◷</span><div><strong>أوقات العمل</strong><small>${escapeHtml(settings.open_time || '09:00')} – ${escapeHtml(settings.close_time || '22:00')} (توقيت الصالون)</small></div></div><div class="booking-aside-detail"><span>✓</span><div><strong>تأكيد بشري</strong><small>يصل طلبك للفريق للمراجعة والتأكيد</small></div></div></aside><form id="customer-booking-form" class="panel customer-booking-form"><div class="form-grid"><label class="field full-field"><span>الخدمة المطلوبة</span><select name="service_id" id="customer-service-select" required><option value="">اختر الخدمة</option>${services.map(s => `<option value="${s.id}" ${String(s.id) === customerPrefillService ? 'selected' : ''}>${escapeHtml(s.name)} · ${money(s.price)} · ${s.duration_minutes} د</option>`).join('')}</select></label><label class="field full-field"><span>الحلاق المفضل</span><select name="barber_id"><option value="">أي حلاق متاح</option>${barbers.map(b => `<option value="${b.id}">${escapeHtml(b.name)}${b.specialty ? ` — ${escapeHtml(b.specialty)}` : ''}</option>`).join('')}</select></label>${field('customer_name', 'اسمك الكامل', profile.name || '', 'text', true, 'minlength="2" autocomplete="name"')}${field('customer_phone', 'رقم الهاتف للتواصل', profile.phone || '', 'tel', true, 'minlength="5" autocomplete="tel"')}${field('start_at', 'التاريخ والوقت', localDateTime(new Date(Date.now() + 86400000)).slice(0, 16), 'datetime-local', true, `min="${localDateTime()}"`)}<label class="field full-field"><span>ملاحظات للفريق (اختياري)</span><textarea name="notes" rows="3" maxlength="500" placeholder="مثال: تفضيل في القصة أو ملاحظة للحلاق"></textarea></label></div><p class="form-hint">إرسال الطلب لا يعني تأكيد الموعد؛ سيُراجع الفريق الحجز أولًا.</p><button class="button button-primary button-wide" type="submit">إرسال طلب الحجز <span>←</span></button></form></div>`;
        if (name === 'mybookings')
            host.innerHTML = `<div class="customer-content-heading"><p class="eyebrow">YOUR APPOINTMENTS</p><h1>مواعيدك.</h1><p>الطلبات التي أرسلتها من هذا الجهاز تظهر هنا.</p></div>${bookings.length ? `<div class="local-booking-list">${bookings.slice().reverse().map(b => `<article class="local-booking-card"><div class="local-booking-date"><strong>${dateLabel(b.start_at, { day: 'numeric' })}</strong><span>${dateLabel(b.start_at, { month: 'short' })}</span></div><div class="local-booking-info"><h3>${escapeHtml(b.service)}</h3><p>${escapeHtml(b.barber)} · ${timeLabel(b.start_at)}</p><small>طلب رقم ${b.id} · ${escapeHtml(b.phone)}</small></div><span class="status-pill status-${statusClass(b.status)}">${statusLabel(b.status)}</span><strong>${money(b.price)}</strong></article>`).join('')}</div><p class="form-hint">سجل المواعيد محفوظ محليًا على هذا الجهاز فقط، وقد لا يعكس تغييرات أجراها الصالون بعد إرسال الطلب.</p>` : emptyState('◷', 'لا توجد مواعيد محفوظة على هذا الجهاز', 'عند إرسال طلب جديد من هنا سيظهر ضمن مواعيدك.', `<button class="button button-primary" data-customer-view="book">احجز موعدًا</button>`)}`;
        if (name === 'loyalty') {
            const visits = bookings.filter(b => b.status === 'completed').length;
            const target = 5;
            host.innerHTML = `<div class="customer-content-heading"><p class="eyebrow">DREEM REWARDS</p><h1>كل زيارة لها قيمة.</h1><p>متابعة بسيطة للزيارات المحفوظة على هذا الجهاز.</p></div><section class="loyalty-card"><div class="loyalty-card-top"><span class="brand-symbol">D<span>✦</span></span><span>THE DREEM CLUB</span></div><p>زيارات مكتملة محفوظة</p><strong>${visits}<small> / ${target}</small></strong><div class="loyalty-progress">${Array.from({ length: target }, (_, i) => `<span class="${i < visits ? 'filled' : ''}">✦</span>`).join('')}</div><small>للتجربة فقط: هذه الزيارات لا تُحتسب كنظام مكافآت فعلي لدى الصالون بعد.</small></section><p class="form-hint">برنامج الولاء يتطلب اعتماد قواعد النقاط والمكافآت من إدارة الصالون. لا توجد خصومات أو أرصدة مالية منشأة تلقائيًا.</p>`;
        }
        if (name === 'profile')
            host.innerHTML = `<div class="customer-content-heading"><p class="eyebrow">YOUR DETAILS</p><h1>ملفك الشخصي.</h1><p>احفظ بياناتك على جهازك لتسهيل الحجز القادم.</p></div><form id="customer-profile-form" class="panel profile-form"><div class="profile-avatar-large">${escapeHtml((profile.name || 'D').slice(0, 1))}</div><div class="form-grid">${field('name', 'الاسم الكامل', profile.name || '', 'text', true, 'minlength="2" autocomplete="name"')}${field('phone', 'رقم الهاتف', profile.phone || '', 'tel', true, 'minlength="5" autocomplete="tel"')}</div><p class="form-hint">البيانات محفوظة في متصفحك فقط لتعبئة نموذج الحجز. لا تستخدم هذا الجهاز المشترك لحفظ بياناتك الخاصة.</p><button class="button button-primary" type="submit">حفظ الملف الشخصي</button></form>`;
    }
    catch (error) {
        host.innerHTML = emptyState('!', 'تعذر تحميل تجربة العميل', escapeHtml(errorText(error)), `<button class="button button-secondary" data-action="customer-retry">إعادة المحاولة</button>`);
    }
}
async function submitCustomerBooking(form) {
    const d = formValues(form);
    const button = $('button[type=submit]', form);
    if (button) {
        button.disabled = true;
        button.textContent = 'جارٍ إرسال الطلب…';
    }
    try {
        if (!d.service_id)
            throw new Error('اختر الخدمة المطلوبة.');
        const profile = { name: d.customer_name, phone: d.customer_phone };
        localStorage.setItem('sd_customer_profile', JSON.stringify(profile));
        const data = await api('/api/public/appointments', { method: 'POST', body: JSON.stringify({ customer_name: d.customer_name, customer_phone: d.customer_phone, service_id: Number(d.service_id), barber_id: d.barber_id ? Number(d.barber_id) : null, start_at: d.start_at, notes: d.notes || '' }) });
        const a = data.appointment;
        const list = localBookings();
        list.push({ id: a.id, name: a.customer_name, phone: a.customer_phone, service: a.service_name, barber: a.barber_name || 'فريق الصالون', start_at: a.start_at, price: a.price, status: a.status, created_at: new Date().toISOString() });
        localStorage.setItem('sd_customer_bookings', JSON.stringify(list.slice(-100)));
        customerPrefillService = '';
        toast('وصل طلبك للصالون بنجاح.');
        await renderCustomerView('mybookings');
    }
    catch (error) {
        toast(errorText(error), 'error');
        if (button) {
            button.disabled = false;
            button.innerHTML = 'إرسال طلب الحجز <span>←</span>';
        }
    }
}
// Event delegation keeps interactions working after each dynamic view render.
document.addEventListener('click', event => {
    const target = event.target;
    const close = target.closest('[data-action="close-modal"]');
    if (close && target.classList.contains('modal-backdrop')) {
        closeModal();
        return;
    }
    const viewButton = target.closest('[data-view]');
    if (viewButton?.dataset.view) {
        setView(viewButton.dataset.view);
        return;
    }
    const customerViewButton = target.closest('[data-customer-view]');
    if (customerViewButton?.dataset.customerView) {
        void renderCustomerView(customerViewButton.dataset.customerView);
        return;
    }
    const actionButtonEl = target.closest('[data-action]');
    if (actionButtonEl) {
        const action = actionButtonEl.dataset.action;
        if (action === 'customer-book-service') {
            customerPrefillService = actionButtonEl.dataset.id || '';
            void renderCustomerView('book');
            return;
        }
        if (action === 'customer-retry') {
            void renderCustomerView(activeCustomerView);
            return;
        }
        void handleAction(actionButtonEl);
    }
});
document.addEventListener('submit', event => {
    const form = event.target;
    if (form.id === 'auth-form') {
        event.preventDefault();
        void handleAuthSubmit(form);
    }
    if (form.id === 'modal-form') {
        event.preventDefault();
        void handleModalSubmit(form);
    }
    if (form.id === 'settings-form') {
        event.preventDefault();
        void handleSettingsSubmit(form);
    }
    if (form.id === 'customer-booking-form') {
        event.preventDefault();
        void submitCustomerBooking(form);
    }
    if (form.id === 'customer-profile-form') {
        event.preventDefault();
        const d = formValues(form);
        localStorage.setItem('sd_customer_profile', JSON.stringify({ name: d.name, phone: d.phone }));
        toast('تم حفظ ملفك على هذا الجهاز.');
    }
});
async function handleAuthSubmit(form) {
    const d = formValues(form);
    const button = $('#auth-submit');
    button.disabled = true;
    try {
        const status = await api('/api/setup/status');
        let result;
        if (status.setup_required) {
            const confirmInput = $('#auth-password-confirm');
            if (d.password !== confirmInput.value)
                throw new Error('كلمتا المرور غير متطابقتين.');
            result = await api('/api/setup', { method: 'POST', body: JSON.stringify({ username: d.username, password: d.password, business_name: d.business_name || 'SALOON DREEM' }) });
        }
        else
            result = await api('/api/auth/login', { method: 'POST', body: JSON.stringify({ username: d.username, password: d.password }) });
        setToken(result.access_token);
        user = result.user;
        toast(status.setup_required ? 'تم إعداد حساب المدير بنجاح.' : 'مرحبًا بعودتك.');
        view = 'dashboard';
        await enterAdmin();
    }
    catch (error) {
        toast(errorText(error), 'error');
    }
    finally {
        button.disabled = false;
    }
}
async function handleSettingsSubmit(form) {
    const d = formValues(form);
    try {
        settings = await api('/api/settings', { method: 'PUT', body: JSON.stringify({ settings: { business_name: d.business_name, phone: d.phone, address: d.address, currency: d.currency, open_time: d.open_time, close_time: d.close_time, theme: d.theme } }) });
        applyTheme();
        $('#sidebar-salon-name').textContent = settings.business_name;
        toast('تم حفظ إعدادات الصالون.');
        await renderView('settings');
    }
    catch (error) {
        toast(errorText(error), 'error');
    }
}
$('#customer-entry')?.addEventListener('click', () => void enterCustomer('discover'));
$('#customer-admin-entry')?.addEventListener('click', async () => { const s = await api('/api/setup/status').catch(() => ({ setup_required: true })); $('#customer-screen')?.classList.add('hidden'); showAuth(s.setup_required); });
$('#open-customer-portal')?.addEventListener('click', () => void enterCustomer('discover'));
$('#quick-book')?.addEventListener('click', () => newBookingModal());
$('#account-menu')?.addEventListener('click', () => passwordModal());
$('#logout-button')?.addEventListener('click', logout);
$('#menu-toggle')?.addEventListener('click', openSidebar);
$('#sidebar-close')?.addEventListener('click', closeSidebar);
$('#sidebar-backdrop')?.addEventListener('click', closeSidebar);
$('#theme-toggle')?.addEventListener('click', () => { const trigger = document.createElement('button'); trigger.dataset.action = 'theme-quick'; void handleAction(trigger); });
$('#save-api-base')?.addEventListener('click', async () => { const input = $('#api-base-input'); const value = input.value.trim().replace(/\/$/, ''); if (value && !/^https?:\/\//i.test(value)) {
    toast('أدخل رابطًا يبدأ بـ https:// أو http://.', 'error');
    return;
} if (value && location.protocol === 'https:' && value.startsWith('http://')) {
    toast('لا يمكن استخدام HTTP غير المشفر من صفحة HTTPS.', 'error');
    return;
} localStorage.setItem('sd_api_base', value); toast('تم حفظ عنوان الخادم. سيتم إعادة تحميل التطبيق.'); setTimeout(() => location.reload(), 700); });
$('#appointment-search')?.addEventListener('input', debounce(() => void renderView('appointments'), 280));
$('#appointment-filter')?.addEventListener('change', () => void renderView('appointments'));
$('#customer-search')?.addEventListener('input', debounce(() => void renderView('customers'), 280));
function debounce(fn, wait) { let timer; return () => { window.clearTimeout(timer); timer = window.setTimeout(fn, wait); }; }
void init();
